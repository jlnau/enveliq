// Browser check for Tags: the tags an email already has, the Tags button and its pop-up, making a new tag, and the full-screen phone form.
// The page is loaded from a pretend Enveliq server (Playwright intercepts the requests), so this needs no Python.
//   node scripts/check_tags.mjs [path/to/prototype/index.html]     (SHOTS=<dir> saves screenshots)
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
let tagNames = ["Taxes", "Work"];
const tagsOf = { "m-plain": ["Work"] };
let canCreate = true, supported = true;
const features = { compose: true, address_book: true, sent: true, media: false, all_mail: false, shipping: false, tags: true, subscriptions: false, travel: false, waiting: false, messages: false, write_help: false };
const mk = (id, subject, name, n) => ({ id, subject, sender_display: name, sender_address: name.toLowerCase() + "@example.invalid", summary: "A summary.", priority: "normal", category: null, action_required: false, received_at: now - n,
  reply_context: { reply_to: name.toLowerCase() + "@example.invalid", delivered_to: null, via_alias: null, message_id: "<" + id + "@x>", references: [], cc: [], also_to: [] } });
const base = [mk("m-plain", "Just you", "Bob", 120), mk("m-other", "Another one", "Cara", 180), mk("m-third", "Third one", "Dan", 240)];
const messages = () => base.map((m) => ({ ...m, tags: tagsOf[m.id] || [] }));
const handler = async (route) => {
  const req = route.request(), p = new URL(req.url()).pathname;
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
  if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
  if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
  if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
  if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1144, username: "bridge", settings: { smtp_port: 1026, send_identities: [], ai_summaries: true } }]);
  if (p === "/api/v1/accounts/a1/messages") return json(200, messages());
  if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: { ...features, address_book_auto: true } });
  if (p === "/api/v1/accounts/a1/tags" && req.method() === "GET") { calls.push(["list"]); await new Promise((r) => setTimeout(r, 150)); return json(200, { supported, names: tagNames, can_create: canCreate }); }
  if (p === "/api/v1/accounts/a1/tags" && req.method() === "POST") {
    const b = JSON.parse(req.postData()); calls.push(["make", b.name]);
    if (/\//.test(b.name)) return json(422, { detail: "Use letters, digits, spaces and the signs - _ . & + ( ) in a tag name." });
    tagNames = [...tagNames, b.name].sort(); return json(201, { supported: true, name: b.name, names: tagNames, can_create: canCreate });
  }
  const tm = p.match(/^\/api\/v1\/accounts\/a1\/messages\/([^/]+)\/tags$/);
  if (tm && req.method() === "PUT") {
    const b = JSON.parse(req.postData()); calls.push(["set", tm[1], b.name, b.on]);
    if (b.name === "Broken") return json(502, { detail: { code: "protocol_error", message: "The mailbox would not change that tag." } });
    const now_ = (tagsOf[tm[1]] || []).filter((x) => x !== b.name); tagsOf[tm[1]] = (b.on ? [...now_, b.name] : now_).sort();
    return json(200, { tags: tagsOf[tm[1]] });
  }
  if (p === "/api/v1/me/drafts") return json(200, { now: Date.now() / 1000, keep_days: 14, items: [] });
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "" });
  if (p === "/api/v1/me/contacts") return json(200, { items: [] });
  if (p === "/api/v1/me/tasks") return json(200, { today: "2026-10-14", tz: "UTC", now: Date.now() / 1000, tasks: [] });
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: {} });
  return json(404, { detail: "not found" });
};

const browser = await chromium.launch();
const run = async (width, height) => {
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-view", JSON.stringify({ layout: "list" })); } catch (e) {} });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route(`${ORIGIN}/**`, handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  return { page, context, errors };
};
const rowOf = (page, subject) => page.locator("article.mail", { hasText: subject });
const openRow = async (page, subject) => {
  const row = rowOf(page, subject);
  if (!(await row.locator("[data-tag-open]").count())) await row.locator(".qmain").click();
  await page.waitForSelector(`article.mail:has-text("${subject}") [data-tag-open]`);
  return row;
};
{
  const { page, context, errors } = await run(1300, 900);
  check("an email that has a tag shows it in the list", /Work/.test(await rowOf(page, "Just you").locator(".qmain").innerText()));
  check("an email with no tag shows none", (await rowOf(page, "Another one").locator(".mtag").count()) === 0);
  const row = await openRow(page, "Another one");
  check("every email in the inbox has a Tags button", (await row.locator("[data-tag-open]").innerText()).trim() === "Tags");
  await row.locator("[data-tag-open]").click();
  await page.waitForSelector("#tagPop:not([hidden]) .tagrow");
  const names = await page.locator("#tagPop .tagrow span").allInnerTexts();
  check("the pop-up lists the tags the mailbox already has", names.join(",") === "Taxes,Work");
  check("a short list of tags has no search box", (await page.locator("#tagFind").count()) === 0);
  check("a tag the email does not have is not ticked", (await page.locator('#tagPop [data-tag-toggle="Taxes"]').isChecked()) === false);
  await page.locator('#tagPop [data-tag-toggle="Taxes"]').check();
  await page.waitForFunction(() => [...document.querySelectorAll("article.mail")].some((a) => /Another one/.test(a.innerText) && /Taxes/.test(a.innerText)));
  check("ticking a tag puts it on the email in the mailbox", calls.some((c) => c[0] === "set" && c[1] === "m-other" && c[2] === "Taxes" && c[3] === true));
  check("the email then shows the tag", /Taxes/.test(await rowOf(page, "Another one").innerText()));
  await page.locator('#tagPop [data-tag-toggle="Taxes"]').uncheck();
  await page.waitForFunction(() => [...document.querySelectorAll("article.mail")].some((a) => /Another one/.test(a.innerText) && !/Taxes/.test(a.innerText)));
  check("unticking takes it off in the mailbox", calls.some((c) => c[0] === "set" && c[2] === "Taxes" && c[3] === false));
  await page.locator("#tagNew").fill("Holiday plans");
  await page.locator("#tagPop button[type=submit]").click();
  await page.waitForFunction(() => /Tag added/.test(document.getElementById("toast").textContent));
  check("making a new tag creates it and puts it on this email", calls.some((c) => c[0] === "make" && c[1] === "Holiday plans") && calls.some((c) => c[0] === "set" && c[2] === "Holiday plans" && c[3] === true));
  check("the new tag is in the list, ticked", (await page.locator('#tagPop [data-tag-toggle="Holiday plans"]').isChecked()) === true);
  await page.locator("#tagNew").fill("a/b");
  await page.keyboard.press("Enter");
  await page.waitForSelector("#tagPop .sa-err");
  check("a tag name that is not allowed says why, in plain words", /letters, digits/.test(await page.locator("#tagPop .sa-err").innerText()));
  check("the pop-up has a note about always tagging a sender", /Always tag or filter this sender/.test(await page.locator("#tagPop [data-tag-info]").innerText()));
  check("the note is not open until it is pressed", (await page.locator("#tagPop .tag-info").count()) === 0);
  await page.locator("#tagPop [data-tag-info]").click();
  await page.waitForSelector("#tagPop .tag-info");
  const info = await page.locator("#tagPop .tag-info").innerText();
  check("pressing it explains that the filter is set up at the email provider", /filter in your email provider/.test(info) && /Proton Mail, Gmail, Microsoft/.test(info) && /add this tag/.test(info));
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "tags_info_desktop.png") });
  await page.keyboard.press("Escape");
  check("Escape closes only the note and leaves the tags open", (await page.locator("#tagPop .tag-info").count()) === 0 && (await page.locator("#tagPop").isVisible()));
  await page.locator("#tagPop [data-tag-info]").click();
  await page.locator("#tagPop [data-tag-info-close]").click();
  check("Got it closes the note and leaves the tags open", (await page.locator("#tagPop .tag-info").count()) === 0 && (await page.locator("#tagPop").isVisible()));
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "tags_desktop.png") });
  await page.keyboard.press("Escape");
  check("Escape closes the pop-up", await page.locator("#tagPop").isHidden());
  await page.click("#previewInboxOptions");
  const filter = page.locator("#filterBy");
  check("the Filter list offers the tags your emails have", (await filter.locator("option").allInnerTexts()).some((t) => /Tag: Work/.test(t)));
  await filter.selectOption("tag:Work");
  await page.waitForFunction(() => document.querySelectorAll("article.mail").length === 1);
  check("choosing a tag shows only the emails with it", /Just you/.test(await page.locator("article.mail").innerText()));
  await filter.selectOption("");
  check("no script errors", errors.length === 0);
  await context.close();
}

{
  // a mailbox that cannot make tags, and one that does not keep them
  canCreate = false;
  const { page, context, errors } = await run(1300, 900);
  const row = await openRow(page, "Third one");
  await row.locator("[data-tag-open]").click();
  await page.waitForSelector("#tagPop:not([hidden]) .tagrow");
  check("when the service cannot make tags the pop-up says so and has no Make tag button", /does not let Enveliq make new tags/.test(await page.locator("#tagPop").innerText()) && (await page.locator("#tagPop button[type=submit]").count()) === 0);
  await page.locator('#tagPop [data-tag-toggle="Taxes"]').check();
  check("an existing tag can still be put on", await page.waitForFunction(() => /Taxes/.test(document.body.innerText)).then(() => true));
  await page.keyboard.press("Escape");
  supported = false;
  await row.locator("[data-tag-open]").click();
  await page.waitForSelector("#tagPop:not([hidden])");
  await page.waitForFunction(() => /does not keep tags/.test(document.getElementById("tagPop").innerText));
  check("a mailbox that keeps no tags says so plainly", true);
  check("no script errors", errors.length === 0);
  await context.close();
  canCreate = true; supported = true;
}

// A long list of tags can be searched by typing part of a name
{
  tagNames = Array.from({ length: 30 }, (_, i) => `Tag ${String(i + 1).padStart(2, "0")}`).concat(["Holidays", "Home"]).sort();
  const { page, context, errors } = await run(1300, 900);
  const row = await openRow(page, "Third one");
  await row.locator("[data-tag-open]").click();
  await page.waitForSelector("#tagPop:not([hidden]) .tagrow");
  check("with a long list the pop-up has a search box", (await page.locator("#tagFind").getAttribute("placeholder")) === "Search your tags");
  check("every tag is listed until something is typed", (await page.locator("#tagPop .tagrow").count()) === 32);
  await page.locator("#tagFind").pressSequentially("ho", { delay: 40 });
  await page.waitForFunction(() => document.querySelectorAll("#tagPop .tagrow").length === 2);
  check("typing part of a name keeps only the tags that have it, whatever the capitals", (await page.locator("#tagPop .tagrow span").allInnerTexts()).join(",") === "Holidays,Home");
  check("the box keeps what was typed and the cursor stays in it", (await page.locator("#tagFind").inputValue()) === "ho" && (await page.evaluate(() => document.activeElement && document.activeElement.id)) === "tagFind");
  const makes = calls.filter((c) => c[0] === "make").length;
  await page.keyboard.press("Enter");
  await page.waitForTimeout(300);
  check("pressing Enter in the search box does not try to make a tag", (await page.locator("#tagPop .sa-err").count()) === 0 && calls.filter((c) => c[0] === "make").length === makes);
  await page.locator('#tagPop [data-tag-toggle="Holidays"]').check();
  await page.waitForFunction(() => [...document.querySelectorAll("article.mail")].some((a) => /Third one/.test(a.innerText) && /Holidays/.test(a.innerText)));
  check("a tag found this way can be put on the email", calls.some((c) => c[0] === "set" && c[1] === "m-third" && c[2] === "Holidays" && c[3] === true));
  check("the search is still there after ticking", (await page.locator("#tagFind").inputValue()) === "ho" && (await page.locator("#tagPop .tagrow").count()) === 2);
  await page.locator("#tagFind").fill("zzz");
  await page.waitForFunction(() => /No tag has those letters/.test(document.getElementById("tagPop").innerText));
  check("when nothing matches it says so kindly", true);
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "tags_search_desktop.png") });
  await page.locator("#tagFind").fill("");
  await page.waitForFunction(() => document.querySelectorAll("#tagPop .tagrow").length === 32);
  check("clearing the box brings every tag back", true);
  await page.keyboard.press("Escape");
  await row.locator("[data-tag-open]").click();
  await page.waitForSelector("#tagPop:not([hidden]) .tagrow");
  check("opening the pop-up again starts with an empty search", (await page.locator("#tagFind").inputValue()) === "");
  check("no script errors", errors.length === 0);
  await context.close();
}
{
  const { page, context, errors } = await run(390, 800);
  await page.locator("article.mail", { hasText: "Another one" }).locator(".qmain").click();
  await page.waitForSelector(".reader [data-tag-open]");
  await page.locator(".reader [data-tag-open]").click();
  await page.waitForSelector("#tagPop:not([hidden]) #tagFind");
  check("on a phone the search box uses large text so the phone does not zoom in", (await page.locator("#tagFind").evaluate((e) => parseFloat(getComputedStyle(e).fontSize))) >= 16);
  await page.locator("#tagFind").fill("hol");
  await page.waitForFunction(() => document.querySelectorAll("#tagPop .tagrow").length === 1);
  const close = await page.locator("#tagPop .sf-top .sf-close").boundingBox();
  check("on a phone Close stays fixed at the top while searching", close.y < 80);
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "tags_search_phone.png") });
  check("no script errors", errors.length === 0);
  await context.close();
  tagNames = ["Taxes", "Work"];
}

// On a phone the pop-up fills the screen with Close at the top and the buttons at the bottom
{
  const { page, context, errors } = await run(390, 800);
  await page.locator("article.mail", { hasText: "Another one" }).locator(".qmain").click();
  await page.waitForSelector(".reader [data-tag-open]");
  await page.locator(".reader [data-tag-open]").click();
  await page.waitForSelector("#tagPop:not([hidden]) .tagrow");
  const full = await page.locator("#tagPop").boundingBox();
  check("on a phone the Tags pop-up fills the whole screen", full.x <= 1 && full.y <= 1 && full.width >= 388 && full.height >= 798);
  const close = await page.locator("#tagPop .sf-top .sf-close").boundingBox(), foot = await page.locator("#tagPop .sf-foot button[type=submit]").boundingBox();
  check("Close is fixed at the top and the buttons at the bottom", close.y < 80 && foot.y > 600 && foot.y + foot.height <= 801);
  check("on a phone the pop-up is above the full screen email", await page.evaluate(() => { const r = document.getElementById("tagPop").getBoundingClientRect(); const el = document.elementFromPoint(r.left + r.width / 2, r.top + 30); return !!el && !!el.closest("#tagPop"); }));
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "tags_phone.png") });
  await page.locator("#tagPop [data-tag-info]").click();
  await page.waitForSelector("#tagPop .tag-info");
  const card = await page.locator("#tagPop .tag-info").boundingBox();
  check("on a phone the note about filters fits on the screen", card.x >= 0 && card.x + card.width <= 390 && card.y >= 0 && card.y + card.height <= 800);
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "tags_info_phone.png") });
  await page.locator("#tagPop [data-tag-info-close]").click();
  await page.locator("#tagPop .sf-foot [data-tag-close]").click();
  check("Done closes it", await page.locator("#tagPop").isHidden());
  check("no script errors", errors.length === 0);
  await context.close();
}
await browser.close();
if (failed) process.exit(1);
