"""Build the app-free rcastley Splunk Health port for Splunk Enterprise 9.4."""

from splunk_dashboard_studio import build_source_template_bundle, canonical_json


def main() -> None:
    bundle = build_source_template_bundle("rcastley_splunk_health_portable", "9.4.3")
    print(canonical_json(bundle.model_dump(mode="json", by_alias=True), indent=2))


if __name__ == "__main__":
    main()
