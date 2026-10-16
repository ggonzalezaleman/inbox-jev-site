# inbox-jev site

The landing page for [inbox-jev](https://github.com/hellolitebox/litebox-inbox-jev), the CLI that sorts
your Gmail with the Jev classifier. One static page, no framework, deployed on Vercel.

## Layout of the repo

- `index.html`: the built page. Committed, served as is.
- `src/template.src.html`: the page source: styles, copy and script, with `{{frag:name}}` placeholders.
- `src/frag-*.html`: the interface mockups (Gmail rows, terminals, the Slack digest, YAML files). They
  carry example data, not real mail.
- `src/frag-run.html` is also the fallback of the "pass itself" figure: with script and motion allowed, the
  page's script replaces it with a run log that streams synthetic records, run after run, while on screen.
- `src/build.mjs`: resolves the fragments, generates the two "How it decides" diagrams (desktop and
  phone) from the worked examples of the spec, and writes `index.html` with its document head.
- `og.png`: the social card, a render of the first screen. `favicon.svg`: the mark.

## Working on it

```sh
node src/build.mjs   # rebuilds index.html; commit the result
```

Node 22 or newer, no dependencies. The eight emails in the diagram are examples `EX-01`, `02`, `04`,
`05`, `15`, `16` and `38` of
[docs/how-it-decides.md](https://github.com/hellolitebox/litebox-inbox-jev/blob/main/docs/how-it-decides.md);
when the spec changes, update `EX` and the verdict texts in the template together.

The Star / Fork / Issues badges read their counts from the public GitHub API once per session.

## The playground

`api/classify.py` is a Vercel Python function behind `/api/classify`. It takes one email as text
(the "Show original" of Gmail, or any text), runs it through the published `inbox-jev` package the
way a pass would (the headers' signals, the state Jev gets, Jev's answer, the policy's decision in
act mode, for an account with no rules and the default categories) and returns the decision with
what Jev answered, the signals, the exact state sent and the cost. `GET /api/classify` reports the
budgets. The page's "Try it" section is its interface; the four sample emails live in
`src/samples.json` and are inlined into the page at build time.

It never stores or logs the email. The log line has the visitor's hash, tokens, cost, category,
confidence and timings.

**Budgets.** TypeSafe bills Jev per input token (about 2,200 per email here). Two caps are enforced
in dollars through a ledger in the project's private Vercel Blob store (`ledger/v1/total.json` and
`ledger/v1/v/<visitor>.json`, the visitor being a salted hash of the IP): per visitor and in total.
Reads bypass the CDN cache (`?cache=0`), so a call sees the previous call's write; two calls landing
at the same instant can both pass a cap, so a cap can be exceeded by one call. A per-minute rate
limit per visitor, per instance, keeps the function from being a bulk classifier.

**Environment** (set with `vercel env add`, never committed):

| Variable | Meaning |
| -- | -- |
| `TYPESAFE_API_KEY` | the author's key; every call is billed to it |
| `PLAYGROUND_SALT` | random; hashes the IP for the ledger |
| `BLOB_READ_WRITE_TOKEN` | added by `vercel blob create-store inbox-jev-playground --access private --yes` |
| `TYPESAFE_MODEL` | optional, default `jev-latest` |
| `JEV_USD_PER_MTOK` | optional, default `0.042`; update when the price changes |
| `PLAYGROUND_CAP_VISITOR_USD` | optional, default `0.50` |
| `PLAYGROUND_CAP_TOTAL_USD` | optional, default `500` |
| `PLAYGROUND_RATE_PER_MINUTE` | optional, default `20` |

To close the playground, set `PLAYGROUND_CAP_TOTAL_USD=0` and redeploy. To reset a budget, delete
its blob (`vercel blob del ledger/v1/total.json`).

**Testing it.** `vercel env pull .env.local`, then with a Python 3.12 environment that has
`requirements.txt` installed: `python tests/test_classify.py parse` (parsing and signals, no
network), `python tests/test_classify.py ledger` (the Blob round trip) and
`python tests/test_classify.py jev` (five real Jev calls, a few hundredths of a cent).

## Deploying

Pushes to `main` deploy through the Vercel project linked to this repo. `vercel --prod` from a
checkout does the same by hand.
