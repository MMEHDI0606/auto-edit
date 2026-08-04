"""
Unit 2.4 done criteria: render/interface.py's contract is confirmed by
using it - get_engine() resolves each known engine name to the right
class and rejects an unknown one, rather than silently returning
something wrong or None.
"""

from __future__ import annotations

import pytest

from render.interface import RenderEngine, get_engine


def test_get_engine_ffmpeg() -> None:
    engine = get_engine("ffmpeg")
    assert isinstance(engine, RenderEngine)
    assert engine.name == "ffmpeg"


def test_get_engine_remotion() -> None:
    engine = get_engine("remotion")
    assert engine.name == "remotion"


def test_get_engine_revideo() -> None:
    engine = get_engine("revideo")
    assert engine.name == "revideo"


def test_get_engine_unknown_name_raises() -> None:
    with pytest.raises(ValueError, match="Unknown render engine"):
        get_engine("not_a_real_engine")
