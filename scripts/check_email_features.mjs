// Browser check for the optional email features on the Inbox page: New email with
// address-book suggestions, Sent (last 14 days), and pictures / attachments on demand.
// The page is loaded from a pretend Enveliq server (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_email_features.mjs [path/to/prototype/index.html]
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
    { address: "cara@example.invalid", name: "Cara Harris", count: 9, last: now, source: "sent" },
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
    if (p === "/api/v1/accounts/a1/messages") return json(200, [{ id: "m1", subject: "Holiday photos", sender_display: "Cara", sender_address: "cara@example.invalid", summary: "Photos.", priority: "normal", category: null, action_required: false, received_at: now - 600,
      reply_context: { reply_to: "cara@example.invalid", delivered_to: null, via_alias: null, message_id: "<m1@x>", references: [] } }]);
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
      { uid: 501, to: [{ name: "Cara Harris", address: "cara@example.invalid" }, { name: "", address: "sam@example.invalid" }], subject: "Dinner on Saturday", date: now - 3600 },
      { uid: 502, to: [{ name: "", address: "alex.chen@example.invalid" }], subject: "Re: Quote", date: now - 86400 * 3 }] }); }
    if (/\/(messages\/m1|sent\/7\/501)\/original$/.test(p)) return json(200, { subject: "Holiday photos", from: { name: "Cara", address: "cara@example.invalid" }, to: [{ name: "", address: "me@example.invalid" }], date: "Mon, 05 Oct 2026 18:20:00 +0000",
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
  const context = await browser.newContext({ viewport: { width, height }, acceptDownloads: true });
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

// ---- Everything on ----
{
  const server = makeServer();
  const { page, errors } = await open(server);
  check("New email button and Sent item are shown", (await page.locator("#newMailBtn").isVisible()) && (await page.locator("#sentNav").isVisible()));

  // New email: suggestions, chips, Cc/Bcc, attachment, send
  await page.click("#newMailBtn");
  check("New email opens with the mailbox and the work address to choose from", (await page.locator("#nmFrom option").allInnerTexts()).join("|") === "me@example.invalid|work@example.invalid");
  await page.locator("#nmTo input").fill("ale");
  await page.waitForSelector("#nmTo .suggest .sg");
  const sugs = await page.locator("#nmTo .sg .sg-who b").allInnerTexts();
  check("typing 'ale' suggests the two matching people from the address book", sugs.join("|") === "Alex Chen|Alexandra Moore");
  await shot(page, "nm-suggest");
  await page.keyboard.press("ArrowDown"); await page.keyboard.press("Enter");
  check("picking a suggestion makes a chip", (await page.locator("#nmTo .pchip").allInnerTexts()).join("").includes("Alex Chen"));
  await page.locator("#nmTo input").fill("sam@example.invalid"); await page.keyboard.press("Enter");
  await page.locator("#nmTo input").fill("not an address"); await page.keyboard.press("Enter");
  check("a bad address is refused and stays in the box", (await page.locator("#nmTo .pchip").count()) === 2 && (await page.locator("#nmTo input").inputValue()) === "not an address");
  await page.locator("#nmTo input").fill("");
  await page.click("#nmCcBtn"); await page.locator("#nmCc input").fill("eve@example.invalid"); await page.keyboard.press("Enter");
  await page.click("#nmBccBtn"); await page.locator("#nmBcc input").fill("frank@example.invalid"); await page.keyboard.press("Enter");
  await page.fill("#nmSubject", "Dinner on Saturday"); await page.fill("#nmText", "Hi both, are you free around 7?");
  await page.setInputFiles("#nmFile", { name: "Booking.pdf", mimeType: "application/pdf", buffer: Buffer.from("hello") });
  await page.waitForFunction(() => document.querySelector("#nmFiles")?.innerText.includes("Booking.pdf"), null, { timeout: 5000 }).catch(() => {});
  check("an attachment shows as a chip", (await page.locator("#nmFiles").innerText()).includes("Booking.pdf"));
  await shot(page, "nm-filled");
  await page.click("#nmCancel");
  check("Cancel with something typed asks again before throwing it away", (await page.locator("#nmCancel").innerText()).includes("Discard") && (await page.locator("#newMail").evaluate((e) => e.classList.contains("open"))));
  await page.click("#nmSend");
  await page.waitForFunction(() => !document.getElementById("newMail").classList.contains("open"));
  const sent = server.calls.find((c) => c[0] === "send")[1];
  check("Send posts recipients, cc, bcc, subject, text and the attachment as base64", JSON.stringify(sent.to) === JSON.stringify(["Alex Chen <alex.chen@example.invalid>", "sam@example.invalid"]) && sent.cc[0] === "eve@example.invalid" && sent.bcc[0] === "frank@example.invalid"
    && sent.subject === "Dinner on Saturday" && sent.files.length === 1 && Buffer.from(sent.files[0].data, "base64").toString() === "hello" && sent.from_address === "me@example.invalid");
  check("a sent confirmation is shown", (await page.locator("#toast").innerText()).includes("Email sent"));

  // Sent
  await page.click("#sentNav");
  await page.waitForSelector(".srow");
  check("Sent hides the inbox list and shows the notes", (await page.locator("#sentView").isVisible()) && !(await page.locator("#list").isVisible()) && (await page.locator(".sent-note").first().innerText()).includes("last 14 days"));
  check("rows show who it went to and the subject", (await page.locator(".swho").allInnerTexts()).join("|") === "Cara Harris +1|alex.chen@example.invalid" && (await page.locator(".ssub").first().innerText()) === "Dinner on Saturday");
  check("the tiny footer says it is limited to the last 14 days", (await page.locator("#sentFoot").innerText()) === "Limited to the last 14 days." && (await page.locator("#sentFoot").isVisible()));
  await page.locator(".shead").first().click();
  check("opening a row shows From, To and View original", (await page.locator(".sbody").first().innerText()).includes("From me@example.invalid to cara@example.invalid, sam@example.invalid"));
  await shot(page, "sent");
  await page.locator(".sbody button").first().click();
  await page.waitForSelector("#attachmentModal.open");
  check("View original opens the viewer with the sent label", (await page.locator("#viewerNote").innerText()).includes("Sent folder"));

  // Pictures
  check("remote pictures are reported as not shown, with no way to show them", (await page.locator(".mail-notice").innerText()).includes("3 pictures from the internet are not shown") && (await page.locator("#attachmentViewer").innerText()).indexOf("Show them") === -1);
  await page.waitForSelector(".pics .pic img");
  check("a picture that is part of the email shows by itself, from memory", (await page.locator(".pics img").getAttribute("src")).startsWith("blob:"));
  check("the PDF offers View and Save", (await page.locator(".att-row").nth(1).innerText()).includes("View") && (await page.locator(".att-row").nth(1).innerText()).includes("Save"));
  await page.locator(".att-row").first().locator("[data-pv]").click();
  await page.waitForSelector("#picImg:not([hidden])");
  check("Preview opens a viewer with the picture", (await page.locator("#picName").innerText()) === "lookout.png" && (await page.locator("#picCount").innerText()).includes("1 of 1 picture"));
  await shot(page, "pic");
  const [dl] = await Promise.all([page.waitForEvent("download"), page.click("#picSave")]);
  check("Save to my device downloads the file", dl.suggestedFilename() === "lookout.png");
  await page.keyboard.press("Escape");
  check("Escape closes the picture first", await page.locator("#picBox").isHidden());
  await page.locator(".att-row").nth(1).locator("[data-vw]").click();
  await page.waitForSelector("#docStage img.doc-page");
  check("View shows the PDF pages as pictures in the page", (await page.locator("#docStage img.doc-page").count()) === 2 && (await page.locator("#docCount").innerText()).includes("3 pages"));
  check("a note says only the first pages are shown", (await page.locator("#docStage").innerText()).includes("first 2 of 3"));
  const w0 = await page.locator("#docStage img.doc-page").first().evaluate((e) => e.getBoundingClientRect().width);
  await page.click("#docIn");
  check("zoom makes the pages bigger", (await page.locator("#docStage img.doc-page").first().evaluate((e) => e.getBoundingClientRect().width)) > w0);
  await shot(page, "doc");
  await page.keyboard.press("Escape");
  check("Escape closes the document viewer", await page.locator("#docBox").isHidden());
  const [dl2] = await Promise.all([page.waitForEvent("download"), page.locator(".att-row").nth(1).locator("[data-sv]").click()]);
  check("the PDF downloads under its own name", dl2.suggestedFilename() === "itinerary.pdf");
  check("pictures are requested as previews, the PDF is not", server.calls.some((c) => c[0] === "att0" && c[1] === "true") && server.calls.some((c) => c[0] === "att1" && c[1] === null));
  await page.keyboard.press("Escape");
  check("no script errors", errors.length === 0);
  await page.close();
}

// ---- A gentle check before a new email leaves: no subject, forgotten attachment ----
{
  const server = makeServer();
  const { page, errors } = await open(server);
  const fill = async (subject, text) => {
    await page.click("#newMailBtn");
    await page.locator("#nmTo input").fill("beth@example.invalid"); await page.keyboard.press("Enter");
    await page.fill("#nmSubject", subject); await page.fill("#nmText", text);
  };
  const sends = () => server.calls.filter((c) => c[0] === "send").length;
  await fill("", "Hi, are you free on Saturday?");
  await page.click("#nmSend");
  await page.waitForSelector("#sendWarn.open");
  check("no subject: a calm check appears and nothing has been sent", (await page.locator("#sendWarnList").innerText()).includes("no subject") && sends() === 0);
  await page.waitForFunction(() => document.activeElement && document.activeElement.id === "sendWarnNo");
  check("the safe button, Go back, has the focus", await page.evaluate(() => document.activeElement && document.activeElement.id === "sendWarnNo"));
  await shot(page, "send-warning");
  await page.click("#sendWarnNo");
  check("Go back keeps the email open and puts the cursor in the subject", (await page.locator("#newMail").evaluate((e) => e.classList.contains("open"))) && !(await page.locator("#sendWarn").evaluate((e) => e.classList.contains("open"))) && await page.evaluate(() => document.activeElement.id === "nmSubject"));
  await page.click("#nmSend"); await page.waitForSelector("#sendWarn.open");
  await page.keyboard.press("Escape");
  check("Escape closes the check and does not close the email", !(await page.locator("#sendWarn").evaluate((e) => e.classList.contains("open"))) && (await page.locator("#newMail").evaluate((e) => e.classList.contains("open"))) && sends() === 0);
  await page.click("#nmSend"); await page.waitForSelector("#sendWarn.open");
  await page.click("#sendWarnYes");
  await page.waitForFunction(() => !document.getElementById("newMail").classList.contains("open"));
  check("Send anyway sends it, once", sends() === 1 && server.calls.find((c) => c[0] === "send")[1].subject === "");

  await fill("Photos", "I have attached the photos.");
  await page.click("#nmSend"); await page.waitForSelector("#sendWarn.open");
  check("mentioning an attachment with none attached gets a check", (await page.locator("#sendWarnList").innerText()).includes("nothing is attached") && sends() === 1);
  await page.click("#sendWarnNo");
  await page.setInputFiles("#nmFile", { name: "photos.png", mimeType: "image/png", buffer: PNG });
  await page.waitForFunction(() => document.querySelector("#nmFiles")?.innerText.includes("photos.png"), null, { timeout: 5000 });
  await page.click("#nmSend");
  await page.waitForFunction(() => !document.getElementById("newMail").classList.contains("open"));
  check("with the file attached it sends with no check", sends() === 2);

  await fill("Photos", "Here you go.\n> the attached one is old\nSee you soon.");
  await page.click("#nmSend");
  await page.waitForFunction(() => !document.getElementById("newMail").classList.contains("open"));
  check("a quoted line that says 'attached' does not count", sends() === 3);

  await fill("Hello", "Just checking in.");
  await page.click("#nmSend");
  await page.waitForFunction(() => !document.getElementById("newMail").classList.contains("open"));
  check("an ordinary email sends with no check", sends() === 4);
  check("no script errors", errors.length === 0);
  await page.close();
}

// ---- Undo send for a new email ----
{
  const server = makeServer({ undo: 20 });
  const { page } = await open(server);
  await page.click("#newMailBtn");
  await page.locator("#nmTo input").fill("cara@example.invalid"); await page.keyboard.press("Enter");
  await page.setInputFiles("#nmFile", { name: "Booking.pdf", mimeType: "application/pdf", buffer: Buffer.from("hello") });
  await page.fill("#nmSubject", "Hold me"); await page.fill("#nmText", "Draft body");
  check("the hint says how long the email is held", (await page.locator("#nmHint").innerText()).includes("20 seconds"));
  await page.click("#nmSend");
  await page.waitForSelector("#sendBar .sendrow");
  check("the bar at the bottom says an email is on its way", (await page.locator("#sendBar").innerText()).includes("Sending your email to cara@example.invalid"));
  await page.click("#sendBar .sendrow button");
  await page.waitForSelector("#newMail.open");
  check("Undo brings the email back with its text and recipient", (await page.inputValue("#nmText")) === "Draft body" && (await page.inputValue("#nmSubject")) === "Hold me" && (await page.locator("#nmTo .pchip").count()) === 1);
  check("Undo keeps the attachment", (await page.locator("#nmFiles").innerText()).includes("Booking.pdf"));
  check("the user is told the attachments are back too", (await page.locator("body > #toast").innerText()).includes("attachments are back"));
  await page.click("#nmSend");
  await page.waitForSelector("#sendBar .sendrow");
  check("the restored attachment is sent again", server.calls.length > 0);
  await page.close();
}

// ---- Switched off ----
{
  const server = makeServer({ features: { compose: false, sent: false, address_book: false, media: false } });
  const { page } = await open(server);
  check("with everything off there is no New email button, no Sent and no pencil on a phone", (await page.locator("#newMailBtn").isHidden()) && (await page.locator("#sentNav").isHidden()) && (await page.locator("#mNewBtn").isHidden()));
  await page.locator("article.mail .subject").first().click().catch(() => {});
  await page.evaluate(() => openRealEmail(data.find((m) => m.real)));
  await page.waitForSelector("#attachmentModal.open");
  check("with previews off, attachments show their names only", (await page.locator(".att-row").first().innerText()).includes("Name only") && (await page.locator(".pics").count()) === 0);
  check("nothing was fetched for attachments or contacts", !server.calls.some((c) => /^att|contacts/.test(c[0])));
  await page.close();
}
{
  const server = makeServer({ features: { address_book: false } });
  const { page } = await open(server);
  await page.click("#newMailBtn");
  await page.locator("#nmTo input").fill("ale");
  await page.waitForTimeout(400);
  check("with the address book off no suggestions are asked for", !server.calls.some((c) => c[0] === "contacts") && (await page.locator("#nmTo .sg").count()) === 0);
  await page.close();
}

// ---- Phone ----
{
  const server = makeServer();
  const { page, csp } = await open(server, { width: 390, height: 800 });
  check("the pencil is in the top bar on a phone", await page.locator("#mNewBtn").isVisible());
  await page.click("#menuBtn");
  check("Sent is in the slide-out menu", await page.locator("#sentNav").isVisible());
  await page.click("#sentNav");
  await page.waitForSelector(".srow");
  check("the phone title says Sent", (await page.locator("#mTitle b").innerText()) === "Sent");
  check("no horizontal scroll on Sent", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  await shot(page, "sent-phone");
  await page.click("#mNewBtn");
  check("New email fits the phone", await page.evaluate(() => { const r = document.getElementById("newMail").getBoundingClientRect(); return r.left >= 0 && r.right <= window.innerWidth; }));
  await shot(page, "nm-phone");
  check("no Content-Security-Policy violations", csp.length === 0);
  await page.close();
}

await browser.close();
process.exit(failed ? 1 : 0);
