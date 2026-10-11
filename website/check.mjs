// Checks the built website (run `node build.mjs` first): every link and picture points at something that exists,
// every #anchor is on its page, and nothing could load from another website or run a script.
//
// Usage: node check.mjs
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dist = path.join(path.dirname(fileURLToPath(import.meta.url)), "dist");
let failed = false, count = 0;
const bad = (msg) => { failed = true; console.log("✗ " + msg); console.log("::error::" + msg); };
const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => e.isDirectory() ? walk(path.join(d, e.name)) : [path.join(d, e.name)]);
const pages = walk(dist).filter((f) => f.endsWith(".html"));
const idsOf = new Map();
const htmlOf = new Map();
for (const f of pages) {
  const html = fs.readFileSync(f, "utf8");
  htmlOf.set(f, html);
  idsOf.set(f, new Set([...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1])));
}
const fileFor = (urlPath) => {
  const p = path.join(dist, decodeURIComponent(urlPath));
  if (fs.existsSync(p) && fs.statSync(p).isFile()) return p;
  const idx = path.join(p, "index.html");
  return fs.existsSync(idx) ? idx : null;
};

for (const [f, html] of htmlOf) {
  const rel = path.relative(dist, f);
  if (/<script\b/i.test(html)) bad(`${rel}: has a script`);
  if (/\sstyle="/i.test(html)) bad(`${rel}: has an inline style (the security policy blocks it)`);
  if (/\son[a-z]+="/i.test(html)) bad(`${rel}: has an inline event handler`);
  if (!/<title>[^<]{4,}<\/title>/.test(html)) bad(`${rel}: no title`);
  if (!/<h1\b/.test(html)) bad(`${rel}: no main heading`);
  for (const m of html.matchAll(/<img\b[^>]*>/g)) if (!/\salt="/.test(m[0])) bad(`${rel}: a picture has no alt text`);
  for (const m of html.matchAll(/\s(?:src|href)="([^"]+)"/g)) {
    const u = m[1]; count++;
    if (/^https?:\/\//i.test(u)) {
      if (/<(?:img|link|script|iframe)\b[^>]*(?:src|href)="/.test(m.input.slice(Math.max(0, m.index - 80), m.index + m[0].length)) && /rel="stylesheet"|<img|<iframe/i.test(m.input.slice(Math.max(0, m.index - 80), m.index + 1))) bad(`${rel}: loads from another website: ${u}`);
      continue;
    }
    if (/^(mailto:|#$)/.test(u)) continue;
    const [p, hash] = u.split("#");
    const target = p ? (p.startsWith("/") ? fileFor(p) : fileFor(path.posix.join("/", path.dirname(rel), p))) : f;
    if (!target) { bad(`${rel}: link to ${u} goes nowhere`); continue; }
    if (hash && target.endsWith(".html") && !idsOf.get(target)?.has(hash)) bad(`${rel}: ${u} has no such heading on that page`);
  }
}
for (const need of ["_headers", "robots.txt", "sitemap.xml", "404.html", "downloads/docker-compose.yml"]) if (!fs.existsSync(path.join(dist, need))) bad(`missing ${need}`);
const headers = fs.existsSync(path.join(dist, "_headers")) ? fs.readFileSync(path.join(dist, "_headers"), "utf8") : "";
if (!/default-src 'none'/.test(headers) || /unsafe-inline|unsafe-eval/.test(headers)) bad("the security policy in _headers is not strict");
if (!failed) console.log(`✓ ${pages.length} pages, ${count} links and pictures checked; no scripts, no outside requests`);
process.exit(failed ? 1 : 0);
