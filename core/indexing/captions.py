# Path: core/indexing/captions.py
# Purpose: Placeholder for caption and tagging integrations.
# Layer: core/indexing.
# Details: Provides a lightweight stub to be replaced with real captioning models.

from __future__ import annotations

from pathlib import Path
from typing import Optional


class CaptionGenerator:
    """Stub caption generator that returns predictable text."""

    def __init__(self, model_name: str = "stub") -> None:
        self.model_name = model_name

    def generate(self, image_path: Path) -> Optional[str]:
        """Return a deterministic placeholder caption for the given image."""

        if not image_path.exists():
            return None
        return f"Placeholder caption for {image_path.name} via {self.model_name}."
