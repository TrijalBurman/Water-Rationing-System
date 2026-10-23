const $ = (id) => document.getElementById(id);
const number = (value, digits = 1) => Number.isFinite(value)
  ? new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(value)
  : '—';
const percent = (value) => Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : 0;
const humanize = (value) => value ? String(value).replaceAll('_', ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase()) : 'Awaiting data';
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const setText = (id, value) => {
  const element = $(id);
  if (element.textContent !== String(value)) element.textContent = value;
};
const setWidth = (id, value) => { $(id).style.width = `${percent(value)}%`; };
const setBadge = (id, text, tone = '') => { setText(id, text); $(id).className = `badge ${tone}`; };
const palette = {
  supply: 'var(--chart-supply, #72aaff)',
  delivered: 'var(--chart-delivered, #58dec9)',
  good: 'var(--success, #58dec9)',
  warning: 'var(--warning, #edbd76)',
  danger: 'var(--danger, #ff8e9b)',
  muted: 'var(--muted, #98a9bd)',
};
const timeFormatter = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' });
const fullTimeFormatter = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
const modeTone = (mode) => ['CRITICAL', 'LEAK_ALERT', 'SENSOR_FAULT', 'TRANSFER_STOPPED'].includes(mode) ? 'danger' : ['WARNING', 'RATIONING', 'SUSPECTED_LEAK'].includes(mode) ? 'warning' : mode === 'NORMAL' ? 'good' : '';
const isTwoTank = (telemetry) => telemetry?.hardware_profile === 'two_tank_transfer';
const localStopLabel = (reason) => ({
  none: 'No local stop', setup_required: 'Commissioning required · source geometry uncalibrated',
  float_stop: 'Float stop or disconnected circuit', float_recovering: 'Waiting for a stable float circuit',
  clock_unsynced: 'Device clock is not synchronized',
}[reason] || 'Not configured');
const floatStateLabel = (telemetry) => ({
  permit: 'Permit circuit closed', recovering: 'Recovering · transfer stopped',
  stop_or_disconnected: telemetry?.float_switch_role === 'receiver_full'
    ? 'Receiver full OR circuit disconnected' : 'Source low OR circuit disconnected',
}[telemetry?.float_switch_state] || 'Not configured');
const receiverLabel = (telemetry) => !isTwoTank(telemetry) || telemetry.float_switch_role !== 'receiver_full'
  ? 'Not configured' : ({
    permit: 'Below full cutoff · float only', recovering: 'Float recovering · level unknown',
    stop_or_disconnected: 'Full OR float circuit disconnected',
  }[telemetry.float_switch_state] || 'Not configured');
const state = {
  overview: null, snapshot: null, deviceId: '', history: [], historySource: null,
  historyRange: 60, demo: null, view: 'overview', admin: false, online: false,
  polling: false, historyLoading: false, demoBusy: false, lastHistoryFetch: 0,
  lastDemoFetch: 0, lastOverviewSuccess: 0, apiKey: '', toastTimer: null,
  historyError: '', historyRequest: 0, pendingScenario: null, demoRevision: 0,
};

try { state.apiKey = sessionStorage.getItem('waterwise.apiKey') || ''; } catch { /* Session storage may be disabled by the browser. */ }
$('api-key').value = state.apiKey;

class ApiError extends Error {
  constructor(message, status) { super(message); this.name = 'ApiError'; this.status = status; }
}

async function request(path, options = {}) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 7000);
  const headers = { Accept: 'application/json', ...(options.headers || {}) };
  if (options.body) headers['Content-Type'] = 'application/json';
  if (state.apiKey) headers['X-API-Key'] = state.apiKey;
  try {
    const response = await fetch(path, { ...options, headers, signal: controller.signal, cache: 'no-store' });
    let payload;
    try { payload = await response.json(); } catch { payload = null; }
    if (!response.ok) {
      let detail = typeof payload?.detail === 'string' ? payload.detail : '';
      if (response.status === 401 || response.status === 403) detail = 'Access was denied. Enter a valid server API key in Operations and try again.';
      else if (response.status === 429) detail = 'The server is receiving too many requests. Please try again shortly.';
      throw new ApiError(detail || `The server returned an error (${response.status}).`, response.status);
    }
    if (payload === null) throw new ApiError('The server returned an unreadable response. Check that the API is running.', response.status);
    return payload;
  } catch (error) {
    if (error.name === 'AbortError') throw new ApiError('The server did not respond in time. Readings will refresh when it reconnects.', 0);
    if (error instanceof ApiError) throw error;
    throw new ApiError('Check that the water monitoring server is running. The portal will reconnect automatically.', 0);
  } finally { clearTimeout(timeout); }
}

function toast(message, error = false) {
  const element = $('toast');
  element.textContent = message;
  element.classList.toggle('error', error);
  element.hidden = false;
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => { element.hidden = true; }, 4500);
}

function setApiError(error) {
  $('api-error').hidden = !error;
  if (!error) return;
  setText('api-error-title', [401, 403].includes(error.status) ? 'An API key is required' : 'Unable to reach the water network');
  setText('api-error-detail', error.message);
}

function freshnessLabel() {
  if (!state.snapshot?.received_at) return 'Waiting for first reading';
  const received = new Date(state.snapshot.received_at).getTime();
  if (!Number.isFinite(received)) return 'Reading time unavailable';
  const elapsed = Math.max(0, Math.floor((Date.now() - received) / 1000));
  if (elapsed < 3) return 'Updated just now';
  if (elapsed < 60) return `Updated ${elapsed}s ago`;
  if (elapsed < 3600) return `Updated ${Math.floor(elapsed / 60)}m ago`;
  return `Updated ${new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(received))}`;
}

function isStale() {
  if (!state.snapshot?.telemetry) return false;
  const received = new Date(state.snapshot.received_at).getTime();
  return Boolean(state.snapshot.stale) || !Number.isFinite(received) || Date.now() - received > 15000;
}

function renderConnection() {
  const element = $('connection-pill');
  let label = 'Awaiting data';
  let tone = '';
  if (!state.online && state.lastOverviewSuccess) { label = 'Offline'; tone = 'offline'; }
  else if (!state.online && !$('api-error').hidden) { label = 'Offline'; tone = 'offline'; }
  else if (isStale()) { label = 'Reading is stale'; tone = 'stale'; }
  else if (state.snapshot?.telemetry) { label = isDemoDevice() ? state.demo?.running === false ? 'Demo stopped' : 'Demo running' : 'Live updates'; tone = isDemoDevice() && state.demo?.running === false ? '' : 'live'; }
  else if (!state.online) label = 'Connecting';
  element.className = `connection-pill ${tone}`;
  setText('connection-label', label);
  setText('last-updated', freshnessLabel());
  setText('health-freshness', freshnessLabel().replace('Updated ', ''));
  $('demo-indicator').hidden = !isDemoDevice();
  $('nav-health').style.background = tone === 'live' ? palette.good : tone === 'stale' ? palette.warning : tone === 'offline' ? palette.danger : palette.muted;
}

function isDemoDevice() {
  if (state.snapshot?.source) return state.snapshot.source === 'demo';
  return Boolean(state.overview?.demo_mode && state.demo?.device_id === state.deviceId && state.snapshot?.telemetry);
}

function renderDevices() {
  const devices = Array.isArray(state.overview?.devices) ? state.overview.devices : [];
  const ids = devices.map((item) => item.telemetry?.device_id).filter(Boolean);
  const fallback = state.overview?.default_device_id || 'tank-01';
  if (!state.deviceId) state.deviceId = ids.includes(fallback) || !ids.length ? fallback : ids[0];
  if (!ids.includes(state.deviceId)) ids.push(state.deviceId);
  const select = $('device-select');
  const currentOptions = Array.from(select.options).map((option) => option.value);
  if (currentOptions.join('\n') !== ids.join('\n')) {
    select.replaceChildren(...ids.map((id) => {
      const option = document.createElement('option');
      option.value = id;
      option.textContent = `${id.replace(/^tank-/i, 'Tank ')} · Community supply`;
      return option;
    }));
  }
  select.value = state.deviceId;
  state.snapshot = devices.find((item) => item.telemetry?.device_id === state.deviceId) || null;
  setText('footer-device', `${state.deviceId} · ${isDemoDevice() ? 'Simulation environment' : 'Water monitoring network'}`);
}

function renderSnapshot() {
  const telemetry = state.snapshot?.telemetry;
  const decision = state.snapshot?.decision;
  const quota = state.snapshot?.quota;
  const tankMode = decision?.tank_mode;
  const branchStatus = decision?.flat_status;
  const twoTank = isTwoTank(telemetry);
  const setupRequired = twoTank && telemetry.local_stop_reason === 'setup_required';
  const level = setupRequired ? null : telemetry?.level_percent;
  setText('tank-heading', twoTank ? 'SOURCE TANK' : 'COMMUNITY TANK');
  setText('level-value', number(level));
  setText('volume-value', number(setupRequired ? null : telemetry?.volume_l));
  $('tank-fill').style.height = `${percent(level)}%`;
  $('tank-visual').setAttribute('aria-label', setupRequired ? 'Source tank geometry is uncalibrated' : Number.isFinite(level) ? `${twoTank ? 'Source tank' : 'Tank'} ${number(level)} percent full, with a protected reserve below 10 percent` : 'Tank water level unavailable');
  const tankModeLabel = { NORMAL: 'Healthy supply', WARNING: 'Supply watch', RATIONING: 'Rationing active', CRITICAL: 'Reserve protected', SENSOR_FAULT: 'Sensor fault' }[tankMode] || 'Awaiting data';
  setText('tank-mode', tankModeLabel);
  $('tank-mode').className = `tank-mode ${modeTone(tankMode) === 'good' ? 'normal' : modeTone(tankMode)}`;
  const captions = { NORMAL: 'A steady supply for your community.', WARNING: 'Supply is declining. Please use water thoughtfully.', RATIONING: 'Sharing the remaining supply fairly.', CRITICAL: 'Community valves are closed to protect the reserve.', SENSOR_FAULT: 'Limited supply while the sensor needs attention.' };
  setText('tank-caption', setupRequired ? 'Commissioning required. Calibrate the source tank geometry before enabling transfer.' : twoTank && tankMode === 'CRITICAL' ? 'Transfer is stopped to protect the source reserve.' : twoTank && tankMode === 'SENSOR_FAULT' ? 'Source level sensor needs attention. Check its probe and wiring.' : captions[tankMode] || 'Your community supply, monitored in real time.');
  const eta = decision?.eta_minutes;
  if (setupRequired) setText('eta-value', 'Uncalibrated');
  else if (Number.isFinite(eta)) $('eta-value').innerHTML = `${escapeHtml(number(Math.max(0, eta), 0))} <small>min</small>`;
  else setText('eta-value', telemetry ? 'No depletion estimate' : '—');
  setText('reserve-status', setupRequired ? 'Calibration required' : tankMode === 'CRITICAL' ? 'Valve locked closed' : telemetry ? '10% reserve threshold' : 'Awaiting readings');

  const used = quota?.consumed_l;
  const allowance = quota?.allowance_l;
  const remaining = quota?.remaining_l;
  $('quota-used').innerHTML = `${escapeHtml(number(used))}<small>L</small>`;
  setText('used-detail', `${number(used)} L`);
  setText('quota-remaining', `${number(remaining)} L`);
  setText('quota-total', `${number(allowance ?? state.overview?.daily_quota_l)} L`);
  const usagePercent = Number.isFinite(used) && allowance > 0 ? percent(used / allowance * 100) : 0;
  $('ring-progress').style.strokeDashoffset = String(408.4 * (1 - usagePercent / 100));
  $('ring-progress').style.stroke = usagePercent >= 100 ? palette.danger : usagePercent >= 85 ? palette.warning : palette.good;
  $('quota-ring').setAttribute('aria-label', quota ? `${number(used)} liters used of ${number(allowance)} liters daily allowance; ${number(remaining)} liters remaining` : 'Daily allowance data unavailable');
  setText('quota-period', quota?.date ? formatQuotaDate(quota.date, quota.timezone || state.overview?.quota_timezone || 'UTC') : 'Today');
  setText('quota-note', !quota ? 'Every liter saved helps your community.' : usagePercent >= 100 ? 'Your allowance has been reached. Please conserve water.' : usagePercent >= 85 ? 'A little care will help your allowance last.' : 'Every liter saved helps your community.');
  setText('flow-in-value', number(telemetry?.flow_lpm, 2));
  setText('flow-out-value', number(telemetry?.flow_out_lpm, 2));
  setText('flow-in-description', twoTank ? 'Leaving the source into the monitored pipe' : 'Entering the monitored branch');
  setText('flow-out-description', twoTank ? 'Reaching the receiving tank' : 'Reaching your household');
  const delta = telemetry ? telemetry.flow_lpm - telemetry.flow_out_lpm : null;
  setText('balance-value', number(delta, 2));
  setWidth('flow-in-bar', (telemetry?.flow_lpm || 0) / 10 * 100);
  setWidth('flow-out-bar', (telemetry?.flow_out_lpm || 0) / 10 * 100);
  const threshold = Math.max(.3, .15 * (telemetry?.flow_lpm || 0));
  setWidth('balance-bar', Math.max(0, delta || 0) / (threshold * 2) * 100);
  const branchLabels = { NORMAL: 'Flow is balanced', SUSPECTED_LEAK: 'Checking a flow imbalance', LEAK_ALERT: 'Sustained flow loss detected' };
  setText('balance-status', branchLabels[branchStatus] || 'Waiting for sensor readings');
  $('balance-dot').style.background = branchStatus === 'NORMAL' ? palette.good : branchStatus === 'LEAK_ALERT' ? palette.danger : branchStatus ? palette.warning : palette.muted;
  $('balance-bar').style.background = branchStatus === 'LEAK_ALERT' ? palette.danger : palette.warning;
  for (const [name, value] of [['master', decision?.master_valve_percent], ['flat', decision?.flat_valve_percent]]) {
    $(`${name}-value`).innerHTML = `${escapeHtml(number(value, 0))}<small>%</small>`;
    setWidth(`${name}-bar`, value);
    setText(`${name}-caption`, !Number.isFinite(value) ? 'Waiting for controller' : twoTank ? value === 0 ? 'Command limit · transfer stopped' : `${number(value, 0)}% maximum duty · one installed valve` : value === 0 ? 'Closed · no flow permitted' : value === 100 ? 'Full duty · continuous supply' : `${number(30 * value / 100, 1)}s open in each 30s cycle`);
  }
  setText('master-label', twoTank ? 'Source command limit' : 'Community valve');
  setText('flat-heading', twoTank ? 'Pipe command limit' : 'Your branch');
  setText('distribution-note', twoTank ? 'One transfer valve uses the lower of the source and pipe command limits. Its reported duty and relay command appear above.' : 'Valves use a 30-second cycle to share supply fairly and protect the reserve.');
  $('transfer-overview').hidden = !twoTank;
  if (twoTank) {
    setBadge('transfer-overview-badge', telemetry.transfer_permitted ? 'Local checks permit transfer' : 'Transfer stopped', telemetry.transfer_permitted ? 'good' : 'danger');
    setText('transfer-overview-detail', setupRequired ? 'Commissioning required: source tank dimensions are uncalibrated. Transfer remains disabled until calibration and hardware checks are complete.' : telemetry.float_switch_role === 'receiver_full' ? 'AJ-SR04M measures the source tank. The receiver float provides a full cutoff only; no receiver percentage is measured.' : 'AJ-SR04M measures the source tank. The float provides a source low-level cutoff; receiver level is not measured.');
    setText('source-level-value', setupRequired ? 'Uncalibrated' : `${number(level)}% · ${number(telemetry.volume_l)} L`);
    setText('receiver-tank-label', `Receiver tank · ${number(telemetry.receiver_capacity_l)} L capacity`);
    setText('receiver-status', receiverLabel(telemetry));
    setText('transfer-duty', `${number(telemetry.valve_percent, 0)}% reported local duty`);
    setText('transfer-relay', telemetry.relay_energized ? 'Energized · commanded output only' : 'De-energized · commanded output only');
  }
  setText('flat-label', telemetry?.flat_id ? `· ${telemetry.flat_id}` : '');
  setText('overview-health', twoTank && !telemetry.transfer_permitted ? `Transfer stopped · ${localStopLabel(telemetry.local_stop_reason)}` : !telemetry ? 'Continuous monitoring · Local reserve protection' : telemetry.sensor_status === 'ok' && !isStale() ? 'Sensor healthy · Local reserve protection' : isStale() ? 'Telemetry is stale · Check the device connection' : 'Sensor needs attention · Conservative supply limit');
  renderAlert();
  renderHealth();
  renderConnection();
}

function formatQuotaDate(date, timezone) {
  let today;
  try {
    const parts = new Intl.DateTimeFormat('en-CA', { year: 'numeric', month: '2-digit', day: '2-digit', timeZone: timezone }).formatToParts(new Date());
    const part = (type) => parts.find((item) => item.type === type)?.value;
    today = `${part('year')}-${part('month')}-${part('day')}`;
  } catch { today = new Date().toISOString().slice(0, 10); }
  $('quota-period').title = `Daily allowance resets at midnight in ${timezone}.`;
  if (date === today) return 'Today';
  const parsed = new Date(`${date}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) ? new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' }).format(parsed) : 'Daily total';
}

function renderAlert() {
  const snapshot = state.snapshot;
  const telemetry = snapshot?.telemetry;
  const decision = snapshot?.decision;
  const twoTank = isTwoTank(telemetry);
  const banner = $('alert-banner');
  let alert = null;
  if (telemetry && isStale()) alert = { title: 'These readings need a refresh', detail: 'The device has not sent recent telemetry. Values below show its last known state.', badge: 'STALE' };
  else if (decision?.tank_mode === 'CRITICAL') alert = { title: twoTank ? 'The source reserve is protected' : 'The community reserve is protected', detail: twoTank ? 'The source tank is below its protected reserve. Transfer is stopped.' : 'The tank is below 10%. Both valves are closed to protect the remaining water.', badge: 'CRITICAL', critical: true };
  else if (decision?.mode === 'TRANSFER_STOPPED') alert = { title: telemetry.local_stop_reason === 'setup_required' ? 'Commissioning is required before transfer' : 'Tank transfer is stopped', detail: decision.reason, badge: 'TRANSFER STOPPED', critical: true };
  else if (decision?.tank_mode === 'SENSOR_FAULT') alert = { title: 'The level sensor needs attention', detail: 'An invalid ultrasonic reading triggered a conservative valve duty limit. Inspect the probe and its wiring.', badge: 'SENSOR FAULT', critical: true };
  else if (decision?.flat_status === 'LEAK_ALERT') alert = { title: twoTank ? 'A sustained flow loss was detected between the tanks' : 'A sustained flow loss was detected in your branch', detail: twoTank ? `The single transfer valve is limited to ${number(Math.min(decision.master_valve_percent, decision.flat_valve_percent), 0)}% duty. Inspect the pipe between the two flow sensors.` : `The branch valve is limited to ${number(decision.flat_valve_percent, 0)}% duty. Check your pipes and taps. The community valve follows the tank's supply needs.`, badge: 'LEAK ALERT', critical: true };
  else if (decision?.flat_status === 'SUSPECTED_LEAK') alert = { title: 'Checking an irregular flow reading', detail: 'Supply and delivery flow differ. The controller waits for three consecutive readings before confirming a leak.', badge: 'VERIFYING' };
  else if (decision?.tank_mode === 'RATIONING') alert = { title: 'Fair-share rationing is active', detail: twoTank ? `The source command limits the transfer valve to ${number(decision.master_valve_percent, 0)}% duty to preserve the source reserve.` : `The community valve is operating at ${number(decision.master_valve_percent, 0)}% duty to extend the remaining supply. Please limit nonessential water use.`, badge: 'RATIONING' };
  else if (decision?.tank_mode === 'WARNING') alert = { title: 'Your community supply is running lower', detail: 'The forecast is approaching the protected reserve. Please use water thoughtfully and prepare for rationing.', badge: 'SUPPLY WATCH' };
  banner.hidden = !alert;
  if (alert) {
    banner.className = `notice ${alert.critical ? 'notice-critical' : ''}`;
    setText('alert-title', alert.title);
    setText('alert-detail', alert.detail);
    setBadge('alert-badge', alert.badge, alert.critical ? 'danger' : 'warning');
  }
}

function renderHealth() {
  const telemetry = state.snapshot?.telemetry;
  const decision = state.snapshot?.decision;
  const twoTank = isTwoTank(telemetry);
  const services = state.overview?.services;
  const healthValue = (id, value, tone) => { setText(id, value); $(id).className = `health-value ${tone}`; };
  healthValue('sensor-health', !telemetry ? 'Awaiting data' : telemetry.sensor_status === 'ok' ? 'Healthy echo' : 'Attention needed', !telemetry ? '' : telemetry.sensor_status === 'ok' ? 'good' : 'danger');
  setText('echo-value', `${number(telemetry?.ultrasonic_distance_cm)} cm`);
  setText('sensor-model', twoTank ? 'AJ-SR04M source tank ultrasonic probe' : `${telemetry?.level_sensor_model || 'JSN-SR04T'} waterproof ultrasonic probe`);
  setText('echo-range-label', twoTank ? 'Installed sensor range' : 'Valid echo range');
  setText('echo-range', twoTank ? 'Use firmware limits; verify on bench' : '20–600 cm');
  setBadge('hardware-profile', twoTank ? 'Two-tank transfer' : 'Not configured');
  const relayMismatch = twoTank && telemetry.relay_energized && (!telemetry.transfer_permitted || telemetry.requested_valve_percent === 0);
  setText('hardware-detail', !twoTank ? 'The selected device does not report the two-tank transfer profile.' : relayMismatch ? 'Reported relay output conflicts with the safety gate or requested duty. Stop commands are issued when the gate is blocked; inspect the device before proceeding.' : 'One relay controls one normally closed transfer valve. Output telemetry reports the software command; there is no valve-position feedback.');
  setText('float-role', twoTank ? telemetry.float_switch_role === 'receiver_full' ? 'Receiver full cutoff' : 'Source low-level cutoff' : 'Not configured');
  setText('float-state', twoTank ? floatStateLabel(telemetry) : 'Not configured');
  setText('receiver-level', receiverLabel(telemetry));
  setText('receiver-capacity', twoTank ? `${number(telemetry.receiver_capacity_l)} L capacity · not a live volume` : 'Not configured');
  setText('transfer-gate', twoTank ? telemetry.transfer_permitted ? 'Local checks permit transfer' : 'Stopped by local checks' : 'Not configured');
  setText('local-stop', twoTank ? localStopLabel(telemetry.local_stop_reason) : 'Not configured');
  setText('requested-transfer-duty', twoTank ? `${number(telemetry.requested_valve_percent, 0)}%` : 'Not configured');
  setText('relay-command', twoTank ? telemetry.relay_energized ? 'Energized · output command only' : 'De-energized · output command only' : 'Not configured');
  setText('safety-copy', twoTank ? 'The ESP32 stops transfer below the protected source reserve. Commissioning, float, and clock checks can also stop transfer locally. An open float circuit means stop, including a disconnected wire. Receiver volume and percentage are not measured; the reported float role identifies its cutoff function.' : 'The ESP32 closes the valve below 10% tank level locally. Invalid ultrasonic echoes limit valve duty to 30%. Sustained branch flow loss triggers emergency branch flow after three consecutive readings.');
  healthValue('mqtt-health', !services ? 'Checking…' : services.mqtt_connected ? 'Connected' : services.mqtt_configured ? 'Not connected' : 'Not configured', !services || !services.mqtt_configured ? '' : services.mqtt_connected ? 'good' : 'warning');
  healthValue('influx-health', !services ? 'Checking…' : services.influx_connected ? 'Connected' : services.influx_configured ? 'Not connected' : 'Local history only', !services ? '' : services.influx_connected ? 'good' : services.influx_configured ? 'warning' : '');
  setText('history-source', state.historySource ? humanize(state.historySource) : services ? 'Local recorder' : '—');
  setBadge('decision-mode', humanize(decision?.mode), modeTone(decision?.mode));
  setText('decision-reason', decision?.reason || 'Connect your water monitoring device or start a demo to see the latest decision.');
  setText('decision-tank', decision ? humanize(decision.tank_mode) : '—');
  setText('decision-branch', decision ? humanize(decision.flat_status) : '—');
  setText('forecast-demand', `${number(decision?.predicted_flow_lpm, 2)} L/min`);
  setText('leak-rate', `${number(decision?.leak_rate_lpm, 2)} L/min`);
}

function renderHistory() {
  const points = state.history;
  const chart = $('flow-chart');
  setText('history-count', `${number(points.length, 0)} readings`);
  setText('history-window-label', `Showing the last ${state.historyRange < 60 ? `${state.historyRange} minutes` : state.historyRange === 60 ? 'hour' : `${state.historyRange / 60} hours`}. Change the time range in Overview.`);
  setText('history-caption', state.historyError ? 'History unavailable · retrying automatically' : points.length ? `${number(points.length, 0)} readings · refreshed every 10 seconds` : 'History refreshes every 10 seconds');
  if (!points.length) {
    chart.onpointermove = null;
    chart.onpointerleave = null;
    chart.onkeydown = null;
    chart.onblur = null;
    chart.removeAttribute('tabindex');
    chart.setAttribute('aria-label', state.historyError ? 'Flow history is temporarily unavailable.' : 'Flow history is waiting for readings.');
    delete chart.dataset.cursorIndex;
    chart.innerHTML = `<div class="chart-empty"><svg class="icon"><use href="#i-activity"/></svg><strong>${state.historyError ? 'History is temporarily unavailable' : 'Waiting for water to flow'}</strong><span>${state.historyError ? escapeHtml(state.historyError) : 'Your first readings will appear here automatically.'}</span></div>`;
    $('history-table').innerHTML = `<tr><td colspan="6" class="empty-table">${state.historyError ? escapeHtml(state.historyError) : 'No telemetry received yet. Start the simulator in Operations or connect your device.'}</td></tr>`;
    return;
  }
  const width = Math.max(200, chart.clientWidth || 620);
  const height = Math.max(200, chart.clientHeight || 240);
  const margin = { left: 34, right: 16, top: 16, bottom: 34 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const end = new Date(points[points.length - 1].timestamp).getTime();
  const start = points.length > 1 ? new Date(points[0].timestamp).getTime() : end - 1000;
  const timeSpan = Math.max(1000, end - start);
  const maxValue = points.reduce((maximum, point) => Math.max(maximum, point.flow_lpm || 0, point.flow_out_lpm || 0), 1);
  const scaleStep = maxValue <= 2 ? .5 : maxValue <= 8 ? 2 : maxValue <= 20 ? 5 : Math.ceil(maxValue / 20) * 5;
  const maxY = Math.ceil(maxValue / scaleStep) * scaleStep;
  const x = (point) => margin.left + (new Date(point.timestamp).getTime() - start) / timeSpan * plotWidth;
  const y = (value) => margin.top + plotHeight - Math.max(0, value || 0) / maxY * plotHeight;
  let grid = '';
  for (let i = 0; i <= 4; i += 1) {
    const yPoint = margin.top + i / 4 * plotHeight;
    grid += `<line class="chart-grid-line" x1="${margin.left}" x2="${width - margin.right}" y1="${yPoint}" y2="${yPoint}"/><text class="chart-axis" x="${margin.left - 8}" y="${yPoint + 4}" text-anchor="end">${escapeHtml(number(maxY * (1 - i / 4), maxY <= 2 ? 2 : 1))}</text>`;
  }
  const timeTicks = Math.min(width < 440 ? 2 : 4, Math.max(1, Math.floor(timeSpan / 1000)));
  const axisTime = timeSpan / timeTicks < 60000 ? fullTimeFormatter : timeFormatter;
  for (let i = 0; i <= timeTicks; i += 1) {
    const timestamp = start + timeSpan * i / timeTicks;
    grid += `<text class="chart-axis" x="${margin.left + plotWidth * i / timeTicks}" y="${height - 7}" text-anchor="${i === 0 ? 'start' : i === timeTicks ? 'end' : 'middle'}">${escapeHtml(axisTime.format(new Date(timestamp)))}</text>`;
  }
  // Keep long histories inexpensive to draw. The export and activity data remain complete.
  const stride = Math.max(1, Math.floor(points.length / 350));
  const plotted = points.filter((_, index) => index % stride === 0 || index === points.length - 1);
  const gapLimit = Math.max(6000, timeSpan / Math.max(1, plotted.length - 1) * 5);
  const segments = [];
  for (const point of plotted) {
    const current = segments[segments.length - 1];
    if (!current || new Date(point.timestamp) - new Date(current[current.length - 1].timestamp) > gapLimit) segments.push([point]);
    else current.push(point);
  }
  const segmentPath = (segment, field) => segment.map((point, index) => `${index ? 'L' : 'M'}${x(point).toFixed(2)},${y(point[field]).toFixed(2)}`).join(' ');
  const path = (field) => segments.map(segment => segmentPath(segment, field)).join(' ');
  const supplyPath = path('flow_lpm');
  const deliveredPath = path('flow_out_lpm');
  const area = segments.map(segment => `${segmentPath(segment, 'flow_lpm')} L${x(segment[segment.length - 1]).toFixed(2)},${height - margin.bottom} L${x(segment[0]).toFixed(2)},${height - margin.bottom} Z`).join(' ');
  const lastPoint = plotted[plotted.length - 1];
  // Polling and layout changes redraw the SVG. Preserve active keyboard
  // inspection so a fresh sample/resize does not silently dismiss its tooltip.
  const keyboardInspection = document.activeElement === chart && chart.dataset.keyboardInspection === 'true';
  chart.tabIndex = 0;
  chart.setAttribute('aria-label', 'Supply and delivery flow history. Use left and right arrow keys to inspect readings.');
  chart.innerHTML = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Supply and delivery water flow history; ${points.length} readings"><defs><linearGradient id="chart-area" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${palette.supply}" stop-opacity=".18"/><stop offset="100%" stop-color="${palette.supply}" stop-opacity="0"/></linearGradient></defs>${grid}<path d="${area}" fill="url(#chart-area)"/><path d="${supplyPath}" class="chart-line" stroke="${palette.supply}"/><path d="${deliveredPath}" class="chart-line" stroke="${palette.delivered}" stroke-dasharray="5 4"/><circle cx="${x(lastPoint)}" cy="${y(lastPoint.flow_lpm)}" r="6" fill="${palette.supply}" opacity=".16"/><circle cx="${x(lastPoint)}" cy="${y(lastPoint.flow_lpm)}" r="3" fill="${palette.supply}"/><circle cx="${x(lastPoint)}" cy="${y(lastPoint.flow_out_lpm)}" r="3" fill="${palette.delivered}"/><line id="chart-crosshair" x1="0" x2="0" y1="${margin.top}" y2="${height - margin.bottom}" stroke="var(--chart-crosshair, #6983a5)" stroke-dasharray="3 3" visibility="hidden"/></svg><div class="chart-tooltip" id="chart-tooltip" hidden></div><span class="sr-only" id="chart-announcement" aria-live="polite"></span>`;
  const hideInspection = () => {
    chart.dataset.keyboardInspection = 'false';
    if ($('chart-tooltip')) $('chart-tooltip').hidden = true;
    $('chart-crosshair')?.setAttribute('visibility', 'hidden');
  };
  const inspectPoint = (index, anchorX, announce = false) => {
    if (announce) chart.dataset.keyboardInspection = 'true';
    const point = points[index];
    const rect = chart.getBoundingClientRect();
    const tooltip = $('chart-tooltip');
    tooltip.innerHTML = `<strong>${escapeHtml(fullTimeFormatter.format(new Date(point.timestamp)))}</strong><span>Supply <b>${escapeHtml(number(point.flow_lpm, 2))} L/min</b></span><span>Delivered <b>${escapeHtml(number(point.flow_out_lpm, 2))} L/min</b></span>`;
    tooltip.hidden = false;
    tooltip.style.left = `${Math.max(0, Math.min(rect.width - tooltip.offsetWidth, anchorX + 14))}px`;
    const crosshair = $('chart-crosshair');
    crosshair.setAttribute('x1', String(x(point)));
    crosshair.setAttribute('x2', String(x(point)));
    crosshair.setAttribute('visibility', 'visible');
    if (announce) setText('chart-announcement', `${fullTimeFormatter.format(new Date(point.timestamp))}. Supply ${number(point.flow_lpm, 2)} liters per minute. Delivered ${number(point.flow_out_lpm, 2)} liters per minute.`);
  };
  chart.onpointermove = (event) => {
    chart.dataset.keyboardInspection = 'false';
    const rect = chart.getBoundingClientRect();
    const virtualX = (event.clientX - rect.left) / rect.width * width;
    const timestamp = start + (virtualX - margin.left) / plotWidth * timeSpan;
    let low = 0, high = points.length - 1;
    while (low < high) {
      const mid = Math.floor((low + high) / 2);
      if (new Date(points[mid].timestamp).getTime() < timestamp) low = mid + 1;
      else high = mid;
    }
    if (low > 0 && timestamp - new Date(points[low - 1].timestamp) < new Date(points[low].timestamp) - timestamp) low -= 1;
    inspectPoint(low, event.clientX - rect.left);
  };
  chart.onpointerleave = hideInspection;
  chart.onblur = hideInspection;
  chart.onkeydown = (event) => {
    if (event.key === 'Escape') { hideInspection(); return; }
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    let index = Number(chart.dataset.cursorIndex ?? points.length - 1);
    index = event.key === 'Home' ? 0 : event.key === 'End' ? points.length - 1 : index + (event.key === 'ArrowLeft' ? -1 : 1);
    index = Math.max(0, Math.min(points.length - 1, index));
    chart.dataset.cursorIndex = String(index);
    inspectPoint(index, x(points[index]), true);
  };
  if (keyboardInspection) {
    const index = Math.max(0, Math.min(points.length - 1, Number(chart.dataset.cursorIndex ?? points.length - 1)));
    inspectPoint(index, x(points[index]), true);
  }
  $('history-table').innerHTML = points.slice(-100).reverse().map((point) => `<tr><td>${escapeHtml(fullTimeFormatter.format(new Date(point.timestamp)))}</td><td>${isTwoTank(point) && point.local_stop_reason === 'setup_required' ? 'Uncalibrated' : `${escapeHtml(number(point.level_percent))}%`}</td><td>${escapeHtml(number(point.flow_lpm, 2))} L/min</td><td>${escapeHtml(number(point.flow_out_lpm, 2))} L/min</td><td>${escapeHtml(number(point.master_valve_percent, 0))}% / ${escapeHtml(number(point.flat_valve_percent, 0))}%</td><td><span class="history-mode badge ${modeTone(point.mode)}">${escapeHtml(humanize(point.mode))}</span></td></tr>`).join('');
}

async function fetchHistory(force = false) {
  if (!state.deviceId || (!force && (state.historyLoading || Date.now() - state.lastHistoryFetch < 10000))) return;
  const requestId = ++state.historyRequest;
  const deviceId = state.deviceId;
  const range = state.historyRange;
  state.historyLoading = true;
  try {
    const payload = await request(`/devices/${encodeURIComponent(deviceId)}/history?minutes=${range}`);
    if (requestId !== state.historyRequest || deviceId !== state.deviceId || range !== state.historyRange) return;
    state.history = (Array.isArray(payload.points) ? payload.points : [])
      .filter((point) => Number.isFinite(new Date(point.timestamp).getTime()))
      .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
    state.historySource = payload.source || null;
    state.historyError = '';
    state.lastHistoryFetch = Date.now();
    renderHistory();
    renderHealth();
  } catch (error) {
    if (requestId !== state.historyRequest) return;
    state.historyError = error.status === 404 ? '' : error.message;
    state.lastHistoryFetch = Date.now();
    renderHistory();
  } finally { if (requestId === state.historyRequest) state.historyLoading = false; }
}

function renderDemo() {
  const demo = state.demo;
  const available = Boolean(demo?.enabled);
  const disabled = !available || state.demoBusy;
  $('scenario-fieldset').disabled = disabled;
  $('simulator-toggle').disabled = disabled;
  $('simulator-reset').disabled = disabled;
  const running = demo?.running;
  $('simulator-toggle').innerHTML = `<svg class="icon"><use href="#${running ? 'i-stop' : 'i-play'}"/></svg><span>${state.demoBusy ? 'Applying…' : running ? 'Stop simulation' : 'Start simulation'}</span>`;
  setBadge('simulator-status', !demo ? 'Unavailable' : !available ? 'Disabled on server' : running ? 'Simulation running' : 'Ready to start', running ? 'good' : '');
  const scenarios = Array.isArray(demo?.scenarios) ? demo.scenarios : [];
  const current = Array.from(document.querySelectorAll('input[name="scenario"]')).map((input) => input.value).join(',');
  if (current !== scenarios.map((scenario) => scenario.id).join(',')) {
    $('scenario-grid').innerHTML = scenarios.map((scenario) => `<label class="scenario-option"><input type="radio" name="scenario" value="${escapeHtml(scenario.id)}"><span><strong>${escapeHtml(scenario.label)}</strong><small>${escapeHtml(scenario.description)}</small></span></label>`).join('');
  }
  document.querySelectorAll('input[name="scenario"]').forEach((input) => { input.checked = input.value === (state.pendingScenario || demo?.scenario || 'normal'); });
  if (!$('simulator-message').classList.contains('error') && !state.demoBusy) {
    setText('simulator-message', !demo ? 'The simulator could not be reached. Check your server connection.' : !available ? 'Simulation is disabled in the server configuration.' : running ? `Sending one reading per second for ${demo.device_id}.` : 'Choose a scenario, then start the simulation.');
  }
  renderConnection();
}

async function fetchDemo(duringAction = false) {
  if (state.demoBusy && !duringAction) return;
  const revision = state.demoRevision;
  try {
    const demo = await request('/api/demo');
    // A read started before a mutation must not overwrite its newer result.
    if (revision !== state.demoRevision || (state.demoBusy && !duringAction)) return;
    state.demo = demo;
    renderDemo();
  } catch { if (!state.demo) renderDemo(); }
  finally { state.lastDemoFetch = Date.now(); }
}

async function demoAction(action, scenario) {
  if (state.demoBusy) return;
  state.demoBusy = true;
  state.demoRevision += 1;
  state.pendingScenario = action === 'scenario' ? scenario : null;
  $('simulator-message').className = 'form-message';
  renderDemo();
  try {
    const payload = await request('/api/demo', { method: 'POST', body: JSON.stringify({ action, ...(scenario ? { scenario } : {}) }) });
    // Servers may return either the demo status directly or a wrapped response.
    const result = payload.demo || payload;
    if ('enabled' in result) state.demo = result;
    else await fetchDemo(true);
    state.lastHistoryFetch = 0;
    if (action === 'reset') { state.history = []; state.historyError = ''; renderHistory(); }
    const messages = { start: 'Simulation started. Live readings will appear shortly.', stop: 'Simulation stopped. The last received readings remain visible.', scenario: 'Scenario updated. Watch the controller respond to the next readings.', reset: 'Demo reset. The network is ready for a fresh run.' };
    toast(messages[action]);
    if (state.demo?.device_id && action === 'start' && state.deviceId !== state.demo.device_id) changeDevice(state.demo.device_id);
    await poll(true);
  } catch (error) {
    // Reconcile with the server when a response fails after a possible write.
    await fetchDemo(true);
    $('simulator-message').className = 'form-message error';
    setText('simulator-message', error.message);
    toast(error.message, true);
  } finally {
    state.pendingScenario = null;
    state.demoBusy = false;
    renderDemo();
  }
}

async function poll(force = false) {
  if (state.polling || (!force && document.hidden)) return;
  state.polling = true;
  $('refresh-button').classList.add('loading');
  try {
    const results = await Promise.allSettled([
      request('/api/overview'),
      Date.now() - state.lastDemoFetch > 6000 ? fetchDemo() : Promise.resolve(),
    ]);
    if (results[0].status === 'rejected') throw results[0].reason;
    state.overview = results[0].value;
    state.online = true;
    state.lastOverviewSuccess = Date.now();
    setApiError(null);
    renderDevices();
    renderSnapshot();
    void fetchHistory(force);
  } catch (error) {
    state.online = false;
    setApiError(error);
    renderConnection();
  } finally {
    state.polling = false;
    $('refresh-button').classList.remove('loading');
  }
}

function changeDevice(deviceId) {
  state.deviceId = deviceId;
  state.history = [];
  state.historyError = '';
  state.lastHistoryFetch = 0;
  state.historyRequest += 1;
  state.historyLoading = false;
  renderDevices();
  renderSnapshot();
  renderHistory();
  void fetchHistory(true);
}

function exportHistory() {
  if (!state.history.length) { toast('No history to export yet. Connect a device or start the simulation.'); return; }
  const fields = ['timestamp', 'level_percent', 'flow_lpm', 'flow_out_lpm', 'master_valve_percent', 'flat_valve_percent', 'eta_minutes', 'mode', 'leak_rate_lpm'];
  if (state.history.some(isTwoTank)) fields.push('hardware_profile', 'level_sensor_model', 'sensor_status', 'float_switch_role', 'float_switch_state', 'transfer_permitted', 'local_stop_reason', 'relay_energized', 'requested_valve_percent', 'valve_percent', 'receiver_capacity_l');
  const csvCell = (value) => {
    let text = value === null || value === undefined ? '' : String(value);
    if (/^[=+@\t\r]/.test(text) || (text.startsWith('-') && !Number.isFinite(Number(text)))) text = `'${text}`;
    return `"${text.replaceAll('"', '""')}"`;
  };
  const csv = [fields.join(','), ...state.history.map((point) => fields.map((field) => csvCell(point[field])).join(','))].join('\r\n');
  const url = URL.createObjectURL(new Blob(['\ufeff', csv], { type: 'text/csv;charset=utf-8;' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = `waterwise-${state.deviceId.replace(/[^a-zA-Z0-9_-]/g, '_')}-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast(`Exported ${number(state.history.length, 0)} readings.`);
}

function setAdmin(admin) {
  state.admin = admin;
  $('resident-view').classList.toggle('selected', !admin);
  $('admin-view').classList.toggle('selected', admin);
  $('resident-view').setAttribute('aria-pressed', String(!admin));
  $('admin-view').setAttribute('aria-pressed', String(admin));
  $('identity-text').innerHTML = admin ? 'Admin workspace<small>Network operations</small>' : 'Resident workspace<small>Community member</small>';
  if (!admin && state.view === 'controls') openView('overview');
}

function openView(view, { focusHeading = false } = {}) {
  const viewCopy = {
    overview: ['Overview', 'Your water. At a glance.', 'A clearer picture of your water, for a better tomorrow.'],
    activity: ['Activity & history', 'Every reading tells a story.', 'Follow your water supply, one measurement at a time.'],
    health: ['System health', 'A network you can understand.', 'Sensor health, connections, and the decisions keeping water flowing.'],
    controls: ['Operations', 'Put the system through its paces.', 'Explore real controller behavior with a guided simulation.'],
  };
  if (!viewCopy[view]) view = 'overview';
  state.view = view;
  if (view === 'controls') setAdmin(true);
  document.querySelectorAll('.view-panel').forEach((panel) => { panel.hidden = panel.id !== `view-${view}`; });
  document.querySelectorAll('.nav-item').forEach((item) => {
    item.classList.toggle('active', item.dataset.view === view);
    if (item.dataset.view === view) item.setAttribute('aria-current', 'page');
    else item.removeAttribute('aria-current');
  });
  const [breadcrumb, title, subtitle] = viewCopy[view];
  setText('breadcrumb-title', breadcrumb);
  setText('page-title', title);
  setText('page-subtitle', subtitle);
  document.title = `${breadcrumb} · WaterWise`;
  if (location.hash !== `#${view}`) history.replaceState(null, '', `#${view}`);
  closeNavigation();
  if (focusHeading) {
    $('page-title').setAttribute('tabindex', '-1');
    $('page-title').focus({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  }
}

const mobileNavigation = window.matchMedia('(max-width: 700px)');
function syncNavigationAccessibility() {
  const open = mobileNavigation.matches && $('sidebar').classList.contains('open');
  const hidden = mobileNavigation.matches && !open;
  $('sidebar').inert = hidden;
  document.querySelector('main').inert = open;
  if (hidden) $('sidebar').setAttribute('aria-hidden', 'true');
  else $('sidebar').removeAttribute('aria-hidden');
}
function closeNavigation({ returnFocus = false } = {}) {
  $('sidebar').classList.remove('open');
  $('mobile-scrim').hidden = true;
  $('menu-button').setAttribute('aria-expanded', 'false');
  syncNavigationAccessibility();
  if (returnFocus && mobileNavigation.matches) $('menu-button').focus({ preventScroll: true });
}
mobileNavigation.addEventListener('change', () => {
  const focusedInside = $('sidebar').contains(document.activeElement);
  closeNavigation({ returnFocus: focusedInside });
});

document.querySelectorAll('[data-view]').forEach((item) => item.addEventListener('click', (event) => { event.preventDefault(); openView(item.dataset.view, { focusHeading: true }); }));
document.querySelectorAll('[data-open-view]').forEach((item) => item.addEventListener('click', () => { openView(item.dataset.openView, { focusHeading: true }); }));
document.querySelector('.brand').addEventListener('click', (event) => { event.preventDefault(); openView('overview', { focusHeading: true }); });
document.querySelector('.skip-link').addEventListener('click', (event) => {
  event.preventDefault();
  closeNavigation();
  $('page-title').setAttribute('tabindex', '-1');
  $('page-title').focus();
});
window.addEventListener('hashchange', () => openView(location.hash.slice(1), { focusHeading: true }));
$('menu-button').addEventListener('click', () => {
  if (!mobileNavigation.matches) return;
  if ($('sidebar').classList.contains('open')) { closeNavigation({ returnFocus: true }); return; }
  $('sidebar').classList.add('open');
  $('mobile-scrim').hidden = false;
  $('menu-button').setAttribute('aria-expanded', 'true');
  syncNavigationAccessibility();
  ($('sidebar').querySelector('.nav-item.active') || $('sidebar').querySelector('a[href], button'))?.focus();
});
$('mobile-scrim').addEventListener('click', () => closeNavigation({ returnFocus: true }));
document.addEventListener('keydown', (event) => {
  const sidebar = $('sidebar');
  if (!mobileNavigation.matches || !sidebar.classList.contains('open') || document.querySelector('dialog[open]')) return;
  if (event.key === 'Escape') {
    event.preventDefault();
    closeNavigation({ returnFocus: true });
  } else if (event.key === 'Tab') {
    const controls = Array.from(sidebar.querySelectorAll('a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex="-1"])')).filter((element) => element.getClientRects().length);
    const first = controls[0], last = controls[controls.length - 1];
    if (!first) return;
    if (event.shiftKey && (document.activeElement === first || !sidebar.contains(document.activeElement))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (document.activeElement === last || !sidebar.contains(document.activeElement))) {
      event.preventDefault();
      first.focus();
    }
  }
});
$('resident-view').addEventListener('click', () => {
  const leavingControls = state.view === 'controls';
  setAdmin(false);
  if (leavingControls) openView('overview', { focusHeading: true });
});
$('admin-view').addEventListener('click', () => { setAdmin(true); openView('controls', { focusHeading: true }); });
$('device-select').addEventListener('change', (event) => changeDevice(event.target.value));
$('history-range').addEventListener('change', (event) => {
  state.historyRange = Number(event.target.value);
  state.history = [];
  state.historyError = '';
  state.lastHistoryFetch = 0;
  renderHistory();
  void fetchHistory(true);
});
$('refresh-button').addEventListener('click', () => { void poll(true); });
$('retry-button').addEventListener('click', () => { void poll(true); });
$('export-button').addEventListener('click', exportHistory);
$('activity-export').addEventListener('click', exportHistory);
$('simulator-toggle').addEventListener('click', () => { void demoAction(state.demo?.running ? 'stop' : 'start', state.demo?.scenario || 'normal'); });
$('simulator-reset').addEventListener('click', () => { void demoAction('reset'); });
$('scenario-grid').addEventListener('change', (event) => { if (event.target.name === 'scenario') void demoAction('scenario', event.target.value); });
$('api-key-form').addEventListener('submit', (event) => {
  event.preventDefault();
  state.apiKey = $('api-key').value.trim();
  let saved = true;
  try { if (state.apiKey) sessionStorage.setItem('waterwise.apiKey', state.apiKey); else sessionStorage.removeItem('waterwise.apiKey'); } catch { saved = false; }
  $('key-message').className = 'form-message success';
  setText('key-message', state.apiKey ? saved ? 'Key saved for this tab session.' : 'Key saved until this page is refreshed.' : 'API key cleared.');
  $('simulator-message').className = 'form-message';
  state.lastDemoFetch = 0;
  void poll(true);
});
$('clear-key').addEventListener('click', () => { $('api-key').value = ''; $('api-key-form').requestSubmit(); });
$('key-visibility').addEventListener('click', () => {
  const showing = $('api-key').type === 'password';
  $('api-key').type = showing ? 'text' : 'password';
  setText('key-visibility', showing ? 'Hide' : 'Show');
  $('key-visibility').setAttribute('aria-label', showing ? 'Hide API key' : 'Show API key');
});
$('tips-button').addEventListener('click', () => $('tips-dialog').showModal());
$('close-tips').addEventListener('click', () => $('tips-dialog').close());
$('tips-done').addEventListener('click', () => $('tips-dialog').close());
$('tips-dialog').addEventListener('click', (event) => { if (event.target === $('tips-dialog')) { const rect = event.target.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) event.target.close(); } });
document.addEventListener('visibilitychange', () => { if (!document.hidden) void poll(true); });
let chartResizeTimer;
const chartResizeObserver = new ResizeObserver((entries) => {
  if (!entries[0].contentRect.width) return;
  clearTimeout(chartResizeTimer);
  chartResizeTimer = setTimeout(renderHistory, 80);
});
chartResizeObserver.observe($('flow-chart'));
setText('current-date', new Intl.DateTimeFormat(undefined, { weekday: 'short', day: 'numeric', month: 'long', year: 'numeric' }).format(new Date()));
openView(location.hash.slice(1));
renderHistory();
void poll(true);
setInterval(() => { void poll(); }, 2000);
setInterval(() => { renderConnection(); renderAlert(); }, 1000);
