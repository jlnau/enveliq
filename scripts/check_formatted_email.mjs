// Browser check for the writing box: bold, lists, links, colours, pasted pictures, the Send arrow (Send later, Quick AI Send)
// and minimising an email to the bottom of the screen. The page is loaded from a pretend Enveliq server (Playwright intercepts requests).
//   node scripts/check_formatted_email.mjs [path/to/prototype/index.html]     (SHOTS=<dir> saves screenshots)
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
const messages = [{ id: "m-a", subject: "Dentist on Monday", sender_display: "Brightwater Dental", sender_address: "clinic@example.invalid", summary: "A check-up.", priority: "normal", category: null, action_required: false, state: "unread", received_at: now - 300,
  reply_context: { reply_to: "clinic@example.invalid", delivered_to: null, via_alias: null, message_id: "<a@x>", references: [], cc: [], also_to: [] } }];
const sent = [], replies = [];
let drafts = [], nextId = 1;
const handler = async (route) => {
  const req = route.request(), u = new URL(req.url()), p = u.pathname;
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (u.origin !== ORIGIN) return route.abort();
  if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
  if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
  if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
  if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
  if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1143, username: "me@example.invalid", settings: {} }]);
  if (p === "/api/v1/accounts/a1/messages") return json(200, messages);
  if (p === "/api/v1/accounts/a1/send") { sent.push(JSON.parse(req.postData())); return json(200, { sent: true, from: "me@example.invalid" }); }
  if (/\/messages\/[^/]+\/reply$/.test(p)) { replies.push(JSON.parse(req.postData())); return json(200, { sent: true, from: "me@example.invalid" }); }
  if (/\/messages\/[^/]+\/original$/.test(p)) return json(200, { subject: "Dentist on Monday", from: { name: "Brightwater Dental", address: "clinic@example.invalid" }, to: [], date: "x", text: "See you Monday", truncated: false, attachments: [] });
  if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features });
  if (p === "/api/v1/me/drafts" && req.method() === "GET") return json(200, { now: Date.now() / 1000, keep_days: 14, items: [...drafts].reverse() });
  if (p === "/api/v1/me/drafts" && req.method() === "POST") { const b = JSON.parse(req.postData()); const d = { ...b, id: "d" + String(nextId++).padStart(16, "0"), created: Date.now() / 1000, updated: Date.now() / 1000, expires: Date.now() / 1000 + 14 * 86400 }; drafts.push(d); return json(201, d); }
  const dm = p.match(/^\/api\/v1\/me\/drafts\/(d[0-9]+)$/);
  if (dm && req.method() === "PUT") { const b = JSON.parse(req.postData()); const i = drafts.findIndex((x) => x.id === dm[1]); drafts[i] = { ...drafts[i], ...b }; return json(200, drafts[i]); }
  if (dm && req.method() === "DELETE") { drafts = drafts.filter((x) => x.id !== dm[1]); return route.fulfill({ status: 204 }); }
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
  if (p === "/api/v1/me/contacts") return json(200, { items: [] });
  if (p === "/api/v1/me/tasks") return json(200, { today: "2026-10-14", tz: "UTC", now: Date.now() / 1000, tasks: [] });
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: now } } });
  return json(404, { detail: "not found" });
};
const browser = await chromium.launch();
const shot = async (page, name) => { if (process.env.SHOTS) { fs.mkdirSync(process.env.SHOTS, { recursive: true }); await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); } };
// A tiny real PNG made in the page, pasted like a screenshot.
const pastePicture = (page, sel) => page.evaluate(async (s) => {
  const c = document.createElement("canvas"); c.width = 40; c.height = 30; c.getContext("2d").fillRect(0, 0, 40, 30);
  const blob = await new Promise((r) => c.toBlob(r, "image/png"));
  const dt = new DataTransfer(); dt.items.add(new File([blob], "shot.png", { type: "image/png" }));
  document.querySelector(s).dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
}, sel);
for (const [width, height] of [[1200, 900], [390, 800]]) {
  const tag = width + "px wide: ";
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  sent.length = 0; replies.length = 0; drafts = [];
  await context.route("**/*", handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  await page.evaluate(() => { view.layout = "list"; view.rows = "open"; applyView(); render(); });
  await page.evaluate(() => openNewMail());
  const bar = (id) => page.locator(`#newMail [data-rte="${id}"]`);
  const ids = ["bold", "italic", "underline", "strike", "color", "ul", "ol", "outdent", "indent", "quote", "link", "photo", "clear"];
  let all = true; for (const i of ids) if (!(await bar(i).isVisible())) all = false;
  check(tag + "the toolbar has bold, italic, underline, strikethrough, colour, lists, indent, quote, link, picture and clear", all);
  await page.locator("#nmTo input").fill("dana@example.invalid"); await page.locator("#nmTo input").press("Enter");
  await page.locator("#nmSubject").fill("Plans");
  await page.locator("#nmText").fill("Hello Dana");
  await page.locator("#nmText").press("Control+A");
  await bar("bold").click();
  check(tag + "Bold wraps the words", /<(b|strong)>Hello Dana<\/(b|strong)>/.test(await page.locator("#nmText").innerHTML()));
  check(tag + "the Bold button shows it is on", (await bar("bold").getAttribute("aria-pressed")) === "true");
  await bar("color").click();
  await page.locator("#newMail .rte-sw").nth(1).click();
  check(tag + "a colour can be chosen", /color:\s*(rgb\(217, 48, 37\)|#d93025)/i.test(await page.locator("#nmText").innerHTML()));
  await bar("link").click();
  await page.locator("#newMail .rte-pop.link input").fill("example.com");
  await page.locator("#newMail .rte-pop.link input").press("Enter");
  check(tag + "a link is added to the chosen words with https in front", (await page.locator('#nmText a[href="https://example.com"]').count()) === 1);
  await page.locator("#nmText").press("Control+End");
  await page.locator("#nmText").press("Enter");
  await bar("ul").click();
  await page.keyboard.type("First point");
  check(tag + "a bullet list can be made", (await page.locator("#nmText ul li").count()) === 1);
  await pastePicture(page, "#nmText");
  await page.waitForSelector("#nmText img");
  check(tag + "a pasted picture appears in the message", (await page.locator("#nmText img").count()) === 1);
  // Resize a picture by its corner; the shape stays the same.
  await page.locator("#nmText img").click();
  check(tag + "pressing a picture shows corner handles", await page.locator("#newMail .rte-handles").isVisible() && (await page.locator("#newMail .rte-h").count()) === 4);
  const w0 = await page.locator("#nmText img").evaluate((e) => e.getBoundingClientRect().width), r0 = await page.locator("#nmText img").evaluate((e) => e.getBoundingClientRect().height / e.getBoundingClientRect().width);
  const hb = await page.locator("#newMail .rte-h.se").boundingBox();
  await page.mouse.move(hb.x + hb.width / 2, hb.y + hb.height / 2); await page.mouse.down(); await page.mouse.move(hb.x + hb.width / 2 + 40, hb.y + hb.height / 2 + 5, { steps: 4 }); await page.mouse.up();
  const w1 = await page.locator("#nmText img").evaluate((e) => e.getBoundingClientRect().width), r1 = await page.locator("#nmText img").evaluate((e) => e.getBoundingClientRect().height / e.getBoundingClientRect().width);
  check(tag + "dragging a corner makes the picture bigger and keeps its shape", w1 > w0 + 30 && Math.abs(r1 - r0) < 0.03);
  check(tag + "the new size goes with the email", (await page.evaluate(() => document.getElementById("nmText").rteOut().html)).includes('width="' + Math.round(w1) + '"'));
  const text = await page.evaluate(() => document.getElementById("nmText").value);
  check(tag + "the plain-text copy has the words, the bullet and the link address", text.includes("Hello Dana") && text.includes("- First point") && text.includes("https://example.com"));
  await shot(page, "formatted-" + width);
  // Safety: nothing but plain formatting comes out, whatever was pasted or typed in.
  const clean = await page.evaluate(() => {
    const ed = document.getElementById("nmText");
    const box = document.createElement("div");
    box.append(rteSan(new DOMParser().parseFromString('<p onclick="x()">Hi <a href="javascript:alert(1)">bad</a> <a href="https://ok.example.com/a">good</a><img src="https://tracker.example.com/p.gif"><script>alert(1)<\/script><iframe src="https://e.example.com"></iframe></p>', "text/html").body, { images: false }));
    return box.innerHTML;
  });
  check(tag + "scripts, frames, remote pictures, event handlers and unsafe links are left out", !/script|iframe|onclick|tracker|javascript:/i.test(clean) && clean.includes('href="https://ok.example.com/a"'));
  // The top bar and the bottom buttons stay put; the middle scrolls (on a phone the whole window is the screen).
  await page.locator("#nmText").evaluate((e) => { e.rteAppend("\n".repeat(60) + "end of a long email"); });
  const geo = await page.evaluate(() => { const d = document.getElementById("newMail").getBoundingClientRect(), f = document.getElementById("nmForm"), hd = d && document.querySelector("#newMail .compose-head").getBoundingClientRect(), ft = document.querySelector("#newMail .compose-foot").getBoundingClientRect(); return { dTop: d.top, dBottom: d.bottom, hTop: hd.top, fBottom: ft.bottom, scrolls: f.scrollHeight > f.clientHeight, vh: innerHeight }; });
  if (width > 760) check(tag + "a long email scrolls in the middle while the top bar and the Send row stay in view", geo.scrolls && geo.fBottom <= geo.vh && geo.hTop >= 0);
  else check(tag + "on a phone the Send row is still reachable with a long email", await page.locator("#nmSend").isVisible());
  await shot(page, "long-" + width);
  await page.locator("#nmText").evaluate((e) => { e.rteLoad(e.rteOut().html, e.rteOut().images); e.focus(); });
  // The split Send button
  check(tag + "the menu is closed until the arrow is pressed", await page.locator("#nmMenu").isHidden());
  await page.locator("#nmMore").click();
  check(tag + "the arrow opens Send later (Quick AI Send only shows when it can be used)", await page.locator("#nmMenu").isVisible() && await page.locator("#nmLater").isVisible() && await page.locator("#nmQuick").isHidden());
  await shot(page, "split-" + width);
  await page.keyboard.press("Escape");
  check(tag + "Escape closes just the menu", await page.locator("#nmMenu").isHidden() && await page.locator("#newMail.open").count() === 1);
  // Send
  await page.locator("#nmSend").click();
  await page.waitForFunction(() => !document.getElementById("newMail").classList.contains("open"));
  const s = sent[0] || {};
  if (process.env.DEBUG) console.log(JSON.stringify({ ...s, images: (s.images || []).map((i) => i.cid) }));
  check(tag + "the email goes out with its formatted copy, plain text and the picture", sent.length === 1 && /<(b|strong)[ >]/.test(s.html || "") && (s.html || "").includes('href="https://example.com"') && /<ul>.*<li>/.test(s.html || "") && s.body.includes("Hello Dana") && Array.isArray(s.images) && s.images.length === 1);
  check(tag + "the picture is sent as its own part and named in the text, never as a web address", s.images[0].type === "image/png" && /^[A-Za-z0-9+/=]+$/.test(s.images[0].data) && (s.html || "").includes("cid:" + s.images[0].cid) && !/data:image/.test(s.html || ""));
  // Minimise
  await page.evaluate(() => openNewMail());
  await page.locator("#nmTo input").fill("erin@example.invalid"); await page.locator("#nmTo input").press("Enter");
  await page.locator("#nmSubject").fill("First draft idea");
  await page.locator("#nmText").fill("Words one");
  await pastePicture(page, "#nmText"); await page.waitForSelector("#nmText img");
  await page.locator("#nmMin").click();
  await page.waitForFunction(() => !document.getElementById("newMail").classList.contains("open"));
  const chips = () => page.locator("#cmTray .cm-chip-open").allInnerTexts();
  check(tag + "Minimise closes the window and leaves a bar at the bottom named by the subject", (await chips()).join() === "First draft idea");
  await page.evaluate(() => openNewMail());
  await page.locator("#nmSubject").fill("Second idea");
  await page.locator("#nmText").fill("Words two");
  await page.locator("#nmMin").click();
  await page.waitForFunction(() => !document.getElementById("newMail").classList.contains("open"));
  check(tag + "several emails can wait at the bottom", (await chips()).join("|") === "First draft idea|Second idea");
  const tb = await page.locator("#cmTray").boundingBox();
  check(tag + "the bar sits at the bottom edge and fits the screen", tb && Math.abs(tb.y + tb.height - height) <= 2 && tb.x >= 0 && tb.x + tb.width <= width + 1);
  await shot(page, "tray-" + width);
  await page.locator("#cmTray .cm-chip-open", { hasText: "First draft idea" }).click();
  await page.waitForSelector("#newMail.open");
  check(tag + "pressing one reopens it with the people, subject, words and picture", (await page.locator("#nmSubject").inputValue()) === "First draft idea" && (await page.evaluate(() => document.getElementById("nmText").value)).includes("Words one") && (await page.locator("#nmText img").count()) === 1 && (await page.locator("#nmTo .pchip span").allInnerTexts()).join() === "erin@example.invalid");
  check(tag + "the one reopened leaves the bar", (await chips()).join() === "Second idea");
  await page.locator("#nmMin").click();
  await page.waitForFunction(() => !document.getElementById("newMail").classList.contains("open"));
  await page.locator("#cmTray .cm-chip-x").first().click();
  check(tag + "the cross asks first", (await chips()).length === 2);
  await page.locator("#cmTray .cm-chip-x").first().click();
  check(tag + "pressing the cross twice throws it away", (await chips()).length === 1);
  // A reply keeps its formatting too
  await page.locator("#cmTray .cm-chip-x").first().click(); await page.locator("#cmTray .cm-chip-x").first().click();
  await page.evaluate(() => openComposer(data.find((m) => m.real).id, "reply"));
  await page.waitForSelector("#compose.open");
  await page.waitForTimeout(300);                 // the window puts the cursor in the box a moment after it opens
  await page.locator("#composeText").fill("Thanks");
  await page.locator("#composeText").press("Control+A");
  await page.locator('#compose [data-rte="italic"]').click();
  await page.waitForFunction(() => /<(i|em)>/.test(document.getElementById("composeText").innerHTML));
  await page.locator("#composeSend").click();
  await page.waitForFunction(() => !document.getElementById("compose").classList.contains("open"));
  check(tag + "a reply carries its formatted copy", replies.length === 1 && /<(i|em)>Thanks<\/(i|em)>/.test(replies[0].html || "") && replies[0].body === "Thanks");
  check(tag + "no sideways scroll", await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  check(tag + "no page errors", errors.length === 0);
  await context.close();
}
await browser.close();
process.exit(failed ? 1 : 0);
