// Browser check for the Tasks page layout: it follows the reading-panel setting, Focus is gone, the Calendar is a full-page pop-up, and the task options work.
// The page is loaded from a pretend Enveliq server (Playwright intercepts the requests), so this needs no Python.
//   node scripts/check_tasks_layout.mjs [path/to/prototype/index.html]     (SHOTS=<dir> saves screenshots)
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
const features = { compose: true, address_book: true, sent: true, media: false, all_mail: false, shipping: false, rss: false, tags: false, subscriptions: false, travel: false, waiting: false, messages: false, write_help: false };
const mk = (id, subject, name, n) => ({ id, subject, sender_display: name, sender_address: name.toLowerCase() + "@example.invalid", summary: "A summary.", priority: "normal", category: null, action_required: false, received_at: now - n,
  reply_context: { reply_to: name.toLowerCase() + "@example.invalid", delivered_to: null, via_alias: null, message_id: "<" + id + "@x>", references: [], cc: [], also_to: [] } });
const t = (n, title, extra = {}) => ({ id: "t" + String(n).padStart(23, "0"), account_id: "a1", message_id: "m-plain", title, detail: "", sender: "Bob", priority: "normal", due: "2026-10-14", days: 0, remind_at: null, state: "open", reason: null, reason_text: "", closed_at: null, received: now - 100, ...extra });
const tasks = [
  t(1, "Ring Brightwater Dental to confirm the check-up", { sender: "Brightwater Dental" }),
  t(2, "Buy a trip insurance policy", { due: "2026-10-20", days: 6, detail: "Cover for the Lisbon trip", sender: "Alice" }),
  t(3, "Send the school form back", { sender: "Westside Primary" }),
  t(4, "Pay the dentist invoice", { state: "done", reason: "done", reason_text: "Done", closed_at: now - 50, sender: "Brightwater Dental" }),
];
const handler = async (route) => {
  const req = route.request(), p = new URL(req.url()).pathname;
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
  if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
  if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
  if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
  if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1144, username: "bridge", settings: { smtp_port: 1026, send_identities: [], ai_summaries: true } }]);
  if (p === "/api/v1/accounts/a1/messages") return json(200, [mk("m-plain", "Just you", "Bob", 120)]);
  if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: { ...features, address_book_auto: true } });
  if (p === "/api/v1/me/drafts") return json(200, { now: Date.now() / 1000, keep_days: 14, items: [] });
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "" });
  if (p === "/api/v1/me/contacts") return json(200, { items: [] });
  if (p === "/api/v1/me/tasks") return json(200, { today: "2026-10-14", tz: "UTC", now: Date.now() / 1000, tasks });
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: {} });
  return json(404, { detail: "not found" });
};
const browser = await chromium.launch();
const run = async (width, height) => {
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-view", JSON.stringify({ layout: "list" })); } catch (e) {} });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route(`${ORIGIN}/**`, handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  return { page, context, errors };
};
const run2 = async (width, height, layout) => {
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript((l) => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-view", JSON.stringify({ layout: l })); localStorage.setItem("enveliq-task-mode", "focus"); } catch (e) {} }, layout);
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route(`${ORIGIN}/**`, handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  return { page, context, errors };
};
const text = (page) => page.locator("#tasksPage").innerText();
{
  const { page, context, errors } = await run2(1400, 900, "right");
  await page.locator('.nav[data-filter="tasks"]').first().click();
  await page.waitForSelector("#taskSearch");
  check("with the reading panel on the right, Tasks has the list on the left and a panel on the right", await page.evaluate(() => document.body.classList.contains("split-read") && !!document.querySelector("#readDock .reading")));
  check("the panel waits for a pick", /Pick a task to read its email/.test(await page.locator("#readDock").innerText()));
  check("there is no Focus button, even if Focus was saved before", (await page.locator('#tasksPage [data-task-mode], #tasksPage .seg').count()) === 0 && !/Focus/.test(await page.locator(".tp-head").innerText()));
  await page.locator('#tasksPage .tmain:not([disabled])').first().click();
  await page.waitForFunction(() => !/Pick a task/.test(document.getElementById("readDock").innerText));
  check("opening a task shows its email on the right and stays on Tasks", (await page.evaluate(() => document.body.classList.contains("on-tasks"))) && /Just you/.test(await page.locator("#readDock").innerText()));
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "tasks_right.png") });
  // Calendar pop-up
  await page.locator("[data-cal-open]").click();
  await page.waitForSelector("#calPop:not([hidden])");
  const box = await page.locator("#calPop").boundingBox();
  check("the Calendar opens as a full-page pop-up", box.x === 0 && box.y === 0 && box.width >= 1399 && box.height >= 899);
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "tasks_calendar.png") });
  await page.keyboard.press("Escape");
  check("Escape closes it", await page.locator("#calPop").isHidden());
  await page.locator("[data-cal-open]").click();
  await page.waitForSelector("#calPop:not([hidden])");
  await page.locator('#calPop .cal-day[data-cal-day="2026-10-14"]').click();
  await page.locator('#calPop .tmain:not([disabled])').first().click();
  await page.waitForSelector("#calPop", { state: "hidden" });
  check("picking an email in the Calendar closes it and shows that email on the right", (await page.evaluate(() => document.body.classList.contains("on-tasks"))) && /Just you/.test(await page.locator("#readDock").innerText()));
  // Options
  await page.locator("[data-task-opts-toggle]").click();
  await page.locator('[data-task-opt="done"]').uncheck();
  check("Show finished tasks off hides the Done list", !/dentist invoice/.test(await text(page)));
  await page.locator('[data-task-opt="later"]').uncheck();
  check("Show tasks that are not due yet off hides Later and says so", !/trip insurance/.test(await text(page)) && /1 task is not due yet and hidden/.test(await text(page)));
  await page.locator('[data-task-opt="sort"]').selectOption("az");
  const order = await page.locator("#tasksPage .ttl").allInnerTexts();
  check("Order A to Z sorts by title", order.join("|") === [...order].sort((a, b) => a.localeCompare(b)).join("|"));
  await page.reload();
  await page.waitForSelector("article.mail", { state: "attached" });
  await page.locator('.nav[data-filter="tasks"]').first().click();
  await page.locator("[data-task-opts-toggle]").click();
  check("the options are remembered", !(await page.locator('[data-task-opt="done"]').isChecked()) && (await page.locator('[data-task-opt="sort"]').inputValue()) === "az");
  check("no script errors", errors.length === 0);
  await context.close();
}
{
  const { page, context, errors } = await run2(1400, 900, "list");
  await page.locator('.nav[data-filter="tasks"]').first().click();
  await page.waitForSelector("#taskSearch");
  check("with another layout Tasks is not split", !(await page.evaluate(() => document.body.classList.contains("split-read"))));
  check("no script errors", errors.length === 0);
  await context.close();
}
{
  const { page, context, errors } = await run2(390, 800, "right");
  await page.locator("#menuBtn").click();
  await page.locator('.nav[data-filter="tasks"]').first().click();
  await page.waitForSelector("#taskSearch");
  await page.locator("[data-cal-open]").click();
  await page.waitForSelector("#calPop:not([hidden])");
  const b = await page.locator("#calPop").boundingBox();
  check("on a phone the Calendar fills the screen", b.x === 0 && b.y === 0 && b.width >= 389 && b.height >= 799);
  const top = await page.locator("#calPop .sf-top").boundingBox(), close = await page.locator("#calPop [data-cal-close]").boundingBox();
  check("the title and Close stay fixed at the top", top.y === 0 && close.y >= 0 && close.y + close.height <= top.y + top.height + 1);
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "tasks_calendar_phone.png") });
  await page.locator("[data-cal-close]").click();
  check("Close brings the list back", await page.locator("#calPop").isHidden());
  check("no script errors", errors.length === 0);
  await context.close();
}
await browser.close();
if (failed) process.exit(1);
