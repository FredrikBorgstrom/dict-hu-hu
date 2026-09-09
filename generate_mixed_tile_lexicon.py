#!/usr/bin/env python3
"""Derive optional-digraph arrangements from the reviewed Hungarian vocabulary.

Every surface keeps its separate-letter spelling. Reviewed classic digraphs may
independently stay combined or split; morpheme boundaries remain authoritative.
Legacy doubled-digraph aliases that add written characters are not propagated.
No new words, heuristic segmentation, or remote operations are involved.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import itertools
import json
from pathlib import Path
import unicodedata

from generate_classic_tile_lexicon import PLAYABLE_TOKENS as CLASSIC_LOWER_TOKENS

CLASSIC_TOKENS = tuple(token.upper() for token in CLASSIC_LOWER_TOKENS)

ROOT = Path(__file__).resolve().parent
SEED_ROOT = ROOT.parent / "private_seed_wordlists/hungarian_hu_hu_ispell"
PLAYABLE_TOKENS = (*CLASSIC_TOKENS, "X", "Y")
TOKEN_ID = {token: index + 1 for index, token in enumerate(PLAYABLE_TOKENS)}


def normalize(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip()).lower()


def read_words(path: Path) -> set[str]:
    return {normalize(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")}


def read_classic(path: Path) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    with path.open(encoding="utf-8") as source:
        for line in source:
            if not line.strip() or line.startswith("#"):
                continue
            key, surface = line.rstrip("\n").split("\t")
            surface = normalize(surface)
            key_bytes = base64.urlsafe_b64decode(key + "=" * (-len(key) % 4))
            if not key_bytes or any(i < 1 or i > len(CLASSIC_TOKENS) for i in key_bytes):
                raise ValueError("Unknown classic tile identifier")
            tokens = tuple(CLASSIC_TOKENS[i - 1] for i in key_bytes)
            if normalize("".join(tokens)) != surface:
                continue  # Historical contraction aliases are classic-only.
            if surface in result and result[surface] != tokens:
                raise ValueError(f"Conflicting reviewed segmentation for {surface}")
            result[surface] = tokens
    return result


def arrangements(surface: str, classic: tuple[str, ...] | None) -> list[tuple[str, ...]]:
    surface = normalize(surface)
    characters = tuple(surface.upper())
    if not characters or any(c not in TOKEN_ID for c in characters):
        raise ValueError(f"Unsupported Hungarian surface: {surface!r}")
    if classic is None:
        return [characters]
    if normalize("".join(classic)) != surface or any(t not in CLASSIC_TOKENS for t in classic):
        raise ValueError(f"Classic tiles do not spell {surface!r}")
    options = [((token,), tuple(token)) if len(token) > 1 else ((token,),) for token in classic]
    variants = {tuple(itertools.chain.from_iterable(parts)) for parts in itertools.product(*options)}
    variants.add(characters)
    # Combined tiles first, retaining the useful shortest representative for
    # surface-based backend operations. Every arrangement remains searchable.
    return sorted(variants, key=lambda tokens: (len(tokens), tokens))


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_runtime(path: Path, words: set[str], classic: dict[str, tuple[str, ...]]) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = 0
    maximum = 0
    split_surfaces = 0
    excluded = sorted(w for w in words if any(c not in TOKEN_ID for c in w.upper()))
    playable_words = words - set(excluded)
    building_path = path.with_suffix(path.suffix + ".building")
    with building_path.open("w", encoding="utf-8", newline="\n") as destination:
        destination.write("# ABCx3 Hungarian mixed tiles v1: optional reviewed digraphs\n")
        for surface in sorted(playable_words):
            variants = arrangements(surface, classic.get(surface))
            maximum = max(maximum, len(variants))
            split_surfaces += len(variants) > 1
            for tokens in variants:
                if normalize("".join(tokens)) != surface:
                    raise ValueError(f"Tile round-trip mismatch: {surface}")
                key = base64.urlsafe_b64encode(bytes(TOKEN_ID[t] for t in tokens)).decode().rstrip("=")
                destination.write(f"{key}\t{surface}\n")
                entries += 1
    building_path.replace(path)
    return {"surfaceCount": len(playable_words), "entryCount": entries, "optionalDigraphSurfaceCount": split_surfaces,
            "maxArrangementsPerSurface": maximum, "sha256": digest(path), "bytes": path.stat().st_size,
            "roundTripMismatches": 0, "unsupportedSurfaceCount": len(excluded), "unsupportedSurfaces": excluded}


def generate(input_path: Path, classic_path: Path, seed_path: Path, runtime_path: Path,
             seed_runtime_path: Path, audit_path: Path) -> dict:
    words = read_words(input_path)
    seed_words = read_words(seed_path)
    if not seed_words <= words:
        raise ValueError("Seed vocabulary must be a subset of the human dictionary")
    classic = read_classic(classic_path)
    audit = {"schemaVersion": 1, "playableTokens": list(PLAYABLE_TOKENS),
             "inputs": {"surfaceSha256": digest(input_path), "classicSha256": digest(classic_path),
                        "seedSurfaceSha256": digest(seed_path)},
             "main": write_runtime(runtime_path, words, classic),
             "seed": write_runtime(seed_runtime_path, seed_words, classic)}
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "output/hungarian_hu_hu_ispell.txt")
    parser.add_argument("--classic", type=Path, default=ROOT / "output/hungarian_hu_hu_ispell_classic_tiles.tsv")
    parser.add_argument("--seed", type=Path, default=SEED_ROOT / "output/hungarian_hu_hu_ispell_seed.txt")
    parser.add_argument("--runtime", type=Path, default=ROOT / "output/hungarian_hu_hu_ispell_mixed_tiles.tsv")
    parser.add_argument("--seed-runtime", type=Path, default=SEED_ROOT / "output/hungarian_hu_hu_ispell_mixed_tiles_seed.tsv")
    parser.add_argument("--audit", type=Path, default=ROOT.parent / "artifacts/Hungarian Mixed Tiles/mixed-tiles.audit.json")
    args = parser.parse_args()
    print(json.dumps(generate(args.input, args.classic, args.seed, args.runtime, args.seed_runtime, args.audit), indent=2))


if __name__ == "__main__":
    main()
