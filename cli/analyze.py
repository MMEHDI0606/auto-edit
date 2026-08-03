"""
Phase 1 entry point (see BUILD_ORDER.md Phase 1: "CLI only, no LLM, no
renderer"). This is deliberately the FIRST thing to make real - it proves
ingest -> signal (L0->L1) end to end and prints an Edit Trace JSON, which
is exactly the Phase 1 success gate in RECUT_SPEC.md sec 11.

Not in the original spec's repo layout (sec 13 has no cli/ despite the
build order being explicitly CLI-first) - see DESIGN_NOTES.md "Missing CLI
entrypoint".

Usage (once implemented):
    python -m cli.analyze <path_or_url> [--depth fast|full] [--out trace.json]
"""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="RECUT Phase 1 CLI: source -> Edit Trace JSON")
    parser.add_argument("source", help="local file path or URL")
    parser.add_argument("--out", default="trace.json")
    args = parser.parse_args()
    raise NotImplementedError


if __name__ == "__main__":
    main()
