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
  let seen = false;
  const base = { subject: "x", sender_address: "s@example.invalid", priority: "normal", category: "Shopping", received_at: now - 300, state: "unread" };
  const msgs = [
    { id: "m1", subject: "Can you make Tuesday?", sender_display: "Dana Whitlock", sender_address: "dana@example.invalid", summary: "Dana asks if you can make Tuesday.", priority: "normal", category: "Information", action_required: true, received_at: now - 600, reply_context: { reply_to: "dana@example.invalid", delivered_to: null, via_alias: null, message_id: "<m1@x>", references: [] } },
    { ...base, id: "m2", subject: "<img src=x onerror=window.__pwned=1>Sale", sender_display: "Shop", summary: "<b>Everything is half price.</b>", held_for_summary: true, files: 1 },
    { ...base, id: "m3", subject: "Your newsletter", sender_display: "News", summary: "This week's news.", category: "Newsletters", held_for_summary: true, files: 2 },
  ];
  const view = () => { const items = msgs.filter((m) => m.held_for_summary && !m.gone).map((m) => ({ account_id: "a1", message_id: m.id, sender: m.sender_display, subject: m.subject, summary: m.summary, category: m.category, held_at: now, received_at: m.received_at, attachments: m.files || 0 })); return { enabled: opts.off !== true, count: items.length, unread: !seen, items }; };
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
    if (p === "/api/v1/accounts/a1/messages") return json(200, msgs.filter((m) => !m.gone).map((m) => ({ ...m })));
    if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
    if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features });
    if (p === "/api/v1/me/write-help") return json(200, info);
    if (p === "/api/v1/me/held-summary") return json(200, view());
    if (p === "/api/v1/me/held-summary/seen") { calls.push(["seen"]); seen = true; return json(200, { ok: true }); }
    if (p === "/api/v1/me/held-summary/complete") { calls.push(["complete"]); const n = msgs.filter((m) => m.held_for_summary && !m.gone).length; msgs.forEach((m) => { m.held_for_summary = false; }); return json(200, { returned: n }); }
    if (p === "/api/v1/me/held-summary/remove") { calls.push(["remove", body().message_id]); msgs.find((m) => m.id === body().message_id).held_for_summary = false; return json(200, { ok: true }); }
    if (/\/api\/v1\/accounts\/a1\/messages\/[^/]+\/resolve$/.test(p)) { const id = p.split("/")[6]; calls.push(["resolve", id, body().outcome]); msgs.find((m) => m.id === id).gone = true; return json(200, { ok: true }); }
    if (/\/api\/v1\/accounts\/a1\/messages\/[^/]+\/original$/.test(p)) { const id = p.split("/")[6]; calls.push(["original", id]); const files = id === "m3" ? [{ index: 0, filename: "Newsletter.pdf", size_bytes: 2048, mime_type: "application/pdf", viewable: true }, { index: 1, filename: "Offer.pdf", size_bytes: 4096, mime_type: "application/pdf", viewable: true }] : id === "m2" ? [{ index: 0, filename: "Receipt.pdf", size_bytes: 1024, mime_type: "application/pdf", viewable: true }] : []; return json(200, { subject: "x", from: { name: "Shop", address: "shop@example.invalid" }, to: [], date: "2026-10-14", text: "The whole email, as sent.", attachments: files, links: [], remote_images: 0 }); }
    if (/\/attachments\/(\d+)\/view$/.test(p)) { calls.push(["view", p.split("/")[8]]); return json(200, { kind: "pdf", pages: ["iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="], total: 1, shown: 1 }); }
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
  page.on("pageerror", (e) => { errors.push(String(e)); if (process.env.DBG) console.log("PAGEERR", String(e)); });
  await context.route(`${ORIGIN}/**`, server.handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  return { page, errors, context };
}
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };
const subjects = (page) => page.evaluate(() => [...document.querySelectorAll("article.mail")].map((a) => a.innerText));
{
  const server = makeServer();
  const { page, errors, context } = await open(server);
  await page.waitForSelector(".dg-row");
  const inbox = (await subjects(page)).join("\n");
  check("held email is not in the inbox list, the other email is", inbox.includes("Can you make Tuesday") && !inbox.includes("Sale") && !inbox.includes("newsletter"));
  const row = await page.locator(".dg-row").innerText();
  check("the summary is a special row at the top of the inbox with a Summary tag and the number waiting", row.includes("Summary") && row.includes("2 emails waiting") && (await page.locator(".dg-row.read").count()) === 0);
  check("it sits above the emails", await page.evaluate(() => document.getElementById("digestStrip").getBoundingClientRect().top < document.querySelector("article.mail").getBoundingClientRect().top));
  const nav = await page.locator("#heldNav").innerText();
  check("Held for summary is in the left menu with the number", nav.includes("Held for summary") && !(await page.locator("#heldNav").isHidden()));
  await shot(page, "daily-summary-row");
  await page.click("#heldNav");
  await page.waitForFunction(() => document.querySelectorAll("article.mail").length === 2);
  const held = (await subjects(page)).join("\n");
  check("the Held for summary list shows the held emails themselves, not the inbox one", held.includes("Sale") && held.includes("newsletter") && !held.includes("Can you make Tuesday"));
  await page.click('.nav[data-filter="all"]');
  await page.click(".dg-row");
  await page.waitForSelector("#digestView.open");
  const text = await page.locator("#dgBody").innerText();
  check("it opens like an email: written by AI, grouped by kind, nothing treated as page code", text.includes("Summaries written by AI") && text.includes("Shopping") && text.includes("Newsletters") && (await page.locator("#dgBody img").count()) === 0 && (await page.evaluate(() => window.__pwned)) === undefined && text.includes("<b>Everything is half price.</b>"));
  const first = page.locator("#dgBody .dg-item").first();
  const names = await first.locator(".dg-ic").evaluateAll((els) => els.map((e) => e.getAttribute("aria-label") + "|" + e.title + "|" + e.innerText.trim()));
  check("each email has four icon-only buttons with names on hover: reviewed, archive, bin, send back", names.length === 4 && names.every((n) => n.split("|")[2] === "" && n.split("|")[1]) && /reviewed/i.test(names[0]) && /archive/i.test(names[1]) && /bin/i.test(names[2]) && /send back to the inbox/i.test(names[3]));
  check("taking one out is a same-size icon button titled Send back to the inbox, not a reply arrow", (await first.locator("button[title='Send back to the inbox']").count()) === 1 && (await first.locator("[aria-label*='reply' i]").count()) === 0);
  check("every email shows the day and time it arrived", (await page.locator("#dgBody .dg-when").count()) === (await page.locator("#dgBody .dg-item").count()) && /\d/.test(await first.locator(".dg-when").innerText()));
  check("the top and bottom bars stay put and only the middle scrolls", await page.evaluate(() => { const v = document.getElementById("digestView"), b = document.getElementById("dgBody"); return getComputedStyle(v).overflow === "hidden" && getComputedStyle(b).overflowY === "auto" && v.getBoundingClientRect().bottom <= innerHeight && document.querySelector("#digestView .compose-foot").getBoundingClientRect().bottom <= innerHeight; }));
  check("opening it marks it seen", await page.waitForFunction(() => document.querySelector(".dg-row.read")).then(() => true).catch(() => false) && server.calls.some((c) => c[0] === "seen"));
  await shot(page, "daily-summary-open");
  // take one out: it goes back to the inbox
  await page.locator("#dgBody .dg-item", { hasText: "newsletter" }).locator("button[title='Send back to the inbox']").click();
  await page.waitForFunction(() => document.querySelectorAll("#dgBody .dg-item").length === 1);
  check("taking one out puts it back in the inbox and out of the summary", server.calls.some((c) => c[0] === "remove" && c[1] === "m3"));
  // archive the other: the summary finishes by itself
  await page.locator("#dgBody .dg-item .dg-ic").nth(1).click();
  await page.waitForFunction(() => !document.getElementById("digestView").classList.contains("open"));
  check("archiving the last one uses the normal action and closes the summary by itself", server.calls.some((c) => c[0] === "resolve" && c[1] === "m2") && (await page.locator(".dg-row").count()) === 0);
  const after = (await subjects(page)).join("\n");
  check("the email that was taken out is back in the inbox", after.includes("newsletter") && after.includes("Can you make Tuesday") && !after.includes("Sale"));
  check("no page errors", errors.length === 0);
  await context.close();
}
{
  const server = makeServer();
  const { page, context } = await open(server);
  await page.click(".dg-row");
  await page.waitForSelector("#digestView.open");
  await page.mouse.click(5, 450);
  await page.waitForFunction(() => !document.getElementById("digestView").classList.contains("open"));
  check("clicking outside the summary box closes it", server.calls.every((c) => c[0] !== "complete"));
  await page.click(".dg-row");
  await page.waitForSelector("#digestView.open");
  await page.click("#dgDone");
  await page.waitForFunction(() => !document.getElementById("digestView").classList.contains("open"));
  await page.waitForFunction(() => document.body.innerText.includes("Sale"));
  const after = (await subjects(page)).join("\n");
  check("Done with summary puts everything still in it back in the inbox, and it is at the top as well as the bottom", server.calls.some((c) => c[0] === "complete") && after.includes("newsletter") && after.includes("Sale") && (await page.locator(".dg-row").count()) === 0);
  await context.close();
}
{
  const server = makeServer();
  const { page, errors, context } = await open(server);
  await page.waitForSelector(".dg-row");
  await page.click(".dg-row");
  await page.waitForSelector("#digestView.open");
  const shop = page.locator("#dgBody .dg-item", { hasText: "Sale" }), news = page.locator("#dgBody .dg-item", { hasText: "newsletter" });
  check("the take-out button is an up arrow, as in the Android app", (await shop.locator("button[title='Send back to the inbox'] svg path").evaluateAll((ps) => ps.map((x) => x.getAttribute("d")))).join("|").includes("m6 12 6-6 6 6"));
  const bg = await shop.locator(".dg-ic").evaluateAll((els) => els.map((e) => getComputedStyle(e).backgroundColor + "/" + getComputedStyle(e).borderTopColor));
  check("Reviewed, Archive and Bin have their own colours, the same as the buttons elsewhere", new Set(bg.slice(0, 3)).size === 3 && bg.slice(0, 3).every((c) => !c.startsWith("rgba(0, 0, 0, 0)")));
  check("the take-out button is blue-edged like the app's other quiet actions", bg[3] !== bg[0] && bg[3] !== bg[1] && bg[3] !== bg[2]);
  const pos = await shop.evaluate((el) => { const w = el.querySelector(".dg-when").getBoundingClientRect(), who = el.querySelector(".dg-who").getBoundingClientRect(), box = el.getBoundingClientRect(); return { fromEdge: box.right - w.right, gap: w.left - who.right }; });
  check("the date and time sit at the far right of the row, not against the sender", pos.fromEdge < 20 && pos.gap > 60);
  check("every email has Show full email; only those with files have Show attachment", (await page.locator("#dgBody .dg-txt", { hasText: "Show full email" }).count()) === 2 && (await shop.locator(".dg-txt", { hasText: "Show attachment" }).count()) === 1 && (await news.locator(".dg-txt", { hasText: "Show attachments" }).count()) === 1);
  check("an email with files has a paperclip", (await shop.locator(".dg-clip svg").count()) === 1 && (await news.locator(".dg-clip svg").count()) === 1);
  await shot(page, "daily-summary-buttons");
  await shop.locator(".dg-txt", { hasText: "Show attachment" }).click();
  await page.waitForFunction(() => !document.getElementById("docBox").hidden);
  check("one attachment opens straight away in the viewer, with no list", server.calls.some((c) => c[0] === "view" && c[1] === "0") && !(await page.locator("#dgAtt").evaluate((e) => e.classList.contains("open"))) && (await page.locator("#docName").innerText()).includes("Receipt"));
  await page.click("#docBox [aria-label='Close'], #docClose").catch(() => {});
  await page.evaluate(() => { document.getElementById("docBox").hidden = true; });
  await page.click(".dg-row").catch(() => {});
  if (!(await page.locator("#digestView.open").count())) { await page.waitForSelector(".dg-row"); await page.click(".dg-row"); await page.waitForSelector("#digestView.open"); }
  await page.locator("#dgBody .dg-item", { hasText: "newsletter" }).locator(".dg-txt", { hasText: "Show attachments" }).click();
  await page.waitForSelector("#dgAtt.open");
  const picks = await page.locator("#dgAtt .dg-pick").allInnerTexts();
  check("two attachments ask which one, listing both by name", picks.length === 2 && picks[0].includes("Newsletter.pdf") && picks[1].includes("Offer.pdf"));
  check("the list sits above the summary and fits the screen", await page.evaluate(() => { const r = document.getElementById("dgAtt").getBoundingClientRect(); return r.width > 200 && r.right <= innerWidth && r.bottom <= innerHeight && Number(getComputedStyle(document.getElementById("dgAtt")).zIndex) > Number(getComputedStyle(document.getElementById("digestView")).zIndex); }));
  await shot(page, "daily-summary-attachment-list");
  await page.locator("#dgAtt .dg-pick").nth(1).click();
  await page.waitForFunction(() => !document.getElementById("docBox").hidden);
  check("choosing one opens that file", server.calls.some((c) => c[0] === "view" && c[1] === "1") && (await page.locator("#docName").innerText()).includes("Offer"));
  check("the list closes once a file is chosen", !(await page.locator("#dgAtt").evaluate((e) => e.classList.contains("open"))));
  await page.evaluate(() => { document.getElementById("docBox").hidden = true; });
  await page.waitForSelector(".dg-row"); await page.click(".dg-row"); await page.waitForSelector("#digestView.open");
  await page.locator("#dgBody .dg-item", { hasText: "Sale" }).locator(".dg-txt", { hasText: "Show full email" }).click();
  await page.waitForSelector("#attachmentModal.open");
  check("Show full email fetches and shows the original email", server.calls.some((c) => c[0] === "original" && c[1] === "m2") && (await page.locator("#attachmentModal").innerText()).includes("The whole email, as sent."));
  check("no page errors", errors.length === 0);
  await context.close();
}
{
  const server = makeServer({ off: true });
  const { page, context } = await open(server);
  await page.waitForTimeout(300);
  const inbox = (await subjects(page)).join("\n");
  check("with the switch off nothing is held and there is no summary row", (await page.locator(".dg-row").count()) === 0 && inbox.includes("Sale") && (await page.locator("#heldNav").isHidden()));
  await context.close();
}
{
  const server = makeServer();
  const { page, context } = await open(server, { width: 390, height: 800 });
  await page.waitForSelector(".dg-row");
  check("phone: the row is tall enough to tap and fits", await page.evaluate(() => { const r = document.querySelector(".dg-row").getBoundingClientRect(); return r.height >= 44 && r.right <= innerWidth; }));
  await page.click(".dg-row");
  await page.waitForSelector("#digestView.open");
  check("phone: it opens full screen with Done and Close reachable and the icon buttons big enough", await page.evaluate(() => { const r = document.getElementById("digestView").getBoundingClientRect(); const c = document.getElementById("dgDone").getBoundingClientRect(); const ic = document.querySelector(".dg-ic").getBoundingClientRect(); return r.width >= innerWidth - 1 && r.height >= innerHeight - 1 && c.bottom <= innerHeight && c.height >= 44 && ic.width >= 44 && ic.height >= 44; }));
  await page.evaluate(() => { for (let i = 0; i < 40; i++) { const d = document.createElement("div"); d.className = "dg-item"; d.textContent = "More mail ".repeat(20); document.getElementById("dgBody").append(d); } });
  check("phone: with a long summary only the middle scrolls, and the buttons stay at the bottom", await page.evaluate(() => { const b = document.getElementById("dgBody"), c = document.getElementById("dgDone").getBoundingClientRect(), x = document.getElementById("dgClose").getBoundingClientRect(); return b.scrollHeight > b.clientHeight && c.bottom <= innerHeight && x.bottom <= innerHeight; }));
  check("phone: the new buttons fit inside the box and are tall enough to tap", await page.evaluate(() => { const box = document.getElementById("dgBody").getBoundingClientRect(); return [...document.querySelectorAll("#dgBody .dg-txt, #dgBody a.dg-open")].every((b) => { const r = b.getBoundingClientRect(); return r.height >= 44 && r.right <= box.right + 1 && r.left >= box.left - 1; }); }));
  await shot(page, "daily-summary-phone");
  await context.close();
}
await browser.close();
if (failed) process.exit(1);
