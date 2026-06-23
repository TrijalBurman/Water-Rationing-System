# Demo Script

## 1. Start the System

```bash
docker compose up --build
```

Open:

- FastAPI docs: http://localhost:8000/docs
- Grafana: http://localhost:3000

## 2. Normal Operation

Run:

```bash
cd backend
python -m app.simulator --scenario normal
```

On Windows, you can also run from the repository root:

```powershell
.\scripts\demo.ps1 -Scenario normal -Seconds 30
```

Expected result:

- Tank level remains stable.
- Flow rate is steady.
- Status remains healthy.
- Valve command remains open.

## 3. Shortage Prediction and Rationing

Stop the simulator and run:

```bash
python -m app.simulator --scenario shortage
```

Or:

```powershell
.\scripts\demo.ps1 -Scenario shortage -Seconds 30
```

Expected result:

- Tank level drops quickly.
- Time-to-depletion decreases.
- When TTD is below the critical threshold, the backend publishes a restricted
  valve command.
- Dashboard shows critical/rationing behavior.

## 4. Leak Detection

Stop the simulator and run:

```bash
python -m app.simulator --scenario leak
```

Or:

```powershell
.\scripts\demo.ps1 -Scenario leak -Seconds 30
```

Expected result:

- Upstream and downstream flow rates diverge.
- Volume loss rises above the threshold.
- Backend reports an anomaly and potential leak.
