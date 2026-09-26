# AI Powered Smart Water Management and Rationing System

An end-to-end IoT and edge-computing water rationing and leak mitigation system designed for residential complexes and high-density apartments. The system combines dual-flow mass conservation leak detection, depletion forecasting, automated duty-cycle/proportional rationing, and a real-time Grafana telemetry flight recorder.

---

## 📑 Project Deliverables & Reports

| Deliverable | Description | File Link |
| :--- | :--- | :--- |
| **Review 2 Report** | Complete Project Progress Report for Review 2 | [Water_Rationing_Review2_Report.docx](reports/Water_Rationing_Review2_Report.docx) |
| **Review 2 Presentation** | Review 2 Progress Presentation Slides | [Review_2_Presentation.pptx](reports/Review_2_Presentation.pptx) |
| **System Workflow Diagram** | Comprehensive Architectural & Sensor Flowchart | [Workflow.pdf](reports/Workflow.pdf) |
| **Review 1 Report** | Foundation Report (Problem Formulation & Literature) | [Water_Rationing_Review1_Report.docx](reports/Water_Rationing_Review1_Report.docx) |
| **Hardware Guide** | JSN-SR04T & YF-S201 Wiring, Calibration, Standoffs | [HARDWARE_AND_CALIBRATION.md](docs/HARDWARE_AND_CALIBRATION.md) |
| **Commissioning Guide** | Flashing ESP32, Docker bootstrap, and Live Bring-up | [CONNECTION_AND_COMMISSIONING_GUIDE.md](docs/CONNECTION_AND_COMMISSIONING_GUIDE.md) |

---

## 🏗️ System Architecture & Data Flow

```text
       [ JSN-SR04T Ultrasonic Sensor ]        [ Dual YF-S201 Flow Meters ]
           (Waterproof Tank Level)                 (Upstream & Downstream)
                      │                                      │
                      ▼                                      ▼
             ┌────────────────────────────────────────────────────────┐
             │               ESP32 Edge Microcontroller               │
             │  • 1 Hz sampling with median filter (blind zone offset)│
             │  • Local edge safety cutoff (Level < 10% -> 0% valve)  │
             │  • Duty-cycle (30s) or PWM proportional valve drive    │
             └──────────────────────────┬─────────────────────────────┘
                                        │ MQTT Telemetry (JSON)
                                        ▼
                             ┌──────────────────────┐
                             │ Mosquitto Broker     │
                             │ (Port 1883, TLS/Auth)│
                             └──────────┬───────────┘
                                        │
             ┌──────────────────────────┴─────────────────────────────┐
             ▼                                                        ▼
┌───────────────────────────────┐                        ┌───────────────────────┐
│ FastAPI Cloud Decision Engine │                        │ InfluxDB 2.7 Time-    │
│ • Depletion ETA Calculation   │                        │ Series Database       │
│ • Dual-Flow Leak Differential │                        │ • High-resolution retention
│ • 3-Cycle Transient Debounce  │                        │ • Telemetry & decisions
│ • Decoupled Branch Throttling │                        └──────────┬────────────┘
└──────────────┬────────────────┘                                   │ Flux Queries
               │ MQTT Command Topic                                 ▼
               ▼                                         ┌───────────────────────┐
      [ ESP32 Valve Actuator ]                           │ Grafana 11.4 Dashboard│
  (Master & Individual Flat Valves)                      │ • 8 Flight-Recorder   │
                                                         │   Telemetry Panels    │
                                                         └───────────────────────┘
```

---

## ⚡ Key Engineering Features

1. **Dual-Flow Mass Conservation Leak Detection**:
   $$\Delta Q = Q_{\text{in}} - Q_{\text{out}}$$
   Monitors the differential between branch input and fixture outlet. Debounces transient air pockets or turbine inertia over 3 consecutive sample cycles before raising a confirmed leak flag.
2. **Decoupled Flat Isolation**:
   When a branch fracture is confirmed, the system throttles that specific flat to **25%** emergency flow while keeping the **Master Tank Valve at 100%**, preventing supply starvation for unaffected residents.
3. **Dynamic Depletion ETA Forecasting**:
   $$\text{ETA} = \frac{V_{\text{current}} - V_{\text{reserve}}}{\overline{Q}_{5\text{sample}}}$$
   Classifies supply state into `NORMAL` ($\text{ETA} > 120\text{ min}$), `WARNING` ($60-120\text{ min}$), `RATIONING` ($< 60\text{ min}$), `CRITICAL` ($< 10\%$), or `SENSOR_FAULT`.
4. **Autonomous Edge Safety**:
   If tank volume breaches the 10% reserve threshold or cloud connectivity drops, ESP32 firmware autonomously closes the valve locally without relying on network commands.

---

## 🚀 Quick Start Guide

### Prerequisites
- Docker Engine & Docker Compose
- Python 3.10+ (for tests & simulator)
- PlatformIO (if flashing physical ESP32)

### 1. Stack Initialization
Run the automated bootstrap script to generate environment configs and Mosquitto credentials:
```bash
./scripts/bootstrap.sh
```

### 2. Launch Services
Start Mosquitto, InfluxDB, FastAPI Backend, and Grafana:
```bash
docker compose --env-file .env up --build -d
```

Service URLs:
- **FastAPI API**: http://localhost:8000
- **API Swagger Docs**: http://localhost:8000/docs
- **Grafana Flight Recorder**: http://localhost:3000 *(Username: `admin`, Password: set in `.env`)*
- **InfluxDB Console**: http://localhost:8086

### 3. Run Validation Tests
Run the unit test suite covering controller decisions, leak detection, and edge cases:
```bash
pytest
```
*(Or inside Docker: `docker compose run --rm api pytest -q`)*

### 4. Interactive Simulation & Leak Demo
To test Grafana telemetry and valve responses without physical hardware:

- **Run Standard Depletion Sequence**:
  ```bash
  python3 tools/simulate.py
  ```
- **Run Live Leak Detection & Mitigation Sequence**:
  ```bash
  python3 tools/demo_leak.py
  ```

---

## 📁 Repository Structure

```text
├── backend/
│   ├── app/
│   │   ├── controller.py       # Core rationing & leak detection decision engine
│   │   ├── influx_store.py     # InfluxDB 2.x time-series client
│   │   ├── main.py             # FastAPI REST endpoints & lifespan hooks
│   │   ├── mqtt_bridge.py      # Paho MQTT bidirectional bridge
│   │   ├── schemas.py          # Pydantic v2 telemetry and decision schemas
│   │   └── settings.py         # Environment configuration
│   ├── tests/
│   │   └── test_controller.py  # 9 comprehensive unit tests
│   ├── Dockerfile              # Production Python 3.12 container definition
│   └── requirements.txt        # Backend dependencies
├── firmware/
│   └── esp32/
│       ├── include/
│       │   └── config.example.h # Hardware pinout & calibration template
│       ├── src/
│       │   └── main.cpp         # ESP32 C++ firmware (Median filter, Dual flow, MQTT)
│       └── platformio.ini       # PlatformIO build configuration
├── grafana/
│   ├── dashboards/
│   │   └── water-rationing.json # Provisioned 8-panel flight recorder dashboard
│   └── provisioning/
│       ├── dashboards/          # Auto-load dashboard provider config
│       └── datasources/         # InfluxDB Flux datasource config
├── mosquitto/
│   └── config/
│       └── mosquitto.conf       # Eclipse Mosquitto broker configuration
├── reports/
│   ├── Water_Rationing_Review2_Report.docx  # Review 2 submission report
│   ├── Review_2_Presentation.pptx          # Review 2 presentation slide deck
│   ├── Water_Rationing_Review1_Report.docx  # Review 1 submission report
│   ├── Workflow.pdf                        # System workflow diagrams
│   ├── templates/                          # University review document templates
│   └── work/                               # Rendered report pages and review assets
├── tools/
│   ├── demo_leak.py            # Terminal demo of dual-flow leak detection
│   └── simulate.py             # End-to-end telemetry playback simulator
├── docs/                       # Technical hardware & calibration documentation
├── scripts/                    # Bootstrap & deployment helper scripts
├── docker-compose.yml          # Multi-container orchestration definition
└── Makefile                    # Convenience shortcuts
```

---

## 👥 Team Branches

- `main`: Production integration branch.
- `trijal`: Trijal Burman (Backend, Leak Detection, Edge Firmware, Flight Recorder).
- `hardik`: Hardik's working branch.
- `gayatri`: Gayatri's working branch.
- `prashant`: Prashant's working branch.
