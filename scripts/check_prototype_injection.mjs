// Browser check: hostile email and account values must render as text, never run.
//
// Fills every field an attacker could control (email sender, subject, summary,
// original body and reply headers, task, attachment name and preview pages, account details, user names) with
// an <img onerror=...> payload, opens every view of the prototype, and fails
// if any payload executes.
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_prototype_injection.mjs [path/to/prototype/index.html]
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const target = path.resolve(process.argv[2] || path.join(here, "..", "prototype", "index.html"));

const browser = await chromium.launch();
const page = await browser.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
await page.goto("file://" + target);

const result = await page.evaluate(async () => {
  const evil = (k) => `X<img src=x onerror="window.__pwn=(window.__pwn||[]).concat('${k}')">"'&`;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const m = data[0];
  for (const k of ["sender", "address", "subject", "summary", "category", "account", "time"]) m[k] = evil(k);
  m.task = { title: evil("task.title"), due: evil("task.due"), detail: evil("task.detail") };
  const a = m.attachments[0];
  for (const k of ["name", "summary", "detail", "mime", "size", "previewTitle"]) a[k] = evil("att." + k);
  a.previewPages = [{ title: evil("page.title"), subtitle: evil("page.subtitle"), lines: [evil("page.line")], body: evil("page.body") }];
  expanded.add("task-" + m.id);
  expanded.add("att-" + m.id + "-0");
  render(); await sleep(100);
  openAttachmentViewer(m.id + ":0"); await sleep(100);
  closeAttachmentViewer();
  // Original email viewer and reply composer
  for (const k of ["replyTo", "deliveredTo", "date"]) m[k] = evil(k);
  m.viaAlias = evil("viaAlias");
  m.body = [evil("body.1"), evil("body.2")];
  openEmailViewer(m.id); await sleep(100);
  closeAttachmentViewer();
  openComposer(m.id); await sleep(100);
  closeComposer();
  const ac = accounts[0];
  for (const k of ["name", "address", "provider", "method", "status", "lastSync", "lastSuccess", "connectedAt", "server", "port", "security", "username"]) ac[k] = evil("acct." + k);
  ac.settings.filters.ignoredSenders = evil("filters");
  ac.settings.notifications.quietStart = evil("quiet");
  ac.settings.folders.inbox = evil("folder");
  openSettings(); await sleep(50);
  for (const pane of ["overview", "sync", "processing", "actions", "notifications", "privacy", "security"]) {
    renderManageAccount(ac.id, pane); await sleep(40);
  }
  renderAccounts(); await sleep(50);
  users.beth.name = evil("user.name");
  currentUser.name = evil("currentUser");
  renderEmailProviderPicker(); emailConnectionForm("proton"); openOAuth("gmail"); await sleep(80);
  return window.__pwn || [];
});
await browser.close();

if (errors.length) {
  console.error("FAIL: page errors:", errors);
  process.exit(1);
}
if (result.length) {
  console.error("FAIL: injected code ran via:", result.join(", "));
  process.exit(1);
}
console.log("PASS: no injected code ran in any view");
