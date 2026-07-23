"""Provenance-locked dashboard templates adapted from external source repositories."""

from __future__ import annotations

import hashlib
import json
from functools import cache, lru_cache
from importlib.resources import files
from pathlib import PurePosixPath
from typing import Any, Final

from splunk_dashboard_studio.contracts import SourceTemplateBundle, SourceTemplateEntry
from splunk_dashboard_studio.models import DashboardDefinition
from splunk_dashboard_studio.validation import validate_dashboard
from splunk_dashboard_studio.version import EnterpriseVersion

_SCHEMA_VERSION: Final = "dashboard-source-templates/v1"
_DATA_ROOT: Final = "template_data"
_MANIFEST_NAME: Final = "manifest.json"


class SourceTemplateError(ValueError):
    """Base error for source-template lookup, integrity, or compatibility failures."""


class SourceTemplateNotFound(SourceTemplateError):
    pass


class SourceTemplateTargetUnsupported(SourceTemplateError):
    pass


class SourceTemplateIntegrityError(SourceTemplateError):
    pass


def _resource_text(name: str) -> str:
    path = PurePosixPath(name)
    if len(path.parts) != 1 or path.suffix != ".json":
        raise SourceTemplateIntegrityError(f"Unsafe source-template resource name {name!r}")
    return files("splunk_dashboard_studio").joinpath(_DATA_ROOT, name).read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _records() -> tuple[tuple[SourceTemplateEntry, str], ...]:
    try:
        manifest = json.loads(_resource_text(_MANIFEST_NAME))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SourceTemplateIntegrityError(
            f"Unable to load source-template manifest: {error}"
        ) from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != _SCHEMA_VERSION:
        raise SourceTemplateIntegrityError(
            f"Source-template manifest must use schema {_SCHEMA_VERSION!r}"
        )
    raw_templates = manifest.get("templates")
    if not isinstance(raw_templates, list) or not raw_templates:
        raise SourceTemplateIntegrityError(
            "Source-template manifest requires a non-empty templates array"
        )

    records: list[tuple[SourceTemplateEntry, str]] = []
    for raw_record in raw_templates:
        if not isinstance(raw_record, dict) or set(raw_record) != {"definition_file", "entry"}:
            raise SourceTemplateIntegrityError(
                "Each source-template record requires only definition_file and entry"
            )
        definition_file = raw_record["definition_file"]
        if not isinstance(definition_file, str):
            raise SourceTemplateIntegrityError("Source-template definition_file must be a string")
        records.append((SourceTemplateEntry.model_validate(raw_record["entry"]), definition_file))
    identifiers = [entry.template_id for entry, _ in records]
    if len(identifiers) != len(set(identifiers)):
        raise SourceTemplateIntegrityError("Source-template IDs must be unique")
    return tuple(records)


def source_template_entries() -> tuple[SourceTemplateEntry, ...]:
    """Return immutable provenance and compatibility records for imported templates."""

    return tuple(entry for entry, _ in _records())


def _record(template_id: str) -> tuple[SourceTemplateEntry, str]:
    try:
        return next(record for record in _records() if record[0].template_id == template_id)
    except StopIteration as error:
        available = ", ".join(entry.template_id for entry, _ in _records())
        raise SourceTemplateNotFound(
            f"Unknown source template {template_id!r}; available templates: {available}"
        ) from error


def _source_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@cache
def _definition(template_id: str) -> DashboardDefinition:
    entry, definition_file = _record(template_id)
    try:
        payload = json.loads(_resource_text(definition_file))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SourceTemplateIntegrityError(
            f"Unable to load definition for {template_id!r}: {error}"
        ) from error
    actual_hash = _source_hash(payload)
    expected_hash = entry.origin.definition_sha256
    if actual_hash != expected_hash:
        raise SourceTemplateIntegrityError(
            f"Source template {template_id!r} hash {actual_hash} does not match {expected_hash}"
        )
    return DashboardDefinition.model_validate(payload)


def build_source_template(template_id: str, target: str) -> DashboardDefinition:
    """Load one source-derived template after enforcing its target and native contracts."""

    entry, _ = _record(template_id)
    platform = EnterpriseVersion.parse(target)
    if platform < entry.minimum_target:
        raise SourceTemplateTargetUnsupported(
            f"Source template {template_id!r} requires Splunk Enterprise "
            f"{entry.minimum_target} or later; received {platform}"
        )
    definition = _definition(template_id).model_copy(deep=True)
    report = validate_dashboard(definition, target=target)
    if not report.is_valid:
        codes = ", ".join(sorted({issue.code for issue in report.issues}))
        raise SourceTemplateTargetUnsupported(
            f"Source template {template_id!r} is invalid for Splunk Enterprise {platform}: {codes}"
        )
    return definition


def build_source_template_bundle(template_id: str, target: str) -> SourceTemplateBundle:
    """Return the imported definition together with its complete provenance contract."""

    entry, _ = _record(template_id)
    return SourceTemplateBundle(
        template=entry,
        definition=build_source_template(template_id, target),
    )
