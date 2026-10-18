// Browser check: the View button on an email's attachment opens that attachment in its viewer (not the original email), Save still works, and the email stays open underneath.
// The page is loaded from a pretend Enveliq server (Playwright intercepts the requests), so this needs no Python.
//   node scripts/check_attachment_view.mjs [path/to/prototype/index.html]     (SHOTS=<dir> saves screenshots)
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
const features = { compose: true, address_book: true, sent: true, media: true, all_mail: false, shipping: false, subscriptions: false, travel: false, waiting: false, messages: false, write_help: false };
const PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";
const PNG = Buffer.from(PNG_B64, "base64");
const messages = [
  { id: "m-att", subject: "Your invoice", sender_display: "Alice", sender_address: "alice@example.invalid", summary: "An invoice to pay.", priority: "normal", category: null, action_required: false, received_at: now - 60, has_attachments: true, attachment_count: 2,
    attachment_summaries: [
      { filename: "Invoice.pdf", mime_type: "application/pdf", size_bytes: 20480, index: 1, state: "done", summary: "An invoice for 120 dollars.", parts: [] },
      { filename: "photo.png", mime_type: "image/png", size_bytes: 2048, index: 0, state: "done", summary: "A small picture.", parts: [] },
    ],
    reply_context: { reply_to: "alice@example.invalid", delivered_to: null, via_alias: null, message_id: "<a@x>", references: [], cc: [], also_to: [] } },
];
const handler = async (route) => {
  const req = route.request(), u = new URL(req.url()), p = u.pathname, q = u.searchParams;
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
  if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
  if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
  if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
  if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "127.0.0.1", port: 1143, username: "me@example.invalid", settings: {} }]);
  if (p === "/api/v1/accounts/a1/messages") return json(200, messages);
  if (/\/messages\/[^/]+\/original$/.test(p)) { calls.push(["original"]); return json(200, { subject: "Your invoice", from: { name: "Alice", address: "alice@example.invalid" }, to: [], date: "2026-10-14", body: "Hello", attachments: [] }); }
  if (/\/attachments\/1\/view$/.test(p)) { calls.push(["view1"]); return json(200, { kind: "pdf", pages: [PNG_B64], total: 1, shown: 1 }); }
  if (/\/attachments\/1$/.test(p)) { calls.push(["save1"]); return route.fulfill({ status: 200, contentType: "application/octet-stream", body: "x" }); }
  if (/\/attachments\/0$/.test(p)) { calls.push(["pic0", q.get("preview")]); return route.fulfill({ status: 200, contentType: "image/png", body: PNG }); }
  if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: { ...features, address_book_auto: true } });
  if (p === "/api/v1/me/drafts") return json(200, { now: Date.now() / 1000, keep_days: 14, items: [] });
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "" });
  if (p === "/api/v1/me/contacts") return json(200, { items: [] });
  if (p === "/api/v1/me/tasks") return json(200, { today: "2026-10-14", tz: "UTC", now: Date.now() / 1000, tasks: [] });
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: {} });
  return json(404, { detail: "not found" });
};

const browser = await chromium.launch();
for (const [name, width, height] of [["computer", 1200, 900], ["phone", 390, 800]]) {
  calls.length = 0;
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-view", JSON.stringify({ layout: "list" })); } catch (e) {} });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route(`${ORIGIN}/**`, handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  await page.locator("article.mail", { hasText: "Your invoice" }).locator(".qmain").click();
  await page.waitForSelector(".ad-row");
  const readerBefore = await page.locator(".reader").count();
  await page.locator(".ad-row", { hasText: "Invoice.pdf" }).locator(".attachment-view").click();
  await page.waitForSelector("#docBox:not([hidden]) img.doc-page");
  check(`[${name}] View on a PDF opens the document viewer`, (await page.locator("#docName").innerText()) === "Invoice.pdf");
  check(`[${name}] it did not open the original email`, !calls.some((c) => c[0] === "original") && (await page.locator("#attachmentModal.open").count()) === 0);
  await page.locator("#docSave").click();
  await page.waitForTimeout(300);
  check(`[${name}] Save to my device still downloads that file`, calls.some((c) => c[0] === "save1"));
  await page.locator("#docClose").click();
  check(`[${name}] closing the viewer leaves the email open`, (await page.locator(".ad-row", { hasText: "Invoice.pdf" }).count()) === 1 && (await page.locator(".reader").count()) === readerBefore);
  await page.locator(".ad-row", { hasText: "photo.png" }).locator(".attachment-view").click();
  await page.waitForSelector("#picBox:not([hidden])");
  await page.waitForFunction(() => !document.getElementById("picImg").hidden);
  check(`[${name}] View on a picture opens the picture viewer`, (await page.locator("#picName").innerText()) === "photo.png" && calls.some((c) => c[0] === "pic0"));
  check(`[${name}] no script errors`, errors.length === 0);
  await context.close();
}
await browser.close();
process.exit(failed ? 1 : 0);
