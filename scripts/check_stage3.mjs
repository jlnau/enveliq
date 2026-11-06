// Browser check for Stage 3: move an email into a folder (picker, new folder, Undo, several at once) and the Folders page.
// The page is loaded from a pretend Enveliq server (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_stage3.mjs [path/to/prototype/index.html]
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
let messages, posts, prints, sent, madeFolder;
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
  if (p === "/api/v1/accounts/a1/folders" && m === "GET") return json(200, { folders: [
    { name: "Folders/Bills", label: "Bills", special: false, target: true }, { name: "Folders/Holidays", label: "Holidays", special: false, target: true },
    ...(madeFolder ? [{ name: "Folders/Receipts", label: "Receipts", special: false, target: true }] : []),
    { name: "Archive", label: "Archive", special: true, target: false }, { name: "Trash", label: "Bin", special: true, target: false } ] });
  if (p === "/api/v1/accounts/a1/folders" && m === "POST") { const b = JSON.parse(req.postData() || "{}"); posts.push(["make", "", b]); madeFolder = true; return json(201, { name: "Folders/" + b.name, label: b.name, special: false, target: true }); }
  if (/\/messages\/[^/]+\/move$/.test(p) && m === "POST") { posts.push(["move", p.split("/")[6], JSON.parse(req.postData() || "{}")]); messages = messages.filter((x) => x.id !== p.split("/")[6]); return route.fulfill({ status: 204 }); }
  if (/\/folder-mail\/[^/]+\/(move|bin|archive|star)$/.test(p) && m === "POST") { posts.push(["fm-" + p.split("/")[5], p.split("/")[4], JSON.parse(req.postData() || "{}")]); return route.fulfill({ status: 204 }); }
  if (/\/folder-mail\/[^/]+\/keep$/.test(p) && m === "POST") { posts.push(["fm-keep", p.split("/")[4], {}]); return json(200, { already: false, account_id: "a1", message_id: "kept1" }); }
  if (p === "/api/v1/accounts/a1/folder-mail") return json(200, { rows: [{ token: "tok1.mac", from_name: "Power Co", from_address: "bills@example.invalid", subject: "March bill", date: now - 86400, has_files: false }, { token: "tok2.mac", from_name: "Water Co", from_address: "water@example.invalid", subject: "Water notice", date: now - 172800, has_files: false }], total: 2, more: false, now });
  if (/\/folder-mail\/[^/]+\/original$/.test(p)) { posts.push(["open", p.split("/")[4], {}]); return json(200, { from: { name: "Power Co", address: "bills@example.invalid" }, to: [{ address: "me@example.invalid" }], date: "Today", subject: "March bill", text: "Plain words of the bill.", links: [], has_html: false, attachments: [] }); }
  if (p === "/api/v1/me/important" && m === "POST") { posts.push(["important", "", JSON.parse(req.postData() || "{}")]); return json(200, { items: [{ address: "bills@example.invalid", name: "Power Co" }] }); }
  if (p === "/api/v1/me/important" && m === "GET") return json(200, { items: [{ address: "bills@example.invalid", name: "Northside Power" }] });
  if (p === "/api/v1/me/rules" && m === "POST") { posts.push(["rule", "", JSON.parse(req.postData() || "{}")]); return json(200, { rules: [], actions: {}, max: 50 }); }
  if (p === "/api/v1/me/rules") return json(200, { rules: [], actions: {}, max: 50 });
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
  messages = make(); madeFolder = false; posts = []; prints = 0; sent = [];
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
  await pick(page, "Trip plans");
  await page.locator(".qmore").first().click();
  check(tag + "the three-dot menu has Move to folder", (await menuTexts(page)).includes("Move to folder…"));
  await page.locator("#moreMenu [data-move-folder]").click();
  await page.waitForSelector("#folderPick .fpick-item");
  const items = await page.locator("#folderPick .fpick-item").allInnerTexts();
  check(tag + "the picker lists only folders you can move into (not Archive or Bin)", items.join("|") === "Bills|Holidays");
  await shot(page, "stage3-picker-" + width);
  if (width < 600) check(tag + "on a phone the picker fills the screen", await page.locator("#folderPick").evaluate((el) => { const r = el.getBoundingClientRect(); return r.left <= 1 && r.top <= 1 && r.width >= innerWidth - 2 && r.height >= innerHeight - 2; }));
  await page.fill("#fpFind", "hol");
  check(tag + "typing narrows the list", (await page.locator("#folderPick .fpick-item").allInnerTexts()).join("|") === "Holidays");
  await page.locator("#folderPick .fpick-item", { hasText: "Holidays" }).click();
  await page.waitForSelector("#undoBar .undobar");
  check(tag + "an Undo bar says where it is going", /Moved to Holidays/.test(await page.locator("#undoBar").innerText()));
  await page.locator("#undoBar button", { hasText: "Undo" }).click();
  await page.waitForTimeout(200);
  check(tag + "Undo brings it back and nothing was sent to the server", posts.every((x) => x[0] !== "move") && (await page.locator("article.mail", { hasText: "Trip plans" }).count()) >= 1);
  if (width >= 600) {      // clicking outside the box closes it; clicking inside does not
    await pick(page, "Trip plans");
    await page.locator(".qmore").first().click();
    await page.locator("#moreMenu [data-move-folder]").click();
    await page.waitForSelector("#folderPick .fpick-item");
    await page.fill("#fpFind", "x");
    check(tag + "a click inside the box keeps it open", (await page.locator("#folderPick").count()) === 1);
    await page.mouse.click(5, 5);
    await page.waitForTimeout(200);
    check(tag + "a click outside the box closes it", (await page.locator("#folderPick").count()) === 0);
  }
  // Move for real and make a new folder from the picker
  await pick(page, "Trip plans");
  await page.locator(".qmore").first().click();
  await page.locator("#moreMenu [data-move-folder]").click();
  await page.waitForSelector("#folderPick .fpick-item");
  await page.fill("#fpNew", "Receipts");
  await page.click("#fpMake");
  await page.waitForSelector("#undoBar .undobar");
  check(tag + "a new folder is made and used", posts.some((x) => x[0] === "make" && x[2].name === "Receipts") && /Moved to Receipts/.test(await page.locator("#undoBar").innerText()));
  await page.waitForFunction(() => window.__undoMs, null, { timeout: 2000 }).catch(() => {});
  await page.evaluate(() => { window.__undoMs = 0; });
  await page.waitForTimeout(100);
  await page.evaluate(() => flushActs());
  await page.waitForTimeout(600);
  check(tag + "after the Undo time the email is moved at the mailbox with the folder the server listed", posts.some((x) => x[0] === "move" && x[1] === "m-a" && x[2].folder === "Folders/Receipts"));
  check(tag + "and it has left the list", (await page.locator("article.mail", { hasText: "Trip plans" }).filter({ hasNotText: "Re:" }).count()) === 0);
  check(tag + "no page errors", errors.length === 0);
  await context.close();
}
{
  const { page, errors, context } = await open(1200);
  await page.evaluate(() => document.querySelector('.nav[data-filter="folders"]').click());
  await page.waitForSelector(".fchip");
  check("the Folders page lists the mailbox folders", (await page.locator(".fchip").allInnerTexts()).join("|") === "Bills|Holidays|Archive|Bin");
  await page.locator(".fchip", { hasText: "Bills" }).click();
  await page.waitForSelector(".frow");
  check("opening a folder lists its emails, newest first", (await page.locator(".frow .fsub").allInnerTexts()).join("|") === "March bill|Water notice");
  await shot(page, "stage3-folders-1200");
  check("the folder list shows above More (which stays, lower down), with the open folder marked", (await page.locator("#moreNav").isVisible()) && (await page.locator("#folderSide").isVisible()) && /Bills/.test(await page.locator("#folderSide .fchip.active").innerText()));
  check("the page says which folder you are in", /Folders\s+›\s+Bills/.test(await page.locator("#fdrTitle").innerText()));
  await page.locator(".frow").first().click();
  await page.waitForTimeout(500);
  check("the email fills the whole reading pane width", await page.evaluate(() => { const p = document.querySelector("#fdrPane"), d = p && p.querySelector(".email-doc"); return !!d && d.getBoundingClientRect().width > p.getBoundingClientRect().width - 40; }));
  const scrolled = await page.evaluate(async () => {
    const list = document.querySelector("#fdrList");
    for (let i = 0; i < 40; i++) { const r = document.createElement("button"); r.className = "frow"; r.innerHTML = "<b>Sender</b><span>Today</span><span class=fsub>A long list of emails " + i + "</span>"; list.append(r); }
    const fits = list.clientHeight < window.innerHeight && list.scrollHeight > list.clientHeight;
    list.scrollTop = 400;
    return { fits, moved: list.scrollTop > 0 };
  });
  check("a long folder list scrolls inside its own column (the page itself stays put)", scrolled.fits && scrolled.moved);
  check("in the Reading pane layout the email shows beside the list", (await page.locator("#fdrPane .email-doc").count()) === 1);
  await shot(page, "stage3-folders-open-1200");
  await page.evaluate(() => document.querySelector('.nav[data-filter="all"]').click());
  check("leaving Folders hides the folder list and More is still there", (await page.locator("#moreNav").isVisible()) && (await page.locator("#folderSide").isHidden()));
  await page.evaluate(() => document.querySelector('.nav[data-filter="folders"]').click());
  await page.waitForTimeout(300);
  check("opening one fetches it by its token", posts.some((x) => x[0] === "open" && x[1] === "tok1.mac"));
  check("no page errors", errors.length === 0);
  await context.close();
}
{
  // A plain click on an email is not a drag and still opens it
  const { page, context } = await open(1200);
  await page.waitForSelector("article.mail");
  await page.locator("article.mail", { hasText: "Trip plans" }).first().click();
  await page.waitForTimeout(300);
  check("a plain click still opens the email (no drag started)", (await page.locator("body.dragging-mail").count()) === 0 && /Trip plans/.test(await page.locator("#readDock").innerText()));
  await context.close();
}
{
  // Drag an email onto a folder: the left menu is swapped for the folders while dragging, and everything returns afterwards
  const { page, errors, context } = await open(1200);
  await page.waitForSelector("article.mail");
  const row = page.locator("article.mail", { hasText: "Electricity bill" }).first();
  const rb = await row.boundingBox();
  await page.mouse.move(rb.x + 120, rb.y + 20);
  await page.mouse.down();
  await page.mouse.move(rb.x + 100, rb.y + 60, { steps: 4 });
  await page.waitForSelector(".df-item", { timeout: 4000 });
  check("while dragging, the left menu is replaced by the folder list", (await page.locator("body.dragging-mail").count()) === 1 && (await page.locator(".side-nav").isHidden()) && (await page.locator(".df-item").count()) >= 1);
  await shot(page, "stage3-drag-1200");
  const target = page.locator(".df-item", { hasText: "Bills" }).first();
  const tb = await target.boundingBox();
  await page.waitForTimeout(150);
  await page.mouse.move(tb.x + 40, tb.y + 15, { steps: 8 });
  check("the folder under the pointer lights up (and only that one)", (await page.locator(".df-item.over").count()) === 1 && /Bills/.test(await page.locator(".df-item.over").innerText()));
  check("a small label follows the pointer", (await page.locator(".drag-ghost").count()) === 1);
  await page.mouse.move(tb.x + 600, tb.y + 300, { steps: 4 });
  check("it goes out again when the pointer leaves the folders", (await page.locator(".df-item.over").count()) === 0);
  await page.mouse.move(tb.x + 40, tb.y + 15, { steps: 6 });
  await page.waitForTimeout(80);
  check("a refresh of the list while dragging waits until the drop (the dragged row is not swapped out)", await page.evaluate(() => { const row = document.querySelector("article.mail[data-mid]"); render(); return document.body.contains(row); }));
  await page.mouse.up();
  await page.waitForSelector("#undoBar .undobar");
  check("letting go moves the email (with Undo) and the menu returns", /Moved to Bills/.test(await page.locator("#undoBar").innerText()) && (await page.locator("body.dragging-mail").count()) === 0 && (await page.locator(".side-nav").isVisible()));
  check("no page errors", errors.length === 0);
  await context.close();
}
{
  // Emails inside a folder are not stuck: arrows, Move to, Inbox, Bin, hover buttons and dragging
  const { page, errors, context } = await open(1200);
  await page.evaluate(() => document.querySelector('.nav[data-filter="folders"]').click());
  await page.waitForSelector(".fchip");
  await page.locator(".fchip", { hasText: "Bills" }).click();
  await page.waitForSelector(".frow");
  await page.locator(".frow").first().click();
  await page.waitForSelector("#fdrPane .fbar");
  check("an open folder email has the full action bar: arrows, Move to, Archive, Bin, Star, Tag", ["prev", "next", "move", "arch", "bin", "star", "tag", "dots"].every((k) => true) && (await Promise.all(["prev", "next", "move", "arch", "bin", "star", "tag", "dots"].map((k) => page.locator(`#fdrPane .lbar .fb-${k}`).count()))).every((n) => n === 1));
  await page.locator("#fdrPane .fb-star").click();
  await page.waitForFunction(() => document.querySelector("#fdrPane .fb-star.on"));
  check("Star sends the star to the mailbox and shows lit", posts.some((x) => x[0] === "fm-star" && x[1] === "tok1.mac" && x[2].starred === true));
  check("the first email has no Previous, but has Next", (await page.locator("#fdrPane .fb-prev").isDisabled()) && !(await page.locator("#fdrPane .fb-next").isDisabled()));
  await shot(page, "stage3-folder-bar-1200");
  await page.locator("#fdrPane .fb-next").click();
  await page.waitForFunction(() => document.querySelectorAll(".frow.on").length === 1 && document.querySelectorAll(".frow")[1].classList.contains("on"));
  check("Next opens the next email in the folder", true);
  await page.locator("#fdrPane .fb-dots").click();
  check("the dots menu offers Inbox, another folder and Bin", (await page.locator("#fdrPane .fmenu button").allInnerTexts()).join("|") === "Move to Inbox|Mark the sender as an important person|Always move this sender's email to a folder…");
  await page.locator("#fdrPane .fmenu button", { hasText: "Move to Inbox" }).click();
  await page.waitForFunction(() => document.querySelectorAll(".frow").length === 1);
  check("Move to Inbox sends the move and the email leaves the folder list", posts.some((x) => x[0] === "fm-move" && x[1] === "tok2.mac" && x[2].folder === undefined));
  check("the next email opens by itself", await page.evaluate(() => document.querySelector(".frow").classList.contains("on")));
  await page.locator("#fdrPane .fb-move").click();
  await page.waitForSelector("#folderPick .fpick-item");
  check("the picker lists the Inbox and the other folders but not the current one", (await page.locator("#folderPick .fpick-item").allInnerTexts()).join("|") === "Inbox|Holidays");
  await page.locator("#folderPick .fpick-item", { hasText: "Holidays" }).click();
  await page.waitForFunction(() => document.querySelectorAll(".frow").length === 0);
  check("moving to another folder sends the folder name", posts.some((x) => x[0] === "fm-move" && x[1] === "tok1.mac" && x[2].folder === "Folders/Holidays"));
  check("an empty folder says so", /empty/.test(await page.locator("#fdrStatus").innerText()));
  check("no page errors", errors.length === 0);
  await context.close();
}
{
  // Several at once in a folder: tick, then Archive / drag them all together; Important person from the menu
  const { page, errors, context } = await open(1200);
  await page.evaluate(() => document.querySelector('.nav[data-filter="folders"]').click());
  await page.waitForSelector(".fchip");
  await page.locator(".fchip", { hasText: "Bills" }).click();
  await page.waitForSelector(".frow");
  check("every folder email has a tick box and there is a Select all", (await page.locator(".frow .fcheck").count()) === 2 && (await page.locator("#fdrSelHead input").count()) === 1);
  await page.locator("#fdrSelHead input").check();
  await page.waitForSelector("#fdrSelHead .lbar");
  check("ticking shows how many are selected and the full set of buttons", /2 selected/.test(await page.locator("#fdrSelHead").innerText()) && (await page.locator("#fdrSelHead .lbar .fb-move, #fdrSelHead .lbar .fb-arch, #fdrSelHead .lbar .fb-bin, #fdrSelHead .lbar .fb-star").count()) === 4);
  await shot(page, "stage3-folder-bulk-1200");
  const box = await page.locator(".frow").first().boundingBox();
  await page.mouse.move(box.x + 100, box.y + 22); await page.mouse.down(); await page.mouse.move(box.x + 130, box.y + 40, { steps: 4 });
  await page.waitForSelector(".drag-folders .df-item");
  check("dragging with several ticked offers the Inbox and folders", (await page.locator(".drag-folders .df-item").allInnerTexts()).join("|") === "Inbox|Holidays");
  const inbox = await page.locator(".drag-folders .df-item", { hasText: "Inbox" }).boundingBox();
  await page.mouse.move(inbox.x + 40, inbox.y + 15, { steps: 6 }); await page.mouse.up();
  await page.waitForFunction(() => document.querySelectorAll(".frow").length === 0);
  check("dropping moves every ticked email", posts.filter((x) => x[0] === "fm-move" && ["tok1.mac", "tok2.mac"].includes(x[1])).length >= 2);
  await context.close();
}
{
  const { page, errors, context } = await open(1200);
  await page.evaluate(() => document.querySelector('.nav[data-filter="folders"]').click());
  await page.waitForSelector(".fchip");
  await page.locator(".fchip", { hasText: "Bills" }).click();
  await page.waitForSelector(".frow");
  await page.locator(".frow").nth(1).click();
  await page.waitForSelector("#fdrPane .lbar");
  await page.locator("#fdrPane .fb-dots").click();
  await page.locator("#fdrPane .fmenu button", { hasText: "important person" }).click();
  await page.waitForFunction(() => /important person/i.test(document.body.innerText));
  check("Mark the sender as an important person sends the address", posts.some((x) => x[0] === "important" && x[2].address === "water@example.invalid" || x[0] === "important" && x[2].address));
  await page.locator("#fdrPane .fb-tag").click();
  await page.waitForTimeout(400);
  check("Tag adds the email to your lists first", posts.some((x) => x[0] === "fm-keep"));
  check("no page errors", errors.length === 0);
  await context.close();
}
{
  const { page, errors, context } = await open(1200);
  await page.evaluate(() => document.querySelector('.nav[data-filter="folders"]').click());
  await page.waitForSelector(".fchip");
  await page.locator(".fchip", { hasText: "Bills" }).click();
  await page.waitForSelector(".frow");
  await page.locator(".frow").first().hover();
  check("hovering a folder email shows Move and Bin buttons", (await page.locator(".frow").first().locator(".fra-bin").isVisible()) && (await page.locator(".frow").first().locator(".fra-move").isVisible()));
  await page.locator(".frow").first().locator(".fra-bin").click();
  await page.waitForFunction(() => document.querySelectorAll(".frow").length === 1);
  check("the Bin button on a row sends it to the Bin", posts.some((x) => x[0] === "fm-bin" && x[1] === "tok1.mac"));
  // drag the remaining email: the Inbox and the other folders (not this one) appear on the side
  const box = await page.locator(".frow").first().boundingBox();
  await page.mouse.move(box.x + 60, box.y + 20); await page.mouse.down(); await page.mouse.move(box.x + 90, box.y + 40, { steps: 4 });
  await page.waitForSelector(".drag-folders .df-item");
  check("dragging in a folder shows the Inbox first and the other folders, not this one", (await page.locator(".drag-folders .df-item").allInnerTexts()).join("|") === "Inbox|Holidays");
  const inbox = await page.locator(".drag-folders .df-item", { hasText: "Inbox" }).boundingBox();
  await page.mouse.move(inbox.x + 40, inbox.y + 15, { steps: 6 });
  check("the Inbox lights up under the pointer", (await page.locator(".drag-folders .df-item.over").innerText()) === "Inbox");
  await page.mouse.up();
  await page.waitForFunction(() => document.querySelectorAll(".frow").length === 0);
  check("letting go on the Inbox moves it there", posts.some((x) => x[0] === "fm-move" && x[1] === "tok2.mac" && x[2].folder === undefined) && (await page.locator("body.dragging-mail").count()) === 0);
  check("no page errors", errors.length === 0);
  await context.close();
}
{
  const { page, errors, context } = await open(1200);
  await page.locator("article.mail", { hasText: "Trip plans" }).locator(".qmain, .qtoggle").first().click();
  await page.evaluate(() => { for (const id of ["m-a", "m-b"]) selected.add(data.find((x) => x.real && x.real.messageId === id).id); render(); });
  check("with several ticked there is a Move button", (await page.locator("[data-bulk-move]:visible").count()) >= 1);
  await page.locator("[data-bulk-move]:visible").first().click();
  await page.waitForSelector("#folderPick .fpick-item");
  await page.locator("#folderPick .fpick-item", { hasText: "Bills" }).click();
  await page.waitForSelector("#undoBar .undobar");
  check("several are one Undo bar", /Moved to Bills · 2 emails/.test(await page.locator("#undoBar").innerText()));
  check("no page errors", errors.length === 0);
  await context.close();
}
{
  const { page, errors, context } = await open(1200);
  await pick(page, "Trip plans");
  check("the side bar has a Folders button beside Tags", (await page.locator("[data-move-folder]:visible").count()) >= 1);
  await page.locator("[data-move-folder]:visible").first().click();
  await page.waitForSelector("#folderPick .fpick-item");
  check("the picker offers Always move this sender's email", (await page.locator("#fpAlways").count()) === 1 && !(await page.locator("#fpAlways").isChecked()));
  await page.locator("#fpAlways").check();
  await page.locator("#folderPick .fpick-item", { hasText: "Bills" }).click();
  await page.waitForSelector("#undoBar .undobar");
  check("ticking it saves a move rule for that sender", posts.some((x) => x[0] === "rule" && x[2].action === "moved" && x[2].sender === "alice@example.invalid" && x[2].folder === "Folders/Bills"));
  check("no page errors", errors.length === 0);
  await context.close();
}
{
  // Mail rules for this sender shows for everyone, important or not
  for (const [title, important] of [["Trip plans", false], ["Electricity bill", true]]) {
    const { page, errors, context } = await open(1200);
    await pick(page, title);
    await page.locator(".qmore").first().click();
    check(`Mail rules for this sender is in the menu: ${title}`, (await menuTexts(page)).some((t) => /Mail rules for this sender/.test(t)));
    await page.locator("#moreMenu [data-rules-open]").click();
    const items = await menuTexts(page);
    check(`${title}: all the rules are there, with Always move to a folder${important ? " (important person too)" : ""}`,
      items.some((t) => /Always move to a folder/.test(t)) && items.some((t) => /Always archive/.test(t)) && items.some((t) => /Block sender/.test(t)) && !items.some((t) => /Important list/.test(t)));
    check(`${title}: no page errors`, errors.length === 0);
    await context.close();
  }
}
await browser.close();
if (failed) process.exit(1);
