// Browser check: View panel, Reading, "Show the original email". The original sits in the reading panel between the Reply row and the
// email details, scrolls by itself, and stays put when the page redraws. The server is pretended (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_original_inline.mjs [path/to/prototype/index.html]
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, "..");
const html = fs.readFileSync(path.resolve(process.argv[2] || path.join(root, "prototype", "index.html")), "utf8");
const css = fs.readFileSync(path.join(root, "web", "static", "auth.css"), "utf8");
const embed = ["welcome.js", "auth.js"].map((n) => fs.readFileSync(path.join(root, "web", "static", n), "utf8")).join("\n");
const ORIGIN = "http://enveliq.test";
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
for (const ev of ["uncaughtException", "unhandledRejection"]) process.on(ev, (e) => { console.log("::error::" + String((e && e.message) || e).split("\n").slice(0, 3).join(" | ")); process.exit(1); });
const now = Math.floor(Date.now() / 1000);

const mails = [1, 2, 3, 4, 5, 6, 7].map((n) => ({ id: "m" + n, subject: "Email number " + n, sender_display: "Sender " + n, sender_address: `s${n}@example.invalid`, summary: "Summary " + n, priority: "normal", category: null, action_required: false, received_at: now - n * 60, reply_context: { reply_to: `s${n}@example.invalid`, delivered_to: null, via_alias: null, message_id: `<m${n}@x>`, references: [] } }));
let queue = { items: [], waiting: 0, writing: 0 };
const puts = [];
let serverView = null;
let originalFetches = 0, framesServed = 0;
const handler = async (route) => {
  const req = route.request(), u = new URL(req.url()), p = u.pathname;
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (u.origin !== ORIGIN) return route.fulfill({ status: 200, contentType: "text/html", body: "<title>elsewhere</title>" });
  if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
  if (p === "/static/auth.css") return route.fulfill({ status: 200, contentType: "text/css", body: css });
  if (p === "/embed.js") return route.fulfill({ status: 200, contentType: "text/javascript", body: embed });
  if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
  if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
  if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin", session: { state: "full" }, security: { totp_enabled: true, passkeys: [] } });
  if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1144, username: "u", settings: {} }]);
  if (p === "/api/v1/accounts/a1/messages") return json(200, mails);
  if (p === "/api/v1/me/mail-view") { if (req.method() === "PUT") { puts.push(JSON.parse(req.postData())); return json(200, { view: puts[puts.length - 1] }); } return json(200, { view: serverView }); }
  if (p === "/api/v1/accounts/a1/messages/m1/original") { originalFetches++; return json(200, { from: { name: "Sender 1", address: "s1@example.invalid" }, to: [{ address: "me@example.invalid" }], date: "Sun 11:24 PM", subject: "Email number 1", text: "Plain words of the original email.", links: [], has_html: true, remote_images: 0, attachments: [], truncated: false }); }
  if (p === "/api/v1/accounts/a1/messages/m1/original/html") { framesServed++; return route.fulfill({ status: 200, contentType: "text/html", body: "<!doctype html><body style='margin:0'><div style='height:1600px;font:14px Arial'>The original email, sent as the sender made it.</div><script>parent.postMessage({enveliq:'height',height:1600},'*')</script></body>" }); }
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
  if (p === "/api/v1/me/features") return json(200, { effective: {}, admin: {}, user: {}, labels: {} });
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: now } } });
  if (p === "/api/v1/me/summary-queue") return json(200, queue);
  return json(404, { detail: "not found" });
};


const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1500, height: 950 } });
await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
await context.route("**/*", handler);
await page.goto(`${ORIGIN}/`);
await page.waitForSelector("article.mail");
await page.locator("article.mail .qmain").first().click();
await page.waitForSelector(".reading .qdetail");
check("by default no original email is shown in the reading panel", (await page.locator(".qorig").count()) === 0 && originalFetches === 0);

await page.locator("#viewTab").click();
check("the View panel has a Show the original email tick box, off to begin with", (await page.locator("#vOrig").count()) === 1 && !(await page.locator("#vOrig").isChecked()));
await page.locator("#vOrig").check();
await page.waitForSelector(".reading .qorig.live iframe.email-frame");
await page.waitForFunction(() => { const f = document.querySelector(".qorig iframe"); return f && f.offsetHeight >= 1500; }, null, { timeout: 10000 });
check("the choice is saved", puts.length > 0 && puts[puts.length - 1].show_original === true);
check("the original email shows in the reading panel", (await page.locator(".reading .qorig").count()) === 1 && (await page.locator(".qorig .fmt-tab").count()) === 2);
const order = await page.evaluate(() => {
  const q = (s) => document.querySelector(".reading " + s);
  const before = (a, b) => !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
  const summary = q(".qsummary"), foot = q(".qfoot"), orig = q(".qorig"), side = q(".qside");
  return { summaryFoot: before(summary, foot), footOrig: before(foot, orig), origSide: before(orig, side) };
});
check("the Reply buttons sit under the AI summary", order.summaryFoot);
check("the original email sits under the Reply buttons", order.footOrig);
check("the email details are shuffled down below the original email", order.origSide);
const scroll = await page.locator(".qorig").evaluate((e) => ({ h: e.clientHeight, s: e.scrollHeight, o: getComputedStyle(e).overflowY }));
check("the original email has its own scroll and is as long as the email is", scroll.o === "auto" && scroll.s > scroll.h + 500);
await page.locator(".qorig").evaluate((e) => { e.scrollTop = 400; });
await page.evaluate(() => { document.querySelector(".qorig iframe").dataset.mark = "same"; });
const fetchesBefore = originalFetches, framesBefore = framesServed;
await page.evaluate(() => render());
await page.waitForTimeout(400);
check("a redraw of the page does not reload the email or lose its place", (await page.locator(".qorig iframe").getAttribute("data-mark")) === "same" && (await page.locator(".qorig").evaluate((e) => e.scrollTop)) === 400 && originalFetches === fetchesBefore && framesServed === framesBefore);
await page.locator("#viewTab").click({ force: true }).catch(() => {});
await page.keyboard.press("Escape");
await page.locator("article.mail .qmain").nth(1).click();
await page.waitForFunction(() => document.querySelector(".reading .rhead h3")?.textContent === "Email number 2");
await page.waitForFunction(() => document.querySelector(".reading .qorig")?.dataset.state === "error");
check("an email whose original cannot be opened shows a plain message, not a blank box", (await page.locator(".reading .qorig .qorig-wait").innerText()).length > 5);
if (process.env.SHOTS) { await page.locator("article.mail .qmain").first().click(); await page.waitForTimeout(800); await page.screenshot({ path: path.join(process.env.SHOTS, "original-inline.png") }); }

await page.locator("#viewTab").click();
await page.locator("#vOrig").uncheck();
await page.waitForFunction(() => !document.querySelector(".qorig"));
check("untick it and the original email goes away", (await page.locator(".reading .qorig").count()) === 0 && puts[puts.length - 1].show_original === false);
check("no script errors", errors.length === 0);
await context.close();

// ---- the same on a phone ----
{
  serverView = { layout: "screen", density: "standard", width: "centered", rows: "collapsed", peek: true, action_feedback: true, show_original: true };
  const pc = await browser.newContext({ viewport: { width: 390, height: 800 }, isMobile: true, hasTouch: true });
  await pc.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-view", JSON.stringify({ layout: "screen", density: "standard", width: "centered", rows: "collapsed", peek: true, action_feedback: true, show_original: true })); } catch (e) {} });
  const pp = await pc.newPage();
  await pc.route("**/*", handler);
  await pp.goto(`${ORIGIN}/`);
  await pp.waitForSelector("article.mail");
  await pp.locator("article.mail .qmain").first().click();
  await pp.waitForSelector(".reader .qorig.live iframe", { timeout: 15000 });
  check("on a phone the original email shows and nothing scrolls sideways", await pp.evaluate(() => document.documentElement.scrollWidth <= innerWidth) && (await pp.locator(".qorig").boundingBox()).height >= 240);
  await pc.close();
}
await browser.close();
if (failed) process.exit(1);
console.log("All inline original email checks passed.");
