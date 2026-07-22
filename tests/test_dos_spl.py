from __future__ import annotations

import pytest

from splunk_dashboard_studio.dos import (
    DosSyntaxError,
    iter_dos_values,
    parse_dos,
    validate_dos_tree,
)
from splunk_dashboard_studio.spl import (
    SplCommand,
    SplPipeline,
    SplSyntaxError,
    longest_common_prefix,
    parse_spl,
)


def test_parse_dos_with_quoted_pipe_and_indexer() -> None:
    expression = parse_dos('> primary | seriesByName("a|b") | lastPoint()[0]')
    assert expression.source == "primary"
    assert expression.stages == ('seriesByName("a|b")', "lastPoint()[0]")


@pytest.mark.parametrize(
    "value",
    [
        "primary | firstPoint()",
        ">",
        "> not valid | firstPoint()",
        "> primary",
        "> primary |",
        "> primary | firstPoint(]",
        '> primary | seriesByName("x)',
        "> primary | invalid stage text",
    ],
)
def test_invalid_dos_is_rejected(value: str) -> None:
    with pytest.raises(DosSyntaxError):
        parse_dos(value)


def test_dos_tree_reports_escaped_json_pointer() -> None:
    value = {"a/b~c": ["> primary no-pipe"]}
    assert list(iter_dos_values(value)) == [("$/a~1b~0c/0", "> primary no-pipe")]
    issues = validate_dos_tree(value)
    assert len(issues) == 1
    assert issues[0].path == "$/a~1b~0c/0"
    assert issues[0].code == "invalid_dos_syntax"


def test_spl_parser_handles_implicit_search_nested_pipes_and_rendering() -> None:
    query = 'index=_internal message="a|b" [ search index=main | head 1 ] | stats count'
    pipeline = parse_spl(query)
    assert pipeline.commands[0].implicit
    assert pipeline.commands[0].name == "search"
    assert pipeline.commands[-1].name == "stats"
    assert pipeline.render() == query


def test_spl_pipeline_builder_is_immutable() -> None:
    base = SplPipeline.build(SplCommand(name="makeresults"))
    completed = base.pipe("eval", "answer=42").pipe("table", "answer")
    assert len(base.commands) == 1
    assert completed.render(force_leading_pipe=True) == (
        "| makeresults | eval answer=42 | table answer"
    )


@pytest.mark.parametrize(
    "query",
    ["", "|", "search x || stats count", "search (x", "search x]", 'search message="x'],
)
def test_invalid_spl_is_rejected(query: str) -> None:
    with pytest.raises(SplSyntaxError):
        parse_spl(query)


def test_longest_common_prefix() -> None:
    first = parse_spl("index=main | stats count by host | head 5")
    second = parse_spl("index=main | stats count by host | sort - count")
    prefix = longest_common_prefix([first, second])
    assert [command.name for command in prefix] == ["search", "stats"]
    assert longest_common_prefix([]) == ()
