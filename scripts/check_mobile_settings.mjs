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
    const s = document.getElementById("settings").getBoundingClientRect(), n = document.getElementById("settingsNav"), nr = n.getBoundingClientRect(),
      m = document.querySelector(".settings-scroll").getBoundingClientRect(), tabs = [...n.querySelectorAll("[data-settings-tab]")];
    return { sw: s.width, left: s.left, nh: nr.height, nw: nr.width, mw: m.width, mtop: m.top, nbot: nr.bottom, tabs: tabs.length, scrolls: n.scrollWidth > n.clientWidth,
      page: document.documentElement.scrollWidth <= innerWidth, tabTop: tabs[0]?.getBoundingClientRect().top, tabTop2: tabs[1]?.getBoundingClientRect().top };
  });
  ok(mode + ": sheet fills the phone width", g.sw >= 388 && g.left <= 1);
  ok(mode + ": sections are a strip above the content, not beside it", g.nh < 80 && g.nw >= 388 && g.mw >= 388 && g.mtop >= g.nbot - 1);
  ok(mode + ": " + g.tabs + " sections in one swipeable row", g.tabs >= 3 && g.scrolls && Math.abs(g.tabTop - g.tabTop2) < 2);
  ok(mode + ": no sideways page scroll", g.page);
  const last = await p.evaluate(() => { const t = [...document.querySelectorAll("#settingsNav [data-settings-tab]")]; const l = t[t.length - 1]; l.click(); return l.dataset.settingsTab; });
  await p.waitForTimeout(500);
  const vis = await p.evaluate(() => { const a = document.querySelector("#settingsNav .active").getBoundingClientRect(); return a.left >= 0 && a.right <= innerWidth + 1; });
  ok(mode + ": last section opens and its tab scrolls into view (" + last + ")", vis);
  await p.evaluate(() => document.getElementById("closeSettings").click());
}
await b.close(); srv.close(); process.exit(fails ? 1 : 0);
