from __future__ import annotations

import importlib.util
import io
import tarfile
import zipfile
from pathlib import Path
from types import ModuleType


def load_guard() -> ModuleType:
    path = Path(__file__).parents[1] / "scripts" / "check_distribution.py"
    spec = importlib.util.spec_from_file_location("check_distribution", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_distribution_guard_accepts_python_only_wheel(tmp_path: Path) -> None:
    guard = load_guard()
    wheel = tmp_path / "package.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("splunk_dashboard_studio/__init__.py", "")
        archive.writestr("splunk_dashboard_studio/py.typed", "")
    assert guard.prohibited_members(wheel) == []


def test_distribution_guard_rejects_node_assets_in_wheel_and_sdist(tmp_path: Path) -> None:
    guard = load_guard()
    wheel = tmp_path / "bad.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("package.json", "{}")
        archive.writestr("node_modules/package/index.js", "")
    assert guard.prohibited_members(wheel) == [
        "node_modules/package/index.js",
        "package.json",
    ]

    sdist = tmp_path / "bad.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        data = b""
        for name in (
            "package/helper.cjs",
            "package/integration/splunk-visual/package-lock.json",
            "package/integration/splunk-visual/tests/render.spec.ts",
        ):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    assert guard.prohibited_members(sdist) == [
        "package/helper.cjs",
        "package/integration/splunk-visual/package-lock.json",
        "package/integration/splunk-visual/tests/render.spec.ts",
    ]


def test_distribution_guard_rejects_unknown_archive_type(tmp_path: Path) -> None:
    guard = load_guard()
    with __import__("pytest").raises(ValueError, match="Unsupported"):
        guard.artifact_members(tmp_path / "artifact.bin")
