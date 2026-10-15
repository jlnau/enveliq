// Browser check for Shipping (v0.51): the page, the Home "Did it arrive?" card, the buttons, and that
// hostile text from an email is shown as text only. Loaded from a pretend Enveliq server.
//
// Usage: node scripts/check_shipping.mjs [path/to/prototype/index.html]
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";

const here = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.resolve(process.argv[2] || path.join(here, "..", "prototype", "index.html")), "utf8");
const ORIGIN = process.env.TOUR ? "https://enveliq.test" : "http://enveliq.test";   // https hides the plain-http warning in the website pictures
let failed = false;
const check = (label, good) => { console.log((good ? "\u2713 " : "\u2717 ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
for (const ev of ["uncaughtException", "unhandledRejection"]) process.on(ev, (e) => { console.log("::error::" + String((e && e.message) || e).split("\n").slice(0, 3).join(" | ")); process.exit(1); });
const now = Math.floor(Date.now() / 1000);
const ctx = (id) => ({ reply_to: "dana@example.invalid", delivered_to: null, via_alias: null, message_id: `<${id}@x>`, references: [] });
const day = (n) => new Date(Date.now() + n * 86400000).toISOString().slice(0, 10);

function makeServer(opts = {}) {
  const calls = [];
  const features = { compose: true, address_book: true, sent: true, media: true, all_mail: false, shipping: opts.shipping !== false };
  const mark = (acct, id) => createHash("sha256").update(`${acct}|${id}`).digest("hex").slice(0, 16);
  const ev = (subject, at, kind, m) => ({ at, kind, subject, m });
  let orders = [
    { id: "s" + "a".repeat(23), shop: "Northside Audio", order_number: "NA-20481", carrier: "SwiftPost", tracking: "SP4471002318AU", items: "Studio headphones", status: "delivered", expected: day(-2), expected_text: null, prev_expected: null, delayed: false, delivered_at: now - 3600, ack: null, unsure: false, needs_confirm: true, track_url: "https://example.invalid/track/SP4471002318AU", updated: now - 3600, events: [ev("Delivered today", now - 3600, "delivered"), ev("Out for delivery", now - 20000, "out_for_delivery")] },
    { id: "s" + "b".repeat(23), shop: "Brightwater Books", order_number: "BB-5509", carrier: "Harbour Freight", tracking: "HF-9984210", items: "3 books", total: "$54.90", note: "", status: "shipped", expected: day(5), expected_text: "Thu 15 Oct", prev_expected: day(3), delayed: true, delivered_at: null, ack: null, unsure: false, needs_confirm: false, track_url: "javascript:alert(1)", updated: now - 9000, events: [ev("Update on your Brightwater order", now - 9000, "delayed", mark("a1", "m1")), ev("Your books are on their way", now - 90000, "shipped", mark("a1", "gone-from-inbox")), ev("Thanks for your order", now - 190000, "order_confirmed")] },
    { id: "s" + "c".repeat(23), shop: "Cobalt Outfitters", order_number: null, carrier: null, tracking: null, items: null, status: "ordered", expected: null, expected_text: null, prev_expected: null, delayed: false, delivered_at: null, ack: null, unsure: true, needs_confirm: false, track_url: null, updated: now - 500, events: [ev("Thanks for your purchase", now - 500, "order_confirmed")] },
    { id: "s" + "d".repeat(23), shop: "<img src=x onerror=window.__pwned=1>Evil Shop", order_number: "<b>9</b>", carrier: "X", tracking: "T1", items: "<script>window.__pwned=1</script>", status: "shipped", expected: null, expected_text: null, prev_expected: null, delayed: false, delivered_at: null, ack: null, unsure: false, needs_confirm: false, track_url: "https://example.invalid/t?a=1&b=2\"onmouseover=\"x", updated: now - 100, events: [] },
  ];
  const shared = (opts.shared || []).map((c) => ({ url: "https://odd.example/{n}", ...c }));
  const carriersView = () => ({ fixed: ["Australia Post", "Sendle"], shared: shared.map(({ id, name, mine }) => ({ id, name, mine })) });
  if (opts.extraTrackable) for (const n of ["e", "f"]) orders.push({ id: "s" + n.repeat(23), shop: "Shop " + n, order_number: "E-" + n, carrier: "Sendle", tracking: "SD11223344" + n, items: null, status: "shipped", expected: null, expected_text: null, prev_expected: null, delayed: false, delivered_at: null, ack: null, unsure: false, needs_confirm: false, track_url: "https://track.sendle.com/tracking?ref=SD11223344" + n, updated: now - 100, events: [] });
  const recompute = () => { for (const o of orders) o.needs_confirm = !!o.delivered_at && !o.unsure && !o.ack && !o.snoozed; };
  const handler = async (route) => {
    const req = route.request(), p = new URL(req.url()).pathname;
    const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
    if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
    if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
    if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: opts.role || "admin" });
    if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1144, username: "u", settings: {} }]);
    if (p === "/api/v1/accounts/a1/messages") return json(200, [
    { id: "m1", subject: "Update on refund", sender_display: "Amazon", sender_address: "a@example.invalid", summary: "Your refund was processed.", priority: "normal", category: "Information", action_required: false, received_at: now - 600, reply_context: ctx("m1") },
    ]);
    if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
    if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features });
    if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: now } } });
    if (p === "/api/v1/me/outbox") return json(200, { now: Date.now() / 1000, items: [] });
    if (p === "/api/v1/me/shipping" && req.method() === "POST") {
      const b = JSON.parse(req.postData()); calls.push(["add", b]);
      if (b.tracking && b.tracking.length < 8) return json(422, { detail: "That tracking number does not look right. It needs 8 to 40 letters or digits." });
      orders.push({ id: "s" + String(orders.length + 1).padStart(23, "1"), shop: b.shop, order_number: null, carrier: null, tracking: b.tracking ? b.tracking.toUpperCase() : null, items: null, status: b.status, expected: null, expected_text: null, prev_expected: null, delayed: false, delivered_at: b.status === "delivered" ? now : null, ack: b.status === "delivered" ? "got_it" : null, unsure: false, manual: true, needs_confirm: false, track_url: null, updated: now, events: [], note: "" });
      return json(200, { enabled: true, orders, now, carriers: carriersView() });
    }
    const sm = p.match(/^\/api\/v1\/me\/shipping\/(s[0-9a-f]{23})\/status$/);
    if (sm && req.method() === "PUT") {
      const o = orders.find((x) => x.id === sm[1]); o.status = JSON.parse(req.postData()).status; calls.push(["status", sm[1], o.status]);
      return json(200, { enabled: true, orders, now, carriers: carriersView() });
    }
    if (p === "/api/v1/me/shipping") { calls.push(["list"]); return json(200, features.shipping ? { enabled: true, orders, now, carriers: carriersView() } : { enabled: false, orders: [], now }); }
    if (p === "/api/v1/shipping/carriers" && req.method() === "POST") {
      const b = JSON.parse(req.postData()); calls.push(["carrier-add", b]);
      let url = b.url.replace("{number}", "{n}");
      if (!url.includes("{n}") && b.example_number && url.includes(b.example_number)) url = url.replace(b.example_number, "{n}");
      if (!url.includes("{n}")) return json(422, { detail: "Put {number} in the address where the tracking number goes." });
      shared.push({ id: "c" + String(shared.length + 1).padStart(16, "0"), name: b.name, url, mine: true });
      for (const o of orders) if (o.carrier && o.tracking && o.carrier.toLowerCase().includes(b.name.toLowerCase())) o.track_url = url.replace("{n}", o.tracking.replace(/[^A-Za-z0-9]/g, ""));
      return json(201, { enabled: true, orders, now, carriers: carriersView() });
    }
    if (p === "/api/v1/shipping/carriers" && req.method() === "GET") { calls.push(["carrier-addresses"]); return json(200, { carriers: shared.map((c) => ({ id: c.id, name: c.name, url: c.url.replace("{n}", "{number}") })) }); }
    const em = p.match(/^\/api\/v1\/shipping\/carriers\/(c\d{16})$/);
    if (em && req.method() === "PUT") {
      const b = JSON.parse(req.postData()); calls.push(["carrier-edit", b]);
      const c = shared.find((x) => x.id === em[1]); const url = b.url.replace("{number}", "{n}");
      if (!url.includes("{n}")) return json(422, { detail: "Put {number} in the address where the tracking number goes." });
      c.name = b.name; c.url = url;
      for (const o of orders) if (o.carrier && o.tracking && o.carrier.toLowerCase().includes(c.name.toLowerCase())) o.track_url = url.replace("{n}", o.tracking.replace(/[^A-Za-z0-9]/g, ""));
      return json(200, { enabled: true, orders, now, carriers: carriersView() });
    }
    const dm = p.match(/^\/api\/v1\/shipping\/carriers\/(c\d{16})$/);
    if (dm && req.method() === "DELETE") {
      calls.push(["carrier-remove", dm[1]]); const i = shared.findIndex((c) => c.id === dm[1]); const gone = shared.splice(i, 1)[0];
      for (const o of orders) if (gone && o.carrier && o.carrier.toLowerCase().includes(gone.name.toLowerCase())) o.track_url = null;
      return json(200, { enabled: true, orders, now, carriers: carriersView() });
    }
    const nm = p.match(/^\/api\/v1\/me\/shipping\/(s[0-9a-f]{23})\/note$/);
    if (nm && req.method() === "PUT") {
      const o = orders.find((x) => x.id === nm[1]); o.note = JSON.parse(req.postData()).note; calls.push(["note", nm[1], o.note]);
      return json(200, { enabled: true, orders, now, carriers: carriersView() });
    }
    const a = p.match(/^\/api\/v1\/me\/shipping\/(s[0-9a-f]{23})\/(\w+)$/);
    if (a && req.method() === "POST") {
      calls.push([a[2], a[1]]);
      const o = orders.find((x) => x.id === a[1]);
      if (a[2] === "confirm") o.ack = "got_it"; if (a[2] === "not_yet") o.snoozed = true; if (a[2] === "track") o.unsure = false;
      if (a[2] === "not_order" || a[2] === "remove") orders = orders.filter((x) => x !== o);
      recompute();
      return json(200, { enabled: true, orders, now, carriers: carriersView() });
    }
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
  await page.addInitScript(() => { window.__opened = []; document.addEventListener("click", (e) => { const a = e.target.closest && e.target.closest("a[target=_blank]"); if (a) { window.__opened.push(a.href); e.preventDefault(); } }, true); });
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  await page.evaluate(() => { view.layout = "list"; applyView(); render(); });   // these checks look at the classic list; the default is now the reading panel on the right
  return { page, errors, csp, context };
}
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };

{
  const server = makeServer();
  const { page, errors, csp, context } = await open(server);
  check("the Shipping entry is shown when the feature is on", await page.locator("#shipNav").isVisible());
  check("the sidebar shows how many orders are being followed (4), not a dash", (await page.locator("#shipBadge").innerText()).trim() === "4");
  check("the number turns blue because one order needs you", await page.locator("#shipBadge.hot").count() === 1);
  check("Home shows the teal card for the delivered order only", (await page.locator("#shipBars .shiprow").count()) === 1 && (await page.locator("#shipBars").innerText()).includes("Northside Audio"));
  await shot(page, "ship-home");

  await page.click("#shipNav");
  await page.waitForSelector("#shipPage .ocard");
  check("the page lists all four cards and hides the email list", (await page.locator("#shipPage .ocard").count()) === 4 && await page.locator("#list").isHidden() && await page.locator("#shipBars").isHidden());
  const txt = await page.locator("#shipPage").innerText();
  check("shows shop, order number and status", txt.includes("Brightwater Books") && txt.includes("Order BB-5509") && /Shipped · due/.test(txt));
  check("a later date shows as Delayed with the old date", /Delayed\. It was/.test(txt));
  check("the unsure order asks the question", txt.includes("Is this an order?") && txt.includes("Yes, track it"));
  check("a javascript: link is never offered; an https link is", (await page.locator('#shipPage a[href^="javascript"]').count()) === 0 && (await page.locator("#shipPage a.obtn").count()) === 1 && (await page.locator("#shipPage [onmouseover]").count()) === 0);
  check("Track links open safely in a new tab", await page.evaluate(() => [...document.querySelectorAll("#shipPage a.obtn")].every((a) => a.target === "_blank" && /noopener/.test(a.rel) && a.href.startsWith("https://"))));
  check("hostile text is shown as text, not run", !(await page.evaluate(() => window.__pwned)) && (await page.locator("#shipPage img").count()) === 0 && (await page.locator("#shipPage script").count()) === 0 && txt.includes("<b>9</b>"));
  check("the progress strip has a readable label", /step \d of 4/.test((await page.locator("#shipPage .ostages").first().getAttribute("aria-label")) || ""));
  await page.locator("[data-ship-open]").nth(1).click();
  check("the matched emails open on demand", (await page.locator("#shipPage .oevents li").count()) === 3 && (await page.locator("#shipPage .oevents").innerText()).includes("Thanks for your order"));
  await shot(page, "ship-page");
  check("the browser's own hash and this page's agree (a known value)", await page.evaluate(() => sha256Hex("a1|m1").slice(0, 16)) === "a7fa9296c2cfd7f1");
  check("the matched email that is still in the inbox is a link; the others are plain text", (await page.locator("#shipPage .oevents .olinkmail").count()) === 1 && (await page.locator("#shipPage .oevents li").count()) === 3);
  check("the total is shown beside the items", (await page.locator("#shipPage").innerText()).includes("3 books · $54.90"));
  await page.locator("#shipPage .olinkmail").click();
  await page.waitForSelector("article.mail.open");
  check("pressing the link opens that email in the inbox", (await page.locator("#shipPage").isHidden()) && (await page.locator("article.mail.open").count()) === 1 && (await page.locator("article.mail.open .subject").innerText()).includes("Update on refund"));
  await page.click("#shipNav");
  await page.waitForSelector("#shipPage .ocard");
  const bw = page.locator("#shipPage .ocard", { hasText: "Brightwater" });
  await bw.locator("[data-ship-note]").click();
  await bw.locator("textarea").fill("Birthday present for Sam\nwrap it");
  check("a note box opens", (await bw.locator("textarea").count()) === 1);
  await bw.locator("[data-ship-notesave]").click();
  await page.waitForFunction(() => document.querySelector("#shipPage .onote"));
  check("saving the note sends it and shows it on the card", server.calls.some((c) => c[0] === "note" && c[2] === "Birthday present for Sam\nwrap it") && (await bw.locator(".onote").innerText()).includes("Birthday present for Sam") && (await bw.locator("[data-ship-note]").innerText()) === "Edit note");
  await bw.locator("[data-ship-note]").click();
  await bw.locator("textarea").fill("half typed");
  await page.evaluate(() => refreshShipping());
  await page.waitForTimeout(150);
  check("a refresh while typing a note does not wipe it", (await bw.locator("textarea").inputValue()) === "half typed");
  await bw.locator("[data-ship-notecancel]").click();
  check("cancel closes the box and keeps the old note", (await bw.locator("textarea").count()) === 0 && (await bw.locator(".onote").innerText()).includes("Birthday present"));

  await page.reload();
  await page.waitForSelector("#shipPage .ocard");
  check("after a refresh you are still on the Shipping page", (await page.evaluate(() => location.hash)) === "#/shipping" && await page.locator("#shipPage").isVisible());
  await page.locator('#shipPage [data-ship="track"]').click();
  await page.waitForFunction(() => !document.querySelector("#shipPage .ocard.unsure"));
  check("Yes, track it asks the server and the question goes away", server.calls.some((c) => c[0] === "track"));
  await page.locator('#shipPage .ocard', { hasText: "Evil Shop" }).locator('[data-ship="not_order"]').click();
  await page.waitForFunction(() => document.querySelectorAll("#shipPage .ocard").length === 3);
  check("Not an order removes the card", server.calls.some((c) => c[0] === "not_order"));

  await page.locator('#shipPage [data-ship="not_yet"]').click();
  await page.waitForFunction(() => !document.querySelector("#shipPage .ocard.arrive"));
  check("Not yet hides the confirm question for now", server.calls.some((c) => c[0] === "not_yet"));

  check("no script errors or policy violations", errors.length === 0 && csp.length === 0);
  await page.close(); await context.close();
}

{
  const server = makeServer();
  const { page, context } = await open(server);
  await page.locator('#shipBars [data-ship="confirm"]').click();
  await page.waitForFunction(() => document.querySelector("#shipBars").hidden);
  check("Yes, I've got it removes the Home card", server.calls.some((c) => c[0] === "confirm"));
  check("Home no longer asks", (await page.locator("#shipBars .shiprow").count()) === 0);
  await page.click("#shipNav");
  check("the order stays on the page as 'You got it' with Undo", (await page.locator("#shipPage").innerText()).includes("You got it") && (await page.locator('#shipPage [data-ship="undo"]').count()) === 1);
  await page.close(); await context.close();
}

{
  // Carriers: Track all, Copy number, adding a carrier everyone shares
  const server = makeServer({ extraTrackable: true, shared: [{ id: "c" + "9".repeat(16), name: "<img src=x onerror=window.__pwned=1>Odd Post", mine: false }] });
  const { page, errors, csp, context } = await open(server);
  await page.click("#shipNav");
  await page.waitForSelector("#shipPage .ocard");
  const all = page.locator("[data-ship-trackall]");
  check("Track all is offered when two or more parcels are on their way, with a count", (await all.count()) === 1 && /Track all \(3\)/.test(await all.innerText()));
  await all.click();
  const opened = await page.evaluate(() => window.__opened);
  check("it opens each parcel on its way in its carrier's own page, and nothing else", opened.length === 3 && opened.every((u) => u.startsWith("https://")) && !opened.some((u) => /Northside|SP4471002318AU/.test(u)));
  check("it explains what to do if the browser blocks pop-ups", (await page.locator("#shipPage").innerText()).includes("allow pop-ups"));

  const bw = page.locator("#shipPage .ocard", { hasText: "Brightwater" });
  check("a carrier without a link says so and offers to add it, plus a Copy number button", (await bw.locator("[data-carrier-add]").count()) === 1 && (await bw.locator("a.obtn").count()) === 0 && (await bw.locator("[data-ship-copy]").count()) === 1);
  await bw.locator("[data-ship-copy]").click();
  await page.waitForFunction(() => /copied|Could not copy/.test(document.getElementById("toast").textContent));
  check("Copy number copies it and says so", (await page.locator("#toast").innerText()).includes("Tracking number copied"));

  const box = page.locator("#carBox");
  check("the carriers box starts folded away", (await page.locator("#carName").count()) === 0);
  await bw.locator("[data-carrier-add]").click();
  await page.waitForSelector("#carName");
  check("Add this carrier opens the form with the carrier's name and tracking number filled in", (await page.inputValue("#carName")) === "Harbour Freight" && (await page.inputValue("#carEx")) === "HF-9984210");
  check("the built-in list and the household's list are shown, the odd name as plain text", (await box.innerText()).includes("Built in: Australia Post, Sendle.") && (await box.innerText()).includes("<img src=x") && (await box.locator("img").count()) === 0 && !(await page.evaluate(() => window.__pwned)));
  await page.fill("#carUrl", "https://track.harbour.example/find");
  await page.click("[data-carrier-save]");
  await page.waitForSelector(".carerr");
  check("an address without the number place is explained, and nothing typed is lost", (await page.locator(".carerr").innerText()).includes("{number}") && (await page.inputValue("#carName")) === "Harbour Freight" && (await page.inputValue("#carUrl")) === "https://track.harbour.example/find");
  await page.fill("#carUrl", "https://track.harbour.example/find/HF-9984210");
  await page.evaluate(() => refreshShipping());
  await page.waitForTimeout(150);
  check("a refresh while typing does not wipe the form", (await page.inputValue("#carUrl")) === "https://track.harbour.example/find/HF-9984210");
  await shot(page, "ship-carriers");
  await page.click("[data-carrier-save]");
  await page.waitForFunction(() => document.querySelector("#shipPage .ocard a.obtn[href*='harbour.example']"));
  check("saving sends the name, address and example, and the parcel gets its Track link at once", server.calls.some((c) => c[0] === "carrier-add" && c[1].name === "Harbour Freight" && c[1].example_number === "HF-9984210") && (await bw.locator("a.obtn").count()) === 1);
  check("the new carrier appears in the list with a way to remove it", (await box.locator(".carchip", { hasText: "Harbour Freight" }).count()) === 1);
  await box.locator(".carchip", { hasText: "Harbour Freight" }).locator("[data-carrier-edit]").click();
  await page.waitForFunction(() => document.getElementById("carUrl") && document.getElementById("carUrl").value.includes("{number}"));
  check("an administrator can edit a saved carrier: the form opens with its name and address, {number} showing", (await page.inputValue("#carName")) === "Harbour Freight" && (await page.inputValue("#carUrl")) === "https://track.harbour.example/find/{number}" && (await page.locator("[data-carrier-save]").innerText()) === "Save changes");
  await page.fill("#carUrl", "https://track.harbour.example/parcel?ref={number}");
  await page.click("[data-carrier-save]");
  await page.waitForFunction(() => document.querySelector("#shipPage .ocard a.obtn[href*='parcel?ref']"));
  check("saving the change updates the parcel's Track link and closes the edit", server.calls.some((c) => c[0] === "carrier-edit" && c[1].url.includes("parcel?ref")) && (await page.locator("[data-carrier-cancel]").count()) === 0 && (await page.inputValue("#carName")) === "");
  await box.locator(".carchip", { hasText: "Harbour Freight" }).locator("[data-carrier-edit]").click();
  await page.waitForSelector("[data-carrier-cancel]");
  await page.click("[data-carrier-cancel]");
  check("Cancel leaves the form empty again", (await page.locator("[data-carrier-cancel]").count()) === 0 && (await page.inputValue("#carName")) === "");
  const rm = box.locator(".carchip", { hasText: "Harbour Freight" }).locator("[data-carrier-remove]");
  await rm.click();
  check("removing asks once more, because it affects everyone", (await box.locator(".carchip", { hasText: "Harbour Freight" }).innerText()).includes("Remove for everyone?") && !server.calls.some((c) => c[0] === "carrier-remove"));
  await box.locator(".carchip", { hasText: "Harbour Freight" }).locator("[data-carrier-remove]").click();
  await page.waitForFunction(() => !document.querySelector("#carBox .carchip:nth-of-type(2)") || document.querySelectorAll("#carBox .carchip").length === 1);
  check("after the second press it is gone, and the parcel loses its link", server.calls.some((c) => c[0] === "carrier-remove") && (await bw.locator("a.obtn").count()) === 0);
  check("no script errors or policy violations", errors.length === 0 && csp.length === 0);
  await page.close(); await context.close();
}

{
  // someone who is not an administrator cannot remove a carrier somebody else added
  const server = makeServer({ role: "user", shared: [{ id: "c" + "8".repeat(16), name: "Zippy Post", mine: false }, { id: "c" + "7".repeat(16), name: "My Courier", mine: true }] });
  const { page, context } = await open(server);
  await page.click("#shipNav");
  await page.waitForSelector("#shipPage .ocard");
  await page.click("[data-carriers-toggle]");
  const z = page.locator(".carchip", { hasText: "Zippy Post" }), m = page.locator(".carchip", { hasText: "My Courier" });
  check("you can remove only the carriers you added", (await z.locator("[data-carrier-remove]").count()) === 0 && (await m.locator("[data-carrier-remove]").count()) === 1);
  check("only an administrator is offered Edit", (await page.locator("[data-carrier-edit]").count()) === 0);
  await page.close(); await context.close();
}

// A parcel added by hand: sender, tracking number and where it is up to
{
  const server = makeServer();
  const { page, errors, context } = await open(server);
  await page.click("#shipNav");
  await page.waitForSelector("#shipPage .ocard");
  const before = await page.locator("#shipPage .ocard").count();
  check("the Shipping page has an Add a parcel button", (await page.locator("[data-ship-add-open]").innerText()).includes("Add a parcel"));
  await page.click("[data-ship-add-open]");
  check("it opens a form with the three fields", (await page.locator("#saShop").count()) === 1 && (await page.locator("#saTrack").count()) === 1 && (await page.locator("#saStatus option").allInnerTexts()).join("|") === "Waiting to be shipped|Shipped|Out for delivery|Delivered");
  check("the cursor starts in the first box", await page.evaluate(() => document.activeElement && document.activeElement.id === "saShop"));
  await shot(page, "ship-add-form");
  await page.click("[data-ship-add-form] button[type=submit]");
  check("an empty sender is not sent and says why", !server.calls.some((c) => c[0] === "add") && /who the parcel is from/i.test(await page.locator(".sa-err").innerText()));
  await page.fill("#saShop", "Corner Hardware");
  await page.fill("#saTrack", "12");
  await page.click("[data-ship-add-form] button[type=submit]");
  await page.waitForFunction(() => /does not look right/.test(document.querySelector(".sa-err")?.innerText || ""));
  check("a tracking number the server refuses shows its message and keeps what you typed", /does not look right/.test(await page.locator(".sa-err").innerText()) && (await page.inputValue("#saShop")) === "Corner Hardware");
  await page.fill("#saTrack", "ab-1234-5678");
  await page.selectOption("#saStatus", "ordered");
  await page.click("[data-ship-add-form] button[type=submit]");
  await page.waitForFunction(() => !document.querySelector("[data-ship-add-form]"));
  const add = server.calls.filter((c) => c[0] === "add").pop();
  check("the parcel is sent with sender, tracking number and status", add[1].shop === "Corner Hardware" && add[1].tracking === "ab-1234-5678" && add[1].status === "ordered");
  check("the new parcel is on the page as 'Waiting to be shipped'", (await page.locator("#shipPage .ocard").count()) === before + 1 && /Corner Hardware/.test(await page.locator("#shipPage").innerText()) && /Waiting to be shipped/.test(await page.locator("#shipPage").innerText()));
  const card = page.locator("#shipPage .ocard", { hasText: "Corner Hardware" });
  check("it shows its tracking number and has no 'Not an order' or email count", /AB-1234-5678/.test(await card.innerText()) && !/Not an order|matched/.test(await card.innerText()));
  await card.locator("select.ostatus").selectOption("shipped");
  await page.waitForFunction(() => [...document.querySelectorAll("#shipPage .ocard")].some((c) => /Corner Hardware/.test(c.innerText) && /Shipped/.test(c.querySelector(".opill")?.innerText || "")));
  check("you can change where it is up to", server.calls.some((c) => c[0] === "status" && c[2] === "shipped") && /Shipped/.test(await page.locator("#shipPage .ocard", { hasText: "Corner Hardware" }).locator(".opill").innerText()));
  await page.locator("#shipPage .ocard", { hasText: "Corner Hardware" }).locator('[data-ship="remove"]').click();
  await page.waitForFunction((n) => document.querySelectorAll("#shipPage .ocard").length === n, before);
  check("Remove takes the parcel off the list", !/Corner Hardware/.test(await page.locator("#shipPage").innerText()));
  await page.click("[data-ship-add-open]");
  await page.click(".sf-foot [data-ship-add-cancel]");
  check("Cancel closes the form without sending", (await page.locator("[data-ship-add-form]").count()) === 0 && server.calls.filter((c) => c[0] === "add").length === 2);
  check("no script errors", errors.length === 0);
  await shot(page, "ship-add");
  await page.close(); await context.close();
}

// On a phone the form fills the screen: title and Close fixed at the top, the buttons fixed at the bottom
{
  const server = makeServer();
  const { page, errors, context } = await open(server, { width: 390, height: 640 });
  await page.evaluate(() => { filter = "shipping"; render(); });
  await page.waitForSelector("[data-ship-add-open]");
  await page.click("[data-ship-add-open]");
  await page.waitForSelector("[data-ship-add-form]");
  const box = await page.locator("[data-ship-add-form]").boundingBox();
  check("phone: the form fills the whole screen", box.x <= 1 && box.y <= 1 && box.width >= 388 && box.height >= 638);
  const parts = await page.evaluate(() => { const r = (s) => document.querySelector(s).getBoundingClientRect(); const t = r(".shipadd .sf-top"), f = r(".shipadd .sf-foot"); return { topY: t.top, footBottom: f.bottom, closeShown: getComputedStyle(document.querySelector(".shipadd .sf-close")).display !== "none" }; });
  check("phone: the title bar is at the top and the buttons are at the bottom", parts.topY <= 1 && parts.footBottom >= 639 && parts.closeShown);
  await shot(page, "ship-add-phone");
  await page.evaluate(() => { const b = document.querySelector(".shipadd .sf-body"); b.style.minHeight = "0"; const pad = document.createElement("div"); pad.style.height = "1200px"; b.append(pad); b.scrollTop = b.scrollHeight; });
  const after = await page.evaluate(() => { const t = document.querySelector(".shipadd .sf-top").getBoundingClientRect(), f = document.querySelector(".shipadd .sf-foot").getBoundingClientRect(); return { top: t.top, foot: f.bottom }; });
  check("phone: after scrolling the form the Close and Add parcel buttons are still in view", after.top <= 1 && after.foot >= 639);
  await page.click(".shipadd .sf-close");
  check("phone: the Close button closes the form", (await page.locator("[data-ship-add-form]").count()) === 0);
  check("no script errors", errors.length === 0);
  await page.close(); await context.close();
}

{
  const server = makeServer({ shipping: false });
  const { page, context } = await open(server);
  check("with the feature off there is no menu entry, no Home card and no request", await page.locator("#shipNav").isHidden() && await page.locator("#shipBars").isHidden() && !server.calls.some((c) => c[0] === "list"));
  await page.close(); await context.close();
}

{
  const server = makeServer();
  const { page, context } = await open(server, { width: 390, height: 800 });
  check("phone: the Home card fits the screen", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  check("phone: its buttons are at least 44px tall", await page.evaluate(() => [...document.querySelectorAll("#shipBars .obtn")].every((b) => b.getBoundingClientRect().height >= 43)));
  await shot(page, "ship-home-phone");
  await page.close(); await context.close();
}

await browser.close();
process.exit(failed ? 1 : 0);
