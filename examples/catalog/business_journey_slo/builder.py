"""Build the checked business_journey_slo catalog dashboard."""

from splunk_dashboard_studio import build_catalog_dashboard, canonical_json

EXAMPLE_ID = "business_journey_slo"
TARGET = "9.4.3"


def main() -> None:
    print(canonical_json(build_catalog_dashboard(EXAMPLE_ID, TARGET), indent=2))


if __name__ == "__main__":
    main()
