// Browser check for "Signature and saved replies": the signature is put in the message box when it opens (new email
// and reply), a signature alone does not count as a message, saved replies are inserted at the cursor, and Settings
// lets a person edit all of it. The pages are served from the real files; the server is pretended.
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_saved_writing.mjs [path/to/prototype/index.html]
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, "..");
const html = fs.readFileSync(path.resolve(process.argv[2] || path.join(root, "prototype", "index.html")), "utf8");
const css = fs.readFileSync(path.join(root, "web", "static", "auth.css"), "utf8");
const embed = ["welcome.js", "auth.js"].map((n) => fs.readFileSync(path.join(root, "web", "static", n), "utf8")).join("\n");
const ORIGIN = "http://enveliq.test";
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
for (const ev of ["uncaughtException", "unhandledRejection"]) process.on(ev, (e) => { console.log("::error::" + String((e && e.message) || e).split("\n").slice(0, 3).join(" | ")); process.exit(1); });
const now = Math.floor(Date.now() / 1000);
const LIMITS = { signature: 1000, replies: 30, title: 60, text: 3000 };

function makeServer(initial) {
  let signature = initial.signature || "", replies = (initial.replies || []).map((r, i) => ({ id: "r" + String(i).padStart(16, "0"), ...r }));
  let next = replies.length;
  const calls = [];
  const view = () => ({ signature, replies, limits: LIMITS });
  const handler = async (route) => {
    const req = route.request(), u = new URL(req.url()), p = u.pathname, m = req.method();
    const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (u.origin !== ORIGIN) return route.fulfill({ status: 200, contentType: "text/html", body: "<title>elsewhere</title>" });
    if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
    if (p === "/static/auth.css") return route.fulfill({ status: 200, contentType: "text/css", body: css });
    if (p === "/embed.js") return route.fulfill({ status: 200, contentType: "text/javascript", body: embed });
    if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
    if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
    if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin", session: { state: "full" }, security: { totp_enabled: true, passkeys: [] } });
    if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1144, username: "u", settings: {} }]);
    if (p === "/api/v1/accounts/a1/messages") return json(200, [{ id: "m1", subject: "Holiday photos", sender_display: "Beth", sender_address: "beth@example.invalid", summary: "Photos.", priority: "normal", category: null, action_required: false, received_at: now - 600,
      reply_context: { reply_to: "beth@example.invalid", delivered_to: null, via_alias: null, message_id: "<m1@x>", references: [] } }]);
    if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
    if (p === "/api/v1/me/features") { const f = { compose: true, address_book: false, sent: false, media: false }; return json(200, { effective: f, admin: f, user: f, labels: {} }); }
    if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: now } } });
    if (p === "/api/v1/accounts/a1/send") { calls.push(["send", JSON.parse(req.postData())]); return json(200, { sent: true, from: "me@example.invalid" }); }
    if (/\/api\/v1\/accounts\/a1\/messages\/m1\/reply$/.test(p)) { calls.push(["reply", JSON.parse(req.postData())]); return json(200, { sent: true, from: "me@example.invalid" }); }
    if (p === "/api/v1/me/saved" && m === "GET") return json(200, view());
    if (p === "/api/v1/me/saved/signature" && m === "PUT") { signature = JSON.parse(req.postData()).text.trim(); calls.push(["sig", signature]); return json(200, view()); }
    if (p === "/api/v1/me/saved/replies" && m === "POST") {
      const b = JSON.parse(req.postData()); calls.push(["add", b]);
      if (!b.title.trim() || !b.text.trim()) return json(422, { detail: "Give the reply a short name and some text." });
      replies = [...replies, { id: "r" + String(100 + next++).padStart(16, "0"), title: b.title.trim(), text: b.text.trim() }]; return json(200, view());
    }
    let mm = p.match(/^\/api\/v1\/me\/saved\/replies\/(r[0-9]{16})$/);
    if (mm && m === "PUT") { const b = JSON.parse(req.postData()); calls.push(["edit", mm[1], b]); replies = replies.map((r) => r.id === mm[1] ? { ...r, title: b.title.trim(), text: b.text.trim() } : r); return json(200, view()); }
    if (mm && m === "DELETE") { calls.push(["remove", mm[1]]); replies = replies.filter((r) => r.id !== mm[1]); return json(200, view()); }
    return json(404, { detail: "not found" });
  };
  return { handler, calls };
}

const browser = await chromium.launch();
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };
async function open(server, width = 1200, height = 900) {
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route("**/*", server.handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  return { page, errors, context };
}
const SIG = "Thanks,\nMorgan";

// ---- a signature and two saved replies ----
{
  const server = makeServer({ signature: SIG, replies: [{ title: "Running late", text: "I am running a little late and will be there soon." }, { title: "Thank you", text: "Thank you, that is very kind." }] });
  const { page, errors } = await open(server);
  await page.click("#newMailBtn");
  check("a new email opens with the signature already in the box, below an empty line", (await page.inputValue("#nmText")) === "\n\n" + SIG);
  check("the saved replies are offered, and the first line of the box is where the cursor goes", (await page.locator("#nmSaved option").allInnerTexts()).join("|") === "Insert a saved reply…|Running late|Thank you" && (await page.locator("#nmSavedRow").isVisible()));
  await page.click("#nmCancel");
  check("a box with only the signature is not 'something typed': Cancel closes it without asking", !(await page.locator("#newMail").evaluate((e) => e.classList.contains("open"))));
  await page.click("#newMailBtn");
  await page.locator("#nmTo input").fill("beth@example.invalid"); await page.keyboard.press("Enter");
  await page.click("#nmSend");
  check("a signature alone is not a message: it asks for a subject or a message and sends nothing", (await page.locator("#toast").innerText()).includes("Add a subject or a message first") && server.calls.filter((c) => c[0] === "send").length === 0);
  await page.fill("#nmSubject", "Hello");
  // put the cursor at the start and insert a saved reply
  await page.locator("#nmText").focus();
  await page.evaluate(() => document.getElementById("nmText").setSelectionRange(0, 0));
  await page.selectOption("#nmSaved", { label: "Running late" });
  const v = await page.inputValue("#nmText");
  check("choosing a saved reply puts it at the cursor, above the signature", v === "I am running a little late and will be there soon.\n\n" + SIG);
  check("the chooser goes back to its first line", (await page.inputValue("#nmSaved")) === "");
  await shot(page, "saved-newmail");
  await page.click("#nmSend");
  await page.waitForFunction(() => !document.getElementById("newMail").classList.contains("open"));
  const sent = server.calls.find((c) => c[0] === "send")[1];
  check("what is sent is exactly what was in the box", sent.body === "I am running a little late and will be there soon.\n\n" + SIG && sent.subject === "Hello");

  // reply
  await page.locator("article.mail .qmain").first().click();
  await page.locator("[data-reply]").first().click();
  await page.waitForSelector("#compose.open");
  check("a reply opens with the signature too", (await page.inputValue("#composeText")) === "\n\n" + SIG);
  check("and the saved replies are offered there", (await page.locator("#composeSaved option").count()) === 3);
  await page.click("#composeSend");
  check("a signature alone is not a reply: it asks for your words first", (await page.locator("#toast").innerText()).includes("Write your reply first") && server.calls.filter((c) => c[0] === "reply").length === 0);
  await page.selectOption("#composeSaved", { label: "Thank you" });
  await page.click("#composeSend");
  await page.waitForFunction(() => !document.getElementById("compose").classList.contains("open"));
  const rep = server.calls.find((c) => c[0] === "reply")[1];
  check("a saved reply sends from a reply box, with the signature below", rep.body === "Thank you, that is very kind.\n\n" + SIG);
  check("no script errors", errors.length === 0);
  await page.close();
}

// ---- nothing saved: the boxes are plain ----
{
  const server = makeServer({});
  const { page } = await open(server);
  await page.click("#newMailBtn");
  check("with no signature the box is empty and no saved-reply chooser shows", (await page.inputValue("#nmText")) === "" && !(await page.locator("#nmSavedRow").isVisible()));
  await page.close();
}

// ---- Settings ----
{
  const server = makeServer({ signature: SIG, replies: [{ title: "Running late", text: "I am running a little late." }] });
  const { page, errors } = await open(server);
  await page.evaluate(() => openSettings("settings"));
  await page.waitForTimeout(300);
  check("Settings has a Signature & saved replies page", (await page.locator('#settingsNav [data-settings-tab~="saved"]').innerText()).includes("People & writing"));
  await page.evaluate(() => document.querySelector('#settingsNav [data-settings-tab~="saved"]').click());
  const host = page.locator('[data-settings-panel="saved"] .embed-host');
  await host.locator("#sv_sig").waitFor({ timeout: 8000 });
  const text = () => host.evaluate((h) => h.shadowRoot.textContent);
  check("it shows the signature and the saved reply", (await host.locator("#sv_sig").inputValue()) === SIG && /Running late/.test(await text()));
  await shot(page, "saved-settings");
  await host.locator("#sv_sig").fill("Best wishes,\nMorgan");
  await host.locator("button", { hasText: "Save signature" }).click();
  await page.waitForFunction(() => true);
  await page.waitForTimeout(300);
  check("saving the signature sends it", server.calls.some((c) => c[0] === "sig" && c[1] === "Best wishes,\nMorgan"));
  await host.locator("#sv_title").fill("");
  await host.locator("button", { hasText: "Save reply" }).click();
  await page.waitForTimeout(300);
  check("a reply with no name or text is refused in plain words", /short name and some text/.test(await host.locator("#toast").innerText()));
  await host.locator("#sv_title").fill("Thank you");
  await host.locator("#sv_text").fill("Thank you, that is very kind.");
  await host.locator("button", { hasText: "Save reply" }).click();
  await page.waitForFunction(() => document.querySelector('[data-settings-panel="saved"] .embed-host').shadowRoot.textContent.includes("Thank you, that is very kind."));
  check("a new saved reply appears in the list", server.calls.some((c) => c[0] === "add" && c[1].title === "Thank you"));
  await host.locator("button", { hasText: "Edit" }).first().click();
  check("Edit fills the form and the button says Update", (await host.locator("#sv_title").inputValue()) === "Running late" && (await host.locator("button", { hasText: "Update reply" }).count()) === 1);
  await host.locator("#sv_text").fill("I am running late.");
  await host.locator("button", { hasText: "Update reply" }).click();
  await page.waitForFunction(() => document.querySelector('[data-settings-panel="saved"] .embed-host').shadowRoot.textContent.includes("I am running late."));
  check("updating changes the reply", server.calls.some((c) => c[0] === "edit" && c[2].text === "I am running late."));
  await host.locator('button[aria-label="Remove Thank you"]').click();
  await page.waitForFunction(() => !document.querySelector('[data-settings-panel="saved"] .embed-host').shadowRoot.textContent.includes("that is very kind"));
  check("removing a saved reply takes it off the list", server.calls.some((c) => c[0] === "remove"));
  check("no script errors", errors.length === 0);
  await page.close();
}

await browser.close();
if (failed) process.exit(1);
console.log("All Signature and saved replies checks passed.");
