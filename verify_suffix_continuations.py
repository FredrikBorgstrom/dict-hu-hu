#!/usr/bin/env python3
"""Audit a suffix-continuation rebuild against its preserved release baseline."""

import argparse
import csv
import gzip
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

from promote_evidence_wordlist import iter_source_mappings, load_sorted_unique_words


def verify(baseline: Path, output: Path, report: Path, dictionary: Path) -> dict:
    name = "hungarian_hu_hu_ispell.txt"
    _, old = load_sorted_unique_words(baseline / name)
    _, new = load_sorted_unique_words(output / name)
    additions, removals = sorted(new - old), sorted(old - new)
    addition_set = frozenset(additions)
    report.mkdir(parents=True, exist_ok=True)
    (report / "added-words.txt").write_text("".join(w + "\n" for w in additions))
    (report / "removed-words.txt").write_text("".join(w + "\n" for w in removals))
    # Run the actual source engine over every new surface, independently of our
    # rule expander. The evidence builder separately applies morphdb.hu policy.
    spell = subprocess.run(
        ["hunspell", "-i", "utf-8", "-d", str(dictionary), "-l"],
        input="".join(w + "\n" for w in additions),
        text=True, capture_output=True, check=True,
    )
    rejected = sorted(set(spell.stdout.splitlines()))
    (report / "source-rejected-additions.txt").write_text("".join(w + "\n" for w in rejected))
    relative = Path("definitions/hu/surface-lemma/v1")
    old_mappings = set(iter_source_mappings(baseline / relative))
    new_mappings = set(iter_source_mappings(output / relative))
    lost_mappings = old_mappings - new_mappings
    unmapped = new - {surface for surface, _ in new_mappings}
    reasons = Counter()
    with gzip.open(output / "evidence.tsv.gz", "rt") as file:
        for row in csv.DictReader(file, delimiter="\t"):
            if row["decision"] == "accept" and row["word"] in addition_set:
                reasons[row["reason"]] += 1
    mode_checks = {}
    for mode in ("classic", "mixed"):
        filename = f"hungarian_hu_hu_ispell_{mode}_tiles.tsv"
        def rows(path):
            return {line for line in path.read_text().splitlines() if line and not line.startswith("#")}
        old_rows, new_rows = rows(baseline / filename), rows(output / filename)
        surfaces = {row.split("\t")[1] for row in new_rows}
        mode_checks[mode] = {
            "surfaces": len(surfaces), "runtime_entries": len(new_rows),
            "added_surfaces": len(surfaces - {row.split("\t")[1] for row in old_rows}),
            "removed_arrangements": len(old_rows - new_rows),
            "reported_form_present": "fájót" in surfaces,
        }
    samples = ["fájó", "fájót", "fájók", "fájókat", "fájóak", "fájónak", "fájón", "fájóan"]
    result = {
        "before": len(old), "after": len(new), "added": len(additions), "removed": len(removals),
        "source_rejected_additions": len(rejected), "lost_definition_mappings": len(lost_mappings),
        "unmapped_surfaces": len(unmapped), "addition_reasons": dict(reasons), "tile_modes": mode_checks,
        "reported_family": {word: {"before": word in old, "after": word in new} for word in samples},
        "sha256": hashlib.sha256((output / name).read_bytes()).hexdigest(),
    }
    (report / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    assert not removals, f"Unexpected removed words: {removals[:10]}"
    assert not rejected, f"Hunspell rejected additions: {rejected[:10]}"
    assert not lost_mappings and not unmapped, "Definition coverage regression"
    assert {"fájót", "fájók", "fájókat", "fájónak"} <= new, "Reported inflection family remains incomplete"
    assert all(not check["removed_arrangements"] and check["reported_form_present"] for check in mode_checks.values())
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "output")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--dictionary", type=Path, default=Path(__file__).resolve().parent / ".cache/sources/hu_HU")
    args = parser.parse_args()
    print(json.dumps(verify(args.baseline, args.output, args.report, args.dictionary), ensure_ascii=False, indent=2))
