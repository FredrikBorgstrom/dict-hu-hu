#!/usr/bin/env python3
"""Verify plural possessions, their admission evidence and release retention."""

import argparse
import csv
import gzip
import json
from pathlib import Path

from verify_suffix_continuations import verify
from verify_possessive_inflections import EXCLUDED, REQUIRED, DERIVED_FAMILIES


PLURAL_FAMILIES = {
    "rügy": "rügyeim rügyeid rügyei rügyeink rügyeitek rügyeik rügyeiket rügyeiknek".split(),
    "füge": "fügéim fügéid fügéi fügéink fügéitek fügéik".split(),
    "könyv": "könyveim könyveid könyvei könyveink könyveitek könyveik".split(),
    "gyík": "gyíkjaim gyíkjaid gyíkjai gyíkjaink gyíkjaitok gyíkjaik".split(),
    "szörfös": "szörföseim szörföseid szörfösei szörföseik".split(),
    "táncos": "táncosaim táncosaid táncosai táncosaink táncosaik".split(),
}
ADMISSION_REASONS = {
    "cross_analyzer_possessive_of_accepted_noun",
    "cross_analyzer_possessive_of_accepted_derived_word",
}


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=root / "output")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.baseline, args.output, args.report, root / ".cache/sources/hu_HU")
    additions = frozenset((args.report / "added-words.txt").read_text().splitlines())
    required = REQUIRED | frozenset(w for family in (*DERIVED_FAMILIES.values(), *PLURAL_FAMILIES.values()) for w in family)
    modes = {}
    for name in ("hungarian_hu_hu_ispell.txt", "hungarian_hu_hu_ispell_classic_tiles.tsv",
                 "hungarian_hu_hu_ispell_mixed_tiles.tsv"):
        with (args.output / name).open() as source:
            words = {line.rstrip("\n").split("\t")[-1] for line in source
                     if line.strip() and not line.startswith("#")}
        assert not required - words, f"{name}: missing {sorted(required - words)}"
        assert not EXCLUDED & words, f"{name}: reintroduced {sorted(EXCLUDED & words)}"
        modes[name] = {"required_forms": len(required), "excluded_controls": len(EXCLUDED)}
    with gzip.open(args.output / "ordinary-possessive-evidence.tsv.gz", "rt") as f:
        ordinary = {row["surface"]: row["accepted_noun_lemmas"].split(",")
                    for row in csv.DictReader(f, delimiter="\t") if row["surface"] in additions}
    with gzip.open(args.output / "derived-possessive-evidence.tsv.gz", "rt") as f:
        derived = {row["surface"] for row in csv.DictReader(f, delimiter="\t")}
    proven = set()
    reported = {}
    with gzip.open(args.output / "evidence.tsv.gz", "rt") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            word = row["word"]
            if word in required:
                reported[word] = row
            if word not in additions:
                continue
            assert row["decision"] == "accept" and row["reason"] in ADMISSION_REASONS, row
            assert row["morphdb_recognized"] == row["morphdb_nonproper"] == "1", row
            if row["reason"] == "cross_analyzer_possessive_of_accepted_noun":
                assert set(ordinary.get(word, ())) & set(row["ordinary_possessive_lemmas"].split(",")), row
            else:
                assert word in derived, row
            proven.add(word)
    assert proven == additions, "Missing admission evidence for new surfaces"
    assert "rügyeik" in additions and "rügy" in ordinary["rügyeik"]
    result.update(plural_families=PLURAL_FAMILIES, mode_checks=modes,
                  additions_with_matching_source_proof=len(proven), reported_evidence=reported)
    (args.report / "plural-possessive-verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "reported_evidence"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
