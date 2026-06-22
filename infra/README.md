# Infrastructure

Deployment and infrastructure files for local development and cloud hosting.

Planned responsibilities:

- Docker Compose for local FastAPI, InfluxDB, Grafana, and MQTT broker.
- AWS deployment notes for EC2 and AWS IoT Core.
- GitHub Actions CI/CD workflow.

## Local Stack

The root `docker-compose.yml` starts:

- Mosquitto MQTT broker on `1883`.
- InfluxDB on `8086`.
- FastAPI backend on `8000`.
- Grafana on `3000`.

Run from the repository root:

```bash
docker compose up --build
```
