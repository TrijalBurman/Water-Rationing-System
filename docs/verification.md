# Verification record

Verified on **27 September 2026** in the project directory. The local demo uses the same controller, recorder, API, and portal as the hardware deployment.

## Completed checks

| Area | Result |
| --- | --- |
| Python backend | **68 tests passed** on Python 3.14.4 |
| Python lint and formatting | Passed |
| Browser integration | **17 checks passed** in Chromium, no uncaught JavaScript errors |
| Responsive dark portal | All four views checked at 1440, 768, 390 and 320 px widths; no horizontal overflow |
| Frontend accessibility | No automated WCAG A/AA violations in all four views at desktop and mobile widths; keyboard navigation, chart inspection, skip link and dialog focus checked |
| Local setup and launcher | Dependency installation and demo server startup passed after directory relocation |
| Firmware safety logic | Native tests and sanitizer checks passed |
| ESP32 firmware | Master/example and branch/TLS configurations compiled and linked |
| Deployment configuration | Compose resolution, shell syntax, credential generation, permissions, dashboard JSON, eight panel definitions and source filters checked |

Backend tests cover all eight cases requested by the original plan, plus threshold boundaries, independent device state, gaps, duplicates, invalid input, write authentication, persistence after restart, daily consumption across midnight, outbox retry, reset/write concurrency, simulator recovery, shutdown cleanup, and MQTT validation. Mocked adapters exercise integration failure handling without requiring running services.

The test run reports one upstream Starlette warning about its HTTPX test-client compatibility. The tests complete successfully. Deployment targets Python 3.12 as specified in the original plan; the actual host test run used Python 3.14.4.

Browser checks exercise actual API requests through the portal: reading display, chart and CSV export, all operating scenarios, branch-only leak restriction, both-valve reserve closure, recovery, stop/stale behavior, reset/empty behavior, network failure/retry, mobile navigation, and JavaScript error monitoring. A separate delayed-response check covers the scenario selection race and failed-request recovery.

The dark redesign was checked with Chromium and axe-core 4.13.0. The visual audit also verifies local font loading, absence of external asset requests, mobile menu focus containment and Escape behavior, chart keyboard controls, and the history table's bounded scroll area. Automated accessibility scans cover the rendered states described above; they do not establish complete accessibility conformance.

## Reproduce the checks

From the project root:

```bash
./scripts/setup.sh
.venv/bin/python -m pytest
.venv/bin/python -m ruff check backend tests
.venv/bin/python -m ruff format --check backend tests
./firmware/esp32/test-native.sh
./firmware/esp32/build.sh
```

See [firmware build details](../firmware/BUILD_STATUS.md) for exact toolchain versions and image sizes.

### Browser test

This test changes simulator scenarios and **resets local demo history**. Run it against the loopback demo launcher. It refuses a server where demo controls are disabled.

In one terminal:

```bash
PORT=8010 ./scripts/run-demo.sh
```

In another terminal, from this project root:

```bash
mkdir -p .runtime/browser .cache
export TMPDIR="$PWD/.runtime"
export XDG_CACHE_HOME="$PWD/.cache"
export XDG_CONFIG_HOME="$PWD/.runtime/browser/config"
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.cache/playwright"
npm --cache "$PWD/.cache/npm" --prefix "$PWD/.runtime/browser" install --no-audit --no-fund playwright@1.63.0 axe-core@4.13.0
node .runtime/browser/node_modules/playwright/cli.js install chromium
node tests/browser-smoke.cjs
node tests/frontend-audit.cjs
```

Results and the CSV export are saved under `.runtime/browser/`. Desktop and mobile captures are saved under `docs/screenshots/`. The current portal is also shown in the [desktop preview](screenshots/desktop.png) and [mobile preview](screenshots/mobile.png).

The frontend audit is read-only and expects a running demo with recorded telemetry. It saves screenshots of all four views, an accessibility report, and keyboard/responsive check results under `.runtime/dark-review/`.

## Checks requiring their target environment

- The four Docker services were **not launched** during implementation. Docker image/container and named-volume storage resides outside the project directory, which was outside the user's allowed working scope. Compose was validated without launching containers.
- The broker ACLs, Influx/Flux queries, and Grafana rendering still need a live full-stack test using the [deployment guide](deployment.md). Automated adapter tests use mocks and do not substitute for this test.
- Firmware was compiled but **not uploaded to an ESP32**. Actual Wi-Fi/TLS operation, sensor calibration, relay polarity, valve behavior, flow-meter accuracy, and hydraulic leak isolation require the [hardware commissioning checklist](hardware.md).
- The supplied pinout contains one relay. Independent master and branch actuation requires the additional physical outputs/topology described in the hardware guide. The UI presents controller commands; it cannot confirm physical valve position.

## Plan clarifications

The architecture guide documents how the implementation handles the plan's undefined low-level/long-ETA case, the correct placement of branch flow meters, nullable ETA, conservative sensor handling, one-relay limitation, and the absence of specified pump-control hardware. See [architecture and assumptions](architecture.md).
