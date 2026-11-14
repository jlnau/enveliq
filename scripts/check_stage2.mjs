// Browser check for Stage 2: star / unstar an email (row, open email, three-dot menu), the Starred page and the Starred filter.
// The page is loaded from a pretend Enveliq server (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_stage2.mjs [path/to/prototype/index.html]
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
  { ...base, id: "m-c", subject: "Electricity bill", starred: true, sender_display: "Northside Power", sender_address: "bills@example.invalid", received_at: now - 1200, reply_context: ctx("c") },
  { ...base, id: "m-r", subject: "Starred and already read", sender_display: "Cara", sender_address: "cara@example.invalid", received_at: now - 5000, from_all_mail: true, starred: true, reply_context: ctx("r") },
];
let messages, posts, prints, sent;
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
  if (/\/api\/v1\/accounts\/a1\/messages\/[^/]+\/star$/.test(p) && m === "POST") {
    const body = JSON.parse(req.postData() || "{}"); const id = p.split("/")[6]; posts.push(["star", id, body]);
    const row = messages.find((x) => x.id === id); if (row) row.starred = body.starred;
    return json(200, { starred: body.starred });
  }
  if (p === "/api/v1/me/drafts" && m === "POST") { posts.push(["draft", "", JSON.parse(req.postData() || "{}")]); return json(200, { id: "d0123456789abcdef", items: [] }); }
  if (p === "/api/v1/me/drafts") return json(200, { items: [] });
  if (/\/original\/headers$/.test(p)) return json(200, { headers: "From: Alice <alice@example.invalid>\nSubject: Trip plans\nReceived: from mx.example.invalid" });
  if (/\/original\/eml$/.test(p)) return route.fulfill({ status: 200, contentType: "message/rfc822", headers: { "Content-Disposition": 'attachment; filename="email.eml"' }, body: "Subject: Trip plans\r\n\r\nHello" });
  if (/\/messages\/[^/]+\/(reply|forward)$/.test(p) && m === "POST") { sent.push([p.split("/").pop(), JSON.parse(req.postData() || "{}")]); return json(200, { sent: true, from: "me@example.invalid" }); }
  if (/\/accounts\/a1\/send$/.test(p) && m === "POST") { sent.push(["send", JSON.parse(req.postData() || "{}")]); return json(200, { sent: true, from: "me@example.invalid" }); }
  if (/\/original$/.test(p)) return json(200, { from: { name: "Alice", address: "alice@example.invalid" }, to: [{ address: "me@example.invalid" }], date: "Today", subject: "Trip plans", text: "Plain words of the original email.", links: [], has_html: false, remote_images: 0, attachments: [], truncated: false });
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
  if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features });
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: now } } });
  return json(404, { detail: "not found" });
};
const browser = await chromium.launch();
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };
async function open(width, height = 900) {
  messages = make(); posts = []; prints = 0; sent = [];
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
const menuTexts = async (page) => (await page.locator("#moreMenu [role=menuitem]").allInnerTexts()).map((x) => x.trim());

for (const width of [1200, 390]) {
  const tag = width + "px wide: ";
  const { page, errors, context } = await open(width);
  check(tag + "a starred email shows a star in the list", (await page.locator("article.mail", { hasText: "Electricity bill" }).locator(".starmark").count()) === 1 && (await page.locator("article.mail", { hasText: "Trip plans" }).first().locator(".starmark").count()) === 0);
  check(tag + "an already read starred email is not in My inbox while read mail is hidden", (await page.locator("article.mail", { hasText: "Starred and already read" }).count()) === 0);
  await pick(page, "Trip plans");
  await page.waitForTimeout(300);
  const starBtn = page.locator("button.starbtn").first();
  check(tag + "the open email has a Star button", (await starBtn.count()) === 1 && (await starBtn.getAttribute("aria-pressed")) === "false" && (await starBtn.getAttribute("aria-label")) === "Star this email");
  await starBtn.click();
  await page.waitForFunction(() => /Starred/.test(document.getElementById("toast").innerText));
  check(tag + "pressing it asks the server to star that email", posts.some((x) => x[0] === "star" && x[1] === "m-a" && x[2].starred === true));
  check(tag + "the button now says Remove star and the row has a star", (await page.locator("button.starbtn").first().getAttribute("aria-label")) === "Remove star" && (await page.locator("article.mail", { hasText: "Trip plans" }).first().locator(".starmark").count()) === 1);
  await shot(page, "stage2-star-" + width);
  await page.locator(".qmore").first().click();
  const items = await menuTexts(page);
  check(tag + "the three-dot menu offers Remove star", items.includes("Remove star") && !items.includes("Star"));
  await page.locator("#moreMenu [data-star]").click();
  await page.waitForFunction(() => /Star removed/.test(document.getElementById("toast").innerText));
  check(tag + "the menu item unstars it", posts.some((x) => x[0] === "star" && x[1] === "m-a" && x[2].starred === false));
  await page.locator("#moreMenu").waitFor({ state: "hidden" }).catch(() => {});
  if (width > 800) {
    await page.locator("article.mail", { hasText: "Re: Trip plans" }).hover();
    check(tag + "hovering a row shows a star button", (await page.locator("article.mail", { hasText: "Re: Trip plans" }).locator("button.action.star").count()) === 1);
  }
  await page.evaluate(() => document.querySelector('.nav[data-filter="starred"]').click());
  await page.waitForTimeout(400);
  const names = await page.locator("article.mail .subject").allInnerTexts();
  check(tag + "the Starred page lists the starred emails, including the one already read", names.length === 2 && names.some((n) => /Electricity bill/.test(n)) && names.some((n) => /Starred and already read/.test(n)));
  await shot(page, "stage2-starred-" + width);
  check(tag + "no sideways scroll", await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  check(tag + "no page errors", errors.length === 0);
  await context.close();
}

{
  const { page, errors, context } = await open(1200);
  await page.evaluate(() => { const f = document.getElementById("filterBy"); f.value = "starred"; f.dispatchEvent(new Event("change", { bubbles: true })); });
  await page.waitForTimeout(300);
  const names = await page.locator("article.mail .subject").allInnerTexts();
  check("the Filter box has a Starred choice that lists only starred emails", names.length === 2 && names.every((n) => /Electricity bill|Starred and already read/.test(n)));
  check("no page errors", errors.length === 0);
  await context.close();
}

await browser.close();
if (failed) process.exit(1);
