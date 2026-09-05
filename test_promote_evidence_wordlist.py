import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from process_words import _write_lemma_index
from promote_evidence_wordlist import (
    ACTIVE_FILE_NAME,
    CANDIDATE_FILE_NAME,
    LEMMA_RELATIVE_PATH,
    promote,
    build_candidate_lemma_index,
)


class EvidencePromotionTests(unittest.TestCase):
    def test_recovers_missing_lemma_mappings_without_replacing_current_ones(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = root / "words.txt"
            candidate.write_text("alján\nalma\n", encoding="utf-8")
            evidence = root / "evidence.tsv.gz"
            with gzip.open(evidence, "wt", encoding="utf-8") as out:
                out.write("word\tdecision\texternal_headword_lemmas\n")
            for name, contents in (("current", "alma\talma\n"),
                                   ("prior", "alján\talja\nalma\talm\n")):
                mappings = root / f"{name}.tsv"
                mappings.write_text(contents, encoding="utf-8")
                _write_lemma_index(str(mappings), str(root / name), blocked_surfaces=set())
            manifest, self_count, _ = build_candidate_lemma_index(
                candidate, evidence, root / "current", root / "target", root / "prior"
            )
            self.assertEqual(0, self_count)
            self.assertEqual(2, manifest["mapping_count"])
            rows = []
            for shard in (root / "target").glob("*.tsv.gz"):
                with gzip.open(shard, "rt", encoding="utf-8") as source:
                    rows.extend(source.read().splitlines())
            self.assertEqual(["alján\talja", "alma\talma"], sorted(rows))

    def test_preserves_existing_ambiguity_and_maps_external_inflections(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            candidate_dir = root / "candidate"
            output_dir = root / "output"
            candidate_dir.mkdir()
            output_dir.mkdir()

            candidate_path = candidate_dir / CANDIDATE_FILE_NAME
            candidate_path.write_text(
                "a\nalma\nújszó\nőzgidák\n", encoding="utf-8"
            )
            with gzip.open(
                candidate_dir / "evidence.tsv.gz",
                "wt",
                encoding="utf-8",
                newline="\n",
            ) as evidence:
                evidence.write(
                    "word\tdecision\texternal_headword_lemmas\n"
                    "a\taccept\t\n"
                    "alma\taccept\t\n"
                    "újszó\taccept\t\n"
                    "őzgidák\taccept\tőzgida\n"
                )
            checksum = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
            (candidate_dir / "audit.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "description": "candidate",
                        "counts": {"accepted": 4},
                        "output_sha256": checksum,
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / ACTIVE_FILE_NAME).write_text(
                "alma\nkörte\n", encoding="utf-8"
            )
            source_mappings = root / "source-mappings.tsv"
            source_mappings.write_text(
                "alma\talm\nalma\talma\nkörte\tkörte\n", encoding="utf-8"
            )
            _write_lemma_index(
                str(source_mappings),
                str(output_dir / LEMMA_RELATIVE_PATH),
                blocked_surfaces=set(),
            )

            audit = promote(candidate_dir, output_dir)
            self.assertEqual(
                (candidate_dir / "evidence.tsv.gz").read_bytes(),
                (output_dir / "evidence.tsv.gz").read_bytes(),
            )

            self.assertEqual(
                ["a", "alma", "újszó", "őzgidák"],
                (output_dir / ACTIVE_FILE_NAME).read_text(encoding="utf-8").splitlines(),
            )
            self.assertEqual(4, audit["lemma_index"]["surface_count"])
            self.assertEqual(5, audit["lemma_index"]["mapping_count"])
            self.assertEqual(
                2,
                audit["lemma_index"][
                    "self_mappings_added_for_unmapped_surfaces"
                ],
            )
            self.assertEqual(
                1,
                audit["lemma_index"][
                    "external_headword_mappings_added_for_unmapped_surfaces"
                ],
            )

            rows = {}
            for shard_path in (output_dir / LEMMA_RELATIVE_PATH).glob("*.tsv.gz"):
                with gzip.open(shard_path, "rt", encoding="utf-8") as source:
                    for line in source:
                        surface, lemmas = line.rstrip("\n").split("\t", 1)
                        rows[surface] = lemmas
            self.assertEqual(
                {
                    "a": "a",
                    "alma": "alm,alma",
                    "újszó": "újszó",
                    "őzgidák": "őzgida",
                },
                rows,
            )

    def test_refuses_checksum_mismatch_before_replacing_active_output(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            candidate_dir = root / "candidate"
            output_dir = root / "output"
            candidate_dir.mkdir()
            (output_dir / LEMMA_RELATIVE_PATH).mkdir(parents=True)
            (candidate_dir / CANDIDATE_FILE_NAME).write_text("alma\n", encoding="utf-8")
            with gzip.open(
                candidate_dir / "evidence.tsv.gz", "wt", encoding="utf-8"
            ) as evidence:
                evidence.write("word\tdecision\texternal_headword_lemmas\n")
            (candidate_dir / "audit.json").write_text(
                json.dumps({"output_sha256": "wrong"}), encoding="utf-8"
            )
            active_path = output_dir / ACTIVE_FILE_NAME
            active_path.write_text("original\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                promote(candidate_dir, output_dir)

            self.assertEqual("original\n", active_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
