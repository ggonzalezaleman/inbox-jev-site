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

## Deploying

Pushes to `main` deploy through the Vercel project linked to this repo. `vercel --prod` from a
checkout does the same by hand.
