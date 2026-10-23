/* Run with a local demo server; see docs/verification.md. */
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs/promises');
const { chromium } = require('../.runtime/browser/node_modules/playwright');

(async () => {
  const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:8010';
  const root = path.resolve(__dirname, '..');
  const screenshots = process.env.SCREENSHOT_DIR || path.join(root, 'docs/screenshots');
  await fs.mkdir(screenshots, { recursive: true });
  await fs.mkdir(path.join(root, '.runtime/browser'), { recursive: true });
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, reducedMotion: 'reduce' });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const checks = [];
  const check = label => { checks.push(label); console.log(`PASS ${label}`); };
  async function mode(expected) {
    await page.waitForFunction(async expectedMode => {
      const response = await fetch('/devices/tank-01/latest');
      return response.ok && (await response.json()).decision.mode === expectedMode;
    }, expected, { timeout: 15000, polling: 400 });
  }
  async function scenario(name, expected) {
    await page.locator('#admin-view').click();
    await page.locator(`input[name="scenario"][value="${name}"]`).check();
    await mode(expected);
    check(`${name} scenario produces ${expected}`);
  }
  try {
    const status = await (await context.request.get(base + '/api/demo')).json();
    assert.equal(status.enabled, true, 'Browser smoke requires a local demo server');
    const started = await context.request.post(base + '/api/demo', { data: { action: 'start', scenario: 'normal' } });
    assert.equal(started.ok(), true, 'Use the unauthenticated loopback demo launcher');
    await page.goto(base + '/frontend/');
    await page.waitForFunction(() => document.querySelector('#level-value').textContent === '82');
    assert.match(await page.title(), /WaterWise/);
    assert.equal(await page.locator('#api-error').isVisible(), false);
    check('live demo renders real tank readings');
    await page.locator('#flow-chart svg').waitFor();
    const downloadReady = page.waitForEvent('download');
    await page.locator('#export-button').click();
    const download = await downloadReady;
    const csvPath = path.join(root, '.runtime/browser/history.csv');
    await download.saveAs(csvPath);
    assert.match(await fs.readFile(csvPath, 'utf8'), /timestamp/i);
    check('history chart and CSV export');

    const overview = await (await context.request.get(base + '/api/overview')).json();
    const smallSource = overview.tank_capacity_l < 100;
    await scenario('leak', smallSource ? 'RATIONING' : 'LEAK_ALERT');
    await page.waitForFunction(async () => {
      const response = await fetch('/devices/tank-01/latest');
      return response.ok && (await response.json()).decision.flat_status === 'LEAK_ALERT';
    });
    await page.waitForFunction(() => document.querySelector('#flat-value').textContent.trim() === '25%');
    assert.equal((await page.locator('#master-value').textContent()).trim(), smallSource ? '82%' : '100%');
    assert.equal(await page.locator('#alert-banner').isVisible(), true);
    check('confirmed leak restricts branch while preserving any stricter source limit');
    await scenario('critical', 'CRITICAL');
    await page.waitForFunction(() => document.querySelector('#master-value').textContent.trim() === '0%');
    assert.equal((await page.locator('#flat-value').textContent()).trim(), '0%');
    check('reserve closes both commands in UI');
    await scenario('sensor_fault', 'SENSOR_FAULT');
    await page.waitForFunction(() => document.querySelector('#master-value').textContent.trim() === '30%');
    await scenario('warning', 'WARNING');
    await scenario('rationing', 'RATIONING');
    await scenario('recovery', 'NORMAL');
    await page.waitForFunction(() => document.querySelector('#flat-value').textContent.trim() === '100%');
    check('flow recovery restores normal commands');
    await page.locator('#simulator-toggle').click();
    await page.waitForFunction(() => document.querySelector('#simulator-toggle').textContent.includes('Start simulation'));
    await page.waitForFunction(() => document.querySelector('#connection-label').textContent.includes('stale'), null, { timeout: 15000 });
    check('stopped telemetry becomes visibly stale');
    await page.locator('#simulator-reset').click();
    await page.waitForFunction(() => document.querySelector('#level-value').textContent === '—');
    check('reset clears local readings and shows honest empty state');
    await page.locator('#simulator-toggle').click();
    await page.waitForFunction(() => document.querySelector('#level-value').textContent === '82');
    await page.locator('#resident-view').click();
    await page.route('**/api/overview', route => route.abort('failed'));
    await page.locator('#refresh-button').click();
    await page.locator('#api-error').waitFor({ state: 'visible' });
    check('network failure displays offline error');
    await page.unroute('**/api/overview');
    await page.locator('#retry-button').click();
    await page.locator('#api-error').waitFor({ state: 'hidden' });
    check('retry restores live readings');
    await page.waitForSelector('#flow-chart svg');
    await page.waitForFunction(() => document.querySelector('#toast').hidden);
    await page.screenshot({ path: path.join(screenshots, 'desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    await page.locator('#menu-button').click();
    await page.locator('[data-view="health"]').click();
    assert.equal(await page.locator('#view-health').isVisible(), true);
    assert.equal(await page.locator('#menu-button').getAttribute('aria-expanded'), 'false');
    await page.locator('#menu-button').click();
    await page.locator('[data-view="overview"]').click();
    await page.screenshot({ path: path.join(screenshots, 'mobile.png'), fullPage: true });
    check('mobile has no horizontal overflow and navigation works');
    assert.deepEqual(errors, []);
    check('no uncaught JavaScript errors');
    await fs.writeFile(path.join(root, '.runtime/browser/results.json'), JSON.stringify({ checks, pageErrors: errors }, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
