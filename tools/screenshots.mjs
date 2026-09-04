// Sanitized screenshot tour of a Firefly III install.
//
//   FF_URL=https://firefly.example.lan FF_EMAIL=you@example.com FF_PASSWORD_CMD="pass show firefly" \
//   SANITIZE_MAP=tools/sanitize-map.json node tools/screenshots.mjs
//
// What it does, per page:
//   1. logs in through the normal login form (the password comes from FF_PASSWORD_CMD, never from a file
//      in this repo and never written to disk);
//   2. loads the page and lets it render;
//   3. rewrites the rendered DOM in place — every text node, input value and title attribute — using the
//      replacement map, the regex list, your pii-names.txt, and an amount scaling factor;
//   4. re-scans the rewritten page text for every left-hand string and every name; if anything survived,
//      the page is reported as UNSAFE and NO screenshot is written;
//   5. saves a full-page PNG to docs/screenshots/NN-<page>.png.
//
// The DOM is sanitized, not a copy of it, so styles, charts and layout are exactly what Firefly renders;
// DUMP_HTML=1 additionally writes the sanitized DOM to tools/out/<page>.html so you can review it as text.
//
// Env:
//   FF_URL             base URL, no trailing slash                                   (required)
//   FF_EMAIL           login email                                                    (required)
//   FF_PASSWORD_CMD    command that prints the password                              (required, or FF_PASSWORD)
//   SANITIZE_MAP       path to the map JSON (see sanitize-map.example.json)          (default tools/sanitize-map.json)
//   OUT_DIR            where PNGs go                                                  (default docs/screenshots)
//   DUMP_HTML          1 to also write sanitized HTML to tools/out/                   (default off)
//   PLAYWRIGHT_MODULE  path to an existing Playwright install's index.mjs             (default: import 'playwright')
//   WIDTH              viewport width                                                 (default 1440)
//   SETTLE_MS          wait after load before sanitizing, for charts to draw          (default 4000)

import { execSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const env = (k, d) => (process.env[k] === undefined || process.env[k] === '' ? d : process.env[k]);

const pw = process.env.PLAYWRIGHT_MODULE ? pathToFileURL(process.env.PLAYWRIGHT_MODULE).href : 'playwright';
const { chromium } = await import(pw);

const base = env('FF_URL', '').replace(/\/$/, '');
const email = env('FF_EMAIL', '');
const password = process.env.FF_PASSWORD_CMD
  ? execSync(process.env.FF_PASSWORD_CMD, { encoding: 'utf8' }).trim()
  : env('FF_PASSWORD', '');
if (!base || !email || !password) {
  console.error('FF_URL, FF_EMAIL and FF_PASSWORD_CMD (or FF_PASSWORD) are required');
  process.exit(2);
}

const mapPath = env('SANITIZE_MAP', 'tools/sanitize-map.json');
if (!existsSync(mapPath)) {
  console.error(`sanitize map not found: ${mapPath} — copy tools/sanitize-map.example.json and fill it in`);
  process.exit(2);
}
const map = JSON.parse(readFileSync(mapPath, 'utf8'));
const outDir = env('OUT_DIR', 'docs/screenshots');
const dumpHtml = env('DUMP_HTML', '') === '1';
const width = Number(env('WIDTH', '1440'));
const settle = Number(env('SETTLE_MS', '4000'));

// Names file: one term per line, # comments. Each becomes a replacement to a fixed placeholder.
let names = [];
if (map.names_file && existsSync(map.names_file)) {
  names = readFileSync(map.names_file, 'utf8')
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith('#'));
} else if (map.names_file) {
  console.error(`names file not found: ${map.names_file} — personal names will NOT be redacted`);
}

// Build the literal replacement list, longest first so "Springfield Savings & Loan" beats "Springfield".
const literal = Object.entries(map.replace || {}).map(([from, to]) => ({ from, to }));
for (const n of names) literal.push({ from: n, to: '[NAME]' });
literal.sort((a, b) => b.from.length - a.from.length);
const regexes = (map.regex || []).map(([pat, to]) => ({ pat, to }));
const amountFactor = map.amount_factor === undefined ? 1 : Number(map.amount_factor);

// Runs inside the page. Rewrites text nodes, input values and title/placeholder attributes.
const sanitizeInPage = ({ literal, regexes, amountFactor }) => {
  const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  // Tolerate any whitespace (incl. NBSP) between words of a multi-word term.
  const lits = literal.map(({ from, to }) => ({
    re: new RegExp(from.trim().split(/\s+/).map(esc).join('\\s+'), 'gi'),
    to,
  }));
  const res = regexes.map(({ pat, to }) => ({ re: new RegExp(pat, 'g'), to }));
  // Currency amounts as Firefly renders them: optional symbol/code, thousands separators, 2 decimals.
  const amountRe = /(-?)\s?((?:[A-Z]{1,3}\s?)?[$€£¥]?)\s?(\d{1,3}(?:[,.\s]\d{3})*|\d+)([.,]\d{2})\b/g;
  const scale = (s) =>
    s.replace(amountRe, (m, sign, cur, intPart, dec) => {
      const n = Number(intPart.replace(/[,\s.]/g, '') + '.' + dec.slice(1));
      if (!Number.isFinite(n)) return m;
      const v = n * amountFactor;
      const fixed = v.toFixed(2);
      const [i, d] = fixed.split('.');
      const grouped = i.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
      return `${sign}${cur}${grouped}.${d}`;
    });
  const rewrite = (s) => {
    let t = s;
    for (const { re, to } of lits) t = t.replace(re, to);
    for (const { re, to } of res) t = t.replace(re, to);
    if (amountFactor !== 1) t = scale(t);
    return t;
  };
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  let changed = 0;
  for (const n of nodes) {
    if (!n.nodeValue || !n.nodeValue.trim()) continue;
    const p = n.parentElement;
    if (p && (p.tagName === 'SCRIPT' || p.tagName === 'STYLE')) continue;
    const v = rewrite(n.nodeValue);
    if (v !== n.nodeValue) { n.nodeValue = v; changed++; }
  }
  for (const el of document.querySelectorAll('input, textarea')) {
    if (el.type === 'password') continue;
    const v = rewrite(el.value || '');
    if (v !== el.value) { el.value = v; changed++; }
  }
  for (const el of document.querySelectorAll('[title], [placeholder], [alt], [data-original-title]')) {
    for (const a of ['title', 'placeholder', 'alt', 'data-original-title']) {
      const cur = el.getAttribute(a);
      if (cur) { const v = rewrite(cur); if (v !== cur) { el.setAttribute(a, v); changed++; } }
    }
  }
  document.title = rewrite(document.title);
  return changed;
};

// Residual check, also in the page: any left-hand literal still visible anywhere in the text?
const residualInPage = ({ literal }) => {
  const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const text = document.body.innerText + '\n' + document.title;
  const hits = [];
  for (const { from } of literal) {
    const re = new RegExp(from.trim().split(/\s+/).map(esc).join('\\s+'), 'i');
    if (re.test(text)) hits.push(from);
  }
  return hits;
};

const pages = map.pages || [
  ['01-dashboard', '/'],
  ['02-asset-accounts', '/accounts/asset'],
  ['03-liabilities', '/accounts/liabilities'],
  ['06-budgets', '/budgets'],
  ['07-subscriptions', '/subscriptions', '/bills'],
  ['08-categories', '/categories'],
];

mkdirSync(outDir, { recursive: true });
if (dumpHtml) mkdirSync('tools/out', { recursive: true });

const browser = await chromium.launch();
const ctx = await browser.newContext({
  viewport: { width, height: 900 },
  ignoreHTTPSErrors: true,
  colorScheme: 'light',
  locale: 'en-CA',
});
const page = await ctx.newPage();

// --- login ---
await page.goto(`${base}/login`, { waitUntil: 'load', timeout: 60000 });
await page.fill('input[name="email"]', email);
await page.fill('input[name="password"]', password);
await Promise.all([
  page.waitForNavigation({ waitUntil: 'load', timeout: 60000 }).catch(() => {}),
  page.click('button[type="submit"], input[type="submit"]'),
]);
await page.waitForTimeout(1500);
if (/\/login/.test(page.url())) {
  const msg = await page.locator('.invalid-feedback, .alert-danger, .text-danger').first().textContent().catch(() => '');
  console.error(`login failed (still on /login). ${msg ? 'Firefly said: ' + msg.trim() : ''}`);
  await browser.close();
  process.exit(3);
}
console.log('logged in as', email.replace(/(.).+(@.*)/, '$1***$2'));

// --- tour ---
let unsafe = 0;
for (const [name, ...paths] of pages) {
  let ok = false;
  for (const path of paths) {
    try {
      const resp = await page.goto(`${base}${path}`, { waitUntil: 'load', timeout: 60000 });
      if (!resp || resp.status() >= 400) { console.log(`skip ${name} ${path} -> HTTP ${resp ? resp.status() : '?'}`); continue; }
      await page.waitForTimeout(settle);
      // Firefly shows an intro tour (intro.js) the first time a page is visited; dismiss it so it
      // does not sit over the capture. Firefly remembers the dismissal per page.
      const skip = page.locator('.introjs-skipbutton');
      if (await skip.count()) { await skip.first().click().catch(() => {}); await page.waitForTimeout(500); }
      const changed = await page.evaluate(sanitizeInPage, { literal, regexes, amountFactor });
      const hits = await page.evaluate(residualInPage, { literal });
      if (hits.length) {
        unsafe++;
        console.log(`UNSAFE ${name} ${path}: ${hits.length} term(s) still visible after rewrite — no file written:`, hits.map((h) => h.slice(0, 3) + '…'));
        ok = true; break;
      }
      const file = `${outDir}/${name}.png`;
      await page.screenshot({ path: file, fullPage: true, animations: 'disabled', timeout: 60000 });
      if (dumpHtml) writeFileSync(`tools/out/${name}.html`, await page.content(), 'utf8');
      console.log(`ok   ${file}  (${changed} text edits)`);
      ok = true; break;
    } catch (e) {
      console.log(`FAIL ${name} ${path}: ${String(e.message).split('\n')[0]}`);
    }
  }
  if (!ok) console.log(`skip ${name}: no path succeeded`);
}
await browser.close();
if (unsafe) {
  console.error(`${unsafe} page(s) were UNSAFE. Add the surviving terms to the map or names file and rerun.`);
  process.exit(4);
}
