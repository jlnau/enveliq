// Browser check for the files listed under an email's summary, with the AI summary of each. Uses the demo build (made-up mail, no server).
// Usage: node scripts/check_attachment_summaries.mjs      Set SHOTS=<folder> to save screenshots.
import { chromium } from "playwright";
import http from "node:http"; import fs from "node:fs"; import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
execFileSync("node", ["demo/build.mjs"], { cwd: root, stdio: "ignore" });
const dist = path.join(root, "demo", "dist");
const headers = Object.fromEntries(fs.readFileSync(path.join(dist, "_headers"), "utf8").split("\n").slice(1).filter((l) => l.includes(":")).map((l) => { const i = l.indexOf(":"); return [l.slice(0, i).trim().toLowerCase(), l.slice(i + 1).trim()]; }));
const types = { ".html": "text/html; charset=utf-8", ".webp": "image/webp", ".png": "image/png" };
const srv = http.createServer((q, r) => {
  const p = q.url.split("?")[0], f = path.join(dist, p === "/" ? "index.html" : p.replace(/^\/+/, ""));
  if (!f.startsWith(dist + path.sep) || f.endsWith("_headers") || !fs.existsSync(f)) { r.statusCode = 404; return r.end("not found"); }
  for (const [k, v] of Object.entries(headers)) r.setHeader(k, v);
  r.setHeader("content-type", types[path.extname(f)] || "application/octet-stream"); r.end(fs.readFileSync(f));
}).listen(0);
const url = `http://127.0.0.1:${srv.address().port}/`;
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
const b = await chromium.launch();
const shots = process.env.SHOTS; if (shots) fs.mkdirSync(shots, { recursive: true });

for (const [name, vp] of [["desktop", { width: 1180, height: 820 }], ["phone", { width: 390, height: 800 }]]) {
  const p = await b.newPage({ viewport: vp }); const errors = [];
  p.on("pageerror", (e) => errors.push(String(e)));
  await p.goto(url); await p.waitForTimeout(600);
  await p.evaluate(() => {
    const base = data.find((x) => x.status === "inbox" && x.owner === currentUser.id);
    data.forEach((m) => { m.attachments = []; });
    const file = (o) => ({ mime: "application/pdf", size: "2.1 MB", pages: 40, state: "done", ...o });
    data.push({ ...base, id: 9201, subject: "Three files", real: { accountId: "a", messageId: "m" }, attachments: [
      file({ name: "rates-letter.pdf", summary: "Your loan rate rises to 6.1% from 1 May.", parts: [{ title: "What changes", text: "The rate rises to 6.1% from 1 May." }, { title: "What to do", text: "Nothing, unless you want to switch lenders by 30 April." }], note: "" }),
      file({ name: "long-contract.pdf", pages: 900, state: "working" }),
      file({ name: "scan.png", mime: "image/png", pages: 0, state: "skipped", reason: "Pictures and scans are not read yet." }),
      file({ name: "broken.docx", mime: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", state: "failed", reason: "The AI server could not be reached, so this file was not summarised." })] });
    data.push({ ...base, id: 9202, subject: "No files here", attachments: [] });
    data.push({ ...base, id: 9203, subject: "Files never read", real: { accountId: "a", messageId: "n" }, attachments: [], hasFiles: true, fileCount: 2 });
    document.querySelector(".demo-banner")?.remove(); expanded.add("row-9201"); expanded.add("row-9202"); expanded.add("row-9203"); render();
  });
  const mail = p.locator("article.mail", { hasText: "Three files" });
  const rows = mail.locator(".ad-row");
  check(name + ": one row per file, under a heading that counts them", (await rows.count()) === 4 && (await mail.locator(".ad-title").innerText()).includes("4 attachments"));
  const unread = p.locator("article.mail", { hasText: "Files never read" });
  check(name + ": an email with files but no rows says its files were not read, with a button to read them again", (await unread.locator(".ad-title").innerText()).includes("2 attachments") && (await unread.locator(".ad-wait").innerText()).includes("has not read the files") && (await unread.locator("[data-att-retry]").innerText()) === "Read the files again");
  check(name + ": an email with no files shows no attachments box", (await p.locator("article.mail", { hasText: "No files here" }).locator(".ad-block").count()) === 0);
  const order = await mail.evaluate((a) => { const s = a.querySelector(".qsummary"), b = a.querySelector(".ad-block"), t = a.querySelector(".qtask, .task, [class*=task]"); return { afterSummary: !!(s.compareDocumentPosition(b) & 4), beforeTask: !t || !!(b.compareDocumentPosition(t) & 4) }; });
  check(name + ": the files sit under the email summary and above the task", order.afterSummary && order.beforeTask);
  check(name + ": each row shows its name, kind and one-line summary", (await rows.nth(0).locator(".ad-name").innerText()) === "rates-letter.pdf" && (await rows.nth(0).locator(".ad-meta").innerText()).includes("PDF") && (await rows.nth(0).locator(".ad-line").innerText()).includes("6.1%"));
  check(name + ": a file being read says so, and one that could not be says that too", (await rows.nth(1).locator(".ad-line").innerText()) === "Reading…" && (await rows.nth(2).locator(".ad-line").innerText()) === "Not summarised" && (await rows.nth(3).locator(".ad-line").innerText()) === "Not summarised");
  check(name + ": the detail is closed until the row is clicked", !(await rows.nth(0).locator(".ad-detail").isVisible()));
  await rows.nth(0).locator(".ad-head").click();
  check(name + ": clicking opens the summary in parts, labelled as written by AI", (await rows.nth(0).locator(".ad-detail").isVisible()) && (await rows.nth(0).locator(".ad-sum h5").count()) === 2 && (await rows.nth(0).locator(".ad-by").innerText()).includes("Summary written by AI") && (await rows.nth(0).locator(".ad-by").innerText()).includes("The file itself is not stored"));
  check(name + ": the open row says it is open", (await rows.nth(0).locator(".ad-head").getAttribute("aria-expanded")) === "true");
  await rows.nth(0).locator(".ad-head").press("Enter");
  check(name + ": Enter closes it again", !(await rows.nth(0).locator(".ad-detail").isVisible()));
  await rows.nth(1).locator(".ad-head").click();
  check(name + ": a file still being read shows a waiting note", (await rows.nth(1).locator(".ad-wait").innerText()).includes("Reading this file"));
  await rows.nth(3).locator(".ad-head").click();
  check(name + ": a failed file explains and offers Try again", (await rows.nth(3).locator(".ad-wait").innerText()).includes("not summarised") && (await rows.nth(3).locator("[data-att-retry]").count()) === 1);
  await rows.nth(2).locator(".ad-head").click();
  check(name + ": a skipped file explains and has no Try again", (await rows.nth(2).locator(".ad-wait").innerText()).includes("not read yet") && (await rows.nth(2).locator("[data-att-retry]").count()) === 0);
  check(name + ": no sideways scrolling", await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  const fit = await rows.nth(0).locator(".ad-head").evaluate((h) => { const r = h.getBoundingClientRect(); return [...h.children].every((c) => { const q = c.getBoundingClientRect(); return q.right <= r.right + 1 && q.left >= r.left - 1; }); });
  check(name + ": nothing in a row spills out of it", fit);
  await rows.nth(0).locator(".ad-head").click();
  if (shots) await mail.screenshot({ path: path.join(shots, `attachments-${name}.png`) });
  check(name + ": no script errors", errors.length === 0);
  await p.close();
}
await b.close(); srv.close();
process.exit(failed ? 1 : 0);
