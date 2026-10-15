// Browser check for the Back button: going back (browser or phone) returns to the section you were in, inside Enveliq, instead of leaving it.
// The page is loaded from a pretend Enveliq server (Playwright intercepts the requests), so this needs no Python.
//   node scripts/check_back_button.mjs [path/to/prototype/index.html]     (SHOTS=<dir> saves screenshots)
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const target = path.resolve(process.argv[2] || path.join(here, "..", "prototype", "index.html"));
const html = fs.readFileSync(target, "utf8");
const ORIGIN = "http://enveliq.test";
const SHOTS = process.env.SHOTS;
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
const now = Math.floor(Date.now() / 1000);
const calls = [];
let drafts = [];
let nextId = 1;
const features = { compose: true, address_book: true, sent: true, media: false, all_mail: false, shipping: false, subscriptions: false, travel: false, waiting: false, messages: false, write_help: false };
const messages = [
  { id: "m-cc", subject: "Plan for May", sender_display: "Alice", sender_address: "alice@example.invalid", summary: "A plan to read.", priority: "normal", category: null, action_required: false, received_at: now - 60,
    reply_context: { reply_to: "alice@example.invalid", delivered_to: null, via_alias: null, message_id: "<c@x>", references: [], cc: ["boss@example.invalid", "sam@example.invalid"], also_to: ["dan@example.invalid"] } },
  { id: "m-third", subject: "Third one", sender_display: "Cara", sender_address: "cara@example.invalid", summary: "Another email.", priority: "normal", category: null, action_required: false, received_at: now - 180,
    reply_context: { reply_to: "cara@example.invalid", delivered_to: null, via_alias: null, message_id: "<t@x>", references: [], cc: [], also_to: [] } },
  { id: "m-plain", subject: "Just you", sender_display: "Bob", sender_address: "bob@example.invalid", summary: "Only to you.", priority: "normal", category: null, action_required: false, received_at: now - 120,
    reply_context: { reply_to: "bob@example.invalid", delivered_to: null, via_alias: null, message_id: "<p@x>", references: [], cc: [], also_to: [] } },
];
const handler = async (route) => {
  const req = route.request(), p = new URL(req.url()).pathname;
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
  if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
  if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
  if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
  if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1144, username: "bridge", settings: { smtp_port: 1026, send_identities: [], ai_summaries: true } }]);
  if (p === "/api/v1/accounts/a1/messages") return json(200, messages);
  if (/\/messages\/[^/]+\/original$/.test(p)) { await new Promise((r) => setTimeout(r, 700)); return json(200, { subject: "Plan for May", from: { name: "Alice", address: "alice@example.invalid" }, to: [], date: "x", text: "Hello", truncated: false, attachments: [{ index: 0, filename: "plan.pdf", mime_type: "application/pdf", size_bytes: 20480, inline: false }, { index: 1, filename: "logo.png", mime_type: "image/png", size_bytes: 900, inline: true }] }); }
  if (/\/messages\/[^/]+\/(reply|forward)$/.test(p)) { calls.push([p.split("/").pop(), JSON.parse(req.postData())]); return json(200, { sent: true, from: "me@example.invalid" }); }
  if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: { ...features, address_book_auto: true } });
  if (p === "/api/v1/me/drafts" && req.method() === "GET") return json(200, { now: Date.now() / 1000, keep_days: 14, items: [...drafts].reverse() });
  if (p === "/api/v1/me/drafts" && req.method() === "POST") { const b = JSON.parse(req.postData()); const d = { ...b, id: "d" + String(nextId++).padStart(16, "0"), created: Date.now() / 1000, updated: Date.now() / 1000, expires: Date.now() / 1000 + 14 * 86400 }; drafts.push(d); calls.push(["draft-new", b]); return json(201, d); }
  const dm = p.match(/^\/api\/v1\/me\/drafts\/(d[0-9]+)$/);
  if (dm && req.method() === "PUT") { const b = JSON.parse(req.postData()); const i = drafts.findIndex((x) => x.id === dm[1]); if (i < 0) return json(404, { detail: "That draft is not there any more." }); drafts[i] = { ...drafts[i], ...b, updated: Date.now() / 1000 }; calls.push(["draft-put", b]); return json(200, drafts[i]); }
  if (dm && req.method() === "DELETE") { drafts = drafts.filter((x) => x.id !== dm[1]); calls.push(["draft-del", dm[1]]); return route.fulfill({ status: 204 }); }
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "" });
  if (p === "/api/v1/me/contacts") return json(200, { items: [] });
  if (p === "/api/v1/me/tasks") return json(200, { today: "2026-10-14", tz: "UTC", now: Date.now() / 1000, tasks: [] });
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: {} });
  return json(404, { detail: "not found" });
};

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1300, height: 900 } });
await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
await context.route(`${ORIGIN}/**`, handler);
await page.goto(`${ORIGIN}/`);
await page.waitForSelector("article.mail");
await page.evaluate(() => { window.__alive = 1; });
const active = () => page.evaluate(() => document.querySelector(".nav[data-filter].active")?.dataset.filter);
const hash = () => page.evaluate(() => location.hash);
const alive = () => page.evaluate(() => window.__alive === 1);
const go = async (f) => {
  const item = page.locator(`.nav[data-filter="${f}"]`).first();
  if (!(await item.isVisible())) { await page.locator("#moreToggle").click(); await page.waitForTimeout(250); }      // Reviewed and Archived live under "More"
  await item.click();
};

check("it starts in the inbox", (await active()) === "all" && (await hash()) === "");
await go("reviewed");
check("opening Reviewed names it in the address", (await active()) === "reviewed" && (await hash()) === "#/reviewed");
await go("archived");
check("opening Archived names it in the address", (await active()) === "archived" && (await hash()) === "#/archived");
await go("tasks");
check("opening Tasks names it in the address", (await active()) === "tasks" && (await hash()) === "#/tasks");

await page.goBack();
await page.waitForTimeout(250);
check("Back from Tasks returns to Archived, still inside Enveliq", (await active()) === "archived" && (await hash()) === "#/archived" && (await alive()));
await page.goBack();
await page.waitForTimeout(250);
check("Back again returns to Reviewed", (await active()) === "reviewed" && (await hash()) === "#/reviewed" && (await alive()));
await page.goBack();
await page.waitForTimeout(250);
check("Back again returns to the inbox", (await active()) === "all" && (await hash()) === "" && (await alive()));
check("the inbox list is showing again", (await page.locator("article.mail").count()) >= 1);
await page.goForward();
await page.waitForTimeout(250);
check("Forward goes to Reviewed again", (await active()) === "reviewed" && (await hash()) === "#/reviewed" && (await alive()));
await go("archived");
await page.goBack();
await page.waitForTimeout(250);
check("after going somewhere new, Back still returns to the section before it", (await active()) === "reviewed" && (await alive()));

// Settings: opening it adds a step, and Back closes it
await page.evaluate(() => openSettings("settings"));
await page.waitForTimeout(250);
check("Settings names itself in the address", /^#\/settings\//.test(await hash()) && (await page.locator("#settings.open").count()) === 1);
await page.goBack();
await page.waitForTimeout(300);
check("Back closes Settings and returns to the section before it", (await page.locator("#settings.open").count()) === 0 && (await active()) === "reviewed" && (await alive()));

// a phone: an email opens full screen, and Back closes it (back to the list) instead of leaving Enveliq
await page.setViewportSize({ width: 390, height: 800 });
await page.waitForTimeout(200);
await page.locator("#menuBtn").click();
await page.locator('.nav[data-filter="all"]').first().click();
await page.waitForSelector("article.mail");
const before = await page.evaluate(() => history.length);
await page.locator("article.mail").first().locator(".qmain").click();
await page.waitForSelector(".reader");
check("an email opens full screen on a phone", (await page.locator(".reader").count()) === 1);
check("opening it adds one step to the history", (await page.evaluate(() => history.length)) === before + 1);
await page.goBack();
await page.waitForTimeout(300);
check("Back closes the email and shows the list again", (await page.locator(".reader").count()) === 0 && (await page.locator("article.mail").count()) > 0 && (await alive()));
check("the list is still the inbox", (await active()) === "all");
// closing with the Close button leaves nothing behind: Back from the list stays inside Enveliq's own pages
await page.locator("article.mail").first().locator(".qmain").click();
await page.waitForSelector(".reader");
await page.locator("[data-reader-close]").click();
await page.waitForTimeout(300);
check("the Close button closes the email", (await page.locator(".reader").count()) === 0 && (await alive()));
check("closing it leaves no extra step marked as an open email", (await page.evaluate(() => !(history.state && history.state.enveliqReader))));
// opening a second email, then Back twice: closed, and still in the app
await page.locator("article.mail").nth(1).locator(".qmain").click();
await page.waitForSelector(".reader");
await page.goBack();
await page.waitForTimeout(300);
check("Back closes a second email too", (await page.locator(".reader").count()) === 0 && (await alive()));
// Phone menu: Back closes the sidebar without leaving the current view.
await page.locator("#menuBtn").click();
check("mobile menu opens", await page.locator("body.menu-open").count() === 1);
await page.goBack();
await page.waitForTimeout(250);
check("Back closes the mobile menu", await page.locator("body.menu-open").count() === 0 && (await active()) === "all" && (await alive()));
const swipe = async (fromX,toX)=>{
  await page.evaluate(({fromX,toX})=>{
    const make=(type,x)=>new TouchEvent(type,{bubbles:true,cancelable:true,touches:type==="touchend"?[]:[new Touch({identifier:1,target:document.body,clientX:x,clientY:280})],changedTouches:[new Touch({identifier:1,target:document.body,clientX:x,clientY:280})]});
    document.dispatchEvent(make("touchstart",fromX));
    document.dispatchEvent(make("touchend",toX));
  },{fromX,toX});
};
await swipe(8,155);
check("edge swipe opens the sidebar", await page.locator("body.menu-open").count() === 1);
await swipe(220,45);
await page.waitForTimeout(200);
check("left swipe closes the sidebar", await page.locator("body.menu-open").count() === 0 && (await alive()));
check("no script errors", errors.length === 0);
await browser.close();
if (failed) process.exit(1);
