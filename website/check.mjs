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
  // The only <script> allowed is a block of search-engine data (JSON), which the browser never runs.
  for (const m of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)) {
    if (rel === path.join("search", "index.html") && /^\s*src="\/search\.js(?:\?v=[0-9a-f]{8})?"\s+defer\s*$/.test(m[1]) && !m[2].trim()) continue;       // the guide search, a file from this site
    if (/^\s*src="\/theme\.js(?:\?v=[0-9a-f]{8})?"\s*$/.test(m[1]) && !m[2].trim()) continue;       // the light / dark switch, a file from this site
    if (!/^\s*type="application\/ld\+json"\s*$/.test(m[1])) { bad(`${rel}: has a script`); continue; }
    try { JSON.parse(m[2]); } catch { bad(`${rel}: its search-engine data is not valid JSON`); }
  }
  if (/<script\b(?![^>]*(?:application\/ld\+json|src="\/(?:search|theme)\.js(?:\?v=[0-9a-f]{8})?"))/i.test(html)) bad(`${rel}: has a script`);
  if (/\sstyle="/i.test(html)) bad(`${rel}: has an inline style (the security policy blocks it)`);
  if (/\son[a-z]+="/i.test(html)) bad(`${rel}: has an inline event handler`);
  if (!/<title>[^<]{4,}<\/title>/.test(html)) bad(`${rel}: no title`);
  if ((html.match(/<h1\b/g) || []).length !== 1) bad(`${rel}: should have exactly one main heading`);
  const title = (html.match(/<title>([^<]*)/) || [])[1] || "", desc = (html.match(/name="description" content="([^"]*)/) || [])[1] || "";
  const plain = (t) => t.replace(/&[a-z#0-9]+;/gi, "x");
  if (plain(title).length > 62) bad(`${rel}: the title is too long for a search result (${plain(title).length} characters)`);
  if (plain(desc).length < 20 || plain(desc).length > 165) bad(`${rel}: the description should be 20 to 165 characters (it is ${plain(desc).length})`);
  const canonical = (html.match(/rel="canonical" href="([^"]*)"/) || [])[1];
  const here = "/" + rel.replace(/index\.html$/, "");
  if (rel !== "404.html" && canonical !== "https://enveliq.app" + here) bad(`${rel}: the canonical address is ${canonical}`);
  for (const need of ['property="og:image"', 'name="twitter:card"', 'property="og:title"', 'name="viewport"']) if (!html.includes(need)) bad(`${rel}: missing ${need}`);
  for (const m of html.matchAll(/<img\b[^>]*>/g)) if (!/\salt="/.test(m[0])) bad(`${rel}: a picture has no alt text`);
  for (const m of html.matchAll(/\s(?:src|href)="([^"]+)"/g)) {
    const u = m[1]; count++;
    if (/^https?:\/\//i.test(u)) {
      if (/<(?:img|link|script|iframe)\b[^>]*(?:src|href)="/.test(m.input.slice(Math.max(0, m.index - 80), m.index + m[0].length)) && /rel="stylesheet"|<img|<iframe/i.test(m.input.slice(Math.max(0, m.index - 80), m.index + 1))) bad(`${rel}: loads from another website: ${u}`);
      continue;
    }
    if (/^(mailto:|#$)/.test(u)) continue;
    const [p, hash] = u.replace(/\?v=[0-9a-f]{8}(?=#|$)/, "").split("#");
    const target = p ? (p.startsWith("/") ? fileFor(p) : fileFor(path.posix.join("/", path.dirname(rel), p))) : f;
    if (!target) { bad(`${rel}: link to ${u} goes nowhere`); continue; }
    if (hash && target.endsWith(".html") && !idsOf.get(target)?.has(hash)) bad(`${rel}: ${u} has no such heading on that page`);
  }
}
{
  const guide = path.join(dist, "docs/install/docker-compose/index.html");
  const html = fs.existsSync(guide) ? fs.readFileSync(guide, "utf8") : "";
  const file = fs.readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "install", "docker-compose.yml"), "utf8");
  if (!html.includes("ENVELIQ_SETUP_CODE") || !html.includes("image: ghcr.io/jlnau/enveliq") || html.indexOf("The install file") > html.indexOf("What is a")) bad("the Docker Compose guide does not show the install file first");
  if (!html.includes("enveliq-render:8766") || !file.includes("enveliq-render:8766")) bad("the Docker Compose guide's install file is out of step with install/docker-compose.yml");
}
for (const need of ["_headers", "robots.txt", "sitemap.xml", "404.html", "downloads/docker-compose.yml"]) if (!fs.existsSync(path.join(dist, need))) bad(`missing ${need}`);
// the sitemap lists real pages, and none that are hidden from search
const sitemap = fs.readFileSync(path.join(dist, "sitemap.xml"), "utf8");
for (const m of sitemap.matchAll(/<loc>https:\/\/enveliq\.app([^<]*)<\/loc>/g)) {
  const f = fileFor(m[1]);
  if (!f) bad(`the sitemap lists ${m[1]}, which does not exist`);
  else if (/name="robots" content="noindex/.test(htmlOf.get(f) || "")) bad(`the sitemap lists ${m[1]}, which is hidden from search`);
}
for (const need of ["favicon.ico", "images/apple-touch-icon.png", ".well-known/security.txt", "tour/index.html"]) if (!fs.existsSync(path.join(dist, need))) bad(`missing ${need}`);
if (!fs.existsSync(path.join(dist, "images/share.png"))) bad("missing the share picture images/share.png");
const headers = fs.existsSync(path.join(dist, "_headers")) ? fs.readFileSync(path.join(dist, "_headers"), "utf8") : "";
if (!/script-src 'self'(?=;)/.test(headers) || /script-src[^;]*(?:http|\*|data:)/.test(headers)) bad("the security policy lets scripts load from somewhere other than this site");
if (!/default-src 'none'/.test(headers) || /unsafe-inline|unsafe-eval/.test(headers)) bad("the security policy in _headers is not strict");
if (!failed) console.log(`✓ ${pages.length} pages, ${count} links and pictures checked; only the guide search and the light/dark switch run scripts, no outside requests, search tags in place`);
process.exit(failed ? 1 : 0);
