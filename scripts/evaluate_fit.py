"""Offline core baseline: python -m scripts.evaluate_fit [--format json]."""

import argparse
import json

from evals.fit import FitSuite, load_suite, markdown_report, run_baseline, summarize


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--reviewed-only", action="store_true")
    args = parser.parse_args(argv)
    suite = load_suite()
    if args.reviewed_only:
        cases = [case for case in suite.cases if case.review.status == "reviewed"]
        if not cases:
            parser.exit(2, "No reviewed fit cases; draft labels cannot establish acceptance.\n")
        suite = FitSuite(
            rubric_version=suite.rubric_version,
            rubric_status=suite.rubric_status,
            profile_hashes=suite.profile_hashes,
            cases=cases,
        )
    results = run_baseline(suite)
    if args.format == "json":
        print(
            json.dumps(
                {
                    "rubric_version": suite.rubric_version,
                    "rubric_status": suite.rubric_status,
                    "summary": summarize(results),
                    "results": [item.model_dump(mode="json") for item in results],
                },
                indent=2,
            )
        )
    else:
        print(markdown_report(suite, results), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
