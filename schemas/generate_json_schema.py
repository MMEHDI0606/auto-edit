"""
Regenerates trace.v1.schema.json and template.v1.schema.json from the
Pydantic models in schemas/models.py.

Run this after any change to models.py:

    python schemas/generate_json_schema.py

Do not hand-edit the .schema.json files - they are build artifacts kept
in version control so that non-Python consumers (the render/ Node worker,
external OTIO tooling, MCP clients that want to validate resource payloads)
have something to point a JSON Schema validator at without needing a
Python runtime. See DESIGN_NOTES.md, "Schema strategy".
"""

from __future__ import annotations

import json
from pathlib import Path

from models import EditTrace, Template  # noqa: E402


def main() -> None:
    out_dir = Path(__file__).parent
    (out_dir / "trace.v1.schema.json").write_text(
        json.dumps(EditTrace.model_json_schema(), indent=2) + "\n"
    )
    (out_dir / "template.v1.schema.json").write_text(
        json.dumps(Template.model_json_schema(), indent=2) + "\n"
    )
    print("Regenerated trace.v1.schema.json and template.v1.schema.json")


if __name__ == "__main__":
    main()
