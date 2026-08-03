"""
Shared type aliases and small value objects used across module boundaries
that do NOT belong in schemas/models.py (those are the persisted/versioned
contracts; this file is for internal plumbing types that can change freely).
"""

from __future__ import annotations

from typing import NewType

JobId = NewType("JobId", str)
AssetId = NewType("AssetId", str)
TemplateId = NewType("TemplateId", str)
BindingId = NewType("BindingId", str)
ContentHash = NewType("ContentHash", str)  # SHA256 of normalized video, see ingest/cache.py
