// The demo: built from the inbox page, no server behind it, nothing leaves the page, and it says plainly that the mail is made up.
// Serves demo/dist the way the host will (with the headers from dist/_headers). Set SHOTS=<folder> to save screenshots.
import { chromium } from "playwright";
import http from "node:http"; import fs from "node:fs"; import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
execFileSync("node", ["demo/build.mjs"], { cwd: root, stdio: "inherit" });
const dist = path.join(root, "demo", "dist");
const headerText = fs.readFileSync(path.join(dist, "_headers"), "utf8");
const headers = Object.fromEntries(headerText.split("\n").slice(1).filter((l) => l.includes(":")).map((l) => { const i = l.indexOf(":"); return [l.slice(0, i).trim().toLowerCase(), l.slice(i + 1).trim()]; }));

const seen = [];
const types = { ".html": "text/html; charset=utf-8", ".webp": "image/webp", ".svg": "image/svg+xml" };
const srv = http.createServer((q, r) => {
  seen.push(q.method + " " + q.url);
  const p = q.url.split("?")[0];
  const file = p === "/" ? "index.html" : p.replace(/^\/+/, "");
  const full = path.join(dist, file);
  if (!full.startsWith(dist + path.sep) || file === "_headers" || !fs.existsSync(full)) { r.statusCode = 404; r.end("not found"); return; }
  for (const [k, v] of Object.entries(headers)) r.setHeader(k, v);
  r.setHeader("content-type", types[path.extname(full)] || "application/octet-stream");
  r.end(fs.readFileSync(full));
}).listen(0);
const url = `http://127.0.0.1:${srv.address().port}/`;

let fails = 0;
const ok = (n, c) => { console.log((c ? "✓ " : "✗ ") + n); if (!c) fails++; };
const b = await chromium.launch();
const shots = process.env.SHOTS; if (shots) fs.mkdirSync(shots, { recursive: true });

ok("the headers forbid every connection and name each script", /connect-src 'none'/.test(headers["content-security-policy"]) && /script-src ('sha256-[A-Za-z0-9+/=]+' ?)+;/.test(headers["content-security-policy"]) && !/unsafe-eval/.test(headers["content-security-policy"]));
ok("the headers stop it being framed and send no referrer", headers["x-frame-options"] === "DENY" && headers["referrer-policy"] === "no-referrer");

for (const [name, vp] of [["desktop", { width: 1280, height: 800 }], ["phone", { width: 390, height: 800 }]]) {
  seen.length = 0;
  const p = await b.newPage({ viewport: vp });
  const problems = [];
  p.on("pageerror", (e) => problems.push("script error: " + e.message));
  p.on("console", (m) => { if (/Content.Security.Policy/i.test(m.text())) problems.push(m.text().slice(0, 160)); });
  await p.addInitScript(() => document.addEventListener("securitypolicyviolation", (e) => console.log("Content-Security-Policy violation: " + e.violatedDirective + " " + e.blockedURI)));
  await p.goto(url); await p.waitForTimeout(800);
  const banner = (await p.locator(".demo-banner").innerText()).toLowerCase();
  ok(name + ": a banner says the mail is made up and nothing is saved", banner.includes("made up") && banner.includes("nothing") && await p.locator(".demo-banner").isVisible());
  const text = await p.locator("body").innerText();
  ok(name + ": the made-up mail is there", text.includes("Skyline Air") && text.includes("Harbourview Strata"));
  await p.getByText("Your Skyline Air Travel Reminder").first().click(); await p.waitForTimeout(400);
  ok(name + ": opening a message shows it", /VA281|check.?in/i.test(await p.locator("body").innerText()));
  // Reviewed, Archive and Bin wait five seconds, with Undo, here as everywhere
  const rowsBefore = await p.locator("article.mail:not(.leaving)").count();
  await p.locator("article.mail [data-status=archived]:visible").first().click();
  await p.waitForSelector("#undoBar:not([hidden])");
  ok(name + ": Archive leaves the list at once and an Undo bar appears", (await p.locator("article.mail:not(.leaving)").count()) === rowsBefore - 1 && /Archived/.test(await p.locator("#undoBar .undobar:last-child span").innerText()));
  if (shots) await p.screenshot({ path: path.join(shots, `demo-undo-${name}.png`) });
  await p.click("#undoBar .undobar:last-child button");
  ok(name + ": Undo brings it back", (await p.locator("article.mail:not(.leaving)").count()) === rowsBefore && !(await p.locator("#undoBar").isVisible()));
  ok(name + ": it never asked for anything but the page and its pictures", seen.every((s) => /^GET \/(?:brand\/[\w.-]+|static\/northern-coast-(?:dark|light)\.svg)?$/.test(s)));
  ok(name + ": no outside requests", seen.every((s) => !/^[A-Z]+ https?:/.test(s)));
  ok(name + ": no script errors or Content-Security-Policy violations", problems.length === 0);
  if (problems.length) console.log("   " + problems.join("\n   "));
  ok(name + ": nothing sticks out sideways", await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  ok(name + ": the title says demo", (await p.title()) === "Enveliq demo");
  const stored = await p.evaluate(() => { try { return Object.keys(localStorage).filter((k) => k !== "enveliq-theme"); } catch { return []; } });
  ok(name + ": nothing is kept in the browser", stored.length === 0);
  if (shots) await p.screenshot({ path: path.join(shots, `demo-${name}.png`) });
  await p.close();
}
await b.close(); srv.close(); process.exit(fails ? 1 : 0);
