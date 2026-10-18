// Browser check that the inbox list stays where it was scrolled to when the page redraws in the background (a refresh, a status update).
// The page is loaded from a pretend Enveliq server (Playwright intercepts the requests), so this needs no Python.
//   node scripts/check_list_scroll.mjs      (SHOTS=<dir> saves screenshots)
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";
const here = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.resolve(path.join(here, "..", "prototype", "index.html")), "utf8");
const ORIGIN = "http://enveliq.test";
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
const now = Math.floor(Date.now() / 1000);
const features = { compose: true, address_book: true, sent: true, media: false, all_mail: false, shipping: false, rss: false, tags: false, subscriptions: false, travel: false, waiting: false, messages: false, write_help: false, find_mail: false };
const mk = (id, n) => ({ id, subject: "Email number " + n, sender_display: "Sender " + n, sender_address: "s" + n + "@example.invalid", summary: "A summary.", priority: "normal", category: null, action_required: false, suggested_task: null, received_at: now - n * 600, state: "unread", has_attachments: false, attachments: [],
  reply_context: { reply_to: "s" + n + "@example.invalid", delivered_to: null, via_alias: null, message_id: "<" + id + "@x>", references: [], cc: [], also_to: [] } });
const messages = Array.from({ length: 40 }, (_, i) => mk("m" + i, i + 1));
const proton = { id: "a1", provider: "Proton Mail", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton", email_address: "me@example.invalid", server: "172.30.0.1", port: 1143, settings: {} };
const handler = async (route) => {
  const req = route.request(), p = new URL(req.url()).pathname;
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
  if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
  if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
  if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
  if (p === "/api/v1/accounts") return json(200, [proton]);
  if (p === "/api/v1/accounts/a1/messages") return json(200, messages);
  if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: { ...features, address_book_auto: true } });
  if (p === "/api/v1/me/drafts") return json(200, { now: Date.now() / 1000, keep_days: 14, items: [] });
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "" });
  if (p === "/api/v1/me/contacts") return json(200, { items: [] });
  if (p === "/api/v1/me/tasks") return json(200, { today: "2026-10-14", tz: "UTC", now: Date.now() / 1000, tasks: [] });
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: {} });
  return json(404, { detail: "not found" });
};
const browser = await chromium.launch();
for (const layout of ["list", "right"]) {
  const context = await browser.newContext({ viewport: { width: 1300, height: 800 } });
  await context.addInitScript((l) => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-view", JSON.stringify({ layout: l })); } catch (e) {} }, layout);
  const page = await context.newPage();
  const errors = []; page.on("pageerror", (e) => errors.push(String(e)));
  await context.route(`${ORIGIN}/**`, handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  // The highlighted email is the first one; then the person scrolls well past it.
  await page.evaluate(() => { const m = data.find((x) => x.real); paneId = m ? m.id : paneId; render(); });
  check(`[${layout}] the list is long enough to scroll`, await page.evaluate(() => document.documentElement.scrollHeight > innerHeight + 200 || [...document.querySelectorAll("#paneList,.main>.content")].some((e) => e.scrollHeight > e.clientHeight + 200)));
  const get = () => page.evaluate(() => [document.getElementById("paneList"), document.querySelector(".main>.content"), document.getElementById("list")].filter(Boolean).map((e) => e.scrollTop).concat([Math.round(window.scrollY)]));
  await page.evaluate(() => { window.scrollTo(0, 900); for (const e of [document.getElementById("paneList"), document.querySelector(".main>.content"), document.getElementById("list")].filter(Boolean)) if (e.scrollHeight > e.clientHeight + 50) e.scrollTop = 900; });
  const before = await get();
  check(`[${layout}] scrolling down moved the list`, before.some((v) => v > 300));
  for (let i = 0; i < 3; i++) { await page.evaluate(() => render()); await page.waitForTimeout(150); }
  await page.waitForTimeout(1500);
  const after = await get();
  check(`[${layout}] a redraw in the background leaves the list where it was scrolled to`, JSON.stringify(before) === JSON.stringify(after));
  await page.evaluate(() => { const next = data.filter((x) => x.real)[30]; if (next) { paneId = next.id; render(); } });
  check(`[${layout}] no script errors`, errors.length === 0);
  await context.close();
}
await browser.close();
process.exit(failed ? 1 : 0);
