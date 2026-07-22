from splunk_dashboard_studio import DashboardBuilder, canonical_json

builder = DashboardBuilder(title="Service health", target="9.4.3")
events = builder.add_search(
    "index=_internal | stats count by sourcetype | sort - count",
    name="events",
)
builder.add_visualization(
    "splunk.table",
    name="events",
    data_sources={"primary": events},
    options={},
)

print(canonical_json(builder.build(), indent=2))
