#!/usr/bin/env python3
"""Promote the evidence-scored Hungarian list and its lemma artifacts.

The evidence build starts from the ordinary Magyar Ispell output, so most
accepted surfaces already have a source-derived lemma mapping.  This promotion
step preserves every existing mapping for retained surfaces, maps newly
discovered external-compound inflections to their independently confirmed
headwords, and self-maps only the remaining new headwords before replacing the
active word list, lemma index, and audit together.
"""

from __future__ import annotations

import argparse
import copy
import csv
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from process_words import _write_lemma_index


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CANDIDATE_DIR = SCRIPT_DIR / "candidate"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output"
CANDIDATE_FILE_NAME = "hungarian_hu_hu_evidence_candidate.txt"
ACTIVE_FILE_NAME = "hungarian_hu_hu_ispell.txt"
LEMMA_RELATIVE_PATH = Path("definitions/hu/surface-lemma/v1")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_sorted_unique_words(path: Path) -> tuple[list[str], frozenset[str]]:
    words = path.read_text(encoding="utf-8").splitlines()
    if not words:
        raise ValueError(f"Candidate is empty: {path}")
    if any(not word for word in words):
        raise ValueError(f"Candidate contains an empty surface: {path}")
    if words != sorted(set(words)):
        raise ValueError(f"Candidate must be sorted and unique: {path}")
    return words, frozenset(words)


def iter_source_mappings(index_dir: Path):
    manifest_path = index_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing source lemma manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for shard_path in sorted(index_dir.glob("*.tsv.gz")):
        shard_key = shard_path.name.removesuffix(".tsv.gz")
        if manifest["shards"].get(shard_key, {}).get("sha256") != sha256_file(shard_path):
            raise ValueError(f"Source lemma shard checksum mismatch: {shard_path}")
        with gzip.open(shard_path, "rt", encoding="utf-8") as source:
            for line in source:
                surface, separator, lemmas = line.rstrip("\n").partition("\t")
                if not separator or not surface or not lemmas:
                    raise ValueError(f"Malformed lemma row in {shard_path}: {line!r}")
                for lemma in lemmas.split(","):
                    if lemma:
                        yield surface, lemma


def load_external_inflection_mappings(
    evidence_path: Path,
    candidate_words: frozenset[str],
) -> dict[str, tuple[str, ...]]:
    """Load confirmed external-headword lemma mappings from build evidence."""
    mappings: dict[str, tuple[str, ...]] = {}
    with gzip.open(evidence_path, "rt", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source, delimiter="\t")
        if reader.fieldnames is None or "external_headword_lemmas" not in reader.fieldnames:
            raise ValueError(
                f"Evidence lacks external_headword_lemmas: {evidence_path}"
            )
        for row in reader:
            surface = row.get("word", "")
            if row.get("decision") != "accept" or surface not in candidate_words:
                continue
            lemmas = tuple(
                sorted(filter(None, (row.get("reviewed_lemmas", "") or row.get("external_headword_lemmas", "")).split(",")))
            )
            if lemmas:
                mappings[surface] = lemmas
    return mappings


def build_candidate_lemma_index(
    candidate_path: Path,
    evidence_path: Path,
    source_index_dir: Path,
    target_index_dir: Path,
    retention_index_dir: Path | None = None,
) -> tuple[dict, int, int]:
    words, candidate_words = load_sorted_unique_words(candidate_path)
    external_inflection_mappings = load_external_inflection_mappings(
        evidence_path, candidate_words
    )
    target_index_dir.parent.mkdir(parents=True, exist_ok=True)
    work_dir = Path(
        tempfile.mkdtemp(prefix=".evidence-lemma-promotion.", dir=target_index_dir.parent)
    )
    raw_mapping_path = work_dir / "mappings.unsorted.tsv"
    sorted_mapping_path = work_dir / "mappings.sorted.tsv"
    mapped_surfaces: set[str] = set()
    external_mapping_count = 0
    self_mapping_count = 0
    try:
        with raw_mapping_path.open("w", encoding="utf-8", newline="\n") as output:
            for surface, lemma in iter_source_mappings(source_index_dir):
                if surface not in candidate_words:
                    continue
                output.write(f"{surface}\t{lemma}\n")
                mapped_surfaces.add(surface)

            if retention_index_dir is not None:
                missing_before_recovery = candidate_words - mapped_surfaces
                for surface, lemma in iter_source_mappings(retention_index_dir):
                    if surface in missing_before_recovery:
                        output.write(f"{surface}\t{lemma}\n")
                        mapped_surfaces.add(surface)

            missing_surfaces = [
                surface for surface in words if surface not in mapped_surfaces
            ]
            for surface in missing_surfaces:
                external_lemmas = external_inflection_mappings.get(surface, ())
                if external_lemmas:
                    for lemma in external_lemmas:
                        output.write(f"{surface}\t{lemma}\n")
                    external_mapping_count += 1
                else:
                    output.write(f"{surface}\t{surface}\n")
                    self_mapping_count += 1

        environment = os.environ.copy()
        environment["LC_ALL"] = "C"
        subprocess.run(
            ["sort", "-u", str(raw_mapping_path), "-o", str(sorted_mapping_path)],
            check=True,
            env=environment,
        )
        manifest = _write_lemma_index(
            str(sorted_mapping_path),
            str(target_index_dir),
            blocked_surfaces=set(),
        )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    if manifest["surface_count"] != len(words):
        raise ValueError(
            "Candidate lemma index does not cover every accepted surface "
            f"({manifest['surface_count']:,} != {len(words):,})"
        )
    return manifest, self_mapping_count, external_mapping_count


def replace_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = target.with_name(f".{target.name}.promoting")
    shutil.copyfile(source, temporary_path)
    os.replace(temporary_path, target)


def replace_directory(source: Path, target: Path) -> None:
    temporary_path = target.with_name(f".{target.name}.promoting")
    shutil.rmtree(temporary_path, ignore_errors=True)
    shutil.copytree(source, temporary_path)
    if target.exists():
        shutil.rmtree(target)
    os.replace(temporary_path, target)


def promote(candidate_dir: Path, output_dir: Path, retention_index_dir: Path | None = None) -> dict:
    candidate_path = candidate_dir / CANDIDATE_FILE_NAME
    candidate_evidence_path = candidate_dir / "evidence.tsv.gz"
    candidate_audit_path = candidate_dir / "audit.json"
    active_path = output_dir / ACTIVE_FILE_NAME
    active_audit_path = output_dir / "audit.json"
    source_index_dir = output_dir / LEMMA_RELATIVE_PATH
    candidate_index_dir = candidate_dir / LEMMA_RELATIVE_PATH

    candidate_audit = json.loads(candidate_audit_path.read_text(encoding="utf-8"))
    actual_sha256 = sha256_file(candidate_path)
    if candidate_audit.get("output_sha256") != actual_sha256:
        raise ValueError(
            "Candidate checksum does not match candidate/audit.json: "
            f"{actual_sha256}"
        )

    manifest, self_mapping_count, external_mapping_count = build_candidate_lemma_index(
        candidate_path,
        candidate_evidence_path,
        source_index_dir,
        candidate_index_dir,
        retention_index_dir,
    )
    word_count = len(candidate_path.read_text(encoding="utf-8").splitlines())
    lemma_summary = {
        "schema_version": manifest["schema_version"],
        "relative_path": LEMMA_RELATIVE_PATH.as_posix(),
        "surface_count": manifest["surface_count"],
        "mapping_count": manifest["mapping_count"],
        "shard_count": len(manifest["shards"]),
        "self_mappings_added_for_unmapped_surfaces": self_mapping_count,
        "external_headword_mappings_added_for_unmapped_surfaces": (
            external_mapping_count
        ),
    }

    promoted_audit = copy.deepcopy(candidate_audit)
    promoted_audit["description"] = (
        "Active conservative evidence-scored Hungarian game word list"
    )
    promoted_audit.setdefault("counts", {})["final_unique_words"] = word_count
    promoted_audit["counts"]["lemma_index_surfaces"] = manifest["surface_count"]
    promoted_audit["counts"]["lemma_index_mappings"] = manifest["mapping_count"]
    promoted_audit["counts"]["lemma_index_shards"] = len(manifest["shards"])
    promoted_audit["lemma_index"] = lemma_summary
    promoted_audit["promotion"] = {
        "candidate_file": CANDIDATE_FILE_NAME,
        "active_file": ACTIVE_FILE_NAME,
        "retained_source_lemma_mappings": True,
        "external_inflections_use_confirmed_headword_lemmas": True,
        "remaining_new_or_previously_unmapped_surfaces_use_self_lemma": True,
    }

    candidate_audit["lemma_index"] = lemma_summary
    candidate_audit_path.write_text(
        json.dumps(candidate_audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    replace_file(candidate_path, active_path)
    # Admission provenance belongs to the promoted vocabulary and must survive
    # a restart or use of a different candidate output directory.
    replace_file(candidate_evidence_path, output_dir / "evidence.tsv.gz")
    replace_directory(candidate_index_dir, source_index_dir)
    temporary_audit_path = active_audit_path.with_name(".audit.json.promoting")
    temporary_audit_path.write_text(
        json.dumps(promoted_audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_audit_path, active_audit_path)
    return promoted_audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-dir", type=Path, default=DEFAULT_CANDIDATE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--retention-lemma-index", type=Path)
    args = parser.parse_args()
    try:
        audit = promote(args.candidate_dir.resolve(), args.output_dir.resolve(), args.retention_lemma_index)
    except (FileNotFoundError, OSError, subprocess.CalledProcessError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    lemma_index = audit["lemma_index"]
    print(
        f"Promoted {audit['counts']['final_unique_words']:,} words with "
        f"{lemma_index['mapping_count']:,} lemma mappings in "
        f"{lemma_index['shard_count']:,} shards."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
