// Browser check for picking several emails on a phone: press and hold an email for about half a second, tick boxes appear
// on the left (the emails shift right), tap more emails, then Reviewed / Archive / Bin, or Done to leave.
// Uses the demo build (made-up mail, no server). Usage: node scripts/check_phone_select.mjs      Set SHOTS=<folder> to save screenshots.
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


const hold = async (p, loc, ms = 650) => { const bx = await loc.boundingBox(); await p.mouse.move(bx.x + bx.width / 2, bx.y + 20); await p.mouse.down(); await p.waitForTimeout(ms); await p.mouse.up(); await p.waitForTimeout(250); };
const again = async () => { await p_.reload(); await p_.waitForTimeout(1200); await p_.evaluate(() => { const base = data.filter((m) => m.status === "inbox" && !m.kept); let id = 9100; while (data.filter((m) => m.status === "inbox" && !m.kept && !m._pending).length < 5) data.push({ ...base[0], id: ++id, subject: "Another made-up email " + id, sender: "Example Sender " + id }); render(); }); await p_.waitForTimeout(300); };
let p_;
const open = async (theme, vp, calm = "0") => {
  const ctx = await b.newContext({ viewport: vp, deviceScaleFactor: 2 });
  await ctx.addInitScript((t) => { try { localStorage.setItem("enveliq-theme", t[0]); localStorage.setItem("enveliq-calm", t[1]); localStorage.setItem("enveliq-welcome-seen", "1"); } catch {} }, [theme, calm]);
  const p = await ctx.newPage(); p_ = p; p.errors = []; p.on("pageerror", (e) => p.errors.push(String(e)));
  await p.goto(origin + "/"); await p.waitForTimeout(1200); await p.evaluate(() => { const base = data.filter((m) => m.status === "inbox" && !m.kept); let id = 9000; while (data.filter((m) => m.status === "inbox" && !m.kept && !m._pending).length < 5) { const c = { ...base[0], id: ++id, subject: "Another made-up email " + id, sender: "Example Sender " + id }; data.push(c); } render(); }); await p.waitForTimeout(300); return [ctx, p];
};
for (const theme of ["dark", "light"]) {
  const [ctx, p] = await open(theme, { width: 390, height: 844 });
  const rows = p.locator("article.mail.quiet");
  const n = await rows.count();
  check(theme + ": there are emails to try", n >= 3);
  check(theme + ": no tick boxes are showing to begin with", await p.evaluate(() => getComputedStyle(document.querySelector(".mail.quiet .check")).display === "none"));
  const x0 = await rows.nth(1).locator(".sender").evaluate((e) => e.getBoundingClientRect().left);
  // a quick tap must not start picking
  await rows.nth(1).locator(".qmain").click(); await p.waitForTimeout(200);
  check(theme + ": a quick tap does not start picking", !(await p.evaluate(() => document.body.classList.contains("selecting"))));
  check(theme + ": a quick tap still opens the email as before", (await p.locator("article.mail.quiet.open").count()) === 1);
  await again();
  // too short a hold
  await again();
  await hold(p, rows.nth(1), 250);
  check(theme + ": a short press does not start picking", !(await p.evaluate(() => document.body.classList.contains("selecting"))));
  await again();
  // a real hold
  await p.evaluate(() => window.scrollTo(0, 0));
  await hold(p, rows.nth(1));
  check(theme + ": holding an email starts picking", await p.evaluate(() => document.body.classList.contains("selecting")));
  const vis = await p.evaluate(() => [...document.querySelectorAll(".mail.quiet:not(.kept) .check")].filter((c) => c.offsetParent && c.getBoundingClientRect().width > 10).length);
  check(theme + ": a tick box appears beside every email (" + vis + ")", vis >= 3);
  const x1 = await rows.nth(1).locator(".sender").evaluate((e) => e.getBoundingClientRect().left);
  check(theme + ": the emails move to the right to make room", x1 > x0 + 20);
  check(theme + ": the held email is ticked", await rows.nth(1).locator(".check").isChecked());
  check(theme + ": the held email did not open", !(await rows.nth(1).evaluate((e) => e.classList.contains("open"))));
  const bar = await p.evaluate(() => { const r = document.querySelector("#previewBulk").getBoundingClientRect(), h = document.querySelector("#previewListHeading").getBoundingClientRect(); return { show: getComputedStyle(document.querySelector("#previewBulk")).display !== "none", inside: r.top >= h.top && r.bottom <= h.bottom + 1, below: r.top > h.top + 30, n: document.querySelector("#previewSelCount").textContent, scrollW: document.documentElement.scrollWidth, iw: innerWidth }; });
  check(theme + ": the buttons sit under the Recent emails title, inside that panel", bar.show && bar.inside && bar.below);
  check(theme + ": it says 1 selected", bar.n === "1");
  check(theme + ": no sideways scrolling", bar.scrollW <= bar.iw);
  if (shots) await p.screenshot({ path: path.join(shots, `phone-select-${theme}-1.png`) });
  // tapping other emails ticks them without opening
  await rows.nth(2).locator(".qmain").click(); await p.waitForTimeout(200);
  await rows.nth(0).locator(".sender").click(); await p.waitForTimeout(200);
  check(theme + ": tapping more emails ticks them", (await p.locator("#previewSelCount").textContent()) === "3");
  check(theme + ": tapping does not open emails", (await p.locator("article.mail.quiet.open").count()) === 0);
  if (shots) await p.screenshot({ path: path.join(shots, `phone-select-${theme}-3.png`) });
  // tapping a ticked email unticks it
  await rows.nth(0).locator(".sender").click(); await p.waitForTimeout(200);
  check(theme + ": tapping a ticked email unticks it", (await p.locator("#previewSelCount").textContent()) === "2");
  // Done leaves picking
  await p.locator("#previewBulkClear").click(); await p.waitForTimeout(250);
  check(theme + ": Clear leaves picking and clears the ticks", !(await p.evaluate(() => document.body.classList.contains("selecting"))) && (await p.locator("article.mail.quiet.selected").count()) === 0);
  check(theme + ": the emails move back", Math.abs((await rows.nth(1).locator(".sender").evaluate((e) => e.getBoundingClientRect().left)) - x0) < 2);
  // a bulk action
  await hold(p, rows.nth(0)); await rows.nth(1).locator(".qmain").click(); await p.waitForTimeout(150);
  const before = await p.locator("article.mail.quiet").count(); 
  await p.locator('#previewBulk [data-bulk="archived"]').click(); await p.waitForTimeout(400);
  const after = await p.evaluate(() => ({ sel: document.body.classList.contains("selecting"), leaving: document.querySelectorAll("article.mail.quiet.leaving").length, rows: document.querySelectorAll("article.mail.quiet").length }));
  console.log("after archive:", JSON.stringify(after), "before:", before);
  check(theme + ": Archive leaves picking and sends both emails away", !after.sel && (after.leaving === 2 || after.rows === before - 2));
  // an Undo bar can be swiped away when it is in the way
  {
    const bb = await p.locator(".undobar").first().boundingBox();
    const drag = async (dx) => { await p.mouse.move(bb.x + bb.width / 2, bb.y + 15); await p.mouse.down(); await p.mouse.move(bb.x + bb.width / 2 + dx / 2, bb.y + 15, { steps: 4 }); await p.mouse.move(bb.x + bb.width / 2 + dx, bb.y + 15, { steps: 4 }); await p.mouse.up(); await p.waitForTimeout(450); };
    await drag(30);
    check(theme + ": a short swipe on the Undo bar springs back", (await p.locator(".undobar").count()) === 1 && await p.evaluate(() => pendingActs.length === 1));
    await drag(-170);
    check(theme + ": swiping the Undo bar away clears it", (await p.locator(".undobar").count()) === 0 && await p.evaluate(() => pendingActs.length === 0));
  }
  // unticking the last email leaves picking too
  await p.waitForTimeout(300);
  const r2 = p.locator("article.mail.quiet:not(.leaving)");
  await hold(p, r2.nth(0)); await r2.nth(0).locator(".sender").click(); await p.waitForTimeout(250);
  check(theme + ": unticking the last email leaves picking", !(await p.evaluate(() => document.body.classList.contains("selecting"))));
  check(theme + ": no script errors", p.errors.length === 0);
  await ctx.close();
}
// the AI queue bar can be swiped out of the way, and the work carries on
{
  const [ctx, p] = await open("dark", { width: 390, height: 844 });
  await p.evaluate(() => { sq = { waiting: 1, writing: 1, new_mail: 0, items: [] }; paintSumBar(); });
  const shown = () => p.evaluate(() => !document.querySelector("#sumBar").hidden && !!document.querySelector("#sumBar .sumrow"));
  check("AI queue bar: it shows while the AI is working", await shown());
  const drag = async (dx) => { const bb = await p.locator("#sumBar .sumrow").boundingBox(); await p.mouse.move(bb.x + bb.width / 2, bb.y + 12); await p.mouse.down(); await p.mouse.move(bb.x + bb.width / 2 + dx / 2, bb.y + 12, { steps: 4 }); await p.mouse.move(bb.x + bb.width / 2 + dx, bb.y + 12, { steps: 4 }); await p.mouse.up(); await p.waitForTimeout(450); };
  await drag(30);
  check("AI queue bar: a short swipe springs back", await shown());
  await drag(150);
  check("AI queue bar: swiping it away hides it", !(await shown()));
  await p.evaluate(() => paintSumBar());
  check("AI queue bar: it stays hidden while the AI is still working", !(await shown()) && await p.evaluate(() => sq.writing === 1));
  await p.evaluate(() => { sq = { waiting: 0, writing: 0, new_mail: 0, items: [] }; paintSumBar(); sq = { waiting: 2, writing: 0, new_mail: 0, items: [] }; paintSumBar(); });
  check("AI queue bar: it comes back the next time the AI starts", await shown());
  check("AI queue bar: no script errors", p.errors.length === 0);
  await ctx.close();
}
// a wide screen never shows the phone tick-box mode
{
  const [ctx, p] = await open("dark", { width: 1200, height: 800 });
  const r = p.locator("article.mail.quiet").first(); await hold(p, r);
  check("wide screen: holding does nothing special", !(await p.evaluate(() => document.body.classList.contains("selecting"))));
  await ctx.close();
}
await b.close(); srv.close();
process.exit(failed ? 1 : 0);
