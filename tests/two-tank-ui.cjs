/* End-to-end hardware metadata check against the isolated loopback demo. */
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs/promises');
const { chromium } = require('../.runtime/browser/node_modules/playwright');

(async () => {
  const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:8010';
  const root = path.resolve(__dirname, '..');
  const output = path.join(root, '.runtime/browser/two-tank');
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, reducedMotion: 'reduce' });
  const page = await context.newPage();
  const errors = [];
  const scans = [];
  page.on('pageerror', error => errors.push(error.message));
  let lastTimestamp = Date.now();
  const payload = {
    device_id: 'transfer-rig', flat_id: '101', level_percent: 80, volume_l: 2,
    flow_lpm: 0, flow_out_lpm: 0, ultrasonic_distance_cm: 34, sensor_status: 'ok',
    valve_percent: 0, hardware_profile: 'two_tank_transfer', level_sensor_model: 'AJ-SR04M',
    receiver_capacity_l: 1.5, float_switch_role: 'receiver_full', float_switch_state: 'permit',
    transfer_permitted: true, local_stop_reason: 'none', relay_energized: false,
    requested_valve_percent: 0,
  };
  async function send(updates) {
    lastTimestamp = Math.max(Date.now(), lastTimestamp + 1);
    const response = await context.request.post(base + '/telemetry', {
      data: { ...payload, ...updates, timestamp: new Date(lastTimestamp).toISOString() },
    });
    assert.equal(response.ok(), true, await response.text());
    return response.json();
  }
  async function view(name) {
    if (await page.locator('#menu-button').isVisible()) await page.locator('#menu-button').click();
    await page.locator(`[data-view="${name}"]`).click();
  }
  async function scan(label) {
    await page.addScriptTag({ path: path.join(root, '.runtime/browser/node_modules/axe-core/axe.min.js') });
    const violations = await page.evaluate(async () => (await axe.run(document, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] },
    })).violations.map(item => ({ id: item.id, impact: item.impact })));
    scans.push({ label, violations });
    assert.deepEqual(violations, [], label);
  }
  try {
    const demo = await (await context.request.get(base + '/api/demo')).json();
    assert.equal(demo.enabled, true, 'Use the isolated unauthenticated demo, never a hardware deployment');
    const stopped = await send({ level_percent: 0, volume_l: 0, sensor_status: 'fault',
      transfer_permitted: false, local_stop_reason: 'setup_required' });
    assert.equal(stopped.mode, 'TRANSFER_STOPPED');
    assert.equal(stopped.master_valve_percent, 0);
    await page.goto(base + '/frontend/');
    await page.locator('#device-select option[value="transfer-rig"]').waitFor({ state: 'attached' });
    await page.locator('#device-select').selectOption('transfer-rig');
    await page.waitForFunction(() => !document.querySelector('#transfer-overview').hidden);
    assert.equal(await page.locator('#level-value').textContent(), '—');
    assert.equal(await page.locator('#volume-value').textContent(), '—');
    assert.match(await page.locator('#receiver-tank-label').textContent(), /1.5 L/);
    await scan('uncommissioned overview desktop');

    const decision = await send({ transfer_permitted: false, local_stop_reason: 'float_stop',
      float_switch_state: 'stop_or_disconnected' });
    assert.equal(decision.master_valve_percent, 0);
    assert.equal(decision.flat_valve_percent, 0);
    await page.locator('#refresh-button').click();
    await page.waitForFunction(() => document.querySelector('#receiver-status').textContent.includes('disconnected'));
    assert.match(await page.locator('#transfer-relay').textContent(), /De-energized/);
    await view('health');
    assert.match(await page.locator('#float-state').textContent(), /full.*disconnected/i);
    assert.match(await page.locator('#receiver-level').textContent(), /full or.*disconnected/i);
    assert.match(await page.locator('#receiver-capacity').textContent(), /1.5 L.*not a live volume/);
    await scan('float stop health desktop');
    for (const width of [768, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `${width}px hardware status overflows`);
    }
    await scan('float stop health mobile');
    await page.screenshot({ path: path.join(output, 'float-health-mobile.png'), fullPage: true });
    await page.setViewportSize({ width: 1440, height: 1100 });
    await send({});
    await page.locator('#refresh-button').click();
    await page.waitForFunction(() => document.querySelector('#transfer-gate').textContent === 'Local checks permit transfer');
    assert.match(await page.locator('#relay-command').textContent(), /De-energized/);
    await view('overview');
    assert.equal(await page.locator('#level-value').textContent(), '80');
    assert.equal(await page.locator('#volume-value').textContent(), '2');
    assert.match(await page.locator('#master-label').textContent(), /Source command limit/);
    assert.match(await page.locator('#receiver-status').textContent(), /not full|below.*full|permits/i);
    const history = await (await context.request.get(base + '/devices/transfer-rig/history')).json();
    assert.equal(history.points[0].local_stop_reason, 'setup_required');
    assert.equal(history.points[1].float_switch_state, 'stop_or_disconnected');
    assert.equal(history.points[2].transfer_permitted, true);
    assert.deepEqual(errors, []);
    await fs.writeFile(path.join(output, 'results.json'), JSON.stringify({ scans, errors }, null, 2));
    console.log('PASS two-tank API, commissioning display, receiver float stop, recovery, history and accessibility');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
