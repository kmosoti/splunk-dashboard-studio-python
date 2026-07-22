"""Run every native compatibility-corpus expectation."""

from __future__ import annotations

import json

from splunk_dashboard_studio.corpus import generate_corpus
from splunk_dashboard_studio.validation import validate_dashboard

TARGETS = ("9.4.3", "10.0.0", "10.2.0", "10.4.0")


def main() -> int:
    failures: list[dict[str, str]] = []
    checked = 0
    for target in TARGETS:
        for case in generate_corpus(target):
            checked += 1
            actual = validate_dashboard(case.definition, target=target).status
            if actual != case.expected_native:
                failures.append(
                    {
                        "target": target,
                        "case_id": case.case_id,
                        "expected": case.expected_native,
                        "actual": actual,
                    }
                )
    print(json.dumps({"checked": checked, "failures": failures}, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
