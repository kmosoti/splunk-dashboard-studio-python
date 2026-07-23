from __future__ import annotations

import json
import struct

from scripts.sync_dashboard_samples import MANIFEST_PATH, OUTPUT, SAMPLES, sync


def test_dashboard_samples_are_exact_reviewed_baseline_copies() -> None:
    assert sync(write=False) == []
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "dashboard-sample-gallery/v1"
    assert len(manifest["samples"]) == len(SAMPLES) == 5
    assert {record["target"] for record in manifest["samples"]} == {
        "9.4.3",
        "10.2.0",
        "10.4.0",
    }
    for sample in SAMPLES:
        image = (OUTPUT / sample["output"]).read_bytes()
        assert image.startswith(b"\x89PNG\r\n\x1a\n")
        assert struct.unpack(">II", image[16:24]) == (1440, 1100)
