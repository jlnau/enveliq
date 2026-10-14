// Browser check for Drafts: the Save as draft / Discard question when a New, Reply, Reply all or Forward window is closed, and the Drafts page.
// The page is loaded from a pretend Enveliq server (Playwright intercepts the requests), so this needs no Python.
//   node scripts/check_drafts.mjs [path/to/prototype/index.html]     (SHOTS=<dir> saves screenshots)
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
const context = await browser.newContext({ viewport: { width: 1200, height: 900 } });
await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
await context.route(`${ORIGIN}/**`, handler);
await page.goto(`${ORIGIN}/`);
await page.waitForSelector("article.mail");
const expand = async (row) => { if (!(await row.evaluate((e) => e.classList.contains("open")))) await row.locator(".qmain").click(); };
const shot = async (name) => { if (SHOTS) await page.screenshot({ path: path.join(SHOTS, name + ".png") }); };
const asking = () => page.locator("#dkAsk.open").count();
const ccRow = page.locator("article.mail", { hasText: "Plan for May" });
await expand(ccRow);

check("the Drafts item is in the side menu", (await page.locator("#draftNav").count()) === 1);

// Reply: nothing written, so closing asks nothing
await ccRow.locator("[data-reply]").first().click();
await page.click("#composeCancel");
check("closing a reply you have not written in asks nothing", (await asking()) === 0 && (await page.locator("#compose.open").count()) === 0);

// Autosave: what is being written is saved by itself, and a closed page saves it once more
await expand(ccRow);
await ccRow.locator("[data-reply]").first().click();
await page.fill("#composeText", "Typed, then the browser closes.");
await page.waitForFunction(() => document.getElementById("cmAuto") && !document.getElementById("cmAuto").hidden, null, { timeout: 8000 }).catch(() => {});
check("a reply being written is saved to Drafts by itself, without closing it", drafts.length === 1 && drafts[0].body === "Typed, then the browser closes." && (await page.locator("#cmAuto").innerText()).includes("Saved to Drafts"));
await page.fill("#composeText", "Typed, then the browser closes. One more line.");
await page.evaluate(() => window.dispatchEvent(new Event("pagehide")));
await page.waitForTimeout(500);
check("closing the page saves the latest words once more, in the same draft", drafts.length === 1 && drafts[0].body.endsWith("One more line."));
await page.click("#composeCancel");
check("closing it afterwards says it is already in Drafts", (await asking()) === 1 && (await page.locator("#dkText").innerText()).includes("already in Drafts"));
await page.click("#dkDiscard");
await page.waitForTimeout(300);
check("Discard deletes the draft that was saved by itself", drafts.length === 0);

// Reply with text: Keep writing, Discard, then Save as draft
await expand(ccRow);
await ccRow.locator("[data-reply]").first().click();
await page.fill("#composeText", "Thanks, let me think.");
await page.click("#composeCancel");
check("closing a reply with writing in it asks to save as a draft", (await asking()) === 1 && (await page.locator("#dkSave").innerText()) === "Save as draft");
await shot("ask");
await page.click("#dkKeep");
check("Keep writing goes back to the reply with the text still there", (await asking()) === 0 && (await page.inputValue("#composeText")) === "Thanks, let me think.");
await page.keyboard.press("Escape");
check("Escape asks too", (await asking()) === 1);
await page.click("#dkDiscard");
check("Discard closes it and saves nothing", (await page.locator("#compose.open").count()) === 0 && drafts.length === 0);

await expand(ccRow);
await ccRow.locator("[data-reply]").first().click();
await page.fill("#composeText", "Thanks, let me think.");
await page.click("#composeClose");
await page.click("#dkSave");
await page.waitForFunction(() => !document.getElementById("compose").classList.contains("open"));
check("Save as draft keeps the reply on the server and closes the window", drafts.length === 1 && drafts[0].kind === "reply" && drafts[0].body === "Thanks, let me think." && drafts[0].to.join() === "alice@example.invalid" && drafts[0].message_id === "m-cc");
await page.waitForFunction(() => document.getElementById("draftBadge").textContent === "1", null, { timeout: 5000 }).catch(() => {});
check("the Drafts item shows how many drafts there are", (await page.locator("#draftBadge").innerText()) === "1");

// Reply all with Cc, Forward, and New email
await expand(ccRow);
await ccRow.locator("[data-reply-all]").first().click();
await page.fill("#composeText", "Agreed.");
await page.click("#composeCancel");
await page.click("#dkSave");
await page.waitForFunction(() => !document.getElementById("compose").classList.contains("open"));
check("a Reply all draft keeps the Cc people", drafts[1].kind === "reply_all" && drafts[1].cc.join() === "boss@example.invalid,sam@example.invalid" && drafts[1].to.length === 2);
await expand(ccRow);
await ccRow.locator("[data-forward]").first().click();
await page.fill("#cmTo input", "mum@example.invalid");
await page.locator("#cmTo input").press("Enter");
await page.click("#composeCancel");
check("closing a forward with someone in To asks to save it", (await asking()) === 1);
await page.click("#dkSave");
await page.waitForFunction(() => !document.getElementById("compose").classList.contains("open"));
check("a Forward draft keeps who it is for", drafts[2].kind === "forward" && drafts[2].to.join() === "mum@example.invalid");
await page.click("#newMailBtn");
await page.fill("#nmTo input", "pat@example.invalid");
await page.locator("#nmTo input").press("Enter");
await page.fill("#nmSubject", "Lunch");
await page.fill("#nmText", "See you at one.");
await page.click("#nmClose");
check("closing a New email with writing in it asks to save it", (await asking()) === 1);
await page.click("#dkSave");
await page.waitForFunction(() => !document.getElementById("newMail").classList.contains("open"));
check("a New email draft keeps people, subject and text", drafts[3].kind === "new" && drafts[3].subject === "Lunch" && drafts[3].body === "See you at one." && drafts[3].to.join() === "pat@example.invalid");
await page.click("#newMailBtn");
await page.click("#nmCancel");
check("closing an empty New email asks nothing", (await asking()) === 0 && (await page.locator("#newMail.open").count()) === 0);

// The Drafts page
if (!(await page.locator("#draftNav").isVisible())) await page.click("#moreToggle");
await page.click("#draftNav");
await page.waitForSelector(".drow");
check("the Drafts page lists all four, newest first", (await page.locator(".drow").count()) === 4 && (await page.locator(".drow .dkind").first().innerText()) === "New email");
check("the page is titled Drafts and offers Back to My inbox", (await page.locator(".top-left h2").innerText()) === "Drafts" && (await page.locator("#backInbox").isVisible()));
check("each draft says how long it is kept", (await page.locator(".drow").first().innerText()).includes("Kept 14 more days"));
await shot("drafts_page");
await page.locator(".drow", { hasText: "Thanks, let me think." }).locator("[data-draft-open]").click();
check("Continue writing opens the reply with its text back", (await page.inputValue("#composeText")) === "Thanks, let me think." && (await page.locator("#compose.open").count()) === 1);
await page.click("#composeCancel");
check("opening a draft and changing nothing closes without asking", (await asking()) === 0);
await page.locator(".drow", { hasText: "Thanks, let me think." }).locator("[data-draft-open]").click();
await page.fill("#composeText", "Thanks, I will do it Friday.");
await page.click("#composeCancel");
await page.click("#dkSave");
await page.waitForFunction(() => !document.getElementById("compose").classList.contains("open"));
check("saving a draft again replaces it, it does not add a new one", calls.some((c) => c[0] === "draft-put" && c[1].body === "Thanks, I will do it Friday.") && drafts.length === 4);
await page.locator(".drow", { hasText: "Lunch" }).locator("[data-draft-open]").click();
check("a New email draft opens as a New email", (await page.inputValue("#nmSubject")) === "Lunch" && (await page.locator("#nmTo .pchip").count()) === 1);
await page.click("#nmClose");
check("an unchanged New email draft closes without asking", (await asking()) === 0 && (await page.locator("#newMail.open").count()) === 0);

// Sending a draft removes it
await page.locator(".drow", { hasText: "Thanks, I will do it Friday." }).locator("[data-draft-open]").click();
await page.click("#composeSend");
await page.waitForFunction(() => !document.getElementById("compose").classList.contains("open"));
await page.waitForTimeout(300);
check("a draft that is sent is removed from Drafts", drafts.length === 3 && !drafts.some((d) => d.kind === "reply"));

// Deleting needs a second press
const del = page.locator(".drow").first().locator("[data-draft-del]");
await del.click();
check("Delete asks again first", (await del.innerText()) === "Delete this draft?" && drafts.length === 3);
await del.click();
await page.waitForTimeout(300);
check("pressing again deletes it", drafts.length === 2 && (await page.locator(".drow").count()) === 2);

check("no script errors on the page", errors.length === 0);
await browser.close();
process.exit(failed ? 1 : 0);
