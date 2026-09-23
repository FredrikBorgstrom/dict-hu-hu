#!/usr/bin/env python3
"""Verify a possessive release, including source validity and baseline retention."""

import argparse
import csv
import gzip
import json
from pathlib import Path

from verify_suffix_continuations import verify


REQUIRED = frozenset("""
fügém fügéd fügéje fügénk fügétek fügéjük fügéteket
almám almád almája almánk almátok almájuk
könyvem könyved könyve könyvünk könyvetek könyvük
házam házad háza házunk házatok házuk
kezetek vizetek lovatok
""".split())
EXCLUDED = frozenset("mii miibe lucaiké büróira exkor cm kg szja tsz uv cöcögd".split())


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=root / "output")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.baseline, args.output, args.report, root / ".cache/sources/hu_HU")
    modes = {}
    for name in ("hungarian_hu_hu_ispell.txt", "hungarian_hu_hu_ispell_classic_tiles.tsv",
                 "hungarian_hu_hu_ispell_mixed_tiles.tsv"):
        with (args.output / name).open() as source:
            words = {line.rstrip("\n").split("\t")[-1] for line in source
                     if line.strip() and not line.startswith("#")}
        missing = sorted(REQUIRED - words)
        unexpected = sorted(EXCLUDED & words)
        assert not missing, f"{name}: missing ordinary possessives {missing}"
        assert not unexpected, f"{name}: excluded forms reintroduced {unexpected}"
        modes[name] = {"required_possessives": len(REQUIRED), "excluded_controls": len(EXCLUDED)}
    with gzip.open(args.output / "evidence.tsv.gz", "rt") as source:
        samples = {row["word"]: row for row in csv.DictReader(source, delimiter="\t") if row["word"] in REQUIRED}
    for word in ("fügétek", "fügéd", "almátok", "könyvetek"):
        assert samples[word]["reason"] == "cross_analyzer_possessive_of_accepted_noun", samples[word]
    result["possessive_checks"] = modes
    result["possessive_evidence"] = samples
    (args.report / "possessive-verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "possessive_evidence"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
