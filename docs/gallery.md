# Dashboard render gallery

These are deterministic Playwright captures from disposable, pinned Splunk Enterprise containers.
They are exact copies of reviewed visual-regression baselines—not mockups—and their source paths,
target versions, byte sizes, and SHA-256 hashes are recorded in
[`images/dashboard-samples/manifest.json`](images/dashboard-samples/manifest.json).

## Splunk Health portable — Enterprise 9.4.3

The app-free compatibility port keeps the eight upstream health searches and dashboard layout,
then renders them with built-in tables and a single value. No custom app is installed on Splunk 9.

![Splunk Health portable dashboard rendered on Splunk Enterprise 9.4.3](images/dashboard-samples/splunk-health-portable-9.4.png)

## Kubernetes workload health — Enterprise 9.4.3

![Kubernetes workload health dashboard rendered on Splunk Enterprise 9.4.3](images/dashboard-samples/kubernetes-workload-health-9.4.png)

## Business journey SLO — Enterprise 10.2.0

![Business journey SLO dashboard rendered on Splunk Enterprise 10.2.0](images/dashboard-samples/business-journey-slo-10.2.png)

## Microservice service map — Enterprise 10.4.0

![Microservice service map dashboard rendered on Splunk Enterprise 10.4.0](images/dashboard-samples/microservice-service-map-10.4.png)

## Splunk Health custom visualizations — Enterprise 10.4.0

This is the provenance-locked source dashboard with the matching `splunk_health` app mounted only
inside the disposable integration fixture.

![Splunk Health custom visualization dashboard rendered on Splunk Enterprise 10.4.0](images/dashboard-samples/splunk-health-custom-10.4.png)

Regenerate the public copies only after reviewing new baselines:

```console
uv run python scripts/sync_dashboard_samples.py --write
uv run python scripts/sync_dashboard_samples.py --check
```
