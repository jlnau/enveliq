// Browser check for Reply all, Forward and the To / Cc / Bcc chips in the reply window.
// The page is loaded from a pretend Enveliq server (Playwright intercepts the requests), so this needs no Python.
//   node scripts/check_reply_all_forward.mjs [path/to/prototype/index.html]     (SHOTS=<dir> saves screenshots)
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
const messages = [
  { id: "m-cc", subject: "Plan for May", sender_display: "Alice", sender_address: "alice@example.invalid", summary: "A plan to read.", priority: "normal", category: null, action_required: false, received_at: now - 60,
    reply_context: { reply_to: "alice@example.invalid", delivered_to: null, via_alias: null, message_id: "<c@x>", references: [], cc: ["boss@example.invalid", "sam@example.invalid"], also_to: ["dan@example.invalid"] } },
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
  if (/\/messages\/[^/]+\/original$/.test(p)) return json(200, { subject: "Plan for May", from: { name: "Alice", address: "alice@example.invalid" }, to: [], date: "x", text: "Hello", truncated: false, attachments: [{ index: 0, filename: "plan.pdf", mime_type: "application/pdf", size_bytes: 20480, inline: false }, { index: 1, filename: "logo.png", mime_type: "image/png", size_bytes: 900, inline: true }] });
  if (/\/messages\/[^/]+\/(reply|forward)$/.test(p)) { calls.push([p.split("/").pop(), JSON.parse(req.postData())]); return json(200, { sent: true, from: "me@example.invalid" }); }
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "" });
  if (p === "/api/v1/me/contacts") return json(200, { items: [] });
  if (p === "/api/v1/me/tasks") return json(200, { today: "2026-10-14", tz: "UTC", now: Date.now() / 1000, tasks: [] });
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: {} });
  return json(404, { detail: "not found" });
};
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1200, height: 900 } });
await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
await context.route(`${ORIGIN}/**`, handler);
await page.goto(`${ORIGIN}/`);
await page.waitForSelector("article.mail");
const expand = async (row) => { if (!(await row.evaluate((e) => e.classList.contains("open")))) await row.locator(".qmain").click(); };
const chips = (sel) => page.locator(`${sel} .pchip span`).allInnerTexts();
const shot = async (name) => { if (SHOTS) await page.screenshot({ path: path.join(SHOTS, name + ".png") }); };

const ccRow = page.locator("article.mail", { hasText: "Plan for May" });
const plainRow = page.locator("article.mail", { hasText: "Just you" });
await expand(plainRow);
check("an email with no Cc has Reply and Forward but no Reply all", (await plainRow.locator("[data-reply]").count()) >= 1 && (await plainRow.locator("[data-forward]").count()) >= 1 && (await plainRow.locator("[data-reply-all]").count()) === 0);
await expand(ccRow);
check("an email with Cc also has Reply all", (await ccRow.locator("[data-reply-all]").count()) >= 1);

// Reply: one chip, Cc and Bcc are plain links that open a field
await ccRow.locator("[data-reply]").first().click();
check("reply starts with the sender as one chip and no Cc or Bcc field", (await chips("#cmTo")).join() === "alice@example.invalid" && await page.locator("#cmCcRow").isHidden() && await page.locator("#cmBccRow").isHidden());
check("Cc and Bcc are small text links", (await page.locator("#cmCcBtn").innerText()) === "Cc" && (await page.locator("#cmBccBtn").innerText()) === "Bcc");
await page.click("#cmCcBtn");
check("clicking Cc adds the Cc field", await page.locator("#cmCcRow").isVisible());
await page.fill("#cmCc input", "pat@example.invalid");
await page.press("#cmCc input", "Tab").catch(() => {});
await page.locator("#cmCc input").press("Enter");
await page.click("#cmBccBtn");
await page.fill("#cmBcc input", "quiet@example.invalid, other@example.invalid");
await page.locator("#cmBcc input").press("Enter");
check("addresses become chips with Enter, and a comma splits several", (await chips("#cmCc")).join() === "pat@example.invalid" && (await chips("#cmBcc")).length === 2);
await page.fill("#cmTo input", "not an address");
await page.locator("#cmTo input").press("Enter");
check("a bad address is not turned into a chip", (await chips("#cmTo")).length === 1);
await page.fill("#cmTo input", "");
await page.fill("#composeText", "Thanks.");
await shot("reply");
await page.click("#composeSend");
await page.waitForFunction(() => document.getElementById("toast").textContent.includes("Reply sent from"));
let sent = calls.at(-1);
check("a reply with Cc and Bcc sends all three lists", sent[0] === "reply" && sent[1].to.join() === "alice@example.invalid" && sent[1].cc.join() === "pat@example.invalid" && sent[1].bcc.length === 2 && sent[1].kind === "reply");
check("the message says it went to several people", (await page.locator("#toast").innerText()).includes("and 3 others"));

// Reply all
await page.waitForTimeout(300);
await expand(ccRow);
await ccRow.locator("[data-reply-all]").first().click();
check("Reply all puts the sender and the other To people in To", (await chips("#cmTo")).join() === "alice@example.invalid,dan@example.invalid");
check("Reply all puts the Cc people in Cc and shows the field", (await chips("#cmCc")).join() === "boss@example.invalid,sam@example.invalid" && await page.locator("#cmCcRow").isVisible());
check("Reply all says how many people it goes to", (await page.locator("#cmCount").innerText()) === "This goes to 4 people.");
await page.locator("#cmCc .pchip button").first().click();
check("anyone can be taken off", (await chips("#cmCc")).join() === "sam@example.invalid" && (await page.locator("#cmCount").innerText()) === "This goes to 3 people.");
await page.fill("#composeText", "Agreed.");
await shot("reply_all");
await page.click("#composeSend");
await page.waitForFunction(() => !document.getElementById("compose").classList.contains("open"));
sent = calls.at(-1);
check("Reply all sends the chosen people and says what kind it is", sent[0] === "reply" && sent[1].kind === "reply_all" && sent[1].to.join() === "alice@example.invalid,dan@example.invalid" && sent[1].cc.join() === "sam@example.invalid");
check("by default the server is told to add the original email under the reply", sent[1].add_original === true);

// The original can instead be put into the message itself, where it can be edited; then it is not added twice
await page.waitForTimeout(300);
await expand(ccRow);
await ccRow.locator("[data-reply]").first().click();
check("a reply says the original is added under it when sent, and offers to put it in the message", (await page.locator("#composeQuote").textContent()).includes("added under your reply when you press Send") && await page.locator("#cmQuoteIn").isVisible());
await page.fill("#composeText", "Thanks for this.");
await page.click("#cmQuoteIn");
await page.waitForFunction(() => document.getElementById("composeText").value.includes("> Hello"));
const inline = await page.inputValue("#composeText");
check("the button puts 'On <date>, <name> <address> wrote:' and the quoted text under the message", inline.startsWith("Thanks for this.") && inline.includes("wrote:\n> Hello") && inline.includes("Alice <alice@example.invalid>"));
await page.fill("#composeText", inline.replace("> Hello", "> Hello (cut down)"));
await shot("reply_inline");
await page.click("#composeSend");
await page.waitForFunction(() => !document.getElementById("compose").classList.contains("open"));
sent = calls.at(-1);
check("a message that already has the original in it tells the server not to add it again", sent[0] === "reply" && sent[1].add_original === false && sent[1].body.includes("> Hello (cut down)"));

// Forward: empty To, Fwd subject, the original's files as removable chips
await page.waitForTimeout(300);
await expand(ccRow);
await ccRow.locator("[data-forward]").first().click();
await page.waitForSelector("#cmFiles .nm-file");
check("Forward starts with nobody in To and a Fwd: subject", (await chips("#cmTo")).length === 0 && (await page.inputValue("#composeSubject")) === "Fwd: Plan for May" && (await page.locator("#composeTitle").innerText()).startsWith("Forward"));
check("the original's files are offered, pictures inside the text are not", (await page.locator("#cmFiles .nm-file").count()) === 1 && (await page.locator("#cmFiles").innerText()).includes("plan.pdf"));
await page.click("#composeSend");
check("Forward will not send to nobody", calls.at(-1)[0] === "reply" && (await page.locator("#compose.open").count()) === 1);
await page.fill("#cmTo input", "mum@example.invalid");
await page.locator("#cmTo input").press("Enter");
await page.click("#cmBccBtn");
await page.fill("#cmBcc input", "me@example.invalid");
await page.locator("#cmBcc input").press("Enter");
await page.fill("#composeText", "Have a look.");
await shot("forward");
await page.click("#composeSend");
await page.waitForFunction(() => !document.getElementById("compose").classList.contains("open"));
sent = calls.at(-1);
check("Forward sends the people, the note and which files to keep", sent[0] === "forward" && sent[1].to.join() === "mum@example.invalid" && sent[1].bcc.join() === "me@example.invalid" && sent[1].body === "Have a look." && sent[1].keep_files.join() === "0");
await page.waitForTimeout(300);
await expand(ccRow);
await ccRow.locator("[data-forward]").first().click();
await page.waitForSelector("#cmFiles .nm-file");
await page.click("#cmFiles .nm-file button");
await page.fill("#cmTo input", "mum@example.invalid");
await page.locator("#cmTo input").press("Enter");
await page.click("#composeSend");
await page.waitForFunction(() => !document.getElementById("compose").classList.contains("open"));
check("a file taken off the list is not sent", calls.at(-1)[1].keep_files.length === 0);

check("no script errors on the page", errors.length === 0);
await browser.close();
process.exit(failed ? 1 : 0);
