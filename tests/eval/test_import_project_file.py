"""
Unit 0.4 tests.

The unit's own done criteria needs >=2 REAL donated project files
alongside their source videos - blocked the same way real golden-set
video is (see eval/golden/NEEDS_INPUT.md), and not something an agent can
fabricate. What CAN be verified without a real donation: the actual
parsing/classification logic, using synthetic Timeline objects built
programmatically with OpenTimelineIO's own API and round-tripped through
its own adapters - this is real OTIO serialization, not a hand-rolled
fake, so it's a faithful test of the read path even without a real
donated file.
"""

from __future__ import annotations

import json

import opentimelineio as otio
import pytest
from opentimelineio.opentime import RationalTime, TimeRange

from eval.golden.import_project_file import (
    UnsupportedProjectFileError,
    _sniff_adapter_name,
    import_project_file,
)

FPS = 30


def _clip(name: str, duration_frames: int) -> otio.schema.Clip:
    return otio.schema.Clip(
        name=name, source_range=TimeRange(RationalTime(0, FPS), RationalTime(duration_frames, FPS))
    )


def _build_synthetic_timeline() -> otio.schema.Timeline:
    """5 shots on the cut track: hard cut, dissolve, whip-pan-named
    transition, an unrecognized ("Barn Door Wipe") transition, and a gap
    before the final shot - covers every branch of _classify_transition
    plus the gap-skip-with-warning path. One overlay track with a single
    named clip ("HOOK TEXT") for text-layer extraction. One marker for
    candidate_beat_grid_s.
    """
    cut_track = otio.schema.Track(name="V1", kind=otio.schema.TrackKind.Video)

    shot1 = _clip("shot1", 30)  # 0.0 - 1.0s
    shot2 = _clip("shot2", 30)  # 1.0 - 2.0s, hard cut before it
    shot3 = _clip("shot3", 30)  # after a dissolve
    shot4 = _clip("shot4", 30)  # after a whip-pan-named transition
    shot5 = _clip("shot5", 30)  # after an unrecognized transition
    shot6 = _clip("shot6", 30)  # after a gap

    dissolve = otio.schema.Transition(
        name="Cross Dissolve",
        transition_type=otio.schema.TransitionTypes.SMPTE_Dissolve,
        in_offset=RationalTime(5, FPS),
        out_offset=RationalTime(5, FPS),
    )
    whip = otio.schema.Transition(
        name="Whip Pan Left",
        transition_type=otio.schema.TransitionTypes.Custom,
        in_offset=RationalTime(3, FPS),
        out_offset=RationalTime(3, FPS),
    )
    unrecognized = otio.schema.Transition(
        name="Barn Door Wipe",
        transition_type=otio.schema.TransitionTypes.Custom,
        in_offset=RationalTime(3, FPS),
        out_offset=RationalTime(3, FPS),
    )
    gap = otio.schema.Gap(source_range=TimeRange(RationalTime(0, FPS), RationalTime(15, FPS)))

    cut_track.append(shot1)
    cut_track.append(shot2)
    cut_track.append(dissolve)
    cut_track.append(shot3)
    cut_track.append(whip)
    cut_track.append(shot4)
    cut_track.append(unrecognized)
    cut_track.append(shot5)
    cut_track.append(gap)
    cut_track.append(shot6)

    marker = otio.schema.Marker(name="beat", marked_range=TimeRange(RationalTime(30, FPS), RationalTime(0, FPS)))
    shot2.markers.append(marker)

    overlay_track = otio.schema.Track(name="Overlay", kind=otio.schema.TrackKind.Video)
    overlay_track.append(otio.schema.Gap(source_range=TimeRange(RationalTime(0, FPS), RationalTime(30, FPS))))
    overlay_track.append(_clip("HOOK TEXT", 30))

    return otio.schema.Timeline(name="synthetic", tracks=[cut_track, overlay_track])


@pytest.fixture()
def synthetic_otio_file(tmp_path):
    timeline = _build_synthetic_timeline()
    path = tmp_path / "synthetic.otio"
    otio.adapters.write_to_file(timeline, str(path), adapter_name="otio_json")
    return path


def test_sniff_adapter_name_by_extension_for_otio(synthetic_otio_file) -> None:
    assert _sniff_adapter_name(synthetic_otio_file) == "otio_json"


def test_sniff_adapter_name_by_root_element_for_xmeml(tmp_path) -> None:
    path = tmp_path / "premiere_export.xml"  # deliberately ambiguous extension, per Unit 0.4's own point
    path.write_text('<?xml version="1.0"?>\n<xmeml version="4"></xmeml>')
    assert _sniff_adapter_name(path) == "fcp_xml"


def test_sniff_adapter_name_by_root_element_for_fcpxml(tmp_path) -> None:
    path = tmp_path / "export.xml"
    path.write_text('<?xml version="1.0"?>\n<fcpxml version="1.10"></fcpxml>')
    assert _sniff_adapter_name(path) == "fcpx_xml"


def test_sniff_adapter_name_rejects_unrecognized_format(tmp_path) -> None:
    path = tmp_path / "project.capcut"
    path.write_text("not a recognized project file format")
    with pytest.raises(UnsupportedProjectFileError):
        _sniff_adapter_name(path)


def test_import_project_file_extracts_correct_cut_count_and_timing(synthetic_otio_file, tmp_path) -> None:
    golden_dir = tmp_path / "golden"
    annotations_path = import_project_file(synthetic_otio_file, video_id="synthetic_video", golden_dir=golden_dir)

    annotations = json.loads(annotations_path.read_text())
    cuts = annotations["cuts"]

    # 6 shots -> 5 boundaries (the gap before shot6 is skipped, not a cut)
    assert len(cuts) == 5
    # First boundary (shot1 -> shot2) is a hard cut at exactly 1.0s.
    assert cuts[0]["t"] == pytest.approx(1.0, abs=0.01)
    assert cuts[0]["type"] == "cut"
    assert cuts[0]["type_confidence"] == "exact"
    assert cuts[0]["source"] == "project_file"


def test_import_project_file_classifies_all_transition_types_in_order(synthetic_otio_file, tmp_path) -> None:
    annotations_path = import_project_file(synthetic_otio_file, video_id="v1", golden_dir=tmp_path / "golden")
    cuts = json.loads(annotations_path.read_text())["cuts"]

    types = [(c["type"], c["type_confidence"]) for c in cuts]
    assert types == [
        ("cut", "exact"),  # shot1 -> shot2, no transition object
        ("dissolve", "exact"),  # shot2 -> shot3, SMPTE_Dissolve
        ("whip_pan", "heuristic"),  # shot3 -> shot4, "Whip Pan Left"
        ("cut", "fallback_cut"),  # shot4 -> shot5, "Barn Door Wipe" - unrecognized
        ("cut", "exact"),  # shot5 -> shot6, across the (skipped) gap - no transition object either
    ]


def test_import_project_file_warns_on_gap_without_crashing(synthetic_otio_file, tmp_path, capsys) -> None:
    import_project_file(synthetic_otio_file, video_id="v1", golden_dir=tmp_path / "golden")
    captured = capsys.readouterr()
    assert "Gap on cut track" in captured.err


def test_import_project_file_extracts_overlay_text_layer(synthetic_otio_file, tmp_path) -> None:
    annotations_path = import_project_file(synthetic_otio_file, video_id="v1", golden_dir=tmp_path / "golden")
    annotations = json.loads(annotations_path.read_text())

    assert len(annotations["text_layers"]) == 1
    layer = annotations["text_layers"][0]
    assert layer["string"] == "HOOK TEXT"
    assert layer["source"] == "project_file_heuristic"
    assert layer["t_in"] == pytest.approx(1.0, abs=0.01)  # overlay track has a 1.0s gap before the clip


def test_import_project_file_surfaces_markers_as_candidate_beat_grid(synthetic_otio_file, tmp_path) -> None:
    annotations_path = import_project_file(synthetic_otio_file, video_id="v1", golden_dir=tmp_path / "golden")
    annotations = json.loads(annotations_path.read_text())

    assert "candidate_beat_grid_s" in annotations
    assert 1.0 in annotations["candidate_beat_grid_s"]
    # Must NOT be written into beat_grid_s directly - that requires human confirmation against audio.
    assert "beat_grid_s" not in annotations


def test_import_project_file_writes_project_file_ref_not_the_file_itself(synthetic_otio_file, tmp_path) -> None:
    golden_dir = tmp_path / "golden"
    import_project_file(synthetic_otio_file, video_id="v1", golden_dir=golden_dir)

    video_dir = golden_dir / "v1"
    assert (video_dir / "project_file.ref").exists()
    assert not (video_dir / synthetic_otio_file.name).exists()
    ref_text = (video_dir / "project_file.ref").read_text()
    assert synthetic_otio_file.name in ref_text
    assert "otio_json" in ref_text


def test_unsupported_project_file_raises_clear_error(tmp_path) -> None:
    path = tmp_path / "project.capcut"
    path.write_text("not parseable")
    with pytest.raises(UnsupportedProjectFileError):
        import_project_file(path, video_id="v1", golden_dir=tmp_path / "golden")


# --- real-format smoke tests (fcp_xml / fcpx_xml round-trip via OTIO's own write path) ---


def test_fcp_xml_round_trip_smoke(tmp_path) -> None:
    """Not the elaborate multi-transition-type timeline above - just
    confirms the fcp_xml adapter (legacy FCP7/xmeml, what Premiere Pro's
    'Export > Final Cut Pro XML' actually produces) can genuinely
    round-trip a real timeline through OTIO's own write path and this
    module's read path without crashing, with correct cut timing."""
    track = otio.schema.Track(name="V1", kind=otio.schema.TrackKind.Video)
    track.append(_clip("shot1", 30))
    track.append(_clip("shot2", 60))
    timeline = otio.schema.Timeline(name="fcp_test", tracks=[track])

    path = tmp_path / "premiere_export.xml"
    otio.adapters.write_to_file(timeline, str(path), adapter_name="fcp_xml")

    annotations_path = import_project_file(path, video_id="fcp_test", golden_dir=tmp_path / "golden")
    cuts = json.loads(annotations_path.read_text())["cuts"]
    assert len(cuts) == 1
    assert cuts[0]["t"] == pytest.approx(1.0, abs=0.01)


def test_fcpx_xml_round_trip_smoke(tmp_path) -> None:
    """Same smoke test for the modern Apple FCPXML adapter - flagged
    best-effort per Unit 0.4 (community-maintained, less consistently
    updated against Apple's DTD than the legacy fcp_xml path), so this is
    deliberately a minimal round-trip check, not the full transition-type
    matrix."""
    track = otio.schema.Track(name="V1", kind=otio.schema.TrackKind.Video)
    track.append(_clip("shot1", 30))
    track.append(_clip("shot2", 60))
    timeline = otio.schema.Timeline(name="fcpx_test", tracks=[track])

    path = tmp_path / "export.fcpxml"
    otio.adapters.write_to_file(timeline, str(path), adapter_name="fcpx_xml")

    annotations_path = import_project_file(path, video_id="fcpx_test", golden_dir=tmp_path / "golden")
    cuts = json.loads(annotations_path.read_text())["cuts"]
    assert len(cuts) == 1
    assert cuts[0]["t"] == pytest.approx(1.0, abs=0.01)
