// Round-gate evidence collector: full-page screenshot + body text of the running app.
// Usage: node snap.cjs <out_prefix>
//   CHROMIUM_EXECUTABLE  explicit headless-shell path (optional; Playwright's own
//                        browser is used when unset)
//   TARGET_URL           page to capture (default http://localhost:3000)
const { chromium } = require('playwright');
(async () => {
  const out = process.argv[2] || '/tmp/round';
  const target = process.env.TARGET_URL || 'http://localhost:3000';
  const exe = process.env.CHROMIUM_EXECUTABLE || undefined;
  const b = await chromium.launch(exe ? { executablePath: exe } : {});
  const ctx = await b.newContext({ viewport: { width: 1280, height: 1000 } });
  const p = await ctx.newPage();
  const errs = [];
  p.on('console', m => { if (m.type() === 'error') errs.push(m.text().slice(0, 120)); });
  p.on('pageerror', e => errs.push(String(e).slice(0, 120)));
  try {
    await p.goto(target, { waitUntil: 'networkidle', timeout: 20000 });
  } catch (e) {
    await p.goto(target, { waitUntil: 'domcontentloaded', timeout: 15000 }).catch(() => {});
  }
  await p.waitForTimeout(1200);
  await p.screenshot({ path: out + '.png', fullPage: true }).catch(async () => { await p.screenshot({ path: out + '.png' }); });
  const text = await p.locator('body').innerText().catch(() => '');
  require('fs').writeFileSync(out + '.txt', JSON.stringify({
    text: text.replace(/\s+/g, ' ').trim().slice(0, 6000),
    console_errors: errs.slice(0, 10)
  }));
  await b.close();
})().catch(e => { console.error('SNAP_FAIL', String(e).slice(0, 200)); process.exit(1); });
