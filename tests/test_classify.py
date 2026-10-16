"""Exercise api/classify.py by hand: `parse` (no network), `ledger` (the Blob store), `jev` (five real Jev
calls). Reads .env.local for the secrets."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

SITE = Path(__file__).resolve().parents[1]
for line in (SITE / ".env.local").read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"'))

spec = importlib.util.spec_from_file_location("classify", SITE / "api" / "classify.py")
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)

samples = {s["id"]: s for s in json.loads((SITE / "src" / "samples.json").read_text())}
what = sys.argv[1] if len(sys.argv) > 1 else "all"

if what in ("parse", "all"):
    print("== parse + signals, no Jev")
    for sid, s in samples.items():
        email = mod.email_from_raw(s["raw"])
        sig = mod.resolve_relay(email.extract_signals(), [])
        print(
            sid,
            "| sender", sig.sender,
            "| dmarc", sig.dmarc_pass,
            "| one_click", sig.one_click,
            "| https", len(sig.unsubscribe_https),
            "| mailto", len(sig.unsubscribe_mailto),
            "| list_id", sig.list_id,
            "| links", email.link_domains,
            "| body", len(email.body), "chars",
            "| rwt", mod.reply_without_thread(email.header("Subject"), email.headers),
        )
    fields = mod.email_from_raw(mod._raw_from_fields({"from": "a@b.example", "subject": "hi", "body": "hello there"}))
    print("fields ->", fields.header("From"), "|", fields.body)

if what in ("ledger", "all"):
    print("== ledger round trip (consistent read)")
    led = mod.Ledger()
    print("ready", led.ready, "store", led.store)
    key = "selftest"
    before = led.read(key)
    led.write(key, {"usd": before["usd"] + 0.001, "calls": before["calls"] + 1})
    t = time.monotonic()
    after = led.read(key)
    print("before", before, "after", after, "read in", round((time.monotonic() - t) * 1000), "ms")
    assert after["calls"] == before["calls"] + 1, "stale read!"

if what in ("jev", "all"):
    print("== through Jev (real calls)")
    headers = {"x-forwarded-for": "203.0.113.9"}
    print("status", mod.status(headers))
    cases = [("pitch", False), ("pitch", True), ("receipt", False), ("phish", False), ("newsletter", False)]
    for sid, wrote in cases:
        out = mod.classify({"raw": samples[sid]["raw"], "wrote_before": wrote}, headers)
        d, g, u = out["decision"], out["gate"], out["usage"]
        print(
            f"{sid:10} wrote={wrote!s:5} -> {out['category']} {out['confidence']} (bar {out['threshold']})",
            "| archive", d["archive"], "| spam", d["spam"], "| unsub", d["unsubscribe"], "| veto", g["veto"],
            "| labels", out["plan"]["add_labels"],
            "| needs_reply", out["needs_reply"]["value"],
            "| tokens", u["input_tokens"], "| cost", u["cost_usd"], "| jev_ms", out["timings_ms"]["jev"],
        )
    print("status", mod.status(headers))
