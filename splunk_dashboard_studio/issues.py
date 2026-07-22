"""Stable, machine-readable validation result models."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from splunk_dashboard_studio.version import TargetPlatform


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class IssueOrigin(StrEnum):
    PYDANTIC = "pydantic"
    COMPATIBILITY = "compatibility"
    REFERENCE = "reference"
    LAYOUT = "layout"
    SPL = "spl"
    DOS = "dos"
    SEARCH_GRAPH = "search_graph"
    NPM_ENGINE = "npm_engine"


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    path: str
    message: str
    severity: Severity = Severity.ERROR
    origin: IssueOrigin
    feature: str | None = None
    required_version: str | None = None
    context: dict[str, JsonValue] = Field(default_factory=dict)


class ValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["valid", "invalid"]
    target: TargetPlatform
    profile: str | None = None
    issues: tuple[ValidationIssue, ...] = ()
    stats: dict[str, int] = Field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return self.status == "valid"

    @classmethod
    def from_issues(
        cls,
        *,
        target: TargetPlatform,
        issues: list[ValidationIssue],
        profile: str | None = None,
        stats: dict[str, int] | None = None,
    ) -> ValidationReport:
        invalid = any(issue.severity == Severity.ERROR for issue in issues)
        return cls(
            status="invalid" if invalid else "valid",
            target=target,
            profile=profile,
            issues=tuple(issues),
            stats=stats or {},
        )
