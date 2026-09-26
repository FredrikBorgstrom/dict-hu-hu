#!/usr/bin/env python3
"""Derive optional-digraph arrangements from the reviewed Hungarian vocabulary.

Every surface keeps its separate-letter spelling. Reviewed classic digraphs may
independently stay combined or split; morpheme boundaries remain authoritative.
Legacy doubled-digraph aliases that add written characters are not propagated.
Words absent from classic mode use the same morphology/boundary tokenizer with
the mixed inventory. Unresolved competing analyses fail before output promotion.
No new surface words or remote operations are involved.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import itertools
import json
from pathlib import Path
import unicodedata
from collections import Counter

from generate_classic_tile_lexicon import (
    PLAYABLE_TOKENS as CLASSIC_LOWER_TOKENS, BoundaryIndex, boundaries_for_surface,
    enumerate_candidates, load_ispell_boundary_index, load_lemma_index,
    load_overrides, load_supplemental_boundary_index, merge_boundary_indexes,
    select_candidate,
)

CLASSIC_TOKENS = tuple(token.upper() for token in CLASSIC_LOWER_TOKENS)

ROOT = Path(__file__).resolve().parent
SEED_ROOT = ROOT.parent / "private_seed_wordlists/hungarian_hu_hu_ispell"
PLAYABLE_TOKENS = (*CLASSIC_TOKENS, "X", "Y")
TOKEN_ID = {token: index + 1 for index, token in enumerate(PLAYABLE_TOKENS)}
LOWER_TOKENS = tuple(token.lower() for token in PLAYABLE_TOKENS)
MULTIGRAPHS = tuple(token for token in LOWER_TOKENS if len(token) > 1)
GENERATOR_VERSION = "2.0.0"


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


def arrangements(surface: str, canonical: tuple[str, ...] | None) -> list[tuple[str, ...]]:
    surface = normalize(surface)
    characters = tuple(surface.upper())
    if not characters or any(c not in TOKEN_ID for c in characters):
        raise ValueError(f"Unsupported Hungarian surface: {surface!r}")
    if canonical is None:
        if any(token in surface for token in MULTIGRAPHS):
            raise ValueError(f"Missing canonical segmentation for {surface!r}")
        return [characters]
    if normalize("".join(canonical)) != surface or any(t not in TOKEN_ID for t in canonical):
        raise ValueError(f"Canonical tiles do not spell {surface!r}")
    options = [((token,), tuple(token)) if len(token) > 1 else ((token,),) for token in canonical]
    variants = {tuple(itertools.chain.from_iterable(parts)) for parts in itertools.product(*options)}
    variants.add(characters)
    # Combined tiles first, retaining the useful shortest representative for
    # surface-based backend operations. Every arrangement remains searchable.
    return sorted(variants, key=lambda tokens: (len(tokens), tokens))


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def resolve_segmentation(surface: str, overrides: dict[str, tuple[str, ...]],
                         lemmas: dict[str, tuple[str, ...]], boundaries: BoundaryIndex):
    candidates = enumerate_candidates(surface, LOWER_TOKENS)
    if surface not in overrides and not lemmas.get(surface):
        raise ValueError(f"Missing source lemma evidence for segmentation of {surface!r}")
    selected, reason = select_candidate(
        surface, candidates, overrides, lemmas, boundaries,
        playable_tokens=LOWER_TOKENS, require_unambiguous=True,
    )
    required = boundaries_for_surface(surface, lemmas, boundaries)
    if not selected.boundary_crossings.isdisjoint(required):
        raise ValueError(f"Override crosses a source boundary in {surface!r}")
    return tuple(token.upper() for token in selected.tokens), {
        "surface": surface, "tokens": list(selected.tokens), "resolution": reason,
        "candidateTokenizations": len({candidate.tokens for candidate in candidates}),
        "lemmas": list(lemmas.get(surface, ())), "requiredBoundaries": sorted(required),
    }


def complete_segmentations(words: set[str], classic: dict[str, tuple[str, ...]],
                           lemma_directory: Path, aff_path: Path, dic_path: Path,
                           supplemental_path: Path, mixed_boundary_path: Path,
                           override_path: Path, mixed_override_path: Path):
    missing = sorted(word for word in words if word not in classic
                     and all(c in TOKEN_ID for c in word.upper())
                     and any(token in word for token in MULTIGRAPHS))
    manifest_path = lemma_directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for shard, metadata in manifest["shards"].items():
        if digest(lemma_directory / f"{shard}.tsv.gz") != metadata["sha256"]:
            raise ValueError(f"Lemma shard differs from its source manifest: {shard}")
    lemmas = load_lemma_index(lemma_directory, set(missing))
    lemma_surfaces = {lemma for values in lemmas.values() for lemma in values}
    lemmas.update(load_lemma_index(lemma_directory, lemma_surfaces))
    boundaries = merge_boundary_indexes(
        load_ispell_boundary_index(aff_path, dic_path),
        load_supplemental_boundary_index(supplemental_path),
        load_supplemental_boundary_index(mixed_boundary_path),
    )
    overrides = load_overrides(override_path, LOWER_TOKENS)
    mixed_overrides = load_overrides(mixed_override_path, LOWER_TOKENS)
    for surface, tokens in mixed_overrides.items():
        if surface in overrides and overrides[surface] != tokens:
            raise ValueError(f"Conflicting segmentation overrides for {surface!r}")
        if surface in classic and tuple(token.upper() for token in tokens) != classic[surface]:
            raise ValueError(f"Mixed override changes an existing classic analysis: {surface!r}")
    overrides.update(mixed_overrides)
    resolved, unresolved = [], []
    for surface in missing:
        try:
            canonical, evidence = resolve_segmentation(surface, overrides, lemmas, boundaries)
            classic[surface] = canonical
            resolved.append(evidence)
        except ValueError as error:
            unresolved.append({"surface": surface, "error": str(error)})
    inputs = {name: digest(path) for name, path in {
        "lemmaManifestSha256": manifest_path, "ispellAffSha256": aff_path,
        "ispellDicSha256": dic_path, "supplementalBoundariesSha256": supplemental_path,
        "mixedBoundariesSha256": mixed_boundary_path, "classicOverridesSha256": override_path,
        "mixedOverridesSha256": mixed_override_path,
    }.items()}
    return {"reviewedSurfaceCount": len(missing),
            "resolutionCounts": dict(sorted(Counter(row["resolution"] for row in resolved).items())),
            "resolved": resolved, "unresolved": unresolved}, inputs


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
             seed_runtime_path: Path, audit_path: Path, *,
             lemma_directory: Path = ROOT / "output/definitions/hu/surface-lemma/v1",
             aff_path: Path = ROOT / ".cache/sources/hu_HU.aff",
             dic_path: Path = ROOT / ".cache/sources/hu_HU.dic",
             supplemental_path: Path = ROOT / "csi_sza_classic_tile_boundaries.txt",
             mixed_boundary_path: Path = ROOT / "mixed_tile_boundaries.txt",
             override_path: Path = ROOT / "classic_tile_segmentation_overrides.tsv",
             mixed_override_path: Path = ROOT / "mixed_tile_segmentation_overrides.tsv") -> dict:
    words = read_words(input_path)
    seed_words = read_words(seed_path)
    if not seed_words <= words:
        raise ValueError("Seed vocabulary must be a subset of the human dictionary")
    classic = read_classic(classic_path)
    segmentation, evidence_inputs = complete_segmentations(
        words, classic, lemma_directory, aff_path, dic_path, supplemental_path,
        mixed_boundary_path, override_path, mixed_override_path,
    )
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    if segmentation["unresolved"]:
        failure_path = audit_path.with_suffix(".unresolved.json")
        failure_path.write_text(json.dumps(segmentation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise ValueError(f"Unresolved segmentation; review {failure_path}")
    # Both runtime files and the audit must validate before either active output
    # is replaced. The publication workflow subsequently verifies this manifest.
    targets = (runtime_path, seed_runtime_path, audit_path)
    if len({path.resolve() for path in targets}) != len(targets):
        raise ValueError("Runtime, seed and audit paths must be distinct")
    staged = tuple(path.with_suffix(path.suffix + ".pending") for path in targets)
    audit = {"schemaVersion": 2, "generatorVersion": GENERATOR_VERSION,
             "playableTokens": list(PLAYABLE_TOKENS), "segmentation": segmentation,
             "inputs": {"surfaceSha256": digest(input_path), "classicSha256": digest(classic_path),
                        "seedSurfaceSha256": digest(seed_path), **evidence_inputs}}
    try:
        audit["main"] = write_runtime(staged[0], words, classic)
        audit["seed"] = write_runtime(staged[1], seed_words, classic)
        staged[2].write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for source, target in zip(staged, targets):
            source.replace(target)
    finally:
        for path in staged:
            path.unlink(missing_ok=True)
            path.with_suffix(path.suffix + ".building").unlink(missing_ok=True)
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "output/hungarian_hu_hu_ispell.txt")
    parser.add_argument("--classic", type=Path, default=ROOT / "output/hungarian_hu_hu_ispell_classic_tiles.tsv")
    parser.add_argument("--seed", type=Path, default=SEED_ROOT / "output/hungarian_hu_hu_ispell_seed.txt")
    parser.add_argument("--runtime", type=Path, default=ROOT / "output/hungarian_hu_hu_ispell_mixed_tiles.tsv")
    parser.add_argument("--seed-runtime", type=Path, default=SEED_ROOT / "output/hungarian_hu_hu_ispell_mixed_tiles_seed.tsv")
    parser.add_argument("--audit", type=Path, default=ROOT.parent / "artifacts/Hungarian Mixed Tiles/mixed-tiles.audit.json")
    parser.add_argument("--lemmas", type=Path, default=ROOT / "output/definitions/hu/surface-lemma/v1")
    parser.add_argument("--ispell-aff", type=Path, default=ROOT / ".cache/sources/hu_HU.aff")
    parser.add_argument("--ispell-dic", type=Path, default=ROOT / ".cache/sources/hu_HU.dic")
    parser.add_argument("--supplemental-boundaries", type=Path, default=ROOT / "csi_sza_classic_tile_boundaries.txt")
    parser.add_argument("--mixed-boundaries", type=Path, default=ROOT / "mixed_tile_boundaries.txt")
    parser.add_argument("--overrides", type=Path, default=ROOT / "classic_tile_segmentation_overrides.tsv")
    parser.add_argument("--mixed-overrides", type=Path, default=ROOT / "mixed_tile_segmentation_overrides.tsv")
    args = parser.parse_args()
    audit = generate(args.input, args.classic, args.seed, args.runtime, args.seed_runtime, args.audit,
                     lemma_directory=args.lemmas, aff_path=args.ispell_aff, dic_path=args.ispell_dic,
                     supplemental_path=args.supplemental_boundaries, mixed_boundary_path=args.mixed_boundaries,
                     override_path=args.overrides, mixed_override_path=args.mixed_overrides)
    print(json.dumps({key: value for key, value in audit.items() if key != "segmentation"}, indent=2))


if __name__ == "__main__":
    main()
