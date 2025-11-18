# Path: core/indexing/scanner.py
# Purpose: Scan folders and collect image file paths with lightweight metadata.
# Layer: core/indexing.
# Details: Provides reusable filesystem scanning for indexing jobs.

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from core.models.domain import ImageRecord

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}


class ImageScanner:
    """Scan filesystem paths for supported image files."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def scan(self) -> List[ImageRecord]:
        """Return a list of discovered images with basic metadata."""

        records: List[ImageRecord] = []
        index = 0
        for path in self._iter_image_files():
            records.append(ImageRecord(id=index, path=path))
            index += 1
        return records

    def _iter_image_files(self) -> Iterable[Path]:
        """Yield image files under the root directory."""

        for path in self.root.rglob("*"):
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                yield path
