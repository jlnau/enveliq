import { chromium } from "playwright";
import http from "node:http"; import fs from "node:fs";
const html = fs.readFileSync(new URL("../prototype/index.html", import.meta.url), "utf8");
const srv = http.createServer((q, r) => { r.setHeader("content-type", "text/html"); r.end(html); }).listen(0);
const url = `http://127.0.0.1:${srv.address().port}/`;
const b = await chromium.launch(); let fails = 0;
const ok = (n, c) => { console.log((c ? "✓ " : "✗ ") + n); if (!c) fails++; };
for (const [name, vp] of [["desktop", { width: 1200, height: 700 }], ["phone", { width: 390, height: 780 }]]) {
  const p = await b.newPage({ viewport: vp }); await p.goto(url); await p.waitForTimeout(500);
  await p.addStyleTag({ content: "body{min-height:3000px}" });
  const ov = () => p.evaluate(() => getComputedStyle(document.documentElement).overflowY + "/" + getComputedStyle(document.body).overflowY);
  ok(name + ": page scrolls normally when nothing is open", !(await ov()).includes("hidden"));
  await p.evaluate(() => document.getElementById("settings").classList.add("open"));
  ok(name + ": page is locked while Settings is open", (await ov()).includes("hidden"));
  await p.evaluate(() => document.getElementById("settings").classList.remove("open"));
  ok(name + ": page scrolls again after it closes", !(await ov()).includes("hidden"));
  if (name === "phone") {
    await p.evaluate(() => document.body.classList.add("menu-open"));
    ok("phone: page is locked while the menu is open", (await ov()).includes("hidden"));
  }
  await p.close();
}
await b.close(); srv.close(); process.exit(fails ? 1 : 0);
