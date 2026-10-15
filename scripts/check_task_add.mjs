// Browser check for the Task button: every email has one, even when the AI found no task, and it makes a task of your own.
// The page is loaded from a pretend Enveliq server (Playwright intercepts the requests), so this needs no Python.
//   node scripts/check_task_add.mjs [path/to/prototype/index.html]     (SHOTS=<dir> saves screenshots)
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
const myTasks = [];
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
  if (p === "/api/v1/me/tasks" && req.method() === "POST") {
    const b = JSON.parse(req.postData()); calls.push(["task", b]);
    if (b.message_id === "m-gone") return json(404, { detail: "That email is no longer in your list." });
    myTasks.push({ id: "t" + String(myTasks.length + 1).padStart(23, "0"), account_id: b.account_id, message_id: b.message_id, title: b.title, detail: "", sender: "Alice", priority: "normal", due: b.on || "2026-10-14", days: 0, remind_at: null, state: "open", reason: null, reason_text: "", closed_at: null, moved: false, manual: true });
    return json(200, { today: "2026-10-14", tz: "UTC", now: Date.now() / 1000, tasks: myTasks });
  }
  if (p === "/api/v1/me/tasks") return json(200, { today: "2026-10-14", tz: "UTC", now: Date.now() / 1000, tasks: myTasks });
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
const open = async (page, subject) => {
  const row = page.locator("article.mail", { hasText: subject });
  if (!(await row.locator("[data-task-add]").count())) await row.locator(".qmain").click();
  await page.waitForSelector(`article.mail:has-text("${subject}") [data-task-add]`);
  return row;
};

{
  const { page, context, errors } = await run(1300, 900);
  const row = await open(page, "Just you");
  check("an email the AI found no task in still has a Task button", (await row.locator("[data-task-add]").innerText()).trim() === "Task");
  check("the other emails have one too", (await page.locator("article.mail [data-task-add]").count()) >= 1);
  await row.locator("[data-task-add]").click();
  check("pressing Task opens a small box asking what to remember", (await page.locator("#taskAddMenu:not([hidden])").count()) === 1 && /remember/i.test(await page.locator("#taskAddMenu").innerText()));
  check("the cursor is in the box", await page.evaluate(() => document.activeElement && document.activeElement.id === "taText"));
  await page.locator("#taskAddMenu [data-task-add-save]").click();
  check("an empty task is not added", calls.filter((c) => c[0] === "task").length === 0 && (await page.locator("#taskAddMenu:not([hidden])").count()) === 1);
  await page.locator("#taText").fill("Ring the plumber when I get home");
  await page.locator("#taDate").fill("2026-10-20");
  await page.locator("#taskAddMenu [data-task-add-save]").click();
  await page.waitForFunction(() => document.getElementById("taskAddMenu").hidden);
  const sent = calls.find((c) => c[0] === "task");
  check("the task is sent for that email with its title and day", !!sent && sent[1].message_id === "m-plain" && sent[1].account_id === "a1" && sent[1].title === "Ring the plumber when I get home" && sent[1].on === "2026-10-20");
  check("the page says it was added", /Added to your tasks/.test(await page.locator("#toast").innerText()));
  check("the email now shows the task as 'Your task'", /Your task/.test(await page.locator("article.mail", { hasText: "Just you" }).innerText()) && /Ring the plumber/.test(await page.locator("article.mail", { hasText: "Just you" }).innerText()));
  // Cancel and Escape close it without adding
  await page.locator("article.mail", { hasText: "Third one" }).locator(".qmain").click();
  await page.locator("article.mail", { hasText: "Third one" }).locator("[data-task-add]").click();
  await page.locator("#taText").fill("Not this one");
  await page.keyboard.press("Escape");
  check("Escape closes the box and adds nothing", (await page.locator("#taskAddMenu").isHidden()) && calls.filter((c) => c[0] === "task").length === 1);
  await page.locator("article.mail", { hasText: "Third one" }).locator("[data-task-add]").click();
  await page.locator("#taText").fill("Enter adds it");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.getElementById("taskAddMenu").hidden);
  check("Enter in the box adds the task", calls.filter((c) => c[0] === "task").length === 2 && calls[calls.length - 1][1].title === "Enter adds it");
  check("no script errors", errors.length === 0);
  await context.close();
}

// On a phone the box sits at the bottom of the screen and fits
{
  const { page, context, errors } = await run(390, 800);
  await page.locator("article.mail", { hasText: "Plan for May" }).locator(".qmain").click();
  await page.waitForSelector(".reader");
  await page.locator(".reader [data-task-add]").click();
  const box = await page.locator("#taskAddMenu").boundingBox();
  check("on a phone the Task box fits on the screen", !!box && box.x >= 0 && box.x + box.width <= 391 && box.y >= 0 && box.y + box.height <= 801);
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "task_add_phone.png") });
  check("on a phone the Task box is above the full screen email", await page.evaluate(() => { const r = document.getElementById("taskAddMenu").getBoundingClientRect(); const el = document.elementFromPoint(r.left + r.width / 2, r.top + 20); return !!el && !!el.closest("#taskAddMenu"); }));
  check("no script errors", errors.length === 0);
  await context.close();
}
await browser.close();
if (failed) process.exit(1);
