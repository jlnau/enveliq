// Browser check: ticking one email's box and then Shift + ticking another ticks every email between them, going down
// or up the list. The pages are served from the real files; the server is pretended (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_shift_select.mjs [path/to/prototype/index.html]
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
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
  if (p === "/api/v1/me/features") return json(200, { effective: {}, admin: {}, user: {}, labels: {} });
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: now } } });
  if (p === "/api/v1/me/summary-queue") return json(200, queue);
  return json(404, { detail: "not found" });
};

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1200, height: 900 } });
await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
await context.route("**/*", handler);
await page.goto(`${ORIGIN}/`);
await page.waitForSelector("article.mail");

const boxes = () => page.locator("input[data-select]");
const ticked = async () => (await boxes().evaluateAll((els) => els.map((e, i) => (e.checked ? i + 1 : 0)).filter(Boolean))).join(",");
const tick = (n, shift = false) => boxes().nth(n - 1).click({ modifiers: shift ? ["Shift"] : [] });
const subjects = await page.locator("article.mail .subject").allInnerTexts();
check("the inbox shows the seven emails", subjects.length === 7);

await tick(2);
check("a plain tick selects just that email", (await ticked()) === "2");
await tick(5, true);
check("Shift + tick further down selects every email between, both ends included", (await ticked()) === "2,3,4,5");
await tick(7, true);
check("Shift + tick again carries on from the one ticked last", (await ticked()) === "2,3,4,5,6,7");

await page.locator("#clear").click();
check("Clear selection empties it", (await ticked()) === "");
await tick(6);
await tick(3, true);
check("Shift + tick further up works too", (await ticked()) === "3,4,5,6");
await tick(1);
check("a plain tick adds only that email and moves the starting point", (await ticked()) === "1,3,4,5,6");

await tick(4);   // untick 4 (now the starting point)
check("unticking one email unticks only it", (await ticked()) === "1,3,5,6");
await tick(6, true);
check("Shift + untick clears the emails between, not just the ends", (await ticked()) === "1,3");

await page.locator("#clear").click();
await tick(4, true);
check("Shift + tick with nothing ticked before acts like a plain tick", (await ticked()) === "4");
check("the bulk bar shows when several are selected", await (async () => { await tick(6, true); return (await page.locator("#bulk.show").count()) === 1; })());

// ---- Select all ----
await page.locator("#clear").click();
const all = page.locator("#selectAll");
check("a Select all control sits above the list", await all.isVisible() && (await page.locator("#selectAllWrap").innerText()).includes("Select all"));
check("it starts unticked", !(await all.isChecked()));
await all.check();
check("Select all ticks every email in the list", (await ticked()) === "1,2,3,4,5,6,7" && (await page.locator("#selectedCount").innerText()) === "7");
check("the bulk bar shows with all of them selected", (await page.locator("#bulk.show").count()) === 1);
await all.uncheck();
check("unticking Select all clears the list", (await ticked()) === "");
await tick(2);
check("with some ticked it shows as partly ticked", await all.evaluate((e) => e.indeterminate && !e.checked));
await all.check();
check("Select all completes a partial selection", (await ticked()) === "1,2,3,4,5,6,7");
await tick(3);
check("unticking one email takes the tick off Select all", !(await all.isChecked()) && (await ticked()) === "1,2,4,5,6,7");
await tick(7, true);
check("Shift unticking a run still works after Select all", (await ticked()) === "1,2");
await page.locator("#clear").click();
check("Clear empties a Select all", (await ticked()) === "" && !(await all.isChecked()));
// An AI summary finishing reloads the list in the background. The emails you ticked stay ticked.
await tick(2); await tick(3, true);
check("two emails are ticked before the summary finishes", (await ticked()) === "2,3");
queue = { items: [{ account_id: "a1", message_id: "m1", state: "done" }], waiting: 0, writing: 0 };
await page.evaluate(() => pollSummaries(false));
await page.waitForTimeout(600);
check("a finished AI summary does not untick the emails", (await ticked()) === "2,3" && (await page.locator("#selectedCount").innerText()) === "2");
await all.check();
await page.locator('#bulk [data-bulk="reviewed"]').click();
await page.waitForFunction(() => document.querySelectorAll("article.mail.leaving").length === 7, null, { timeout: 15000 });
check("the bulk Reviewed button acts on every email a Select all ticked", true);
check("no script errors", errors.length === 0);
if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, "shift-select.png") });

// ---- the same on a phone ----
{
  const pc = await browser.newContext({ viewport: { width: 390, height: 780 }, hasTouch: true, isMobile: true });
  await pc.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
  const pp = await pc.newPage();
  await pc.route("**/*", handler);
  await pp.goto(`${ORIGIN}/`);
  await pp.waitForSelector("article.mail");
  const sa = pp.locator("#selectAll");
  check("on a phone Select all is there and easy to press", await sa.isVisible() && (await pp.locator("#selectAllWrap").boundingBox()).height >= 30);
  await pp.locator("#selectAllWrap").tap();
  check("on a phone Select all ticks every email", (await pp.locator("input[data-select]:checked").count()) === 7);
  check("on a phone nothing scrolls sideways", await pp.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  if (process.env.SHOTS) await pp.screenshot({ path: path.join(process.env.SHOTS, "select-all-phone.png") });
  await pc.close();
}
await browser.close();
if (failed) process.exit(1);
console.log("All Shift-select checks passed.");
