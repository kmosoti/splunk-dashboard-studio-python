"""Deterministic SPL1 pipeline construction and structural validation."""

from __future__ import annotations

import re
from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

_COMMAND_PATTERN = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*)(?:\s+(.*))?$", re.DOTALL)

KNOWN_COMMANDS = frozenset(
    {
        "abstract",
        "addcoltotals",
        "addinfo",
        "addtotals",
        "append",
        "appendcols",
        "appendpipe",
        "bin",
        "chart",
        "collect",
        "convert",
        "dedup",
        "eval",
        "eventstats",
        "fields",
        "filldown",
        "fillnull",
        "foreach",
        "format",
        "head",
        "inputlookup",
        "join",
        "lookup",
        "makeresults",
        "map",
        "multikv",
        "mvcombine",
        "mvexpand",
        "nomv",
        "rare",
        "regex",
        "rename",
        "replace",
        "rex",
        "search",
        "sort",
        "spath",
        "stats",
        "streamstats",
        "table",
        "tail",
        "timechart",
        "top",
        "transaction",
        "transpose",
        "tstats",
        "where",
        "xyseries",
    }
)

TRANSFORMING_COMMANDS = frozenset(
    {"chart", "eventstats", "stats", "streamstats", "table", "timechart", "tstats"}
)


class SplSyntaxError(ValueError):
    pass


class SplCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    expression: str = ""
    implicit: bool = False

    @property
    def normalized(self) -> str:
        suffix = " ".join(self.expression.split())
        return f"{self.name.lower()} {suffix}".rstrip()

    def render(self, *, include_implicit_name: bool = False) -> str:
        if self.implicit and not include_implicit_name:
            return self.expression.strip()
        return f"{self.name} {self.expression}".strip()


class SplPipeline(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    commands: tuple[SplCommand, ...] = Field(min_length=1)

    @classmethod
    def parse(cls, query: str) -> SplPipeline:
        return parse_spl(query)

    @classmethod
    def build(cls, first: SplCommand, *commands: SplCommand) -> SplPipeline:
        return cls(commands=(first, *commands))

    def pipe(self, name: str, expression: str = "") -> SplPipeline:
        return SplPipeline(commands=(*self.commands, SplCommand(name=name, expression=expression)))

    def render(self, *, force_leading_pipe: bool = False) -> str:
        rendered: list[str] = []
        for index, command in enumerate(self.commands):
            text = command.render()
            if index == 0 and not force_leading_pipe:
                rendered.append(text)
            else:
                rendered.append(f"| {text}")
        return " ".join(rendered)


def _split_commands(query: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    stack: list[str] = []
    quote: str | None = None
    escaped = False
    pairs = {")": "(", "]": "[", "}": "{"}

    for character in query:
        if escaped:
            current.append(character)
            escaped = False
            continue
        if character == "\\" and quote is not None:
            current.append(character)
            escaped = True
            continue
        if quote is not None:
            current.append(character)
            if character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            quote = character
            current.append(character)
            continue
        if character in "([{":
            stack.append(character)
            current.append(character)
            continue
        if character in ")]}":
            if not stack or stack.pop() != pairs[character]:
                raise SplSyntaxError(f"Unmatched closing delimiter {character!r}")
            current.append(character)
            continue
        if character == "|" and not stack:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(character)

    if quote is not None:
        raise SplSyntaxError("Unterminated SPL string literal")
    if stack:
        raise SplSyntaxError(f"Unclosed SPL delimiter {stack[-1]!r}")
    parts.append("".join(current).strip())
    return parts


def parse_spl(query: str) -> SplPipeline:
    query = query.strip()
    if not query:
        raise SplSyntaxError("SPL query must not be empty")
    segments = _split_commands(query)
    if query.startswith("|") and segments and not segments[0]:
        segments = segments[1:]
    if not segments or any(not segment for segment in segments):
        raise SplSyntaxError("SPL query contains an empty pipeline command")

    commands: list[SplCommand] = []
    for index, segment in enumerate(segments):
        first_token = segment.split(maxsplit=1)[0]
        if index == 0 and (
            "=" in first_token
            or first_token.startswith(("$", "`", "("))
            or first_token.lower() not in KNOWN_COMMANDS
        ):
            commands.append(SplCommand(name="search", expression=segment, implicit=True))
            continue
        match = _COMMAND_PATTERN.fullmatch(segment)
        if match is None:
            raise SplSyntaxError(f"Invalid SPL command segment {segment!r}")
        commands.append(
            SplCommand(name=match.group(1).lower(), expression=(match.group(2) or "").strip())
        )
    return SplPipeline(commands=tuple(commands))


def longest_common_prefix(pipelines: Iterable[SplPipeline]) -> tuple[SplCommand, ...]:
    command_sets = [pipeline.commands for pipeline in pipelines]
    if not command_sets:
        return ()
    prefix: list[SplCommand] = []
    for commands in zip(*command_sets, strict=False):
        normalized = {command.normalized for command in commands}
        if len(normalized) != 1:
            break
        prefix.append(commands[0])
    return tuple(prefix)
