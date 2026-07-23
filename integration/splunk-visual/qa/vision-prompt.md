# Dashboard Studio visual QA prompt

Inspect the supplied QA overview and individual dashboard screenshots as test artifacts. The data
is deterministic synthetic data; do not infer production health from it.

Check only these categories: blank, loading, search_error, overlap, clipping, contrast,
wrong_chart, malformed_graph, whitespace, and alignment. For every finding return the dashboard
ID, category, severity, confidence from 0 through 1, a concise summary, a pixel bounding box, and
the matching deterministic evidence ID when one exists. Use `null` for deterministic evidence
when the finding is visual judgment only.

Return JSON conforming to `splunk-vision-qa-report/v1`. Model-only findings are advisory. An error
may gate a build only when a deterministic browser, search-result, or screenshot-diff failure
corroborates it.
