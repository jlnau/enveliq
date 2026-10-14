// Browser check for moving around: a "Back to My inbox" button on every other page, Inbox options on Needs action and the other email pages,
// and the full-screen email sitting beside the left menu with normal-sized buttons.
// Uses the demo build (made-up mail, no server).
// Usage: node scripts/check_back_to_inbox.mjs      Set SHOTS=<folder> to save screenshots.
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


const ctx = await b.newContext({ viewport: { width: 1600, height: 900 } });
await ctx.addInitScript(() => { try { localStorage.setItem("enveliq-calm", "0"); localStorage.setItem("enveliq-welcome-seen", "1"); } catch {} });
const p = await ctx.newPage(); const errors = []; p.on("pageerror", (e) => errors.push(String(e)));
await p.goto(origin + "/"); await p.waitForTimeout(1200);
await p.evaluate(() => document.querySelector(".demo-banner")?.remove());
const vis = (sel) => p.locator(sel).isVisible();
check("My inbox: there is no Back button", !(await vis("#backInbox")) && (await p.locator(".top-left h2").innerText()) === "My inbox");
await p.click('.nav[data-filter="action"]'); await p.waitForTimeout(300);
check("Needs action: the title is the page name and a Back to My inbox button shows above it", (await p.locator(".top-left h2").innerText()) === "Needs action" && await vis("#backInbox") && /Back to My inbox/.test(await p.locator("#backInbox").innerText()) && await p.evaluate(() => document.getElementById("backInbox").getBoundingClientRect().bottom <= document.querySelector(".top-left h2").getBoundingClientRect().top + 2));
check("Needs action: the Recent emails panel with Inbox options shows, same as My inbox", await vis("#previewListHeading") && await vis("#previewInboxOptions"));
await p.click("#previewInboxOptions"); await p.waitForTimeout(200);
check("Needs action: Inbox options opens the filters and closes again", await vis(".filters") && (await p.locator("#previewInboxOptions").getAttribute("aria-expanded")) === "true");
await p.click("#previewInboxOptions"); await p.waitForTimeout(200);
check("Needs action: Inbox options closes", !(await vis(".filters")));
await p.click('.nav[data-filter="tasks"]'); await p.waitForTimeout(300);
check("Tasks: the title is Tasks and the Back button shows", (await p.locator(".top-left h2").innerText()) === "Tasks" && await vis("#backInbox") && !(await vis("#previewListHeading")));
await p.evaluate(() => { document.querySelector("[data-view-list], [data-tview=list]")?.click(); });
check("Tasks: the lists use the full width of the page, not a narrow column", await p.evaluate(() => { const g = document.querySelector("#tasksPage .tgroup, #tasksPage .tp-head"), page = document.querySelector("#tasksPage"); return !g || g.getBoundingClientRect().width > page.getBoundingClientRect().width * 0.9; }));
if (shots) await p.screenshot({ path: path.join(shots, "back-tasks.png") });
await p.click("#backInbox"); await p.waitForTimeout(300);
check("Back to My inbox goes home and lights up My inbox in the menu", (await p.locator(".top-left h2").innerText()) === "My inbox" && !(await vis("#backInbox")) && (await p.locator('.nav[data-filter="all"].active').count()) === 1);
await p.evaluate(() => { document.getElementById("sentNav").hidden = false; });
await p.click('.nav[data-filter="sent"]'); await p.waitForTimeout(400);
check("Sent: the Back to My inbox button shows above the title, like the other pages", await vis("#sentBack") && /Back to My inbox/.test(await p.locator("#sentBack").innerText()) && await vis("#sentView h2"));
if (shots) await p.screenshot({ path: path.join(shots, "back-sent.png") });
await p.click("#sentBack"); await p.waitForTimeout(300);
check("Sent: Back to My inbox goes home and lights up My inbox in the menu", (await p.locator(".top-left h2").innerText()) === "My inbox" && !(await vis("#sentView")) && (await p.locator('.nav[data-filter="all"].active').count()) === 1);
check("The Settings icon in the left menu is the same cogwheel as in the name menu (not a sun)", await p.evaluate(() => document.querySelector("#sideSettings svg").innerHTML.replace(/\s+/g, "") === document.querySelector("#settingsBtn svg").innerHTML.replace(/\s+/g, "")));
// Open full screen
await p.evaluate(() => { view.layout = "screen"; readerOpen = true; render(); });
await p.waitForTimeout(300);
const geo = await p.evaluate(() => { const r = document.querySelector(".reader").getBoundingClientRect(), sb = document.querySelector(".sidebar").getBoundingClientRect(), tb = document.querySelector(".preview-toolbar").getBoundingClientRect(), a = document.querySelector(".ract").getBoundingClientRect(), bs = [...document.querySelectorAll(".ract .action")].map((x) => x.getBoundingClientRect()); return { rl: r.left, rt: r.top, sbr: sb.right, tbb: tb.bottom, aw: a.width, bw: bs.map((x) => x.width), bl: Math.min(...bs.map((x) => x.left)), br: Math.max(...bs.map((x) => x.right)), h: bs.map((x) => x.height) }; });
check("Full screen: the email sits beside the left menu and below the top bar", geo.rl >= geo.sbr - 1 && geo.rt >= geo.tbb - 1);
check("Full screen: Reviewed, Archive and Bin are normal buttons, fully visible and not stretched across the screen", geo.bw.length >= 2 && geo.bw.every((w) => w < 260) && geo.bl >= geo.sbr && geo.h.every((h) => h <= 48));
if (shots) await p.screenshot({ path: path.join(shots, "full-screen.png") });
check("no page errors", errors.length === 0);
await b.close(); srv.close();
if (failed) process.exit(1);
console.log("Back-to-inbox check passed.");
