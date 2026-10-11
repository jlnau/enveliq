// Browser check for phones: every pop-up window (the original email, a reply, New email, pictures, documents) must
// have a Close button that is on screen and not covered by the top bar, and must fit the screen.
// The page is loaded from a pretend Enveliq server (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_phone_overlays.mjs [path/to/prototype/index.html]
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
const now = Math.floor(Date.now() / 1000);
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", "base64");
const PNG_B64 = PNG.toString("base64");

function makeServer(opts = {}) {
  const calls = [];
  const features = { compose: true, address_book: true, sent: true, media: true, ...(opts.features || {}) };
  let undo = opts.undo || 0, held = null;
  const people = [
    { address: "alex.chen@example.invalid", name: "Alex Chen", count: 14, last: now, source: "seen" },
    { address: "alexandra@example.invalid", name: "Alexandra Moore", count: 3, last: now, source: "seen" },
    { address: "beth@example.invalid", name: "Beth Harris", count: 9, last: now, source: "sent" },
  ];
  const settle = () => { if (held && held.state === "pending" && held.send_at <= Date.now() / 1000) held.state = "sent"; };
  const handler = async (route) => {
    const req = route.request(), p = new URL(req.url()).pathname, q = new URL(req.url()).searchParams;
    const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
    if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
    if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
    if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
    if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1144, username: "u", settings: { send_identities: ["work@example.invalid"] } }]);
    if (p === "/api/v1/accounts/a1/messages") return json(200, [{ id: "m1", subject: "Holiday photos", sender_display: "Beth", sender_address: "beth@example.invalid", summary: "Photos.", priority: "normal", category: null, action_required: false, received_at: now - 600,
      reply_context: { reply_to: "beth@example.invalid", delivered_to: null, via_alias: null, message_id: "<m1@x>", references: [] } }]);
    if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: undo });
    if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features });
    if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: now } } });
    if (p === "/api/v1/me/contacts") {
      if (!features.address_book) return json(403, { detail: "Address book is switched off." });
      const s = (q.get("q") || "").toLowerCase();
      calls.push(["contacts", s]);
      return json(200, { items: people.filter((x) => x.address.includes(s) || x.name.toLowerCase().includes(s)) });
    }
    if (p === "/api/v1/accounts/a1/send") {
      const body = JSON.parse(req.postData()); calls.push(["send", body]);
      if (undo > 0) { held = { id: "o9", state: "pending", send_at: Date.now() / 1000 + undo, body: body.body, from: body.from_address, to: body.to[0], draft: { to: body.to, cc: body.cc, bcc: body.bcc, subject: body.subject, attachments: body.files.length }, files: body.files };
        return json(200, { queued: true, id: "o9", send_at: held.send_at, now: Date.now() / 1000, from: body.from_address, to: body.to[0] }); }
      return json(200, { sent: true, from: body.from_address });
    }
    if (p === "/api/v1/me/outbox" && req.method() === "GET") { settle(); return json(200, { now: Date.now() / 1000, items: held ? [{ id: held.id, kind: "new", account_id: "a1", message_id: null, state: held.state, send_at: held.send_at, from: held.from, to: held.to, error: null, subject: held.draft.subject }] : [] }); }
    if (p === "/api/v1/me/outbox/o9" && req.method() === "DELETE") { settle(); if (!held || held.state !== "pending") return json(409, { detail: { code: "conflict", message: "gone" } });
      const out = { cancelled: true, body: held.body, from: held.from, to: held.to, account_id: "a1", message_id: null, draft: held.draft, files: held.files }; calls.push(["cancel"]); held = null; return json(200, out); }
    if (p === "/api/v1/accounts/a1/sent") { calls.push(["sent"]); return json(200, { validity: 7, days: 14, more: false, items: [
      { uid: 501, to: [{ name: "Beth Harris", address: "beth@example.invalid" }, { name: "", address: "sam@example.invalid" }], subject: "Dinner on Saturday", date: now - 3600 },
      { uid: 502, to: [{ name: "", address: "alex.chen@example.invalid" }], subject: "Re: Quote", date: now - 86400 * 3 }] }); }
    if (/\/(messages\/m1|sent\/7\/501)\/original$/.test(p)) return json(200, { subject: "Holiday photos", from: { name: "Beth", address: "beth@example.invalid" }, to: [{ name: "", address: "me@example.invalid" }], date: "Mon, 05 Oct 2026 18:20:00 +0000",
      text: "Here are the shots.", truncated: false, remote_images: 3, attachments: [
        { index: 0, filename: "lookout.png", mime_type: "image/png", size_bytes: 68, inline: true, previewable: true },
        { index: 1, filename: "itinerary.pdf", mime_type: "application/pdf", size_bytes: 217088, inline: false, previewable: false, viewable: true }] });
    if (/\/attachments\/0$/.test(p)) { calls.push(["att0", q.get("preview")]); return route.fulfill({ status: 200, contentType: "image/png", body: PNG }); }
    if (/\/attachments\/1\/view$/.test(p)) { calls.push(["view1"]); return json(200, { kind: "pdf", pages: [PNG_B64, PNG_B64], total: 3, shown: 2 }); }
    if (/\/attachments\/1$/.test(p)) { calls.push(["att1", q.get("preview")]); return route.fulfill({ status: 200, contentType: "application/octet-stream", headers: { "content-disposition": 'attachment; filename="itinerary.pdf"' }, body: Buffer.from("%PDF-1.4 fake") }); }
    return json(404, { detail: "not found" });
  };
  return { handler, calls };
}

const browser = await chromium.launch();
async function open(server, { width = 1200, height = 900 } = {}) {
  const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 3, isMobile: true, hasTouch: true, acceptDownloads: true });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
  const page = await context.newPage();
  const errors = [], csp = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (/Content Security Policy|Refused to/.test(m.text())) csp.push(m.text()); });
  await context.route(`${ORIGIN}/**`, server.handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  return { page, errors, csp, context };
}
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };

// A control counts as reachable when it is inside the screen and is what a finger would actually touch there.
const reachable = (page, sel) => page.evaluate((s) => {
  const el = document.querySelector(s); if (!el) return "missing";
  const r = el.getBoundingClientRect(), bad = [];
  if (r.width < 40 || r.height < 40) bad.push("too small " + Math.round(r.width) + "x" + Math.round(r.height));
  if (r.left < 0 || r.top < 0 || r.right > window.innerWidth || r.bottom > window.innerHeight) bad.push("off screen " + JSON.stringify([r.left, r.top, r.right, r.bottom].map(Math.round)));
  const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  if (!(hit && (hit === el || el.contains(hit)))) bad.push("covered by " + (hit ? hit.tagName + "#" + hit.id + "." + String(hit.className).slice(0, 30) : "nothing"));
  return bad.length ? bad.join("; ") : "ok";
}, sel);
const fits = (page, sel) => page.evaluate((s) => { const r = document.querySelector(s).getBoundingClientRect(); return r.left >= 0 && r.top >= 0 && r.right <= window.innerWidth + 0.5 && r.bottom <= window.innerHeight + 0.5; }, sel);

for (const [w, h] of [[360, 640], [390, 800]]) {
  const server = makeServer();
  const { page, csp, errors } = await open(server, { width: w, height: h });
  const tag = `${w}x${h}: `;

  // The original email, from the inbox
  await page.locator("article.mail .qrow").first().click();
  await page.locator("[data-open-email]").first().click();
  await page.waitForSelector("#attachmentModal.open");
  check(tag + "View original fits the screen", await fits(page, "#attachmentModal"));
  check(tag + "its Close button can be seen and tapped (" + (await reachable(page, "#attachmentModalClose")) + ")", (await reachable(page, "#attachmentModalClose")) === "ok");
  await page.locator("#attachmentViewer").evaluate((e) => { e.scrollTop = e.scrollHeight; });
  check(tag + "after scrolling to the bottom Close is still there", (await reachable(page, "#attachmentModalClose")) === "ok");
  await shot(page, `orig-${w}`);
  await page.tap("#attachmentModalClose");
  check(tag + "tapping Close closes it", !(await page.locator("#attachmentModal").evaluate((e) => e.classList.contains("open"))));
  await page.locator("[data-open-email]").first().click();
  await page.waitForSelector("#attachmentModal.open");
  await page.goBack().catch(() => {});
  await page.waitForTimeout(300);
  const stayed = page.url().startsWith(ORIGIN) && (await page.locator("article.mail").count().catch(() => 0)) > 0;
  check(tag + "the phone's Back button closes it and stays on the inbox", stayed && !(await page.locator("#attachmentModal").evaluate((e) => e.classList.contains("open")).catch(() => true)));
  if (!stayed) { await page.goto(`${ORIGIN}/`); await page.waitForSelector("article.mail"); }

  // New email
  await page.tap("#mNewBtn");
  await page.waitForSelector("#newMail.open");
  check(tag + "New email fits the screen", await fits(page, "#newMail"));
  check(tag + "New email's Close can be tapped (" + (await reachable(page, "#nmClose")) + ")", (await reachable(page, "#nmClose")) === "ok");
  await shot(page, `new-${w}`);
  await page.tap("#nmClose");
  await page.waitForFunction(() => !document.getElementById("newMail").classList.contains("open"));

  // Reply
  if (!(await page.locator("article.mail [data-reply]").first().isVisible())) await page.locator("article.mail .qrow").first().click();
  await page.locator("article.mail [data-reply]").first().click();
  await page.waitForSelector("#compose.open");
  check(tag + "the reply window fits the screen", await fits(page, "#compose"));
  check(tag + "the reply window's Close can be tapped (" + (await reachable(page, "#composeClose")) + ")", (await reachable(page, "#composeClose")) === "ok");
  await shot(page, `reply-${w}`);
  await page.tap("#composeClose");
  await page.waitForFunction(() => !document.getElementById("compose").classList.contains("open"));

  check(tag + "no script errors or Content-Security-Policy violations", errors.length === 0 && csp.length === 0);
  await page.close();
}

await browser.close();
process.exit(failed ? 1 : 0);
