# Path: scripts/index_images.py
# Purpose: CLI tool to scan image folders and build embedding indexes.
# Layer: scripts.
# Details: Demonstrates how to wire scanning, embedding, and vector store components together.

from __future__ import annotations

import argparse
from pathlib import Path

from config import AppSettings
from core.embedders.clip_embedder import ClipEmbedder
from core.indexing.index_builder import IndexBuilder
from core.indexing.scanner import ImageScanner
from core.vector_store.faiss_store import FaissStore


def main() -> None:
    """Run indexing over a folder of images."""

    parser = argparse.ArgumentParser(description="Index images for ImgModalDB")
    parser.add_argument("--folder", type=Path, default=Path("storage/images"), help="Folder containing images to index")
    parser.add_argument("--batch-size", type=int, default=8, help="Number of images to embed per batch")
    args = parser.parse_args()

    settings = AppSettings(image_folder=args.folder, batch_size=args.batch_size)

    scanner = ImageScanner(settings.image_folder)
    images = scanner.scan()

    embedder = ClipEmbedder(dim=settings.vector_store.dim)
    vector_store = FaissStore(dim=settings.vector_store.dim)

    index_builder = IndexBuilder(embedder=embedder, vector_store=vector_store, batch_size=settings.batch_size)
    index_builder.build_index(images)

    vector_store.save(str(settings.vector_store.index_path))
    print(f"Indexed {len(images)} images into {settings.vector_store.index_path}")


if __name__ == "__main__":
    main()
