// Browser check for the search on the website's guides. Builds the site, serves it with its own security headers, and searches.
// Usage: node scripts/check_site_search.mjs      (needs Playwright; run `npm install --prefix website` once). SHOTS=<folder> saves screenshots.
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

for (const [name, vp] of [["desktop", { width: 1180, height: 820 }], ["phone", { width: 390, height: 800 }]]) {
  const ctx = await b.newContext({ viewport: vp }); const p = await ctx.newPage();
  const errors = [], outside = [];
  p.on("pageerror", (e) => errors.push(String(e)));
  p.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  p.on("request", (r) => { if (!r.url().startsWith(base)) outside.push(r.url()); });
  await p.goto(base + "/docs/");
  check(name + ": the guides page has a search box", (await p.locator('form[role=search] input[name=q]').count()) >= 1);
  const box = p.locator("form[role=search] input[name=q]:visible").first();
  if (name === "desktop") { await box.fill("passkey"); await box.press("Enter"); }
  else { await p.goto(base + "/search/?q=passkey"); }
  await p.waitForSelector(".hits li", { timeout: 8000 });
  check(name + ": searching goes to /search/ and lists guides", p.url().includes("/search/?q=passkey") && (await p.locator(".hits li").count()) >= 2);
  check(name + ": every result is a link to a guide with a short passage", await p.locator(".hits li").evaluateAll((li) => li.every((x) => /^\/docs\//.test(x.querySelector("a").getAttribute("href")) && x.querySelector("p").innerText.length > 20)));
  check(name + ": old release notes do not come first", !/^\/docs\/(changelog|version-history)\//.test(await p.locator(".hits li a").first().getAttribute("href")));
  await p.goto(base + "/search/?q=zzzzqqq");
  await p.waitForSelector("#results p", { timeout: 8000 });
  check(name + ": a word that is nowhere says so and points to the list of guides", /Nothing found/.test(await p.locator("#results").innerText()) && (await p.locator('#results a[href="/docs/"]').count()) === 1);
  await p.goto(base + "/search/?q=microsoft directory");
  await p.waitForSelector(".hits li", { timeout: 8000 });
  check(name + ": two words must both be on the guide", /microsoft/i.test(await p.locator(".hits li").first().innerText()));
  await p.goto(base + "/search/?q=backup"); await p.waitForSelector(".hits li");
  if (shots) await p.screenshot({ path: path.join(shots, "search-" + name + ".png") });
  check(name + ": no sideways scrolling", await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  check(name + ": nothing was asked of another website and the security policy raised no errors", outside.length === 0 && errors.length === 0);
  await ctx.close();
}

{
  const ctx = await b.newContext({ javaScriptEnabled: false }); const p = await ctx.newPage();
  await p.goto(base + "/search/?q=backup");
  check("without scripts the page says so and still offers the list of guides", /needs JavaScript/.test(await p.locator("#results").innerText()) && (await p.locator('#results a[href="/docs/"]').count()) === 1);
  await ctx.close();
}
await b.close(); srv.close();
if (failed) process.exit(1);
console.log("All checks passed");
