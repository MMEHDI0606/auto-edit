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
import sys
import tempfile
from pathlib import Path

from common.config import load_settings
from common.logging import get_logger
from ingest import cache as cache_mod
from ingest.downloader import UnsupportedSourceError, fetch
from ingest.normalize import normalize, probe
from signals.trace_builder import build_trace

logger = get_logger(__name__)


def _resolve_source(source: str, download_dir: Path) -> Path:
    """URL download is optional/best-effort per the ingest policy - a
    failure here must never look like a fatal crash, since the user could
    just upload the file instead."""
    if source.startswith("http://") or source.startswith("https://"):
        try:
            result = fetch(source, download_dir)
        except UnsupportedSourceError as exc:
            print(
                f"Could not download {source!r}: {exc}\n"
                "Please upload the file directly instead - see the ingest policy in DESIGN_NOTES.md.",
                file=sys.stderr,
            )
            sys.exit(1)
        return result.local_path

    local_path = Path(source)
    if not local_path.exists():
        print(f"File not found: {local_path}", file=sys.stderr)
        sys.exit(1)
    return local_path


def main() -> None:
    parser = argparse.ArgumentParser(description="RECUT Phase 1 CLI: source -> Edit Trace JSON")
    parser.add_argument("source", help="local file path or URL")
    parser.add_argument("--out", default="trace.json")
    args = parser.parse_args()

    settings = load_settings()

    with tempfile.TemporaryDirectory(prefix="recut_cli_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        local_path = _resolve_source(args.source, tmp_path)

        # Cache key here is the AS-PROVIDED source file's own bytes - a
        # Phase 1 CLI convenience for "run it twice, second run is instant,"
        # distinct from ingest/cache.py's canonical hash (of the NORMALIZED
        # video) used for cross-user global dedup once a hosted API exists
        # (Phase 4/5). A source file re-encoded into a different container
        # would miss this cache and just re-normalize - a missed
        # optimization, not a correctness issue, and out of scope here.
        source_hash = cache_mod.hash_file(local_path)
        cached = cache_mod.get(source_hash)
        if cached is not None and cached.trace_path is not None:
            Path(args.out).write_text(cached.trace_path.read_text())
            logger.info("cache_hit", source_hash=source_hash, out=args.out)
            print(f"cache hit - wrote {args.out}", file=sys.stderr)
            return

        norm_result = normalize(
            local_path,
            tmp_path / "normalized",
            fps=settings.normalize_fps,
            width=settings.normalize_width,
            height=settings.normalize_height,
            crf=settings.normalize_crf,
        )
        probe_dict = probe(norm_result.normalized_path)
        trace = build_trace(norm_result.normalized_path, norm_result.wav_path, probe_dict)

        trace_json = trace.model_dump_json(indent=2)

        cache_dir = Path(settings.cache_root) / source_hash
        cache_dir.mkdir(parents=True, exist_ok=True)
        trace_path = cache_dir / "trace.json"
        trace_path.write_text(trace_json)
        cache_mod.put(
            source_hash,
            cache_mod.CacheEntry(
                content_hash=source_hash,
                normalized_video_path=norm_result.normalized_path,
                wav_path=norm_result.wav_path,
                probe_json_path=cache_mod.write_probe_json(source_hash, probe_dict),
                trace_path=trace_path,
            ),
        )

    Path(args.out).write_text(trace_json)
    logger.info("trace_written", source_hash=source_hash, out=args.out)
    print(f"wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
