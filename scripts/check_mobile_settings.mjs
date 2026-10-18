// Browser check for Settings on a phone: it opens as a plain full-screen list, each page opens full screen with a Back button,
// the search finds pages, and nothing scrolls sideways. The server is not needed (the page runs in its prototype mode).
import { chromium } from "playwright";
import http from "node:http"; import fs from "node:fs";
const html = fs.readFileSync(new URL("../prototype/index.html", import.meta.url), "utf8");
const srv = http.createServer((q, r) => { r.setHeader("content-type", "text/html"); r.end(html); }).listen(0);
const url = `http://127.0.0.1:${srv.address().port}/`;
const b = await chromium.launch(); let fails = 0;
const ok = (n, c) => { console.log((c ? "✓ " : "✗ ") + n); if (!c) fails++; };
const p = await b.newPage({ viewport: { width: 390, height: 780 } });
await p.goto(url); await p.waitForTimeout(600);
for (const mode of ["settings", "admin"]) {
  await p.evaluate(m => { openSettings(m); }, mode); await p.waitForTimeout(300);
  const g = await p.evaluate(() => {
    const s = document.getElementById("settings"), sr = s.getBoundingClientRect(), n = document.getElementById("settingsNav").getBoundingClientRect(),
      m = document.querySelector(".settings-main"), tabs = [...document.querySelectorAll("#settingsNav [data-settings-tab]")];
    return { sw: sr.width, sh: sr.height, left: sr.left, menu: s.classList.contains("menu-view"), nw: n.width, mainHidden: getComputedStyle(m).display === "none", tabs: tabs.length,
      tall: tabs.every((t) => t.getBoundingClientRect().height >= 44), page: document.documentElement.scrollWidth <= innerWidth };
  });
  ok(mode + ": Settings fills the phone", g.sw >= 388 && g.sh >= 770 && g.left <= 1);
  ok(mode + ": it opens as a list, with the page itself hidden", g.menu && g.mainHidden && g.nw >= 388);
  ok(mode + ": " + g.tabs + " big, easy-to-press rows", g.tabs >= 3 && g.tall);
  ok(mode + ": no sideways page scroll", g.page);
  await p.fill("#settingsSearchM", "undo");
  await p.waitForSelector("#settingsResults .sres");
  ok(mode + ": searching shows matching pages", (await p.locator("#settingsResults .sres").count()) >= 1);
  await p.press("#settingsSearchM", "Escape");
  const last = await p.evaluate(() => { const t = [...document.querySelectorAll("#settingsNav [data-settings-tab]")]; const l = t[t.length - 1]; l.click(); return l.dataset.settingsTab; });
  await p.waitForTimeout(500);
  const st = await p.evaluate(() => ({ menu: document.getElementById("settings").classList.contains("menu-view"), back: document.getElementById("settingsBack").getBoundingClientRect(), fit: document.documentElement.scrollWidth <= innerWidth }));
  ok(mode + ": a page opens full screen with a Back button at the top (" + last + ")", !st.menu && st.back.height >= 40 && st.back.top >= 0 && st.fit);
  await p.click("#settingsBack"); await p.waitForTimeout(200);
  ok(mode + ": Back returns to the list", await p.evaluate(() => document.getElementById("settings").classList.contains("menu-view")));
  await p.evaluate(() => document.getElementById("settingsBackInbox").click());
  ok(mode + ": Back to inbox closes Settings", await p.evaluate(() => !document.getElementById("settings").classList.contains("open")));
}
await b.close(); srv.close(); process.exit(fails ? 1 : 0);
