// End-to-end browser check of first-run setup and every sign-in method.
// Needs a FRESH server (see scripts/run_signin_e2e.sh) plus Node.js and
// Playwright with Chromium. Passkeys use Chromium's virtual authenticator.
import { chromium } from "playwright";
import crypto from "node:crypto";
const BASE = process.env.ENVELIQ_E2E_URL || "http://localhost:8799";
const SETUP_CODE = process.env.ENVELIQ_E2E_SETUP_CODE || "e2e-setup-code-12345";
function totp(secret, offset = 0) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'; let bits = '';
  for (const ch of secret.replace(/\s|=/g, '').toUpperCase()) bits += alphabet.indexOf(ch).toString(2).padStart(5, '0');
  const key = Buffer.from(bits.match(/.{8}/g).map(b => parseInt(b, 2)));
  const step = Math.floor(Date.now() / 30000) + offset; const msg = Buffer.alloc(8); msg.writeBigUInt64BE(BigInt(step));
  const hm = crypto.createHmac('sha1', key).update(msg).digest(); const o = hm[hm.length - 1] & 15;
  return String((hm.readUInt32BE(o) & 0x7fffffff) % 1e6).padStart(6, '0');
}
await (async () => {
  const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 1180, height: 860 } });
  const p = await ctx.newPage(); const problems = [];
  p.on('pageerror', e => problems.push('pageerror: ' + e)); p.on('console', m => { if (m.type() === 'error') problems.push('console: ' + m.text()); });
  const cdp = await ctx.newCDPSession(p); await cdp.send('WebAuthn.enable');
  await cdp.send('WebAuthn.addVirtualAuthenticator', { options: { protocol: 'ctap2', transport: 'internal', hasResidentKey: true, hasUserVerification: true, isUserVerified: true } });
  const step = (s) => console.log('✓', s);

  await p.goto(BASE + '/'); await p.waitForURL('**/setup'); step('fresh server sends you to /setup');
  await p.screenshot({ path: `${process.env.ENVELIQ_E2E_SHOTS || '.'}/e2e-setup.png`, fullPage: true });
  await p.fill('#setup_code', SETUP_CODE); await p.fill('#display_name', 'Jules'); await p.fill('#username', 'jules');
  await p.fill('#password', 'Admin password 2026 e2e'); await p.fill('#password2', 'Admin password 2026 e2e');
  await p.fill('#passphrase', 'Vault passphrase 2026 e2e'); await p.fill('#passphrase2', 'Vault passphrase 2026 e2e');
  await p.click('button[type=submit]'); await p.waitForURL('**/account?enroll=1'); step('setup done, admin sent to two-factor setup');
  await p.screenshot({ path: `${process.env.ENVELIQ_E2E_SHOTS || '.'}/e2e-enroll.png`, fullPage: true });

  await p.click('text=Set up authenticator app'); await p.waitForSelector('.qr img');
  const secret = (await p.textContent('.qr .mono')).replace(/\s/g, '');
  await p.fill('#totp_code', totp(secret)); await p.click('form >> text=Confirm');
  await p.waitForSelector('.codes'); const codes = await p.$$eval('.codes span', els => els.map(e => e.textContent));
  step(`authenticator confirmed, ${codes.length} recovery codes shown`);
  await p.screenshot({ path: `${process.env.ENVELIQ_E2E_SHOTS || '.'}/e2e-recovery.png`, fullPage: true });
  await p.click('#continue'); await p.waitForURL(BASE + '/welcome'); await p.waitForSelector('text=Step 1: connect your email');
  step('a brand-new install opens the setup guide after first sign-in');
  await p.goto(BASE + '/'); await p.waitForSelector('.mail');
  step('inbox loads after enrolment: ' + await p.title());

  await p.goto(BASE + '/account'); await p.fill('#pk_name', 'Virtual laptop key'); await p.click('text=Add a passkey');
  await p.waitForSelector('text=Virtual laptop key'); step('passkey registered through the browser');
  await p.screenshot({ path: `${process.env.ENVELIQ_E2E_SHOTS || '.'}/e2e-account.png`, fullPage: true });

  await p.click('nav >> text=Sign out'); await p.waitForURL('**/login');
  await p.screenshot({ path: `${process.env.ENVELIQ_E2E_SHOTS || '.'}/e2e-login.png`, fullPage: true });
  const shots = process.env.ENVELIQ_E2E_SHOTS || '.';
  const theme = () => p.evaluate(() => document.documentElement.getAttribute('data-theme') || 'dark');
  if ((await theme()) !== 'dark' || (await p.locator('#legal a').allInnerTexts()).join('|') !== 'Terms|Privacy|Security') throw new Error('footer or default theme');
  await p.click('.theme-toggle'); if ((await theme()) !== 'light') throw new Error('toggle did not switch to light');
  await p.reload(); await p.waitForSelector('#username'); if ((await theme()) !== 'light') throw new Error('light mode not remembered on the sign-in page');
  await p.screenshot({ path: `${shots}/e2e-login-light.png`, fullPage: true });
  const size = p.viewportSize(); await p.setViewportSize({ width: 390, height: 780 });
  await p.screenshot({ path: `${shots}/e2e-login-light-phone.png`, fullPage: true });
  if (await p.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error('sign-in page scrolls sideways on a phone');
  await p.click('.theme-toggle'); await p.screenshot({ path: `${shots}/e2e-login-dark-phone.png`, fullPage: true });
  for (const path of ['/terms', '/privacy', '/security']) {
    await p.goto(BASE + path); await p.waitForSelector('.notes h1');
    await p.screenshot({ path: `${shots}/e2e${path.replace('/', '-')}-phone.png`, fullPage: true });
    if (await p.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error(path + ' scrolls sideways on a phone');
  }
  await p.setViewportSize(size); await p.goto(BASE + '/login'); await p.waitForSelector('#username');
  await p.click('.theme-toggle'); await p.goto(BASE + '/terms'); await p.waitForSelector('.notes h1'); if ((await theme()) !== 'light') throw new Error('theme not kept across pages');
  await p.screenshot({ path: `${shots}/e2e-terms-light.png`, fullPage: true });
  await p.click('.theme-toggle'); await p.goto(BASE + '/login'); await p.waitForSelector('#username');
  step('light/dark switch, footer, terms and privacy pages work on desktop and phone');
  const dlg = p.locator('.trust-dialog');
  if ((await p.locator('.trust-badge').count()) !== 3 || await dlg.isVisible()) throw new Error('badges missing or pop-up open at start');
  await p.click('.trust-link'); await dlg.waitFor(); if ((await dlg.locator('.trust-row').count()) !== 5) throw new Error('trust pop-up rows');
  await p.screenshot({ path: `${process.env.ENVELIQ_E2E_SHOTS || '.'}/e2e-login-trust.png`, fullPage: true });
  await p.keyboard.press('Escape'); if (await dlg.isVisible()) throw new Error('pop-up did not close with Escape');
  await p.click('.trust-link'); await p.click('.trust-close'); if (await dlg.isVisible()) throw new Error('pop-up did not close with the button');
  step('sign-in badges and pop-up work');
  await p.click('.trust-link'); await p.click('text=Read the full security notes'); await p.waitForURL('**/security'); await p.waitForSelector('text=How Enveliq protects your data');
  await p.click('.back'); await p.waitForURL('**/login'); step('security notes page opens and returns');
  await p.click('text=Sign in with a passkey'); await p.waitForURL(BASE + '/'); step('passwordless passkey sign-in works');

  await p.goto(BASE + '/account'); await p.click('nav >> text=Sign out'); await p.waitForURL('**/login');
  await p.fill('#username', 'jules'); await p.fill('#password', 'Admin password 2026 e2e'); await p.click('button[type=submit]');
  await p.waitForSelector('#code'); await p.screenshot({ path: `${process.env.ENVELIQ_E2E_SHOTS || '.'}/e2e-mfa.png`, fullPage: true });
  await p.fill('#code', '123456'); await p.click('text=Verify'); await p.waitForSelector('.form-error'); step('wrong code refused: ' + await p.textContent('.form-error'));
  await p.fill('#code', totp(secret, 1)); await p.click('text=Verify'); await p.waitForURL(BASE + '/'); step('password + authenticator code sign-in works');

  await p.goto(BASE + '/admin'); await p.waitForSelector('text=Add a person');
  await p.fill('#nu_username', 'beth'); await p.fill('#nu_name', 'Beth'); await p.fill('#nu_password', 'Temporary pw 2026 e2e');
  await p.click('text=Add user'); await p.waitForSelector('td >> text=beth'); step('admin added user beth');
  await p.click('summary:has-text("Set up single sign-on")');
  await p.fill('#sso_issuer', 'https://auth.example.com/application/o/enveliq/'); await p.fill('#sso_client_id', 'enveliq');
  await p.screenshot({ path: `${process.env.ENVELIQ_E2E_SHOTS || '.'}/e2e-admin.png`, fullPage: true });

  const csp = problems.filter(x => /Content Security Policy|Refused/i.test(x));
  console.log('page errors / console errors:', JSON.stringify(problems)); console.log('CSP violations:', csp.length);
  if (csp.length || problems.some(x => x.startsWith('pageerror'))) process.exitCode = 1;
  await b.close();
})().catch(e => { console.error('E2E FAILED:', e.message); process.exit(1); });
