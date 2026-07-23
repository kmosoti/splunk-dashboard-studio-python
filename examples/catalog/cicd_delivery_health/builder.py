"""Build the checked cicd_delivery_health catalog dashboard."""

from splunk_dashboard_studio import build_catalog_dashboard, canonical_json

EXAMPLE_ID = "cicd_delivery_health"
TARGET = "9.4.3"


def main() -> None:
    print(canonical_json(build_catalog_dashboard(EXAMPLE_ID, TARGET), indent=2))


if __name__ == "__main__":
    main()
