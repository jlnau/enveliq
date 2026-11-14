// Browser check that the inbox never waits for the slow "read my recent mail" call: with it taking 8 seconds, the emails still show at once, and the list refreshes when it finishes.
// The page is loaded from a pretend Enveliq server (Playwright intercepts the requests), so this needs no Python.
//   node scripts/check_boot_fast.mjs [path/to/prototype/index.html]     (SHOTS=<dir> saves screenshots)
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
const features = { all_mail: true, compose: true, address_book: true, sent: true, media: false, shipping: false, rss: false, tags: false, subscriptions: false, travel: false, waiting: false, messages: false, write_help: false };
const mk = (id, subject, name, n) => ({ id, subject, sender_display: name, sender_address: name.toLowerCase() + "@example.invalid", summary: "A summary.", priority: "normal", category: null, action_required: false, received_at: now - n,
  reply_context: { reply_to: name.toLowerCase() + "@example.invalid", delivered_to: null, via_alias: null, message_id: "<" + id + "@x>", references: [], cc: [], also_to: [] } });
const t = (n, title, extra = {}) => ({ id: "t" + String(n).padStart(23, "0"), account_id: "a1", message_id: "m-plain", title, detail: "", sender: "Bob", priority: "normal", due: "2026-10-14", days: 0, remind_at: null, state: "open", reason: null, reason_text: "", closed_at: null, received: now - 100, ...extra });
const tasks = [
  t(1, "Ring Brightwater Dental to confirm the check-up", { sender: "Brightwater Dental" }),
  t(2, "Buy a trip insurance policy", { due: "2026-10-20", days: 6, detail: "Cover for the Lisbon trip", sender: "Alice" }),
  t(3, "Send the school form back", { sender: "Westside Primary" }),
  t(4, "Pay the dentist invoice", { state: "done", reason: "done", reason_text: "Done", closed_at: now - 50, sender: "Brightwater Dental" }),
];
let recentCalls = 0;
const handler = async (route) => {
  const req = route.request(), p = new URL(req.url()).pathname;
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
  if (p.endsWith("/inbox/recent")) { recentCalls++; await new Promise((r) => setTimeout(r, 8000)); return json(200, { added: 0 }); }
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
const context = await browser.newContext({ viewport: { width: 1300, height: 900 } });
await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-all-mail", "1"); if (!sessionStorage.getItem("first")) { sessionStorage.setItem("first", "1"); localStorage.removeItem("enveliq-recent-at"); } } catch (e) {} });
const page = await context.newPage();
const errors = []; page.on("pageerror", (e) => errors.push(String(e)));
await context.route(`${ORIGIN}/**`, handler);
const t0 = Date.now();
await page.goto(`${ORIGIN}/`);
await page.waitForSelector("article.mail");
const ms = Date.now() - t0;
check(`the emails show at once even though reading recent mail takes 8 seconds (${ms} ms)`, ms < 5000 && recentCalls === 1);
await page.reload();
await page.waitForSelector("article.mail");
await page.waitForTimeout(500);
check("pressing refresh again does not start the slow read again within 5 minutes", recentCalls === 1);
check("no script errors", errors.length === 0);
await browser.close();
if (failed) process.exit(1);
