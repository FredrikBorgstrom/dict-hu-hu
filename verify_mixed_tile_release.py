#!/usr/bin/env python3
"""Verify a mixed-only correction against frozen published word lists, locally."""
from __future__ import annotations

import argparse
import base64
import itertools
import json
from pathlib import Path

from generate_mixed_tile_lexicon import PLAYABLE_TOKENS, TOKEN_ID, digest


def groups(path: Path):
    def rows():
        previous = ""
        with path.open(encoding="utf-8") as source:
            for line in source:
                if not line.strip() or line.startswith("#"):
                    continue
                key, surface = line.rstrip("\n").split("\t")
                assert surface >= previous, f"Unsorted/repeated surface group in {path}: {surface}"
                previous = surface
                tokens = base64.b64decode(key + "=" * (-len(key) % 4), altchars=b"-_", validate=True)
                assert tokens and all(1 <= token <= len(PLAYABLE_TOKENS) for token in tokens)
                assert base64.urlsafe_b64encode(tokens).decode().rstrip("=") == key
                assert "".join(PLAYABLE_TOKENS[token - 1] for token in tokens).lower() == surface
                yield surface, key
    for surface, entries in itertools.groupby(rows(), key=lambda item: item[0]):
        keys = [key for _, key in entries]
        assert len(keys) == len(set(keys)), f"Duplicate canonical key: {surface}"
        yield surface, set(keys)


def compare(before: Path, after: Path, additions: Path, seed_keys: set[tuple[str, str]] | None = None):
    counts = {"surfaces": 0, "previousArrangements": 0, "arrangements": 0, "addedArrangements": 0,
              "changedSurfaces": 0, "removedSurfaces": 0, "removedArrangements": 0}
    collected = set()
    with additions.open("w", encoding="utf-8") as destination:
        for prior, current in itertools.zip_longest(groups(before), groups(after)):
            assert prior is not None and current is not None, "Surface inventory changed"
            surface, keys = current
            assert surface == prior[0], f"Surface inventory changed: {prior[0]} / {surface}"
            assert prior[1] <= keys, f"Lost arrangements: {surface}"
            new_keys = keys - prior[1]
            counts["surfaces"] += 1
            counts["previousArrangements"] += len(prior[1])
            counts["arrangements"] += len(keys)
            counts["addedArrangements"] += len(new_keys)
            counts["changedSurfaces"] += bool(new_keys)
            for key in sorted(new_keys):
                destination.write(f"{key}\t{surface}\n")
            if seed_keys is None:
                collected.update((surface, key) for key in keys)
            else:
                seed_keys.difference_update((surface, key) for key in keys)
    counts.update(sha256=digest(after), bytes=after.stat().st_size)
    return counts, collected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    assert not audit["segmentation"]["unresolved"]
    assert audit["playableTokens"] == list(PLAYABLE_TOKENS)
    seed_name = "hungarian_hu_hu_ispell_mixed_tiles_seed.tsv"
    main_name = "hungarian_hu_hu_ispell_mixed_tiles.tsv"
    seed, seed_keys = compare(args.baseline / seed_name, args.candidate / seed_name,
                              args.report.parent / "seed-added-arrangements.tsv")
    for tokens in [("SZ", "E", "X"), ("S", "Z", "E", "X")]:
        key = base64.urlsafe_b64encode(bytes(TOKEN_ID[token] for token in tokens)).decode().rstrip("=")
        assert ("szex", key) in seed_keys, f"Missing regression arrangement in seed: {tokens}"
    main_result, _ = compare(args.baseline / main_name, args.candidate / main_name,
                             args.report.parent / "main-added-arrangements.tsv", seed_keys)
    assert not seed_keys, "Seed arrangements must be a subset of human arrangements"
    for name, result in [("main", main_result), ("seed", seed)]:
        assert result["sha256"] == audit[name]["sha256"]
        assert result["surfaces"] == audit[name]["surfaceCount"]
        assert result["arrangements"] == audit[name]["entryCount"]
    report = {"main": main_result, "seed": seed, "seedSubsetVerified": True,
              "allKeysRoundTrip": True, "uniqueKeys": True, "unresolved": 0,
              "reviewedSurfaceCount": audit["segmentation"]["reviewedSurfaceCount"],
              "resolutionCounts": audit["segmentation"]["resolutionCounts"]}
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
