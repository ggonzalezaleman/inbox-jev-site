"""The playground behind inbox-jev-site.vercel.app: one email in, the tool's decision out.

POST /api/classify with a JSON body {"raw": "<the email as text, headers first>",
"wrote_before": false}, or {"from": "...", "subject": "...", "body": "...", "wrote_before": false},
runs what a pass runs on one email, with the published inbox-jev package: the headers' signals,
the state Jev receives, Jev's answer and the policy's decision, in act mode, for an account with
no allowlist, no rules and the default categories. GET /api/classify says whether the playground
is open and what is left of the budgets.

It never stores or logs the email. The log line carries the visitor's hash, the tokens, the
cost, the category, the confidence and the timings. The ledger, a private Vercel Blob store,
holds the spend per visitor (keyed by a salted hash of the IP) and the total, in dollars, which
is how the two caps are enforced. Two calls landing at the same instant can both pass a cap
that only one of them should have, so a cap can be exceeded by one call, never by more.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import time
from collections import deque
from datetime import UTC, datetime
from email import message_from_string
from email import policy as email_policy
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from http.server import BaseHTTPRequestHandler
from typing import Any

import httpx
from inbox_jev import policy
from inbox_jev.body import calendar_method, extract_body, extract_link_domains
from inbox_jev.classification import Classification, PreviousContact
from inbox_jev.classifier import (
    CATEGORY_Q,
    NEEDS_REPLY_Q,
    TAG_PREFIX,
    Classifier,
    JevError,
    _request_id,
    build_state,
    describe_jev_error,
)
from inbox_jev.config import Account, Mode, load_categories
from inbox_jev.gmail import Email
from inbox_jev.paths import bundled
from inbox_jev.signals import reply_without_thread, resolve_relay

MAX_RAW_BYTES = 256 * 1024
# Settings.body_chars: how much of the body a pass sends to Jev.
BODY_CHARS = 3000
ACCOUNT = "you@example.com"
MODEL = os.environ.get("TYPESAFE_MODEL", "jev-latest")
# TypeSafe bills Jev by input token; output is free. Overridable when the price changes.
USD_PER_MTOK = float(os.environ.get("JEV_USD_PER_MTOK", "0.042"))
CAP_VISITOR_USD = float(os.environ.get("PLAYGROUND_CAP_VISITOR_USD", "0.50"))
CAP_TOTAL_USD = float(os.environ.get("PLAYGROUND_CAP_TOTAL_USD", "500"))
# Calls per minute per visitor on one instance: the budget would allow thousands, this keeps the
# function from being a bulk classifier.
RATE_PER_MINUTE = int(os.environ.get("PLAYGROUND_RATE_PER_MINUTE", "20"))
LEDGER_PREFIX = "ledger/v1/"
JEV_TIMEOUT_S = 20.0

_cfg = load_categories(bundled("categories.yaml"))
_account = Account(email=ACCOUNT)


class PlaygroundError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


# ---- the email, from pasted text ------------------------------------------------------------


def _raw_from_fields(data: dict[str, Any]) -> str:
    sender = str(data.get("from") or "").strip().replace("\n", " ")
    subject = str(data.get("subject") or "").strip().replace("\n", " ")
    body = str(data.get("body") or "")
    if not sender and not subject and not body.strip():
        raise PlaygroundError(400, "empty", "Paste an email first.")
    date = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S +0000")
    return (
        f"From: {sender or 'someone@example.com'}\nTo: {ACCOUNT}\nSubject: {subject}\n"
        f"Date: {date}\nMIME-Version: 1.0\nContent-Type: text/plain; charset=\"UTF-8\"\n\n{body}"
    )


def _payload_of(part: EmailMessage) -> dict[str, Any]:
    """The part as the Gmail API would return it (what inbox_jev.body reads)."""
    node: dict[str, Any] = {
        "mimeType": part.get_content_type(),
        "filename": part.get_filename() or "",
        "body": {},
    }
    if part.is_multipart():
        node["parts"] = [_payload_of(p) for p in part.iter_parts()]
    elif node["mimeType"] in ("text/plain", "text/html"):
        try:
            text = part.get_content()
        except Exception:  # noqa: BLE001 - a part it can't decode is a part without text
            text = ""
        if isinstance(text, str):
            node["body"]["data"] = base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii")
    return node


def email_from_raw(raw: str) -> Email:
    msg = message_from_string(raw, policy=email_policy.default)
    headers: dict[str, list[str]] = {}
    for name, value in msg.items():
        headers.setdefault(name.lower(), []).append(str(value))
    if "from" not in headers:
        # Plain text without headers: an email from nobody in particular, its first line the
        # subject. Jev still reads it; the sender checks have nothing to go on.
        first = next((ln.strip() for ln in raw.splitlines() if ln.strip()), "")
        return email_from_raw(
            _raw_from_fields({"from": "someone@unknown.example", "subject": first[:120], "body": raw})
        )
    payload = _payload_of(msg)
    body = extract_body(payload)
    try:
        when = parsedate_to_datetime(headers["date"][0]) if headers.get("date") else None
    except (TypeError, ValueError):
        when = None
    when = when or datetime.now(UTC)
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return Email(
        id="playground",
        thread_id="playground",
        label_ids=["INBOX", "UNREAD"],
        headers=headers,
        snippet=body[:200],
        body=body,
        internal_date_ms=int(when.timestamp() * 1000),
        link_domains=extract_link_domains(payload),
        calendar_method=calendar_method(payload),
    )


# ---- the ledger: dollars spent, per visitor and in total -------------------------------------


class Ledger:
    """Two counters in a private Vercel Blob store, read straight from origin (`cache=0`) so a
    write is visible to the next call, and written with overwrite."""

    def __init__(self) -> None:
        self.token = os.environ.get("BLOB_READ_WRITE_TOKEN", "")
        parts = self.token.split("_")
        self.store = parts[3].lower() if len(parts) >= 5 else ""
        self._auth = {"authorization": f"Bearer {self.token}"}

    @property
    def ready(self) -> bool:
        return bool(self.token and self.store)

    def _url(self, key: str) -> str:
        return f"https://{self.store}.private.blob.vercel-storage.com/{LEDGER_PREFIX}{key}.json"

    def read(self, key: str) -> dict[str, Any]:
        r = httpx.get(self._url(key), params={"cache": "0"}, headers=self._auth, timeout=10)
        if r.status_code == 404:
            return {"usd": 0.0, "calls": 0}
        r.raise_for_status()
        data = r.json()
        return {"usd": float(data.get("usd", 0)), "calls": int(data.get("calls", 0))}

    def write(self, key: str, entry: dict[str, Any]) -> None:
        body = json.dumps({**entry, "at": datetime.now(UTC).isoformat(timespec="seconds")})
        r = httpx.put(
            "https://blob.vercel-storage.com/",
            params={"pathname": f"{LEDGER_PREFIX}{key}.json"},
            content=body.encode(),
            headers={
                **self._auth,
                "x-api-version": "13",
                "x-vercel-blob-access": "private",
                "x-content-type": "application/json",
                "x-add-random-suffix": "0",
                "x-allow-overwrite": "1",
                "x-cache-control-max-age": "60",
            },
            timeout=10,
        )
        r.raise_for_status()


_ledger = Ledger()
_recent: dict[str, deque[float]] = {}


def visitor_of(req_headers: dict[str, str]) -> str:
    ip = (req_headers.get("x-forwarded-for") or req_headers.get("x-real-ip") or "").split(",")[0]
    salt = os.environ.get("PLAYGROUND_SALT", "")
    return hashlib.sha256(f"{salt}|{ip.strip() or 'unknown'}".encode()).hexdigest()[:20]


def _rate_limited(visitor: str) -> bool:
    now = time.monotonic()
    q = _recent.setdefault(visitor, deque())
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_PER_MINUTE:
        return True
    q.append(now)
    return False


def _budgets(visitor: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if not _ledger.ready:
        raise PlaygroundError(503, "closed", "The playground is not configured.")
    return _ledger.read(f"v/{visitor}"), _ledger.read("total")


def status(req_headers: dict[str, str]) -> dict[str, Any]:
    visitor = visitor_of(req_headers)
    mine, total = _budgets(visitor)
    return {
        "open": mine["usd"] < CAP_VISITOR_USD and total["usd"] < CAP_TOTAL_USD,
        "visitor_spent_usd": round(mine["usd"], 6),
        "visitor_cap_usd": CAP_VISITOR_USD,
        "total_spent_usd": round(total["usd"], 4),
        "total_cap_usd": CAP_TOTAL_USD,
        "usd_per_mtok": USD_PER_MTOK,
        "model": MODEL,
    }


# ---- one email through the pass ------------------------------------------------------------


def classify(data: dict[str, Any], req_headers: dict[str, str]) -> dict[str, Any]:
    t0 = time.monotonic()
    raw = data.get("raw")
    raw = str(raw) if raw else _raw_from_fields(data)
    if len(raw.encode("utf-8", "replace")) > MAX_RAW_BYTES:
        raise PlaygroundError(413, "too_large", "That email is over 256 KB. Trim it first.")
    wrote_before = bool(data.get("wrote_before"))

    visitor = visitor_of(req_headers)
    if _rate_limited(visitor):
        raise PlaygroundError(429, "rate", "Twenty a minute is plenty. Try again in a moment.")
    mine, total = _budgets(visitor)
    if total["usd"] >= CAP_TOTAL_USD:
        raise PlaygroundError(429, "total_cap", "The playground's budget is spent. It is closed.")
    if mine["usd"] >= CAP_VISITOR_USD:
        raise PlaygroundError(
            429, "visitor_cap", f"You have used your ${CAP_VISITOR_USD:.2f} of Jev. Install it."
        )

    email = email_from_raw(raw)
    sig = resolve_relay(email.extract_signals(), _account.group_domains)
    previous = PreviousContact.WROTE_TO_SENDER if wrote_before else PreviousContact.NEVER
    state = build_state(email, _account.email, BODY_CHARS, previous, sig)

    api_key = os.environ.get("TYPESAFE_API_KEY", "")
    clf = Classifier(api_key, MODEL, _cfg)
    t1 = time.monotonic()
    try:
        # Classifier.classify drops the usage the SDK reports; the same call, kept whole.
        result = clf._client.system_one(state, clf._questions, timeout=JEV_TIMEOUT_S)  # noqa: SLF001
    except JevError as exc:
        raise PlaygroundError(502, "jev", describe_jev_error(exc)) from exc
    finally:
        clf.close()
    jev_ms = round((time.monotonic() - t1) * 1000)
    choice = result.choices[CATEGORY_Q]
    classification = Classification(
        category=choice.choice,
        confidence=choice.confidence,
        probabilities=dict(choice.probabilities),
        needs_reply=result.nouls[NEEDS_REPLY_Q].noul,
        tags={t.key: result.nouls[TAG_PREFIX + t.key].noul for t in _cfg.tags},
        request_id=_request_id(result),
    )
    tokens = result.usage.input_tokens
    if tokens is None:
        tokens = len(json.dumps(state)) // 3 + 600
    cost = tokens * USD_PER_MTOK / 1_000_000

    decision = policy.decide(_cfg, _account, sig, classification, previous_contact=previous)
    gate = policy.unsubscribe_gate(
        _cfg, _account, sig, decision.category, previous, manual_rule=False
    )
    plan = policy.plan(_cfg, decision, Mode.ACT)
    threshold = policy.category_threshold(_cfg, _account, decision.category)
    category = _cfg.by_key[decision.category]

    mine = {"usd": mine["usd"] + cost, "calls": mine["calls"] + 1}
    total = {"usd": total["usd"] + cost, "calls": total["calls"] + 1}
    _ledger.write(f"v/{visitor}", mine)
    _ledger.write("total", total)

    out = {
        "category": decision.category,
        "label": category.label,
        "action": category.action.value,
        "confidence": round(decision.confidence, 4),
        "threshold": threshold,
        "probabilities": {
            k: round(v, 4)
            for k, v in sorted(classification.probabilities.items(), key=lambda kv: -kv[1])
        },
        "needs_reply": {
            "value": round(classification.needs_reply, 4),
            "threshold": _cfg.needs_reply.threshold,
            "label": _cfg.needs_reply.label,
        },
        "tags": {
            t.key: {"value": round(classification.tags[t.key], 4), "threshold": t.threshold, "label": t.label}
            for t in _cfg.tags
            if t.key in classification.tags
        },
        "decision": {
            "source": decision.source.value,
            "low_confidence": decision.low_confidence,
            "archive": decision.archive,
            "spam": decision.spam,
            "unsubscribe": decision.unsubscribe,
            "archive_group": decision.archive_group,
            "known_contact_kept": decision.known_contact_kept,
            "unsubscribe_skipped_unverified": decision.unsubscribe_skipped_unverified,
            "add_labels": decision.add_labels,
        },
        "plan": {
            "add_labels": plan.add_labels,
            "remove_labels": plan.remove_labels,
            "archived": plan.archived,
            "spammed": plan.spammed,
            "unsubscribe": plan.unsubscribe,
        },
        "gate": {
            "allowed": gate.allowed,
            "veto": gate.veto.value if gate.veto else None,
            "contact_unknown": gate.contact_unknown,
        },
        "signals": {
            "sender": sig.sender,
            "sender_domain": sig.sender_domain,
            "dmarc_pass": sig.dmarc_pass,
            "auth_results": bool(email.headers.get("authentication-results")),
            "had_headers": email.header("From") != "someone@unknown.example",
            "list_id": sig.list_id,
            "unsubscribe_https": list(sig.unsubscribe_https),
            "unsubscribe_mailto": list(sig.unsubscribe_mailto),
            "one_click": sig.one_click,
            "is_discussion_list": sig.is_discussion_list,
            "relayed_by": sig.relayed_by,
            "reply_without_thread": reply_without_thread(email.header("Subject"), email.headers),
            "link_domains": email.link_domains,
            "previous_contact": previous.value,
        },
        "state": state,
        "usage": {
            "input_tokens": tokens,
            "output_tokens": result.usage.output_tokens,
            "cost_usd": round(cost, 8),
            "visitor_spent_usd": round(mine["usd"], 6),
            "visitor_cap_usd": CAP_VISITOR_USD,
            "total_spent_usd": round(total["usd"], 4),
            "total_cap_usd": CAP_TOTAL_USD,
        },
        "model": result.model,
        "request_id": classification.request_id,
        "timings_ms": {"jev": jev_ms, "total": round((time.monotonic() - t0) * 1000)},
    }
    print(
        json.dumps(
            {
                "event": "classified",
                "visitor": visitor,
                "category": decision.category,
                "confidence": out["confidence"],
                "archive": decision.archive,
                "unsubscribe": decision.unsubscribe,
                "veto": out["gate"]["veto"],
                "input_tokens": tokens,
                "cost_usd": out["usage"]["cost_usd"],
                "request_id": classification.request_id,
                "jev_ms": jev_ms,
            }
        ),
        file=sys.stderr,
    )
    return out


# ---- HTTP ----------------------------------------------------------------------------------


class handler(BaseHTTPRequestHandler):  # noqa: N801 - the name Vercel looks for
    def _send(self, code: int, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _headers(self) -> dict[str, str]:
        return {k.lower(): v for k, v in self.headers.items()}

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return  # the classify log line is the one that matters

    def do_GET(self) -> None:  # noqa: N802
        try:
            self._send(200, status(self._headers()))
        except PlaygroundError as exc:
            self._send(exc.status, {"error": exc.code, "message": exc.message})
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"event": "status_failed", "error": repr(exc)}), file=sys.stderr)
            self._send(500, {"error": "internal", "message": "Something broke on this side."})

    def do_POST(self) -> None:  # noqa: N802
        try:
            length = int(self.headers.get("content-length") or 0)
            if length > MAX_RAW_BYTES + 4096:
                raise PlaygroundError(413, "too_large", "That email is over 256 KB. Trim it first.")
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
            except ValueError as exc:
                raise PlaygroundError(400, "bad_json", "The request body is not JSON.") from exc
            if not isinstance(data, dict):
                raise PlaygroundError(400, "bad_json", "The request body is not a JSON object.")
            self._send(200, classify(data, self._headers()))
        except PlaygroundError as exc:
            self._send(exc.status, {"error": exc.code, "message": exc.message})
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"event": "classify_failed", "error": repr(exc)}), file=sys.stderr)
            self._send(500, {"error": "internal", "message": "Something broke on this side."})
