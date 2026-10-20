// Browser check for the daily summary item at the top of the inbox: the special row,
// opening it, the link to the original email, read and delete. Pretend Enveliq server.
//
// Usage: node scripts/check_daily_summary.mjs [path/to/prototype/index.html]
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.resolve(process.argv[2] || path.join(here, "..", "prototype", "index.html")), "utf8");
const ORIGIN = process.env.TOUR ? "https://enveliq.test" : "http://enveliq.test";   // https hides the plain-http warning in the website pictures
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
for (const ev of ["uncaughtException", "unhandledRejection"]) process.on(ev, (e) => { console.log("::error::" + String((e && e.message) || e).split("\n").slice(0, 3).join(" | ")); process.exit(1); });
const now = Math.floor(Date.now() / 1000);
const SUGGESTION = "Hi Dana,\n\nThanks for asking. I can make Tuesday at [time].\n\nThanks,\n[your name]";

function makeServer(opts = {}) {
  const calls = [];
  const digests = [{ id: "d-2026-10-21", day: "2026-10-21", created_at: now, read: false, items: [
    { account_id: "a1", message_id: "m1", sender: "Dana Whitlock", subject: "Can you make Tuesday?", summary: "Dana asks if you can make Tuesday.", category: "Personal", reason: "Dana needs an answer today", urgent: true, received_at: now },
    { account_id: "a1", message_id: "zz", sender: "Shop", subject: "<img src=x onerror=window.__pwned=1>Sale", summary: "<b>Everything is half price.</b>", category: "Shopping", reason: "", urgent: false, received_at: now }] }];
  const features = { compose: true, address_book: true, sent: true, media: true, all_mail: false, shipping: false, waiting: false, messages: false, write_help: opts.feature !== false };
  const info = { available: true, quick: opts.quick !== false, on: opts.on !== false, ai_ready: true, instructions: "x", is_default: true, default: "x", max: 2000 };
  const handler = async (route) => {
    const req = route.request(), p = new URL(req.url()).pathname;
    const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    const body = () => { try { return JSON.parse(req.postData() || "{}"); } catch (e) { return {}; } };
    if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
    if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
    if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
    if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
    if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1144, username: "u", settings: {} }]);
    if (p === "/api/v1/accounts/a1/messages") return json(200, [{ id: "m1", subject: "Can you make Tuesday?", sender_display: "Dana Whitlock", sender_address: "dana@example.invalid", summary: "Dana asks if you can make Tuesday.", priority: "normal", category: "Information", action_required: true, received_at: now - 600, reply_context: { reply_to: "dana@example.invalid", delivered_to: null, via_alias: null, message_id: "<m1@x>", references: [] } }]);
    if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
    if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features });
    if (p === "/api/v1/me/write-help") return json(200, info);
    if (p === "/api/v1/me/digests") return json(200, { enabled: true, items: opts.none ? [] : digests.map((d) => ({ id: d.id, day: d.day, created_at: d.created_at, read: d.read, count: d.items.length, urgent: d.items.filter((i) => i.urgent).length })) });
    if (p === "/api/v1/me/digests/d-2026-10-21" && req.method() === "GET") return json(200, digests[0]);
    if (p === "/api/v1/me/digests/d-2026-10-21/read") { calls.push(["read"]); digests[0].read = true; return json(200, { ok: true }); }
    if (p === "/api/v1/me/digests/d-2026-10-21" && req.method() === "DELETE") { calls.push(["delete"]); digests.length = 0; return json(200, { ok: true }); }
    if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: now } } });
    if (p === "/api/v1/me/outbox") return json(200, { now: Date.now() / 1000, items: [] });
    if (p === "/api/v1/accounts/a1/messages/m1/write-help") {
      calls.push(["help", body().draft]);
      if (opts.fail) return json(502, { detail: { code: "ai_unreachable", message: "The AI server could not be reached or took too long to answer." } });
      return json(200, { text: opts.suggestion || SUGGESTION, notes: ["Added a greeting"], gaps: /\[/.test(opts.suggestion || SUGGESTION) });
    }
    if (p === "/api/v1/messages/send" || p.endsWith("/send")) { calls.push(["newsend", body().body]); return json(200, { from: "me@example.invalid", queued: false }); }
    if (p === "/api/v1/me/write-help/new") { calls.push(["helpnew", body().draft, body().subject]); return json(200, { text: "Hi all,\n\nDinner is at seven.", notes: [], gaps: false }); }
    if (p === "/api/v1/me/write-help/quick-fix") {
      calls.push(["quick", body().draft, body().subject]);
      if (opts.fail) return json(502, { detail: { code: "ai_unreachable", message: "The AI server could not be reached or took too long to answer." } });
      return json(200, { subject: body().subject, text: "Hi Dana,\n\nYes, Tuesday works.", changed: true });
    }
    if (p === "/api/v1/accounts/a1/messages/m1/reply") { calls.push(["reply", body().body]); return json(200, { from: "me@example.invalid", queued: false }); }
    return json(404, { detail: "not found: " + p });
  };
  return { handler, calls };

}
const browser = await chromium.launch();
async function open(server, { width = 1200, height = 900 } = {}) {
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route(`${ORIGIN}/**`, server.handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  return { page, errors, context };
}
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };
{
  const server = makeServer();
  const { page, errors, context } = await open(server);
  await page.waitForSelector(".dg-row");
  const row = await page.locator(".dg-row").innerText();
  check("the summary is a special row at the top of the inbox, labelled Summary and not read yet", row.includes("Summary") && row.includes("Daily summary") && row.includes("2 emails") && row.includes("1 that needs you today") && (await page.locator(".dg-row.read").count()) === 0);
  check("it sits above the emails", await page.evaluate(() => document.getElementById("digestStrip").getBoundingClientRect().top < document.querySelector("article.mail").getBoundingClientRect().top));
  await shot(page, "daily-summary-row");
  await page.click(".dg-row");
  await page.waitForSelector("#digestView.open");
  const text = await page.locator("#dgBody").innerText();
  check("it opens like an email: written by AI, what needs you today first, then the rest by kind", text.includes("Written by AI") && text.indexOf("Needs you today") < text.indexOf("Shopping") && text.includes("Why today: Dana needs an answer today"));
  check("nothing in it is treated as page code", (await page.locator("#dgBody img").count()) === 0 && (await page.evaluate(() => window.__pwned)) === undefined && text.includes("<b>Everything is half price.</b>"));
  await shot(page, "daily-summary-open");
  check("opening it marks it read", await page.waitForFunction(() => document.querySelector(".dg-row.read")).then(() => true).catch(() => false) && server.calls.some((c) => c[0] === "read"));
  await page.locator("#dgBody a.dg-open").first().click();
  await page.waitForFunction(() => !document.getElementById("digestView").classList.contains("open"));
  check("the link closes the summary and goes to the original email in Enveliq", await page.evaluate(() => expanded.has("row-" + data.find((x) => x.real && x.real.messageId === "m1").id) || paneId === data.find((x) => x.real && x.real.messageId === "m1").id));
  await page.click(".dg-row");
  await page.waitForSelector("#digestView.open");
  await page.click("#dgDelete");
  await page.waitForFunction(() => !document.querySelector(".dg-row"));
  check("deleting the summary removes only the summary", server.calls.some((c) => c[0] === "delete") && (await page.locator("article.mail").count()) > 0);
  check("no page errors", errors.length === 0);
  await context.close();
}
{
  const server = makeServer({ none: true });
  const { page, context } = await open(server);
  await page.waitForTimeout(300);
  check("with no summary there is no special row", await page.locator(".dg-row").count() === 0 && await page.locator("#digestStrip").isHidden());
  await context.close();
}
{
  const server = makeServer();
  const { page, context } = await open(server, { width: 390, height: 800 });
  await page.waitForSelector(".dg-row");
  check("phone: the row is tall enough to tap and fits", await page.evaluate(() => { const r = document.querySelector(".dg-row").getBoundingClientRect(); return r.height >= 44 && r.right <= innerWidth; }));
  await page.click(".dg-row");
  await page.waitForSelector("#digestView.open");
  check("phone: it opens full screen with Close and Delete reachable", await page.evaluate(() => { const r = document.getElementById("digestView").getBoundingClientRect(); const c = document.getElementById("dgClose").getBoundingClientRect(); return r.width >= innerWidth - 1 && r.height >= innerHeight - 1 && c.bottom <= innerHeight && c.height >= 44; }));
  await page.evaluate(() => { for (let i = 0; i < 40; i++) { const d = document.createElement("div"); d.className = "dg-item"; d.textContent = "More mail ".repeat(20); document.getElementById("dgBody").append(d); } });
  check("phone: with a long summary only the middle scrolls, and Close and Delete stay at the bottom", await page.evaluate(() => { const b = document.getElementById("dgBody"), c = document.getElementById("dgClose").getBoundingClientRect(), x = document.getElementById("dgDelete").getBoundingClientRect(); return b.scrollHeight > b.clientHeight && c.bottom <= innerHeight && x.bottom <= innerHeight; }));
  await shot(page, "daily-summary-phone");
  await context.close();
}
await browser.close();
if (failed) process.exit(1);
