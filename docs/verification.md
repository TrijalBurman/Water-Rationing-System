# Verification record

The local demo uses the same controller, recorder, API, and portal as the hardware deployment. Results below distinguish the Windows compatibility work from the earlier implementation checks.

## Windows compatibility update — 23 October 2026

The `windows` branch adds native setup/demo/bootstrap entry points, portable browser and firmware wrappers, Windows timezone data, line-ending rules, and Windows instructions. A Linux virtual environment must be recreated on Windows. Documentation and command examples are in the [Windows guide](windows.md).

| Area | Verification status |
| --- | --- |
| Windows backend and lint, Python 3.12/3.14 | **Passed: 80 tests on each version**, Ruff lint/format, PowerShell and CMD launchers; checkout path includes spaces |
| Windows Chromium smoke and accessibility checks | **Passed: 17 smoke checks, 14 interface/keyboard checks**, eight desktop/mobile accessibility scans with zero violations |
| Windows native firmware safety tests and ESP32 PlatformIO build | **Passed** through the PowerShell wrappers: MSVC safety suite and PlatformIO 6.1.18 ESP32 example compile |
| Linux backend/lint, browser, native firmware, and ESP32 build | **Passed** on Python 3.12/3.14: 79 tests plus one Windows-only ACL test skipped; browser, GCC safety suite, and ESP32 compile passed |
| Real full-stack Docker integration | **Passed** on Linux: all four containers healthy, authenticated MQTT/InfluxDB readiness, live demo ingestion and leak restriction, Grafana health |
| Docker Desktop, USB upload, and wet hardware on a physical Windows computer | Not verified in this Linux workspace |

All seven jobs passed in [GitHub Actions run 39979578873](https://github.com/TrijalBurman/Water-Rationing-System/actions/runs/39979578873), testing code commit `2b8c174` on 23 October 2026. The Windows runner used Windows Server 2025; Python 3.12 and 3.14 were installed independently from fresh checkouts. The native permission test verifies owner-only access even when PowerShell module lookup is unavailable. Another regression starts quota storage with system timezone lookup disabled, proving the packaged timezone data works.

Local Linux validation also passed: native setup, two credential-bootstrap runs, isolated browser checks, GCC safety tests (including source/compiler paths with spaces), and the ESP32 example build. Browser checks own a temporary database and do not reset existing demo history. Secrets, databases, downloaded tools, and caches remain excluded from Git.

The Docker job checks service startup and API integration; it does not establish every provisioned Grafana panel's Flux/rendering behavior. Linux container checks and hosted Windows tests do not establish Docker Desktop networking or physical USB/hardware behavior on a personal Windows computer. Complete the hardware commissioning checklist before operating valves.

## Historical implementation verification — 27 September 2026

The following recorded checks were completed on the original Linux computer before the Windows compatibility work.

### Completed checks

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

On Windows, from the project root after installing Python 3.12+:

```powershell
py -3.12 scripts/manage.py setup
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check backend tests
.\.venv\Scripts\python.exe -m ruff format --check backend tests
py -3.12 firmware/esp32/test_native.py
py -3.12 firmware/esp32/build.py
```

Native firmware tests require a supported C++ compiler. Install PlatformIO for the ESP32 build as described in the [firmware guide](../firmware/README.md); the wrapper finds that installed tool. On Linux/macOS:

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

The portable runner installs the browser dependencies, starts a loopback demo with a fresh isolated data directory, runs smoke/accessibility checks, and stops the server. It preserves existing demo history. Node.js with npm must be installed. No manually running server is required.

PowerShell, after project setup:

```powershell
.\.venv\Scripts\python.exe scripts/browser_tests.py install
.\.venv\Scripts\python.exe scripts/browser_tests.py run
```

Linux/macOS:

```bash
.venv/bin/python scripts/browser_tests.py install
.venv/bin/python scripts/browser_tests.py run
```

Reports, downloads, and screenshots are stored under project runtime/cache directories. The earlier [desktop preview](screenshots/desktop.png) and [mobile preview](screenshots/mobile.png) remain as implementation captures.

### Manually running the browser checks on Linux

The individual browser smoke script changes simulator scenarios and **resets the selected demo's history**. Only run this manual route against a disposable loopback demo; it refuses a server where demo controls are disabled. The portable runner above is the default on either OS.

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

- The four Docker services were **not launched during the September implementation checks**. Docker image/container and named-volume storage resides outside the project directory, which was outside that run's allowed working scope. Compose was validated without launching containers. The October CI table above separately records the new real-stack integration status.
- The broker ACLs, Influx/Flux queries, and Grafana rendering still need a live full-stack test using the [deployment guide](deployment.md). Automated adapter tests use mocks and do not substitute for this test.
- Firmware was compiled but **not uploaded to an ESP32**. Actual Wi-Fi/TLS operation, sensor calibration, relay polarity, valve behavior, flow-meter accuracy, and hydraulic leak isolation require the [hardware commissioning checklist](hardware.md).
- The supplied pinout contains one relay. Independent master and branch actuation requires the additional physical outputs/topology described in the hardware guide. The UI presents controller commands; it cannot confirm physical valve position.

## Plan clarifications

The architecture guide documents how the implementation handles the plan's undefined low-level/long-ETA case, the correct placement of branch flow meters, nullable ETA, conservative sensor handling, one-relay limitation, and the absence of specified pump-control hardware. See [architecture and assumptions](architecture.md).
