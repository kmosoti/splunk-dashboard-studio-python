"""Small repeatable benchmark without a benchmark-framework dependency."""

from __future__ import annotations

import json
import statistics
import time

from splunk_dashboard_studio.corpus import generate_corpus
from splunk_dashboard_studio.validation import validate_dashboard


def main(iterations: int = 1_000) -> None:
    definition = generate_corpus("10.2.0")[0].definition
    samples: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        report = validate_dashboard(definition, target="10.2.0")
        samples.append((time.perf_counter_ns() - start) / 1_000_000)
        if not report.is_valid:
            raise RuntimeError(report)
    samples.sort()
    print(
        json.dumps(
            {
                "iterations": iterations,
                "median_ms": statistics.median(samples),
                "p95_ms": samples[int(iterations * 0.95) - 1],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
