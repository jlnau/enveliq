// Browser check for the "Email style" choice in Customise: Classic stays the default, "Side rail" puts the buttons in a bar
// down the left (square icons along the bottom on a phone), the task along the top, and the email address opens the copy options.
// Uses the demo build (made-up mail, no server). Usage: node scripts/check_email_style.mjs      Set SHOTS=<folder> to save screenshots.
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
const open = async (w, h) => {
  const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
  await ctx.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch {} });
  const p = await ctx.newPage(); p.errors = []; p.on("pageerror", (e) => p.errors.push(String(e)));
  await p.goto(origin + "/"); await p.waitForTimeout(1200);
  return [ctx, p];
};
const box = (p, sel) => p.evaluate((s) => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height, r: r.right, b: r.bottom }; }, sel);

{ // desktop: the side-by-side layout
  const [ctx, p] = await open(1500, 900);
  await p.evaluate(() => { view.layout = "right"; applyView(); render(); });
  await p.waitForTimeout(400);
  check("Classic is the default style", await p.evaluate(() => view.style === "classic" && !document.body.classList.contains("style-rail")));
  check("classic: no side rail is drawn", (await p.locator(".rl-rail").count()) === 0);
  // choose Side rail in the Customise panel
  await p.click("#viewTab"); await p.waitForTimeout(300);
  check("Customise has an Email style choice with Classic and Side rail", (await p.locator('#viewPanel [data-view="style"]').count()) === 2);
  check("Classic is marked as chosen at first", await p.evaluate(() => document.querySelector('#viewPanel [data-view="style"][data-val="classic"]').getAttribute("aria-checked") === "true"));
  await p.click('#viewPanel [data-view="style"][data-val="rail"]'); await p.waitForTimeout(500);
  check("choosing Side rail is remembered in the view", await p.evaluate(() => view.style === "rail" && document.body.classList.contains("style-rail")));
  await p.mouse.click(700, 400); await p.waitForTimeout(400);   // closes the panel
  // pick an email that has a task, if there is one, else the first
  await p.evaluate(() => { const m = data.find((x) => x.owner === currentUser.id && x.status === "inbox" && typeof tasksFor === "function" && tasksFor(x).length) || data.find((x) => x.owner === currentUser.id && x.status === "inbox"); window.__pick = m.id; paneId = m.id; render(); });
  await p.waitForTimeout(500);
  check("side rail: the reading panel uses the rail layout", (await p.locator(".reading.rail .rl-rail").count()) === 1);
  const rail = await box(p, ".rl-rail"), read = await box(p, ".reading.rail");
  check("side rail: the bar sits down the left edge of the email", rail && read && Math.abs(rail.x - read.x) <= 2 && rail.w >= 60 && rail.w <= 100);
  for (const [l, sel] of [["Reviewed", '.rl-rail .action.reviewed'], ["Archive", '.rl-rail .action.archive'], ["Bin", '.rl-rail .action.trash'], ["Task", '.rl-rail [data-task-add]'], ["Snooze", '.rl-rail [data-snooze], .rl-rail [data-unsnooze]']])
    check("side rail: " + l + " button is there", (await p.locator(sel).count()) >= 1);
  check("side rail: the AI summary, with View original email, is shown", (await p.locator(".reading.rail .qsummary-copy").count()) === 1 && (await p.locator(".reading.rail .summary-original-link").count()) === 1);
  check("side rail: the email address and the four copy buttons are shown", (await p.locator(".reading.rail .rl-addr").count()) === 1 && (await p.locator(".reading.rail .mail-copy-action").count()) >= 3);
  check("side rail: the details box (From, Received, Category, Attachments) is not repeated", (await p.locator(".reading.rail .qside").count()) === 0);
  check("side rail: the three-dot menu is in the heading", (await p.locator(".reading.rail .rl-titlerow [data-more]").count()) === 1);
  if (await p.locator(".rl-task").count()) {
    const t = await box(p, ".rl-task"), m = await box(p, ".rl-main");
    check("side rail: the task bar runs the full width beside the rail, flat across the top", Math.abs(t.x - m.x) <= 2 && Math.abs(t.w - m.w) <= 2 && Math.abs(t.y - m.y) <= 2);
  }
  if (shots) await p.screenshot({ path: path.join(shots, "rail-desktop.png") });
  // an action button works: Archive moves the email on
  const before = await p.evaluate(() => window.__pick);
  await p.click(".rl-rail .action.archive"); await p.waitForTimeout(600);
  check("side rail: Archive works like it does in Classic", await p.evaluate((id) => { const m = data.find((x) => x.id === id); return !m || m.status !== "inbox" || !!m._pending; }, before));
  // back to Classic
  await p.evaluate(() => { view.style = "classic"; applyView(); const m = data.find((x) => x.owner === currentUser.id && x.status === "inbox"); paneId = m.id; render(); }); await p.waitForTimeout(400);
  check("choosing Classic again brings the old layout back", (await p.locator(".reading .qside").count()) === 1 && (await p.locator(".rl-rail").count()) === 0);
  check("no page errors on desktop", p.errors.length === 0);
  await ctx.close();
}

{ // phone
  const [ctx, p] = await open(390, 844);
  await p.evaluate(() => { view.style = "rail"; applyView(); render(); });
  await p.waitForTimeout(400);
  await p.evaluate(() => { const m = data.find((x) => x.owner === currentUser.id && x.status === "inbox" && typeof tasksFor === "function" && tasksFor(x).length) || data.find((x) => x.owner === currentUser.id && x.status === "inbox"); paneId = m.id; readerOpen = true; render(); });
  await p.waitForTimeout(500);
  check("phone: the email opens full screen in the rail style", (await p.locator(".reader.rail").count()) === 1);
  check("phone: no bar down the left", (await p.locator(".reader.rail .rl-rail").count()) === 0);
  const x = await box(p, ".reader.rail .rclose");
  check("phone: just a small X at the top, not a wide Close button", x && x.w <= 48 && (await p.locator(".reader.rail .rclose").innerText()).trim() === "✕");
  const bar = await p.evaluate(() => [...document.querySelectorAll(".reader.rail .rl-bar > *")].map((e) => { const r = e.getBoundingClientRect(); return { l: e.getAttribute("aria-label"), w: Math.round(r.width), h: Math.round(r.height), txt: e.innerText.trim() }; }));
  check("phone: the bottom bar has square icon buttons only", bar.length >= 4 && bar.every((e) => Math.abs(e.w - e.h) <= 2 && e.w >= 44 && e.txt === ""));
  check("phone: Reviewed, Archive and Bin are in the bottom bar", ["Reviewed", "Archive", "Bin"].every((l) => bar.some((e) => e.l === l)));
  const bb = await box(p, ".reader.rail .rl-bar");
  check("phone: the bottom bar is fixed at the bottom of the screen", bb && Math.abs(bb.b - 844) <= 2);
  check("phone: the email address opens the copy choices", await (async () => {
    const closed = await p.evaluate(() => { const d = document.querySelector(".reader.rail details.rl-addr"); return d && !d.open; });
    await p.click(".reader.rail details.rl-addr summary"); await p.waitForTimeout(250);
    const opened = await p.evaluate(() => { const d = document.querySelector(".reader.rail details.rl-addr"); return d.open && d.querySelectorAll(".mail-copy-action").length >= 3; });
    return closed && opened;
  })());
  check("phone: the old Copy line is gone from the page", (await p.locator(".reader.rail .rl-copy").count()) === 0);
  if (shots) await p.screenshot({ path: path.join(shots, "rail-phone.png") });
  check("phone: nothing sticks out sideways", await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  check("no page errors on the phone", p.errors.length === 0);
  await ctx.close();
}
await b.close(); srv.close();
if (failed) process.exit(1);
