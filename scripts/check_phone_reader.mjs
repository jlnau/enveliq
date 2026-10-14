// Browser check for phones: whatever layout is chosen, an email opens full screen and the only way to the next one is to close it.
// The page is loaded from a pretend Enveliq server (Playwright intercepts the requests), so this needs no Python.
//   node scripts/check_phone_reader.mjs [path/to/prototype/index.html]     (SHOTS=<dir> saves screenshots)
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
const run = async (layout, width, height) => {
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript((l) => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-view", JSON.stringify({ layout: l })); } catch (e) {} }, layout);
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route(`${ORIGIN}/**`, handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  return { page, context, errors };
};
const fills = (page) => page.locator(".reader").evaluate((el) => { const r = el.getBoundingClientRect(); return r.left <= 1 && r.top <= 1 && r.width >= innerWidth - 2 && r.height >= innerHeight - 2; }).catch(() => false);

for (const layout of ["list", "right", "bottom", "screen", "deck"]) {
  const { page, context, errors } = await run(layout, 390, 800);
  check(`[${layout}] on a phone no email is open until one is tapped`, (await page.locator(".reader").count()) === 0);
  await page.locator("article.mail", { hasText: "Plan for May" }).locator(".qmain").click();
  await page.waitForSelector(".reader");
  check(`[${layout}] tapping an email opens it full screen`, await fills(page));
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `phone_${layout}.png`) });
  check(`[${layout}] it shows that email`, (await page.locator(".reader h3").innerText()).includes("Plan for May"));
  check(`[${layout}] there is a Close button and no Next or Previous`, (await page.locator(".reader [data-reader-close]").innerText()).includes("Close") && (await page.locator(".reader [aria-label='Next email'], .reader [aria-label='Previous email']").count()) === 0);
  await page.locator(".reader [data-reader-close]").click();
  check(`[${layout}] Close goes back to the list`, (await page.locator(".reader").count()) === 0 && (await page.locator("article.mail").count()) >= 3);
  await page.locator("article.mail", { hasText: "Third one" }).locator(".qmain").click();
  await page.waitForSelector(".reader");
  check(`[${layout}] the next email is opened from the list`, (await page.locator(".reader h3").innerText()).includes("Third one"));
  check(`[${layout}] no script errors`, errors.length === 0);
  await context.close();
}

// Reviewed, Archive and Bin inside the full screen email: it closes at once, the Undo bar still shows, and Undo brings the email back
for (const [cls, word] of [["reviewed", "Marked reviewed"], ["archive", "Archived"], ["trash", "Moved to Bin"]]) {
  const { page, context, errors } = await run("list", 390, 800);
  await page.locator("article.mail", { hasText: "Plan for May" }).locator(".qmain").click();
  await page.waitForSelector(".reader");
  await page.locator(`.reader .ract .action.${cls}`).click();
  check(`[${cls}] the full screen email closes straight away`, (await page.locator(".reader").count()) === 0);
  check(`[${cls}] the Undo bar shows "${word}"`, (await page.locator("#undoBar .undobar").innerText()).includes(word));
  await page.locator("#undoBar .undobar button").click();
  await page.waitForSelector("article.mail", { hasText: "Plan for May" });
  check(`[${cls}] Undo puts the email back in the list`, (await page.locator("article.mail", { hasText: "Plan for May" }).count()) === 1);
  check(`[${cls}] no script errors`, errors.length === 0);
  await context.close();
}

// A big screen keeps the chosen layout: "right" shows the reading pane beside the list and no full screen reader
{
  const { page, context } = await run("right", 1300, 900);
  await page.locator("article.mail", { hasText: "Plan for May" }).locator(".qmain").click();
  await page.waitForTimeout(300);
  check("on a big screen the chosen layout is kept (no full screen reader)", (await page.locator(".reader").count()) === 0 && (await page.locator("#readDock .reading").count()) === 1);
  // and shrinking the window to phone size switches to the full screen way without losing the setting
  await page.setViewportSize({ width: 390, height: 800 });
  await page.waitForTimeout(400);
  check("shrinking to phone size stops showing the side panel", (await page.locator("#readDock .reading").count()) === 0 && (await page.locator("article.mail").count()) >= 3);
  check("the saved layout choice is unchanged", await page.evaluate(() => JSON.parse(localStorage.getItem("enveliq-view")).layout === "right"));
  await context.close();
}
await browser.close();
process.exit(failed ? 1 : 0);
