# Grafana

Dashboard configuration and provisioning files.

Planned panels:

- Main tank level percentage.
- Flow rate and total consumption.
- Predicted time-to-depletion.
- System mode: normal, warning, critical, rationing.
- Leak or anomaly alerts.

## Provisioning

Grafana provisioning files are stored in `grafana/provisioning`.
The dashboard is loaded automatically when the Docker Compose stack starts.
