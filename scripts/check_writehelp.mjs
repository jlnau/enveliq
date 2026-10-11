// Browser check for Writing help (v0.64): the button in the reply and New email boxes, the second "Suggested by AI" box,
// Accept / Put my version back, and the check before sending (only when writing help was used). Pretend Enveliq server.
//
// Usage: node scripts/check_writehelp.mjs [path/to/prototype/index.html]
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
const SUGGESTION = "Hi Dana,\n\nThanks for asking. I can make Tuesday at [time].\n\nThanks,\n[your name]";

function makeServer(opts = {}) {
  const calls = [];
  const features = { compose: true, address_book: true, sent: true, media: true, all_mail: false, shipping: false, waiting: false, messages: false, write_help: opts.feature !== false };
  const info = { available: true, on: opts.on !== false, ai_ready: true, instructions: "x", is_default: true, default: "x", max: 2000 };
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
    if (p === "/api/v1/me/write-help/new") { calls.push(["helpnew", body().draft, body().subject]); return json(200, { text: "Hi all,\n\nDinner is at seven.", notes: [], gaps: false }); }
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
  const errors = [], csp = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (/Content Security Policy|Refused to/.test(m.text())) csp.push(m.text()); });
  await context.route(`${ORIGIN}/**`, server.handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  return { page, errors, csp, context };
}
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };
async function openReply(page) {
  await page.locator("article.mail").first().click();
  await page.locator("article.mail [data-reply]").first().click();
  await page.waitForSelector("#compose.open");
}

// ---- computer-sized window ----
{
  const server = makeServer();
  const { page, errors, csp, context } = await open(server);
  await openReply(page);
  check("the reply box has a Write a reply for me button while the box is empty", (await page.locator("#whBtn_reply").innerText()) === "Write a reply for me");
  check("there is no AI box until it is asked for", (await page.locator("#whSug_reply").count()) === 0);
  await page.click("#whBtn_reply");
  await page.waitForSelector("#whSug_reply");
  check("an empty box is allowed: the server is asked with no draft", server.calls.some((c) => c[0] === "help" && c[1] === ""));
  const box = await page.locator("#whSug_reply").innerText();
  check("the suggestion is in a second box labelled Suggested by AI, with Nothing here is sent", box.includes("Suggested by AI") && box.includes("Nothing here is sent") && box.includes("Thanks for asking"));
  check("the person's own box is still empty", (await page.inputValue("#composeText")) === "");
  check("the bracket gap is pointed out", box.includes("Check the [brackets]"));
  await shot(page, "writehelp-reply");

  await page.getByRole("button", { name: "Accept", exact: true }).click();
  check("Accept puts the suggestion in the person's box", (await page.inputValue("#composeText")).includes("Thanks for asking"));
  check("the button now offers to check", (await page.locator("#whBtn_reply").innerText()) === "Check my reply");
  await page.getByRole("button", { name: "Put my version back" }).click();
  check("Put my version back restores what was there", (await page.inputValue("#composeText")) === "");

  await page.fill("#composeText", "yes tuesday ok");
  check("with text in the box the button says Check my reply", (await page.locator("#whBtn_reply").innerText()) === "Check my reply");
  await page.click("#whBtn_reply");
  await page.waitForFunction(() => document.getElementById("whSug_reply") && !document.getElementById("whBtn_reply").disabled);
  check("the draft goes to the server and the box is not changed by the AI", server.calls.some((c) => c[0] === "help" && c[1] === "yes tuesday ok") && (await page.inputValue("#composeText")) === "yes tuesday ok");
  check("Accept says it replaces the text", (await page.locator("#whSug_reply").innerText()).includes("Accept (replaces my text)"));

  // sending with an open suggestion that was not used
  await page.click("#composeSend");
  await page.waitForSelector("#whCheck.open");
  check("sending after using writing help asks first, and says only the box is sent", (await page.locator("#whCheckMsg").innerText()).includes("Only what is in your box will be sent") && (await page.locator("#whCheckText").innerText()) === "yes tuesday ok");
  await page.click("#whCheckNo");
  check("Go back sends nothing", !server.calls.some((c) => c[0] === "reply") && (await page.inputValue("#composeText")) === "yes tuesday ok");

  // accepted wording with a gap
  await page.getByRole("button", { name: "Accept (replaces my text)" }).click();
  await page.click("#composeSend");
  await page.waitForSelector("#whCheck.open");
  check("accepted AI wording is named, and a [bracket] left in it is flagged", (await page.locator("#whCheckMsg").innerText()).includes("suggested by AI") && !(await page.locator("#whCheckGap").isHidden()) && (await page.locator("#whCheckYes").innerText()) === "Send anyway");
  await shot(page, "writehelp-check");
  await page.click("#whCheckNo");
  await page.fill("#composeText", "Hi Dana,\n\nYes, I can make Tuesday at 10.\n\nThanks");
  await page.click("#composeSend");
  await page.waitForSelector("#whCheck.open");
  check("with no gaps the button says Yes, send it", (await page.locator("#whCheckYes").innerText()) === "Yes, send it" && (await page.locator("#whCheckGap").isHidden()));
  await page.click("#whCheckYes");
  await page.waitForFunction(() => !document.getElementById("compose").classList.contains("open"));
  check("confirming sends exactly what is in the person's box", server.calls.filter((c) => c[0] === "reply").length === 1 && server.calls.find((c) => c[0] === "reply")[1] === "Hi Dana,\n\nYes, I can make Tuesday at 10.\n\nThanks");

  // a reply that never used writing help is not slowed down
  await page.waitForTimeout(300);
  await page.locator("article.mail").first().click().catch(() => {});
  check("no console errors or CSP problems", errors.length === 0 && csp.length === 0);
  await context.close();
}

// ---- an ordinary reply: no check ----
{
  const server = makeServer();
  const { page, context } = await open(server);
  await openReply(page);
  await page.fill("#composeText", "Yes, Tuesday works.");
  await page.click("#composeSend");
  await page.waitForFunction(() => !document.getElementById("compose").classList.contains("open"));
  check("a reply written without writing help sends straight away", server.calls.some((c) => c[0] === "reply") && (await page.locator("#whCheck.open").count()) === 0);
  await context.close();
}

// ---- hostile suggestion, failures, switched off ----
{
  const server = makeServer({ suggestion: "<img src=x onerror=window.__pwned=1>Hello" });
  const { page, context } = await open(server);
  await openReply(page);
  await page.click("#whBtn_reply");
  await page.waitForSelector("#whSug_reply");
  check("a hostile suggestion is shown as text only", (await page.locator("#whSug_reply img").count()) === 0 && (await page.evaluate(() => window.__pwned)) === undefined);
  await context.close();
}
{
  const server = makeServer({ fail: true });
  const { page, context } = await open(server);
  await openReply(page);
  await page.click("#whBtn_reply");
  await page.waitForFunction(() => document.querySelector("#composeWh [role=alert]"));
  check("when the AI cannot be reached a plain message is shown and the box is untouched", (await page.locator("#composeWh [role=alert]").innerText()).includes("could not be reached") && (await page.locator("#whSug_reply").count()) === 0);
  await context.close();
}
{
  const server = makeServer({ on: false });
  const { page, context } = await open(server);
  await openReply(page);
  check("until the person turns it on there is only a short pointer to Settings", (await page.locator("#whBtn_reply").count()) === 0 && (await page.locator("#composeWh").innerText()).includes("turn on Writing help in Settings"));
  await context.close();
}
{
  const server = makeServer({ feature: false });
  const { page, context } = await open(server);
  await openReply(page);
  check("when the feature is off nothing about it shows", await page.locator("#composeWh").isHidden());
  await context.close();
}

// ---- New email ----
{
  const server = makeServer();
  const { page, context } = await open(server);
  await page.click("#newMailBtn");
  await page.waitForSelector("#newMail.open");
  check("New email has Help me write", (await page.locator("#whBtn_new").innerText()) === "Help me write");
  await page.fill("#nmSubject", "Dinner on Friday");
  await page.click("#whBtn_new");
  await page.waitForSelector("#whSug_new");
  check("the subject goes along, the box is not changed and the suggestion is labelled", server.calls.some((c) => c[0] === "helpnew" && c[2] === "Dinner on Friday") && (await page.inputValue("#nmText")) === "" && (await page.locator("#whSug_new").innerText()).includes("Suggested by AI"));
  await page.getByRole("button", { name: "Accept", exact: true }).click();
  check("Accept fills the New email box", (await page.inputValue("#nmText")).includes("Dinner is at seven"));
  await context.close();
}

// ---- a phone ----
{
  const server = makeServer();
  const { page, context } = await open(server, { width: 390, height: 800 });
  await openReply(page);
  await page.click("#whBtn_reply");
  await page.waitForSelector("#whSug_reply");
  const sizes = await page.evaluate(() => [...document.querySelectorAll("#composeWh button")].map((b) => Math.round(b.getBoundingClientRect().height)));
  check("phone: the writing help buttons are at least 44px tall", sizes.length >= 4 && sizes.every((h) => h >= 44));
  check("phone: nothing sticks out sideways", await page.evaluate(() => document.getElementById("compose").scrollWidth <= document.getElementById("compose").clientWidth + 1));
  await shot(page, "writehelp-phone");
  await context.close();
}

await browser.close();
if (failed) process.exit(1);
