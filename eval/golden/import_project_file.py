"""
Unit 0.4 - project-file ground-truth importer (OTIO-based).

Golden-set ACQUISITION tool, not a pipeline component - never runs in
production, only ahead of eval/run.py / as an alternative on-ramp into
Unit 0.3's annotation format. Given an editor project file (.fcpxml from
Final Cut Pro X, the legacy FCP7 XML interchange format Premiere Pro
exports via File > Export > Final Cut Pro XML, or native .otio) plus its
matching source video, produces a draft eval/golden/<video_id>/annotations.json
with hand-scrubbing-free cut timestamps and cut/transition types, and -
best-effort only, not a done criterion - text/graphic-layer timing if the
project has a dedicated overlay track.

Explicitly out of scope: CapCut project files (proprietary, undocumented,
no OTIO adapter exists) and After Effects .aep (proprietary binary
container; text timing is frequently expression-driven rather than
keyframed, so even a successful parse often can't recover "exact" text
timing). See DESIGN_NOTES.md sec 16 for the full rationale.

This module does NOT replace video acquisition - the donor must still
supply the actual video (source.ref); a project file only replaces the
SCRUBBING labor, not the footage requirement. Output still needs a human
"second look-through" against the video before it counts (Unit 0.3's
done-criterion, unchanged).

DEPENDENCY CORRECTION vs the original plan: "opentimelineio-contrib" does
not exist on PyPI under any name (verified directly). fcp_xml/fcpx_xml/AAF
are each separate plugin packages - otio-fcp-adapter, otio-fcpx-xml-adapter,
otio-aaf-adapter - none of which ship in opentimelineio core (core ships
only otio_json/otioz/otiod). All three self-register into
otio.adapters.available_adapter_names() on import via OTIO's plugin
manifest mechanism - no explicit registration code needed here, just the
pyproject.toml `golden-import` extra installed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import opentimelineio as otio

# Real API note (differs from an earlier assumption): OTIO 0.18's Clip has
# no transformed_time_range(track) form - that method takes
# (time_range, to_item) for cross-item time conversion, not a direct
# "where does this land in my parent" query. range_in_parent() (or
# equivalently track.range_of_child(clip)) is the actual API for that.
COVERAGE_THRESHOLD = 0.9  # a video track covering >=90% of timeline duration is the cut/shot track

_TRANSITION_KEYWORD_MAP: list[tuple[tuple[str, ...], str]] = [
    (("whip",), "whip_pan"),
    (("flash", "flare", "strobe"), "flash"),
    (("zoom", "cross zoom", "push"), "zoom"),
]


class UnsupportedProjectFileError(Exception):
    """CapCut/.aep or anything else with no real OTIO read path - raised
    rather than attempted, per this module's explicit out-of-scope list."""


def _sniff_adapter_name(path: Path) -> str:
    """Sniffs the file's actual format rather than trusting its extension -
    editors name these files inconsistently (a Premiere "Final Cut Pro XML"
    export is still just called something.xml, indistinguishable by
    extension alone from a modern FCPXML export)."""
    suffix = path.suffix.lower()
    if suffix == ".otio":
        return "otio_json"
    if suffix == ".aaf":
        return "AAF"  # otio-aaf-adapter registers under the uppercase name, not "aaf"

    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:4096]
    except OSError as exc:
        raise UnsupportedProjectFileError(f"could not read {path}: {exc}") from exc

    lowered = head.lower()
    if "<fcpxml" in lowered:
        return "fcpx_xml"
    if "<xmeml" in lowered:
        return "fcp_xml"

    raise UnsupportedProjectFileError(
        f"could not determine project-file format for {path} - expected .otio, .aaf, or an XML file "
        "with <fcpxml> (modern Apple Final Cut Pro X) or <xmeml> (legacy FCP7 interchange, what "
        "Premiere Pro's 'Export > Final Cut Pro XML' produces) as its root element. CapCut and "
        "After Effects (.aep) project files are explicitly out of scope - see this module's docstring."
    )


def _read_timeline(path: Path) -> otio.schema.Timeline:
    adapter_name = _sniff_adapter_name(path)
    result = otio.adapters.read_from_file(str(path), adapter_name=adapter_name)
    if isinstance(result, otio.schema.Timeline):
        return result
    # Some adapters (e.g. AAF with multiple top-level compositions) can
    # return a SerializableCollection - take the first timeline in it
    # rather than silently failing on an unexpected type.
    if hasattr(result, "__iter__"):
        for item in result:
            if isinstance(item, otio.schema.Timeline):
                return item
    raise UnsupportedProjectFileError(f"{path} did not parse into a usable Timeline (adapter: {adapter_name})")


def _select_cut_track(timeline: otio.schema.Timeline) -> tuple[otio.schema.Track, list[otio.schema.Track]]:
    """Lowest-indexed video track with near-continuous coverage of the
    timeline duration is the cut/shot track; any other video tracks are
    candidate overlay tracks for text-layer extraction only."""
    video_tracks = list(timeline.video_tracks())
    if not video_tracks:
        raise ValueError("project file has no video tracks")

    total_duration = timeline.duration().value or 1.0
    for track in video_tracks:
        coverage = track.duration().value / total_duration
        if coverage >= COVERAGE_THRESHOLD:
            return track, [t for t in video_tracks if t is not track]

    # Nothing cleared the threshold - fall back to whichever track covers
    # the most, rather than refusing to produce a draft at all.
    best = max(video_tracks, key=lambda t: t.duration().value)
    return best, [t for t in video_tracks if t is not best]


def _classify_transition(transition: otio.schema.Transition | None) -> tuple[str, str]:
    """Returns (recut_transition_type, type_confidence). Priority order per
    Unit 0.4: no Transition object (hard edit) -> cut/exact;
    SMPTE_Dissolve or a raw name containing dissolve/fade -> dissolve/exact;
    a raw name matching a known keyword -> that type/heuristic; anything
    else (wipe, vendor plugin, unrecognized) -> cut/fallback_cut, emitted
    (not dropped) so a human knows to check it."""
    if transition is None:
        return "cut", "exact"

    raw_name = f"{transition.name or ''} {transition.metadata or {}}".lower()

    if transition.transition_type == otio.schema.TransitionTypes.SMPTE_Dissolve or any(
        kw in raw_name for kw in ("dissolve", "fade")
    ):
        return "dissolve", "exact"

    for keywords, recut_type in _TRANSITION_KEYWORD_MAP:
        if any(kw in raw_name for kw in keywords):
            return recut_type, "heuristic"

    return "cut", "fallback_cut"


def _extract_cuts(cut_track: otio.schema.Track) -> tuple[list[dict], list[str]]:
    """Walks the cut track's children in order. Gaps are skipped with a
    warning (not bridged silently - RECUT's Shot list assumes continuous
    coverage, and a real gap needs a human decision), not treated as data."""
    children = list(cut_track)
    cuts: list[dict] = []
    warnings: list[str] = []
    prev_clip: otio.schema.Clip | None = None

    for i, child in enumerate(children):
        if isinstance(child, otio.schema.Gap):
            gap_duration_s = child.duration().value / (child.duration().rate or 1)
            warnings.append(
                f"Gap on cut track at position {i} (duration ~{gap_duration_s:.2f}s) - skipped, "
                "needs a human decision, not bridged automatically"
            )
            continue

        if isinstance(child, otio.schema.Clip):
            if prev_clip is not None:
                clip_range = cut_track.range_of_child(child)
                t = clip_range.start_time.value / clip_range.start_time.rate
                transition_obj = children[i - 1] if i > 0 and isinstance(children[i - 1], otio.schema.Transition) else None
                recut_type, confidence = _classify_transition(transition_obj)
                cuts.append(
                    {"t": round(t, 3), "type": recut_type, "source": "project_file", "type_confidence": confidence}
                )
            prev_clip = child

    return cuts, warnings


def _extract_text_layers(overlay_tracks: list[otio.schema.Track]) -> list[dict]:
    """Best-effort only, not a done-criterion: any named clip on an overlay
    track is treated as literal on-screen text (common for FCPX title
    clips and Premiere graphic clips named after their content). box/font/
    style are NOT recoverable this way and stay absent."""
    layers = []
    for track in overlay_tracks:
        for child in track:
            if not isinstance(child, otio.schema.Clip):
                continue
            name = (child.name or "").strip()
            if not name:
                continue
            clip_range = track.range_of_child(child)
            t_in = clip_range.start_time.value / clip_range.start_time.rate
            t_out = t_in + clip_range.duration.value / clip_range.duration.rate
            layers.append({"t_in": round(t_in, 3), "t_out": round(t_out, 3), "string": name, "source": "project_file_heuristic"})
    return layers


def _extract_candidate_beat_grid(timeline: otio.schema.Timeline) -> list[float]:
    """Surfaces markers as a CANDIDATE beat grid, never written directly
    into beat_grid_s - a marker could mean chapter mark, note-to-self,
    anything. Only a human confirming against the actual audio should
    promote a candidate into the real beat grid."""
    candidates: set[float] = set()
    for track in timeline.tracks:
        for child in track:
            for marker in getattr(child, "markers", []):
                rng = marker.marked_range
                candidates.add(round(rng.start_time.value / rng.start_time.rate, 3))
    return sorted(candidates)


def import_project_file(project_file_path: Path, *, video_id: str, golden_dir: Path) -> Path:
    """Parses `project_file_path` and writes a draft
    eval/golden/<video_id>/annotations.json (+ project_file.ref). Returns
    the annotations.json path. Raises UnsupportedProjectFileError for a
    format with no real read path (CapCut, .aep, or anything unrecognized)."""
    timeline = _read_timeline(project_file_path)
    cut_track, overlay_tracks = _select_cut_track(timeline)
    cuts, warnings = _extract_cuts(cut_track)
    text_layers = _extract_text_layers(overlay_tracks)
    candidate_beat_grid_s = _extract_candidate_beat_grid(timeline)

    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)

    annotations: dict = {"cuts": cuts, "text_layers": text_layers}
    if candidate_beat_grid_s:
        annotations["candidate_beat_grid_s"] = candidate_beat_grid_s

    video_dir = golden_dir / video_id
    video_dir.mkdir(parents=True, exist_ok=True)

    annotations_path = video_dir / "annotations.json"
    annotations_path.write_text(json.dumps(annotations, indent=2))

    # Never commit the project file itself - see eval/golden/.gitkeep - it
    # routinely embeds the donor's local file paths and OS username.
    (video_dir / "project_file.ref").write_text(
        "Imported from a locally-provided editor project file (not committed to git).\n"
        f"Original filename: {project_file_path.name}\n"
        f"Adapter used: {_sniff_adapter_name(project_file_path)}\n"
    )

    return annotations_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import cut/transition ground truth from an editor project file (Unit 0.4)"
    )
    parser.add_argument("project_file", type=Path, help=".fcpxml / Premiere 'Final Cut Pro XML' / .otio")
    parser.add_argument("video_id", help="matches the eval/golden/<video_id>/ directory this writes into")
    parser.add_argument("--golden-dir", type=Path, default=Path("eval/golden"))
    args = parser.parse_args()

    out_path = import_project_file(args.project_file, video_id=args.video_id, golden_dir=args.golden_dir)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
