// Builds ../index.html from template.src.html: resolves the {{frag:name}} interface mockups, generates the
// two decision diagrams (desktop and phone) from the worked examples of docs/how-it-decides.md in the
// inbox-jev repo, and wraps the page in its document head. No dependencies: `node src/build.mjs`.
import { readFileSync, writeFileSync } from 'node:fs';

export const SITE = 'https://inboxjev.dev';
const DESCRIPTION = "inbox-jev reads your Gmail every ten minutes, labels each email with the Jev classifier, archives receipts, notifications, newsletters and pitches, unsubscribes from the pitches it can verify, and learns from your corrections. Free, MIT licensed, runs on your own machine.";

// Outcome rows (index → label, action, group)
const OUT = [
  { id: 'important', label: 'Jev/Important', action: 'stays', group: 'inbox' },
  { id: 'action', label: 'Jev/Action', action: 'stays', group: 'inbox' },
  { id: 'review', label: 'Jev/Review', action: 'stays, flagged', group: 'inbox' },
  { id: 'transactional', label: 'Jev/Transactional', action: 'archived', group: 'archive' },
  { id: 'notification', label: 'Jev/Notifications', action: 'archived', group: 'archive' },
  { id: 'newsletter', label: 'Jev/Newsletters', action: 'archived', group: 'archive' },
  { id: 'marketing', label: 'Jev/Marketing', action: 'archived, unsubscribed', group: 'archive' },
  { id: 'outreach', label: 'Jev/Outreach', action: 'archived, unsubscribed', group: 'archive' },
  { id: 'spam', label: 'Jev/Spam', action: 'moved to Spam', group: 'spam' },
];

// The eight emails, each a worked example of the spec (EX-NN), with its route and its outcome.
export const EX = [
  { id: 'ex15a', ex: 'EX-15', subject: 'Signed contract by Friday?', sender: 'ana@client.example', note: 'a client with a rule', via: 'rule', out: 'important' },
  { id: 'ex02', ex: 'EX-02', subject: 'Approve payment to Acme Supplies', sender: 'alerts@bank.example', note: 'automated', via: 'jev', out: 'action' },
  { id: 'ex04', ex: 'EX-04', subject: 'Re: quick question about your pipeline', sender: 'sam@growthagency.example', note: 'a stranger', via: 'jev', out: 'outreach' },
  { id: 'ex01', ex: 'EX-01', subject: 'Your weekly product analytics', sender: 'digest@analytics.example', note: 'a tool you use', via: 'jev', out: 'notification' },
  { id: 'ex38', ex: 'EX-38', subject: 'RE: Updated permit schedule for review', sender: 'noreply@dailywire-news.example', note: 'a fake reply', via: 'jev', out: 'spam' },
  { id: 'ex15b', ex: 'EX-15', subject: 'This week in product', sender: 'news@weekly.example', note: 'a learned rule', via: 'rule', out: 'newsletter' },
  { id: 'ex05', ex: 'EX-05', subject: 'Re: quick question about your pipeline', sender: 'sam@growthagency.example', note: 'a known contact', via: 'jev', out: 'outreach' },
  { id: 'ex16', ex: 'EX-16', subject: 'Announcing our spring collection', sender: 'hello@brand.example', note: 'Jev is not sure', via: 'jev', out: 'review' },
];

const outIndex = (id) => OUT.findIndex((o) => o.id === id);
const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const r = (n) => Math.round(n * 10) / 10;

// ---------- Desktop: 1200 × 490, left to right ----------
// Widths come from measuring the strings with the page's fonts: the longest subject is 272px at
// 14px, the longest gate line 126px at 12.5px, the longest outcome action 144px at 12.5px.
function desktop() {
  const W = 1200, H = 490;
  const pile = { x: 0, w: 320, y0: 30, h: 40, gap: 4 };
  const rules = { x: 356, w: 150, y: 30, h: 436 };
  const jev = { x: 542, w: 150, y: 80, h: 386 };
  const pol = { x: 728, w: 150, y: 80, h: 386 };
  const outs = { x: 960, w: 240, h: 40, gap: 4, ggap: 22 };
  const cy = (i) => pile.y0 + i * (pile.h + pile.gap) + pile.h / 2;
  const outY = [];
  let y = 30;
  OUT.forEach((o, i) => {
    if (i > 0 && OUT[i - 1].group !== o.group) y += outs.ggap;
    outY.push(y);
    y += outs.h + outs.gap;
  });
  const oy = (i) => outY[i] + outs.h / 2;
  // Rule-decided mail leaves the rules box, climbs the gap before Jev and runs along a corridor above it.
  const lanes = [{ ly: 48, vx: 518 }, { ly: 62, vx: 530 }];
  let laneN = 0;

  const routes = EX.map((e, i) => {
    const y1 = cy(i), o = outIndex(e.out), y2 = oy(o);
    let d;
    if (e.via === 'rule') {
      const { ly, vx } = lanes[laneN++ % lanes.length];
      d = `M ${pile.x + pile.w} ${y1} H ${vx - 10} Q ${vx} ${y1} ${vx} ${y1 - 10} V ${ly + 10} Q ${vx} ${ly} ${vx + 10} ${ly} H ${outs.x - 55} C ${outs.x - 28} ${ly}, ${outs.x - 30} ${y2}, ${outs.x} ${y2}`;
    } else {
      const xe = pol.x + pol.w;
      d = `M ${pile.x + pile.w} ${y1} H ${xe} C ${xe + 44} ${y1}, ${outs.x - 44} ${y2}, ${outs.x} ${y2}`;
    }
    return `<path class="route" data-for="${e.id}" d="${d}" />`;
  });

  const pileRows = EX.map((e, i) => {
    const y = pile.y0 + i * (pile.h + pile.gap);
    return `<g class="mail" role="button" tabindex="0" data-ex="${e.id}" aria-label="${esc(e.subject)}, from ${esc(e.sender)}">
      <rect x="${pile.x}" y="${y}" width="${pile.w}" height="${pile.h}" />
      <text x="${pile.x + 12}" y="${y + 17}" class="t1">${esc(e.subject)}</text>
      <text x="${pile.x + 12}" y="${y + 32}" class="t2">${esc(e.sender)} · ${esc(e.note)}</text>
    </g>`;
  });

  const bar = (b, title, lines) => `<g class="gate"><rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" />
    <text x="${b.x + 12}" y="${b.y + 24}" class="g1">${title}</text>
    ${lines.map((l, k) => `<text x="${b.x + 12}" y="${b.y + 46 + k * 16}" class="g2">${esc(l)}</text>`).join('')}</g>`;

  const outRows = OUT.map((o, i) => {
    const y = outY[i];
    return `<g class="out" data-out="${o.id}"><rect x="${outs.x}" y="${y}" width="${outs.w}" height="${outs.h}" />
      <text x="${outs.x + 12}" y="${y + 17}" class="o1">${o.label}</text>
      <text x="${outs.x + 12}" y="${y + 32}" class="o2">${esc(o.action)}</text></g>`;
  });

  const groupLabels = [
    `<text x="${outs.x}" y="22" class="cap">Stays in the inbox</text>`,
    `<text x="${outs.x}" y="${outY[3] - 7}" class="cap">Leaves the inbox</text>`,
    `<text x="${outs.x}" y="${outY[8] - 7}" class="cap">Gmail's spam folder</text>`,
  ];

  return `<svg class="flow flow-desktop" viewBox="0 0 ${W} ${H}" role="img" aria-label="Eight real emails traced through inbox-jev: your rules decide first, the rest go to Jev, then policy turns Jev's confidence into an action.">
  <text x="0" y="22" class="cap">Eight emails from the spec · pick one</text>
  ${groupLabels.join('\n  ')}
  <text x="${jev.x + 18}" y="34" class="cap">Decided by a rule: Jev is not asked</text>
  <text x="${(rules.x + rules.w + jev.x) / 2}" y="${H - 6}" class="cap" text-anchor="middle">no rule</text>
  <text x="${(jev.x + jev.w + pol.x) / 2}" y="${H - 6}" class="cap" text-anchor="middle">category + confidence</text>
  <text x="${(pol.x + pol.w + outs.x) / 2}" y="${H - 6}" class="cap" text-anchor="middle">action</text>
  <g class="routes">${routes.join('\n  ')}</g>
  ${bar(rules, 'Your rules', ['the allowlist and', 'the sender rules', 'learned from your', 'corrections.', '', 'A match decides', 'the category', 'on the spot.'])}
  ${bar(jev, 'Jev', ['gets the headers,', 'the first lines,', 'the domains links', "point to, Gmail's", 'auth verdicts, and', 'whether you ever', 'wrote to them.', '', 'Answers one', 'category and', 'how sure it is.'])}
  ${bar(pol, 'Policy', ['At or above the', "category's bar", '(0.80, 0.90):', 'its action.', '', 'Archive categories', 'that together', 'reach 0.90:', 'archived.', '', 'Anything else:', 'stays, Jev/Review.'])}
  <g class="pile">${pileRows.join('\n  ')}</g>
  <g class="outs">${outRows.join('\n  ')}</g>
</svg>`;
}

// ---------- Phone: 390 × 1010, top to bottom, gates left and outcomes right ----------
function phone() {
  const W = 390, H = 1010;
  const pile = { x: 0, w: 390, y0: 24, h: 40, gap: 4 };
  const gx = 0, gw = 160;
  const rules = { x: gx, w: gw, y: 420, h: 100 };
  const jev = { x: gx, w: gw, y: 576, h: 164 };
  const pol = { x: gx, w: gw, y: 778, h: 164 };
  const outs = { x: 204, w: 186, h: 42, gap: 4, ggap: 24, y0: 540 };
  const outY = [];
  let y = outs.y0;
  OUT.forEach((o, i) => {
    if (i > 0 && OUT[i - 1].group !== o.group) y += outs.ggap;
    outY.push(y);
    y += outs.h + outs.gap;
  });
  const oy = (i) => outY[i] + outs.h / 2;
  const pileBottom = pile.y0 + EX.length * (pile.h + pile.gap) - pile.gap;
  const xf = (i) => 30 + i * 47; // where the route leaves the pile
  const xl = (i) => 18 + i * 15; // its lane inside the gates
  let ruleN = 0;

  const routes = EX.map((e, i) => {
    const o = outIndex(e.out), y2 = oy(o);
    const a = `M ${xf(i)} ${pileBottom} C ${xf(i)} ${pileBottom + 24}, ${xl(i)} ${rules.y - 24}, ${xl(i)} ${rules.y}`;
    const xe = gx + gw;
    let d;
    if (e.via === 'rule') {
      const ry = rules.y + 30 + (ruleN++) * 28;
      d = `${a} L ${xl(i)} ${ry} L ${xe} ${ry} C ${xe + 36} ${ry}, ${outs.x - 36} ${y2}, ${outs.x} ${y2}`;
    } else {
      const py = pol.y + 20 + i * 12;
      d = `${a} L ${xl(i)} ${py} L ${xe} ${py} C ${xe + 36} ${py}, ${outs.x - 36} ${y2}, ${outs.x} ${y2}`;
    }
    return `<path class="route" data-for="${e.id}" d="${d}" />`;
  });

  const pileRows = EX.map((e, i) => {
    const y = pile.y0 + i * (pile.h + pile.gap);
    return `<g class="mail" role="button" tabindex="0" data-ex="${e.id}" aria-label="${esc(e.subject)}, from ${esc(e.sender)}">
      <rect x="${pile.x}" y="${y}" width="${pile.w}" height="${pile.h}" />
      <text x="${pile.x + 12}" y="${y + 17}" class="t1">${esc(e.subject)}</text>
      <text x="${pile.x + 12}" y="${y + 32}" class="t2">${esc(e.sender)} · ${esc(e.note)}</text>
    </g>`;
  });

  const bar = (b, title, lines) => `<g class="gate"><rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" />
    <text x="${b.x + 12}" y="${b.y + 24}" class="g1">${title}</text>
    ${lines.map((l, k) => `<text x="${b.x + 12}" y="${b.y + 44 + k * 16}" class="g2">${esc(l)}</text>`).join('')}</g>`;

  const outRows = OUT.map((o, i) => {
    const y = outY[i];
    return `<g class="out" data-out="${o.id}"><rect x="${outs.x}" y="${y}" width="${outs.w}" height="${outs.h}" />
      <text x="${outs.x + 10}" y="${y + 17}" class="o1">${o.label}</text>
      <text x="${outs.x + 10}" y="${y + 33}" class="o2">${esc(o.action)}</text></g>`;
  });

  return `<svg class="flow flow-phone" viewBox="0 0 ${W} ${H}" role="img" aria-label="Eight real emails traced through inbox-jev: your rules decide first, the rest go to Jev, then policy turns Jev's confidence into an action.">
  <text x="0" y="14" class="cap">Eight emails from the spec · tap one</text>
  <text x="${outs.x}" y="${outs.y0 - 8}" class="cap">Stays in the inbox</text>
  <text x="${outs.x}" y="${outY[3] - 8}" class="cap">Leaves the inbox</text>
  <text x="${outs.x}" y="${outY[8] - 8}" class="cap">Gmail's spam folder</text>
  <text x="${outs.x}" y="${rules.y + 16}" class="cap">Decided by a rule:</text>
  <text x="${outs.x}" y="${rules.y + 32}" class="cap">Jev is not asked</text>
  <g class="routes">${routes.join('\n  ')}</g>
  ${bar(rules, 'Your rules', ['the allowlist and the', 'sender rules learned', 'from your corrections'])}
  ${bar(jev, 'Jev', ['sees headers, first', 'lines, link domains,', 'auth verdicts and', 'whether you wrote', 'to them. Answers a', 'category and how', 'sure it is.'])}
  ${bar(pol, 'Policy', ["Above the category's", 'bar (0.80 / 0.90):', 'its action. Archive', 'categories together', 'at 0.90: archived.', 'Else stays, with', 'Jev/Review.'])}
  <g class="pile">${pileRows.join('\n  ')}</g>
  <g class="outs">${outRows.join('\n  ')}</g>
</svg>`;
}

const here = (p) => new URL(p, import.meta.url);
const frag = (name) => {
  let f = readFileSync(here(`./frag-${name}.html`), 'utf8');
  if (name === 'labels') f = f.slice(0, f.trimEnd().lastIndexOf('</div>')); // the sidebar mockup is cropped by its window
  return f;
};
const tpl = readFileSync(here('./template.src.html'), 'utf8')
  .replace(/^<title>.*<\/title>\n<meta name="claude:[^>]*>\n/, '')
  .replace(/\{\{frag:([a-z]+)\}\}/g, (_, n) => frag(n))
  .replace('<!--DIAGRAM-DESKTOP-->', desktop())
  .replace('<!--DIAGRAM-PHONE-->', phone())
  .replace('{{samples}}', () => JSON.stringify(JSON.parse(readFileSync(here('./samples.json'), 'utf8'))).replace(/<\//g, '<\\/'));
if (tpl.includes('{{frag')) throw new Error('unresolved fragment');
const cut = tpl.indexOf('</style>') + '</style>'.length;
const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>inbox-jev · sorts your Gmail with Jev</title>
<meta name="description" content="${DESCRIPTION}">
<meta name="theme-color" content="#0a1829">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="canonical" href="${SITE}/">
<meta property="og:type" content="website">
<meta property="og:url" content="${SITE}/">
<meta property="og:title" content="inbox-jev · sorts your Gmail with Jev">
<meta property="og:description" content="${DESCRIPTION}">
<meta property="og:image" content="${SITE}/og.png">
<meta property="og:image:width" content="2400">
<meta property="og:image:height" content="1260">
<meta name="twitter:card" content="summary_large_image">
${tpl.slice(0, cut)}
</head>
<body>
${tpl.slice(cut).trim()}
</body>
</html>
`;
writeFileSync(here('../index.html'), html);
console.log('index.html written:', html.length, 'bytes');
