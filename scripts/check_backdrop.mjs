// Browser check for the inbox backdrop (night scene in dark mode, morning scene in light mode) and the plain logo in the sidebar.
// Uses the demo build (made-up mail, no server). Usage: node scripts/check_backdrop.mjs      Set SHOTS=<folder> to save screenshots.
import { chromium } from "playwright";
import http from "node:http"; import fs from "node:fs"; import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
execFileSync("node", ["demo/build.mjs"], { cwd: root, stdio: "ignore" });
const dist = path.join(root, "demo", "dist");
const headers = Object.fromEntries(fs.readFileSync(path.join(dist, "_headers"), "utf8").split("\n").slice(1).filter((l) => l.includes(":")).map((l) => { const i = l.indexOf(":"); return [l.slice(0, i).trim().toLowerCase(), l.slice(i + 1).trim()]; }));
const types = { ".html": "text/html; charset=utf-8", ".webp": "image/webp", ".png": "image/png" };
const srv = http.createServer((q, r) => {
  const p = q.url.split("?")[0], f = path.join(dist, p === "/" ? "index.html" : p.replace(/^\/+/, ""));
  if (!f.startsWith(dist + path.sep) || f.endsWith("_headers") || !fs.existsSync(f)) { r.statusCode = 404; return r.end("not found"); }
  for (const [k, v] of Object.entries(headers)) r.setHeader(k, v);
  r.setHeader("content-type", types[path.extname(f)] || "application/octet-stream"); r.end(fs.readFileSync(f));
}).listen(0);
const origin = `http://127.0.0.1:${srv.address().port}`;
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
const b = await chromium.launch();
const shots = process.env.SHOTS; if (shots) fs.mkdirSync(shots, { recursive: true });

const scenes = {};
for (const [name, theme, vp] of [["desktop dark", "dark", { width: 1440, height: 900 }], ["desktop light", "light", { width: 1440, height: 900 }], ["wide dark", "dark", { width: 2000, height: 1000 }], ["tablet light", "light", { width: 900, height: 900 }], ["phone dark", "dark", { width: 390, height: 800 }]]) {
  const ctx = await b.newContext({ viewport: vp });
  await ctx.addInitScript((t) => { try { localStorage.setItem("enveliq-theme", t); localStorage.setItem("enveliq-welcome-seen", "1"); } catch {} }, theme);
  const p = await ctx.newPage(); const errors = [], outside = [];
  p.on("pageerror", (e) => errors.push(String(e)));
  p.on("request", (r) => { if (!r.url().startsWith(origin) && !r.url().startsWith("data:")) outside.push(r.url()); });
  await p.goto(origin + "/"); await p.waitForTimeout(1200);
  const info = await p.evaluate(() => {
    const main = document.querySelector(".main"), before = getComputedStyle(main, "::before"), top = getComputedStyle(document.querySelector("header.top")), brand = document.querySelector(".sidebar .brand");
    const bs = brand ? getComputedStyle(brand) : null;
    return { image: before.backgroundImage, theme: document.documentElement.dataset.theme, topBg: top.backgroundImage + "|" + top.backgroundColor, topPos: top.position, brandBg: bs ? bs.backgroundColor + "|" + bs.backgroundImage : "", brandShadow: bs ? bs.boxShadow : "", scrollW: document.documentElement.scrollWidth, innerW: window.innerWidth };
  });
  const big = vp.width >= 761;
  if (big) {
    check(name + ": a scene is drawn behind the top of the page, from a picture held inside the page", /^url\("data:image\/svg\+xml,/.test(info.image));
    check(name + ": the heading area has no solid band over the scene, and scrolls away with the page", /none\|rgba\(0, 0, 0, 0\)/.test(info.topBg) && info.topPos === "relative");
    scenes[theme] = info.image;
  } else check(name + ": no backdrop on a phone, so nothing takes up space", info.image === "none");
  if (theme === "light") check(name + ": the logo sits on the sidebar colour, with no white box", /rgba\(0, 0, 0, 0\)\|none/.test(info.brandBg) && (info.brandShadow === "none" || info.brandShadow === ""));
  check(name + ": no sideways scrolling", info.scrollW <= info.innerW);
  check(name + ": nothing was fetched from another address", outside.length === 0);
  check(name + ": no script errors", errors.length === 0);
  if (shots) await p.screenshot({ path: path.join(shots, `backdrop-${name.replace(/ /g, "-")}.png`) });
  await ctx.close();
}
check("dark and light mode use two different scenes", scenes.dark && scenes.light && scenes.dark !== scenes.light);
await b.close(); srv.close();
process.exit(failed ? 1 : 0);
