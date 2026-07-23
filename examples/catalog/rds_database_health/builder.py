"""Build the checked rds_database_health catalog dashboard."""

from splunk_dashboard_studio import build_catalog_dashboard, canonical_json

EXAMPLE_ID = "rds_database_health"
TARGET = "9.4.3"


def main() -> None:
    print(canonical_json(build_catalog_dashboard(EXAMPLE_ID, TARGET), indent=2))


if __name__ == "__main__":
    main()
