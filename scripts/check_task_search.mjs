// Browser check for the task search box: typing part of a task's words lists only the tasks that have them (open and done), in every task view.
// The page is loaded from a pretend Enveliq server (Playwright intercepts the requests), so this needs no Python.
//   node scripts/check_task_search.mjs [path/to/prototype/index.html]     (SHOTS=<dir> saves screenshots)
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
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-view", JSON.stringify({ layout: "list" })); localStorage.setItem("enveliq-task-mode", "list"); } catch (e) {} });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route(`${ORIGIN}/**`, handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  return { page, context, errors };
};
const titles = (page) => page.locator("#tasksPage").innerText();
{
  const { page, context, errors } = await run(1300, 900);
  await page.locator('.nav[data-filter="tasks"]').first().click();
  await page.waitForSelector("#taskSearch");
  check("the Tasks page has a search box", (await page.locator("#taskSearch").getAttribute("placeholder")) === "Search your tasks");
  const all = await titles(page);
  check("with nothing typed every task shows", /Brightwater Dental to confirm/.test(all) && /trip insurance/.test(all) && /school form/.test(all) && /dentist invoice/.test(all));
  await page.locator("#taskSearch").pressSequentially("dent", { delay: 40 });
  await page.waitForFunction(() => !/school form/.test(document.getElementById("tasksPage").innerText));
  const hit = await titles(page);
  check("typing part of the words lists the tasks that have them (by title or sender)", /confirm the check-up/.test(hit) && /dentist invoice/.test(hit) && !/trip insurance/.test(hit));
  check("the box keeps what was typed and the cursor stays in it", (await page.locator("#taskSearch").inputValue()) === "dent" && (await page.evaluate(() => document.activeElement && document.activeElement.id)) === "taskSearch");
  check("it says how many tasks match", /2 tasks match/.test(hit));
  check("done tasks are found too, under Done", /Done/.test(hit) && /dentist invoice/.test(hit));
  await page.locator("#taskSearch").fill("LISBON");
  await page.waitForFunction(() => /trip insurance/.test(document.getElementById("tasksPage").innerText) && !/confirm the check-up/.test(document.getElementById("tasksPage").innerText));
  check("it matches the details too, and ignores capital letters", /1 task matches/.test(await titles(page)));
  await page.locator("#taskSearch").fill("zzz");
  await page.waitForFunction(() => /No task has those words/.test(document.getElementById("tasksPage").innerText));
  check("when nothing matches it says so kindly", true);
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "task_search_desktop.png") });
  await page.locator("#taskSearch").fill("");
  await page.waitForFunction(() => /school form/.test(document.getElementById("tasksPage").innerText));
  check("clearing the box brings every task back", true);
  await page.locator('[data-task-mode="focus"]').click();
  await page.waitForSelector("#taskSearch");
  await page.locator("#taskSearch").fill("school");
  await page.waitForFunction(() => /1 task matches/.test(document.getElementById("tasksPage").innerText));
  check("searching works in the Focus view too", /school form/.test(await titles(page)));
  await page.locator("#taskSearch").fill("");
  await page.locator('[data-task-mode="calendar"]').click();
  await page.waitForSelector("#taskSearch");
  check("and the box is there in the Calendar view", true);
  check("no script errors", errors.length === 0);
  await context.close();
}
{
  const { page, context, errors } = await run(390, 800);
  await page.locator("#menuBtn").click();
  await page.locator('.nav[data-filter="tasks"]').first().click();
  await page.waitForSelector("#taskSearch");
  const box = await page.locator("#taskSearch").boundingBox();
  check("on a phone the search box fits the screen", box.x >= 0 && box.x + box.width <= 390);
  check("and uses large text so the phone does not zoom in", (await page.locator("#taskSearch").evaluate((e) => parseFloat(getComputedStyle(e).fontSize))) >= 16);
  await page.locator("#taskSearch").fill("school");
  await page.waitForFunction(() => /1 task matches/.test(document.getElementById("tasksPage").innerText));
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "task_search_phone.png") });
  check("no script errors", errors.length === 0);
  await context.close();
}
await browser.close();
if (failed) process.exit(1);
