#!/usr/bin/env python3
"""Import only permissioned CsiSza tile-boundary annotations.

The CsiSza dictionary is not used as an ABCx3 word-validity source. This
importer verifies the reviewed upstream file and retains only entries whose
``_`` marker records a mandatory physical-tile boundary.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from generate_classic_tile_lexicon import parse_marked_boundary_surface


ROOT = Path(__file__).resolve().parent
SOURCE_REPOSITORY = "https://github.com/betuTboy/CsiSza"
SOURCE_COMMIT = "ea50d3ef6dded9c2409014bcfa56a8e8d9994af4"
SOURCE_FILE_SHA256 = "65a39854a0c01bd21ede750f609832d96bb6e4cfb00aba16f158e46f89da63f9"
PERMISSION_DATE = "2026-09-02"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def import_boundaries(source_path: Path, output_path: Path) -> int:
    actual_sha256 = sha256_file(source_path)
    if actual_sha256 != SOURCE_FILE_SHA256:
        raise ValueError(
            f"Unexpected CsiSza dictionary SHA-256: {actual_sha256}; "
            f"expected {SOURCE_FILE_SHA256}"
        )

    annotations: dict[str, str] = {}
    with source_path.open("r", encoding="utf-8-sig") as source:
        for line_number, raw_line in enumerate(source, 1):
            fields = raw_line.strip().split()
            if not fields or "_" not in fields[0]:
                continue
            marked_surface = fields[0].lower()
            surface, _ = parse_marked_boundary_surface(marked_surface)
            if surface in annotations:
                raise ValueError(
                    f"Duplicate CsiSza boundary surface {surface!r} "
                    f"at source line {line_number}"
                )
            annotations[surface] = marked_surface

    lines = [
        "# CsiSza 2.2 physical-tile boundary annotations for ABCx3",
        '# One lowercase marked surface per line; "_" is a mandatory tile boundary.',
        f"# Source: {SOURCE_REPOSITORY}",
        f"# Source commit: {SOURCE_COMMIT}",
        f"# Source file: szotar22a_kat.dic (SHA-256 {SOURCE_FILE_SHA256})",
        "# Annotation author: Attila (GitHub: betuTboy)",
        f"# Written permission for ABCx3 dictionary validation and improvement: {PERMISSION_DATE}",
        "# Policy: boundary evidence only; this file does not grant word validity.",
        "",
        *sorted(annotations.values()),
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return len(annotations)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "csi_sza_classic_tile_boundaries.txt",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    count = import_boundaries(args.source, args.output)
    print(f"Imported {count} CsiSza tile-boundary annotations.")


if __name__ == "__main__":
    main()
