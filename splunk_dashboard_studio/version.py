"""Splunk Enterprise product-version contracts."""

from __future__ import annotations

import re
from functools import total_ordering
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, RootModel, field_validator

_VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


@total_ordering
class EnterpriseVersion(RootModel[str]):
    """An exact three-component Splunk Enterprise version."""

    model_config = ConfigDict(frozen=True)

    @field_validator("root")
    @classmethod
    def validate_version(cls, value: str) -> str:
        if not _VERSION_PATTERN.fullmatch(value):
            raise ValueError("Splunk Enterprise versions must use major.minor.patch")
        return value

    @classmethod
    def parse(cls, value: str | EnterpriseVersion) -> EnterpriseVersion:
        if isinstance(value, cls):
            return value
        return cls(root=cast(str, value))

    @property
    def parts(self) -> tuple[int, int, int]:
        major, minor, patch = self.root.split(".")
        return int(major), int(minor), int(patch)

    @property
    def release_line(self) -> tuple[int, int]:
        return self.parts[:2]

    def __str__(self) -> str:
        return self.root

    def __hash__(self) -> int:
        return hash(self.parts)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, EnterpriseVersion):
            return self.parts == other.parts
        if isinstance(other, str):
            try:
                return self.parts == EnterpriseVersion.parse(other).parts
            except ValueError:
                return False
        return False

    def __lt__(self, other: Any) -> bool:
        if isinstance(other, str):
            other = EnterpriseVersion.parse(other)
        if not isinstance(other, EnterpriseVersion):
            return NotImplemented
        return self.parts < other.parts


class TargetPlatform(BaseModel):
    """The product target for generation and validation.

    Cloud is intentionally not a valid product value.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    product: Literal["splunk-enterprise"] = "splunk-enterprise"
    version: EnterpriseVersion

    @field_validator("version", mode="before")
    @classmethod
    def parse_version(cls, value: object) -> object:
        if isinstance(value, str):
            return EnterpriseVersion(root=value)
        return value

    @classmethod
    def enterprise(cls, version: str | EnterpriseVersion) -> TargetPlatform:
        return cls(version=EnterpriseVersion.parse(version))

    def __str__(self) -> str:
        return f"{self.product}@{self.version}"
