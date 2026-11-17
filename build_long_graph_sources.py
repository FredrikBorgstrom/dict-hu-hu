#!/usr/bin/env python3
"""Build the longer Hungarian graph sources beside the 10-letter lists.

Older apps download the 10-letter text lists in ``output/``. Apps that read
graphs play with graphs built from ``output/*_max<N>.*`` (N = 12 since
17 November 2026). Run this after every vocabulary change, once the
10-letter list, its lemma index and both tile lists are final, so the two
agree: the backend's ``upload_dictionary`` refuses a graph source whose words
up to 10 letters are not exactly the 10-letter list.

All intermediate files go to ``--work-dir``; only the final step writes
``output/``:

1. ``process_words`` with the cap raised: raw candidates and their lemmas.
2. ``build_evidence_wordlist`` with the cap raised.
3. ``promote_evidence_wordlist`` into a copy of ``output/`` whose lemma index
   is the raw one from step 1 (so long forms get their real lemmas).
4. Merge: every word of up to 10 letters comes from ``output/`` unchanged; only
   the accepted 11..N letter words come from the new build. The lemma index
   keeps every short line and adds the long words' lines.
5. Classic and mixed tile lexicons over the merged list and index.
6. Check that both tile lists' short rows equal the 10-letter tile lists,
   then install ``*_max<N>.*`` and the merged lemma index into ``output/``.

Typical run (about 45 minutes, 12 GB of memory):

    python3 build_long_graph_sources.py --work-dir "../artifacts/Long graph sources <date>" --offline
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
TEXT_LIST_MAX = 10
LIST = "hungarian_hu_hu_ispell.txt"
CLASSIC = "hungarian_hu_hu_ispell_classic_tiles.tsv"
MIXED = "hungarian_hu_hu_ispell_mixed_tiles.tsv"
INDEX = Path("definitions/hu/surface-lemma/v1")


def long_name(file_name: str, max_length: int) -> str:
    stem, dot, extension = file_name.rpartition(".")
    return f"{stem}_max{max_length}.{extension}"


def run_stage(script: str, args: list[str], max_length: int, log: Path) -> None:
    """Run one pipeline script with process_words.MAX_WORD_LEN raised."""
    bootstrap = (
        "import os, runpy, sys\n"
        f"sys.path.insert(0, {str(ROOT)!r}); os.chdir({str(ROOT)!r})\n"
        "import process_words\n"
        f"process_words.MAX_WORD_LEN = {max_length}\n"
        f"sys.argv = {[script, *args]!r}\n"
        f"if {script!r} == 'process_words.py': sys.exit(process_words.main())\n"
        f"runpy.run_path({str(ROOT / script)!r}, run_name='__main__')\n"
    )
    print(f"== {script} (max {max_length}) -> {log.name}", flush=True)
    with open(log, "w", encoding="utf-8") as handle:
        result = subprocess.run([sys.executable, "-c", bootstrap], stdout=handle, stderr=subprocess.STDOUT)
    if result.returncode != 0:
        raise SystemExit(f"{script} failed ({result.returncode}); see {log}")


def read_shard(path: Path) -> list[str]:
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [line.rstrip("\n") for line in handle if line.strip()]


def merge_index(current: Path, built: Path, long_words: set[str], out: Path) -> dict:
    """Short lines from the current index unchanged, long lines from the build."""
    out.mkdir(parents=True)
    keys = {p.name[: -len(".tsv.gz")] for d in (current, built) for p in d.glob("*.tsv.gz")}
    current_manifest = json.loads((current / "manifest.json").read_text(encoding="utf-8"))
    shards, surfaces, mappings, missing = {}, 0, 0, set(long_words)
    for key in sorted(keys):
        lines = [line for line in read_shard(current / f"{key}.tsv.gz") if len(line.split("\t", 1)[0]) <= TEXT_LIST_MAX]
        for line in read_shard(built / f"{key}.tsv.gz"):
            surface = line.split("\t", 1)[0]
            if surface in long_words:
                lines.append(line)
                missing.discard(surface)
        if not lines:
            continue
        lines.sort(key=lambda line: line.split("\t", 1)[0])
        path = out / f"{key}.tsv.gz"
        with open(path, "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as packed:
            for line in lines:
                packed.write((line + "\n").encode("utf-8"))
        shards[key] = {"surface_count": len(lines), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        surfaces += len(lines)
        mappings += sum(len(line.split("\t", 1)[1].split(",")) for line in lines)
    if missing:
        raise SystemExit(f"{len(missing)} long words have no lemma mapping, e.g. {sorted(missing)[:5]}")
    manifest = {
        "schema_version": current_manifest["schema_version"],
        "language_code": "hu",
        "format": current_manifest["format"],
        "sharding": current_manifest["sharding"],
        "surface_count": surfaces,
        "mapping_count": mappings,
        "shards": shards,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"surfaces": surfaces, "mappings": mappings, "shards": len(shards)}


def tile_rows(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]


def check_short_tile_rows(text_list: Path, graph_source: Path) -> int:
    short = lambda row: len(row.split("\t", 1)[1]) <= TEXT_LIST_MAX  # noqa: E731
    live = set(tile_rows(text_list))
    built_rows = tile_rows(graph_source)
    built_short = {row for row in built_rows if short(row)}
    if built_short != live:
        raise SystemExit(
            f"{graph_source.name}: short rows differ from {text_list.name} "
            f"({len(live - built_short)} missing, {len(built_short - live)} extra)"
        )
    return len(built_rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--max-length", type=int, default=12)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--morph-workers", type=int, default=12)
    parser.add_argument("--no-install", action="store_true", help="Build and check, but leave output/ unchanged.")
    args = parser.parse_args()
    n = args.max_length
    if n <= TEXT_LIST_MAX:
        parser.error(f"--max-length must exceed {TEXT_LIST_MAX}")
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=False)
    offline = ["--offline"] if args.offline else []

    source, candidate, promoted, final = (work / name for name in ("source", "candidate", "promoted", "final"))
    run_stage("process_words.py", [*offline, "--output-dir", str(source)], n, work / "1 process_words.log")
    # The promoted vocabulary's provenance, as an ordinary rebuild reads it beside the list.
    shutil.copy2(OUTPUT / "evidence.tsv.gz", source / "evidence.tsv.gz")
    run_stage(
        "build_evidence_wordlist.py",
        [*offline, "--source-output-dir", str(source), "--output-dir", str(candidate), "--morph-workers", str(args.morph_workers)],
        n,
        work / "2 evidence.log",
    )
    shutil.copytree(OUTPUT, promoted, ignore=shutil.ignore_patterns("*.dawg", "*_tiles*", "definitions", "*_max*"))
    shutil.copytree(source / "definitions", promoted / "definitions")
    run_stage(
        "promote_evidence_wordlist.py",
        ["--candidate-dir", str(candidate), "--output-dir", str(promoted)],
        n,
        work / "3 promote.log",
    )

    final.mkdir()
    short_words = [w for w in (OUTPUT / LIST).read_text(encoding="utf-8").splitlines() if w]
    if max(len(w) for w in short_words) > TEXT_LIST_MAX:
        raise SystemExit(f"output/{LIST} has words over {TEXT_LIST_MAX} letters")
    long_words = {
        w for w in (promoted / LIST).read_text(encoding="utf-8").splitlines() if TEXT_LIST_MAX < len(w) <= n
    }
    merged = sorted(set(short_words) | long_words)
    (final / long_name(LIST, n)).write_text("\n".join(merged) + "\n", encoding="utf-8")
    index_report = merge_index(OUTPUT / INDEX, promoted / INDEX, long_words, final / INDEX)

    classic, mixed = final / long_name(CLASSIC, n), final / long_name(MIXED, n)
    lemmas = str(final / INDEX)
    run_stage(
        "generate_classic_tile_lexicon.py",
        ["--input", str(final / long_name(LIST, n)), "--runtime", str(classic),
         "--source", str(work / "classic.source.tsv.gz"), "--audit", str(work / "classic.audit.json"),
         "--excluded", str(work / "classic.excluded.tsv.gz"), "--lemmas", lemmas],
        n,
        work / "4 classic.log",
    )
    run_stage(
        "generate_mixed_tile_lexicon.py",
        ["--input", str(final / long_name(LIST, n)), "--classic", str(classic), "--runtime", str(mixed),
         "--seed-runtime", str(work / "mixed-seed-unused.tsv"), "--audit", str(work / "mixed.audit.json"),
         "--lemmas", lemmas],
        n,
        work / "5 mixed.log",
    )
    report = {
        "maxLength": n,
        "shortWords": len(short_words),
        "longWords": len(long_words),
        "words": len(merged),
        "lemmaIndex": index_report,
        "classicRows": check_short_tile_rows(OUTPUT / CLASSIC, classic),
        "mixedRows": check_short_tile_rows(OUTPUT / MIXED, mixed),
        "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (final / long_name(LIST, n), classic, mixed)},
    }
    (work / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))

    if not args.no_install:
        for path in (final / long_name(LIST, n), classic, mixed):
            shutil.copy2(path, OUTPUT / path.name)
        staged = OUTPUT / INDEX.with_name("v1.staged")
        shutil.rmtree(staged, ignore_errors=True)
        shutil.copytree(final / INDEX, staged)
        shutil.rmtree(OUTPUT / INDEX)
        staged.rename(OUTPUT / INDEX)
        print(f"Installed {long_name(LIST, n)}, both tile lists and the merged lemma index into output/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
