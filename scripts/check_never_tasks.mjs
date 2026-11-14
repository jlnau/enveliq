// Browser check for "Never make tasks from this sender": the three-dot menu entry, the button on a task, the rule that is saved, and the task that goes away.
// The page is loaded from a pretend Enveliq server (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_never_tasks.mjs [path/to/prototype/index.html]
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.resolve(process.argv[2] || path.join(here, "..", "prototype", "index.html")), "utf8");
const ORIGIN = "http://enveliq.test";
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
for (const ev of ["uncaughtException", "unhandledRejection"]) process.on(ev, (e) => { console.log("::error::" + String((e && e.message) || e).split("\n").slice(0, 3).join(" | ")); process.exit(1); });
const features = { compose: true, address_book: true, sent: true, media: true };
const now = Math.floor(Date.now() / 1000);
const ctx = (id, refs = []) => ({ reply_to: "x@example.invalid", delivered_to: null, via_alias: null, message_id: `<${id}@x>`, references: refs });
const base = { summary: "A short summary.", priority: "normal", category: "Information", action_required: false, state: "unread", snoozed_until: null };
const make = () => [
  { ...base, id: "m-a", subject: "Trip plans", sender_display: "Alice", sender_address: "alice@example.invalid", received_at: now - 300, reply_context: ctx("a2", ["<a1@x>"]) },
  { ...base, id: "m-b", subject: "Re: Trip plans", sender_display: "Bob", sender_address: "bob@example.invalid", received_at: now - 900, reply_context: ctx("a1") },
  { ...base, id: "m-c", subject: "Electricity bill", sender_display: "Northside Power", sender_address: "bills@example.invalid", received_at: now - 1200, reply_context: ctx("c") },
  { ...base, id: "m-r", subject: "Already read one", sender_display: "Cara", sender_address: "cara@example.invalid", received_at: now - 5000, state: "reviewed", resolved_at: now - 100, reply_context: ctx("r") },
];
let messages, posts, prints, rulePosts, taskList;
const handler = async (route) => {
  const req = route.request(), u = new URL(req.url()), p = u.pathname, m = req.method();
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (u.origin !== ORIGIN) return route.abort();
  if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
  if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
  if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
  if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
  if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1143, username: "me@example.invalid", settings: {} }]);
  if (p === "/api/v1/accounts/a1/messages") return json(200, messages);
  if (p === "/api/v1/me/mail-view") return json(200, m === "GET" ? { view: null } : { view: JSON.parse(req.postData() || "{}") });
  if (/\/api\/v1\/accounts\/a1\/messages\/[^/]+\/(mute|unread|resolve)$/.test(p) && m === "POST") {
    posts.push([p.split("/").pop(), p.split("/")[6], JSON.parse(req.postData() || "{}")]);
    return route.fulfill({ status: p.endsWith("/mute") ? 200 : 204, contentType: "application/json", body: p.endsWith("/mute") ? JSON.stringify({ muted: true, id: "q0123456789abcdef" }) : "" });
  }
  if (p === "/api/v1/me/rules" && m === "POST") { rulePosts.push(JSON.parse(req.postData() || "{}")); return json(200, { rules: [], actions: {}, max: 50 }); }
  if (p === "/api/v1/me/tasks") return json(200, { today: "2026-10-14", tz: "UTC", now: Date.now() / 1000, tasks: taskList });
  if (/^\/api\/v1\/me\/tasks\/t1\/remove$/.test(p) && m === "POST") { taskList = taskList.map((t) => ({ ...t, state: "removed" })); return json(200, { today: "2026-10-14", tz: "UTC", now: Date.now() / 1000, tasks: taskList }); }
  if (p === "/api/v1/me/drafts" && m === "POST") { posts.push(["draft", "", JSON.parse(req.postData() || "{}")]); return json(200, { id: "d0123456789abcdef", items: [] }); }
  if (p === "/api/v1/me/drafts") return json(200, { items: [] });
  if (/\/original$/.test(p)) return json(200, { from: { name: "Alice", address: "alice@example.invalid" }, to: [{ address: "me@example.invalid" }], date: "Today", subject: "Trip plans", text: "Plain words of the original email.", links: [], has_html: false, remote_images: 0, attachments: [], truncated: false });
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
  if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features });
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: now } } });
  return json(404, { detail: "not found" });
};
const browser = await chromium.launch();
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };
async function open(width, height = 900) {
  messages = make(); posts = []; prints = 0; rulePosts = [];
  taskList = [{ id: "t1", account_id: "a1", message_id: "m-c", title: "Pay the electricity bill", detail: "", sender: "Northside Power", priority: "normal", received: now - 1200, due: "2026-10-14", remind_at: null, state: "open", reason: null, closed_at: null }];
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-calm", "0"); } catch (e) {} window.print = () => { window.__prints = (window.__prints || 0) + 1; window.__printDoc = !!document.getElementById("printDoc") && document.getElementById("printDoc").textContent.includes("Plain words"); dispatchEvent(new Event("beforeprint")); setTimeout(() => dispatchEvent(new Event("afterprint")), 700); }; });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route("**/*", handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  await page.waitForTimeout(300);
  return { page, errors, context };
}
const pick = async (page, title) => { if (await page.locator(".qmore").first().isVisible().catch(() => false)) return; await page.locator("article.mail", { hasText: title }).locator(".qmain, .qtoggle").first().click(); await page.waitForSelector(".qmore"); };

for (const width of [1200, 390]) {
  const tag = width + "px wide: ";
  const { page, errors, context } = await open(width);
  await pick(page, "Electricity bill");
  await page.locator(".qmore").first().click();
  const menu = page.locator("#moreMenu");
  const items = (await menu.locator("[role=menuitem]").allInnerTexts()).join("|");
  check(tag + "the three-dot menu has one Mail rules entry", items.includes("Mail rules for this sender"));
  await menu.locator("[data-rules-open]").click();
  const sub = (await menu.locator("[role=menuitem]").allInnerTexts()).join("|");
  check(tag + "it opens the rules list in the same pop-up, with a Back entry", await menu.isVisible() && sub.includes("Back") && sub.includes("Never make tasks from this sender") && sub.includes("Always archive these") && sub.includes("Always mark these as read") && sub.includes("Block sender") && sub.includes("See all my mail rules"));
  await shot(page, "rules-popup-" + width);
  await menu.locator("[data-rules-back]").click();
  check(tag + "Back returns to the main menu", (await menu.locator("[role=menuitem]").allInnerTexts()).join("|").includes("Reply"));
  await menu.locator("[data-rules-open]").click();
  await menu.locator("[data-notask]").click();
  await page.waitForTimeout(400);
  check(tag + "a never-make-tasks rule is saved for that sender", rulePosts.length === 1 && rulePosts[0].action === "notasks" && rulePosts[0].sender === "bills@example.invalid" && rulePosts[0].subject === "");
  check(tag + "the open task for that email is removed", taskList[0].state === "removed");
  check(tag + "it says what happened in plain words", /will not make tasks/.test(await page.locator("body").innerText()));
  await shot(page, "never-tasks-" + width);
  check(tag + "no page errors", errors.length === 0);
  await context.close();
}
for (const width of [1200, 390]) {
  const tag = width + "px wide: ";
  const { page, errors, context } = await open(width);
  await pick(page, "Electricity bill");
  await page.waitForTimeout(300);
  const btn = page.locator(".taskline [data-notask]").first();
  check(tag + "the task card on the email has a No tasks from this sender button", (await btn.count()) === 1 && await btn.isVisible());
  await shot(page, "never-tasks-card-" + width);
  await btn.click();
  await page.waitForTimeout(400);
  check(tag + "pressing it saves the rule and removes the task", rulePosts.length === 1 && rulePosts[0].action === "notasks" && taskList[0].state === "removed");
  check(tag + "no page errors", errors.length === 0);
  await context.close();
}
for (const width of [1200, 390]) {
  const tag = width + "px wide: ";
  const { page, errors, context } = await open(width);
  await pick(page, "Electricity bill");
  await page.waitForTimeout(300);
  const dots = page.locator(".taskline [data-rules-menu]").first();
  check(tag + "the task card has a vertical three-dot rules button", (await dots.count()) === 1 && await dots.isVisible());
  await dots.click();
  const menu = page.locator("#moreMenu");
  const items = (await menu.locator("[role=menuitem]").allInnerTexts()).join("|");
  check(tag + "it offers the usual rules: never make tasks, archive, mark reviewed, block sender, and all my rules", ["Never make tasks from this sender", "Always archive these", "Always mark these as read", "Block sender", "See all my mail rules"].every((t) => items.includes(t)));
  await shot(page, "rules-menu-" + width);
  await menu.locator("[data-rule-reviewed]").click();
  await page.waitForTimeout(400);
  check(tag + "Always mark as reviewed saves a reviewed rule for that sender", rulePosts.length === 1 && rulePosts[0].action === "reviewed" && rulePosts[0].sender === "bills@example.invalid");
  await dots.click();
  await page.locator("#moreMenu [data-rule]").click();
  await page.waitForTimeout(400);
  check(tag + "Always archive these saves an archive rule", rulePosts.length === 2 && rulePosts[1].action === "archived");
  check(tag + "no page errors", errors.length === 0);
  await context.close();
}
await browser.close();
if (failed) process.exit(1);
