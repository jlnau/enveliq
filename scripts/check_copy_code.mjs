// Sign-in codes: the table of emails that should and should not get a Copy code button. The Android app's CodeFinder uses the same rule and the same table (see docs/ANDROID.md).
import fs from "node:fs";
import vm from "node:vm";
const html = fs.readFileSync(new URL("../prototype/index.html", import.meta.url), "utf8");
const start = html.indexOf("function findCode(subject,summary){");
const end = html.indexOf("const codeBtn=", start);
if (start < 0 || end < 0) { console.log("✗ could not find findCode in index.html"); process.exit(1); }
const ctx = {};
vm.createContext(ctx);
vm.runInContext(html.slice(start, end) + "\nthis.findCode = findCode;", ctx);
let bad = 0;
const check = (name, ok) => { console.log((ok ? "✓ " : "✗ ") + name); if (!ok) bad++; };
const cases = [
  ["AustralianSuper: Your verification code", "This email is a verification code from AustralianSuper, requesting you to enter the code 762252 to continue. The code is valid for 10 minutes. If you have any questions, contact AustralianSuper on 1300 300 273.", "762252"],
  ["Your sign-in code", "Use code 4821 to sign in.", "4821"],
  ["Security code", "Your security code is 123 456. Do not share it.", "123456"],
  ["Login code", "Your one-time passcode is 98765432.", "98765432"],
  ["Your login code is 554433", "", "554433"],
  ["Order 20261107 shipped", "Your order 8215771001761662 was collected by the carrier.", ""],
  ["Meeting at 2026", "Please call 1300 300 273 about your account.", ""],
  ["Invoice 4412", "Your invoice number is 4412 and is due next week.", ""],
  ["Sign in from a new device", "A new device signed in to your account on 7 November 2026.", ""],
  ["Parcel update", "Use code SAVE20 for 20% off.", ""],
];
for (const [s, m, want] of cases) check(`"${s}" -> ${want || "no button"}`, ctx.findCode(s, m) === want);
check("the button is on the AI summary and copies the code", html.includes("${codeBtn(m)}</div>${taskHtml}") && html.includes("data-copy-code") && html.includes('"Copied the code."'));
process.exit(bad ? 1 : 0);
