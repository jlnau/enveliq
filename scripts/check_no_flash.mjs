// Browser check for the split-second flash on a quick refresh. Before the page is ready, nothing is drawn but the background: no menu, no boxes,
// no buttons, and in particular not the search box (far right of the title) or the "?" help button in their old places. It loads the page with its script switched off, which is exactly what a
// very quick refresh sees, and looks at what would be painted. A phone keeps its own layout.
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_no_flash.mjs [path/to/prototype/index.html]
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.resolve(process.argv[2] || path.join(here, "..", "prototype", "index.html")), "utf8");
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
const browser = await chromium.launch();
for (const [width, height, name] of [[1200, 900, "desktop"], [390, 800, "phone"]]) {
  const context = await browser.newContext({ viewport: { width, height }, javaScriptEnabled: false });
  const page = await context.newPage();
  await page.setContent(html, { waitUntil: "domcontentloaded" });
  const seen = await page.evaluate(() => {
    const painted = (el) => { if (!el) return false; const cs = getComputedStyle(el); const r = el.getBoundingClientRect(); return cs.display !== "none" && cs.visibility !== "hidden" && r.width > 0 && r.height > 0; };
    const kids = [".sidebar", ".preview-toolbar", ".preview-list-heading", ".nav", ".preview-help"].map((q) => [...document.querySelectorAll(q)].some(painted));
    return { oldSearch: painted(document.querySelector(".top-inner > .search-col")), help: painted(document.querySelector(".preview-help")), anything: kids.some(Boolean), app: getComputedStyle(document.querySelector(".app")).visibility, bg: getComputedStyle(document.documentElement).backgroundColor };
  });
  check(name + ": before the page is ready nothing is drawn (no menu, no boxes, no buttons), only the background", seen.app === "hidden" && !seen.anything);
  check(name + ": the background colour is already there (not white)", seen.bg !== "rgba(0, 0, 0, 0)" && seen.bg !== "rgb(255, 255, 255)");
  if (name === "desktop") {
    check("desktop: before the script runs, the search box is not drawn at the right of the title", !seen.oldSearch);
    check("desktop: before the script runs, the \"?\" help button is not drawn on its own", !seen.help);
  } else {
    const desktopOnly = await page.evaluate(() => {
      const hits = [];
      for (const sheet of document.styleSheets) for (const rule of sheet.cssRules) {
        const inner = rule.cssRules ? [...rule.cssRules].filter((r) => /top-inner\s*>\s*\.search-col/.test(r.selectorText || "") && r.style.display === "none") : [];
        if (inner.length) hits.push(rule.conditionText || rule.media?.mediaText || "");
      }
      return hits.length > 0 && hits.every((m) => /min-width:\s*761px/.test(m));
    });
    check("phone: the rule that hides the old search box only applies on a computer, so the phone layout is unchanged", desktopOnly);
  }
  await context.close();
}
await browser.close();
if (failed) process.exit(1);
console.log("All checks passed");
