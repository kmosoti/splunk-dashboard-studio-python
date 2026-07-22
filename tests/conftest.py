from __future__ import annotations

from typing import Any

import pytest

from splunk_dashboard_studio import DashboardBuilder


@pytest.fixture
def dashboard_payload() -> dict[str, Any]:
    builder = DashboardBuilder(title="Test dashboard", target="10.2.0")
    source = builder.add_search(
        "index=_internal | stats count by sourcetype",
        data_source_id="ds_events",
    )
    builder.add_visualization(
        "splunk.table",
        name="events",
        visualization_id="viz_events",
        data_sources={"primary": source},
        options={},
    )
    return builder.build().as_json_value()
