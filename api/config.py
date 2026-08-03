"""
API-layer configuration (DB URL, Redis URL, S3/R2 credentials, CORS).
Distinct from common/config.py (pipeline tunables) - this file is
deployment-environment concerns, that file is algorithm tunables. Keep
that split; do not let deployment config leak into common/.
"""

from __future__ import annotations
