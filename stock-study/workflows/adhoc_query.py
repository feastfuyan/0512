"""Ad-hoc query entry — CEO / 陈夏童 chat interface to Agent-XT-Reasoner.

Usage:
    python -m workflows.adhoc_query "Why did PLS drop 30% in Q2?"
"""

from __future__ import annotations

import argparse
import sys


def adhoc(query: str) -> dict:
    """TODO: full ad-hoc loop with multi-turn (currently single-shot).

    For S0/S1, this just routes the question to Agent-XT-Reasoner using a
    minimal NarrativeTask shim. Multi-turn comes in S3.
    """
    raise NotImplementedError("TODO: ad-hoc multi-turn loop — S3 deliverable for 陈夏童")


def _cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query", help="natural-language question")
    args = parser.parse_args()
    try:
        result = adhoc(args.query)
        print(result)
    except NotImplementedError as e:
        print(f"not yet wired: {e}")
        sys.exit(2)


if __name__ == "__main__":  # pragma: no cover
    _cli_main()
