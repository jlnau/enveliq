// Checks text colour against its background on the built site, in dark and light, on a few key pages. Needs Playwright.
// Usage: node build.mjs && node audit-contrast.mjs
import { chromium } from "playwright";
import http from "node:http"; import fs from "node:fs"; import path from "node:path"; import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "dist");
const types = { ".html": "text/html", ".css": "text/css", ".png": "image/png", ".webp": "image/webp", ".ico": "image/x-icon" };
const srv = http.createServer((q, r) => { let p = path.join(root, decodeURIComponent(q.url.split("?")[0])); if (fs.existsSync(p) && fs.statSync(p).isDirectory()) p = path.join(p, "index.html"); if (!fs.existsSync(p)) { r.statusCode = 404; return r.end(); } r.setHeader("content-type", types[path.extname(p)] || "text/plain"); r.end(fs.readFileSync(p)); }).listen(0);
const port = srv.address().port;
const pages = ["/", "/tour/", "/docs/scam-warning/", "/docs/snooze/", "/docs/search/", "/docs/subscriptions/", "/docs/trips/", "/docs/backup/", "/docs/demo/", "/docs/undo/", "/docs/send-checks/", "/docs/important-people/", "/docs/saved-replies/", "/docs/", "/docs/install/docker-desktop/", "/docs/security/", "/404.html"];
const browser = await chromium.launch();
let worst = 99, problems = 0;
for (const scheme of ["dark", "light"]) for (const w of [1280, 390]) {
  const page = await browser.newPage({ viewport: { width: w, height: 900 }, colorScheme: scheme });
  for (const u of pages) {
    await page.goto(`http://localhost:${port}${u}`);
    // open every folded section so hidden text is measured as well
    await page.evaluate(() => document.querySelectorAll("details").forEach((d) => (d.open = true)));
    const found = await page.evaluate(() => {
      const parse = (c) => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const [r, g, b, a = 1] = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return { r, g, b, a }; };
      const over = (top, bot) => ({ r: top.r * top.a + bot.r * (1 - top.a), g: top.g * top.a + bot.g * (1 - top.a), b: top.b * top.a + bot.b * (1 - top.a), a: 1 });
      const lum = ({ r, g, b }) => { const f = (v) => { v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }; return .2126 * f(r) + .7152 * f(g) + .0722 * f(b); };
      const bgOf = (el) => { const stack = []; for (let e = el; e; e = e.parentElement) { const cs = getComputedStyle(e); if (cs.backgroundImage !== "none") return null; const c = parse(cs.backgroundColor); if (c && c.a > 0) { stack.push(c); if (c.a === 1) break; } } let base = { r: 255, g: 255, b: 255, a: 1 }; for (const c of stack.reverse()) base = over(c, base); return base; };
      const out = [];
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      const seen = new Set();
      for (let n; (n = walker.nextNode());) {
        if (!n.textContent.trim()) continue; const el = n.parentElement; if (!el || seen.has(el)) continue; seen.add(el);
        const r = el.getBoundingClientRect(); if (!r.width || !r.height) continue; const cs = getComputedStyle(el);
        if (cs.visibility === "hidden" || cs.opacity === "0" || el.closest("[aria-hidden=true]")) continue;
        const bg = bgOf(el); if (!bg) continue; let fg = parse(cs.color); if (!fg) continue; fg = over(fg, bg);
        const L1 = lum(fg), L2 = lum(bg), ratio = (Math.max(L1, L2) + .05) / (Math.min(L1, L2) + .05);
        const size = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight) >= 700, large = size >= 24 || (size >= 18.66 && bold);
        if (ratio < (large ? 3 : 4.5)) out.push({ text: n.textContent.trim().slice(0, 40), ratio: Math.round(ratio * 100) / 100, need: large ? 3 : 4.5, tag: el.tagName.toLowerCase() + (el.className ? "." + String(el.className).split(" ")[0] : "") });
      }
      return out;
    });
    for (const f of found) { problems++; worst = Math.min(worst, f.ratio); console.log(`✗ ${scheme} ${w}px ${u}  ${f.ratio} (needs ${f.need})  ${f.tag}  "${f.text}"`); }
  }
  await page.close();
}
await browser.close(); srv.close();
console.log(problems ? `${problems} text colours are too faint (worst ${worst}:1)` : "✓ every text colour has enough contrast (WCAG AA) in dark and light, on desktop and phone");
process.exit(problems ? 1 : 0);
