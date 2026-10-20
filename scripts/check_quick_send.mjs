// Browser check for Quick AI Send: the button beside Send in the reply and New email boxes,
// it proofreads and sends at once, and keeps the draft when anything fails. Pretend Enveliq server.
//
// Usage: node scripts/check_quick_send.mjs [path/to/prototype/index.html]
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
  await page.evaluate(() => { view.layout = "list"; applyView(); render(); });
  return { page, errors, context };
}
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };
async function openReply(page) {
  await page.locator("article.mail").first().click();
  await page.locator("article.mail [data-reply]").first().click();
  await page.waitForSelector("#compose.open");
}
{
  const server = makeServer();
  const { page, errors, context } = await open(server);
  await openReply(page);
  await page.waitForFunction(() => !document.getElementById("composeQuick").hidden);
  check("Quick AI Send sits beside Send", (await page.locator("#composeQuick").innerText()).includes("Quick AI"));
  await page.fill("#composeText", "yes tuesday ok");
  await page.click("#composeQuick");
  await page.waitForFunction(() => !document.getElementById("compose").classList.contains("open"));
  check("the draft goes to the AI check, then the corrected text is sent with no extra question", server.calls.some((c) => c[0] === "quick" && c[1] === "yes tuesday ok") && server.calls.find((c) => c[0] === "reply")?.[1] === "Hi Dana,\n\nYes, Tuesday works." && (await page.locator("#whCheck.open").count()) === 0);
  check("no page errors", errors.length === 0);
  await context.close();
}
{
  const server = makeServer({ fail: true });
  const { page, context } = await open(server);
  await openReply(page);
  await page.waitForFunction(() => !document.getElementById("composeQuick").hidden);
  await page.fill("#composeText", "yes tuesday ok");
  await page.click("#composeQuick");
  await page.waitForFunction(() => !document.getElementById("composeQuick").disabled);
  await page.waitForTimeout(200);
  check("when the AI fails nothing is sent and the draft is untouched", !server.calls.some((c) => c[0] === "reply") && (await page.inputValue("#composeText")) === "yes tuesday ok" && await page.locator("#compose.open").count() === 1);
  await context.close();
}
{
  const server = makeServer({ quick: false });
  const { page, context } = await open(server);
  await openReply(page);
  await page.waitForTimeout(300);
  check("switched off: no Quick AI Send button", await page.locator("#composeQuick").isHidden());
  await context.close();
}
{
  const server = makeServer();
  const { page, context } = await open(server);
  await page.click("#newMailBtn");
  await page.waitForSelector("#newMail.open");
  await page.waitForFunction(() => !document.getElementById("nmQuick").hidden);
  check("New email has Quick AI Send", true);
  await context.close();
}
{
  const server = makeServer();
  const { page, context } = await open(server, { width: 390, height: 800 });
  await page.evaluate(() => { lay = () => view.layout; render(); });
  await openReply(page);
  await page.waitForFunction(() => !document.getElementById("composeQuick").hidden);
  const h = await page.evaluate(() => Math.round(document.getElementById("composeQuick").getBoundingClientRect().height));
  check("phone: the button is at least 44px tall and nothing sticks out", h >= 44 && await page.evaluate(() => document.getElementById("compose").scrollWidth <= document.getElementById("compose").clientWidth + 1));
  await shot(page, "quicksend-phone");
  await context.close();
}
await browser.close();
if (failed) process.exit(1);
