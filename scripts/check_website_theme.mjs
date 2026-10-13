// Browser check for the website's light / dark switch: only one set of pictures shows at a time (dark in dark mode, light in light mode),
// the switch works and remembers the choice, and pictures and styles carry a fingerprint so an old copy is never shown. Builds the site and serves it with its own security headers.
import { chromium } from "playwright";
import http from "node:http"; import fs from "node:fs"; import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
execFileSync("node", ["build.mjs"], { cwd: path.join(root, "website"), stdio: "ignore" });
const dist = path.join(root, "website", "dist");
const csp = (fs.readFileSync(path.join(dist, "_headers"), "utf8").match(/Content-Security-Policy:\s*(.*)/) || [])[1];
const types = { ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript", ".json": "application/json", ".webp": "image/webp", ".png": "image/png", ".ico": "image/x-icon" };
const srv = http.createServer((q, r) => {
  const p = decodeURIComponent(q.url.split("?")[0]);
  let f = path.join(dist, p.replace(/^\/+/, ""));
  if (fs.existsSync(f) && fs.statSync(f).isDirectory()) f = path.join(f, "index.html");
  if (!f.startsWith(dist + path.sep) || !fs.existsSync(f)) { r.statusCode = 404; return r.end("not found"); }
  r.setHeader("Content-Security-Policy", csp); r.setHeader("content-type", types[path.extname(f)] || "application/octet-stream"); r.end(fs.readFileSync(f));
}).listen(0);
const base = `http://127.0.0.1:${srv.address().port}`;
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
const b = await chromium.launch();
const shots = process.env.SHOTS; if (shots) fs.mkdirSync(shots, { recursive: true });
const html = fs.readFileSync(path.join(dist, "index.html"), "utf8");
check("the stylesheet, the script and every picture on the front page have a fingerprint in their address", /href="\/style\.css\?v=[0-9a-f]{8}"/.test(html) && /src="\/theme\.js\?v=[0-9a-f]{8}"/.test(html) && [...html.matchAll(/src="(\/images\/[^"]+)"/g)].filter((m) => !/icon\.webp/.test(m[1])).every((m) => /\?v=[0-9a-f]{8}$/.test(m[1])));
const shown = (p, sel) => p.evaluate((s) => [...document.querySelectorAll(s)].filter((e) => e.getClientRects().length && getComputedStyle(e).display !== "none").length, sel);
for (const scheme of ["dark", "light"]) {
  const ctx = await b.newContext({ viewport: { width: 1400, height: 900 }, colorScheme: scheme }); const p = await ctx.newPage(); const errors = [];
  p.on("pageerror", (e) => errors.push(String(e)));
  for (const url of ["/", "/tour/"]) {
    await p.goto(base + url); await p.waitForTimeout(300);
    const want = scheme, other = scheme === "dark" ? "light" : "dark";
    check(`${url} (${scheme} device): the switch is shown and the ${want} pictures show, not the ${other} ones`, await p.locator("#themeToggle").isVisible() && (await shown(p, `img.img-${want}`)) > 0 && (await shown(p, `img.img-${other}`)) === 0);
    await p.click("#themeToggle"); await p.waitForTimeout(200);
    check(`${url} (${scheme} device): pressing the switch changes the theme and swaps every picture`, (await p.evaluate(() => document.documentElement.getAttribute("data-theme"))) === other && (await shown(p, `img.img-${other}`)) > 0 && (await shown(p, `img.img-${want}`)) === 0);
    if (shots && url === "/") await p.screenshot({ path: path.join(shots, `site-${scheme}-device-switched.png`) });
    await p.reload(); await p.waitForTimeout(200);
    check(`${url} (${scheme} device): the choice is remembered after a reload`, (await p.evaluate(() => document.documentElement.getAttribute("data-theme"))) === other && (await shown(p, `img.img-${want}`)) === 0);
    await p.evaluate(() => localStorage.clear());
  }
  check(`${scheme} device: no page errors`, errors.length === 0);
  await ctx.close();
}
await b.close(); srv.close();
if (failed) process.exit(1);
console.log("Website theme check passed.");
