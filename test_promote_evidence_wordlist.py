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
)


class EvidencePromotionTests(unittest.TestCase):
    def test_preserves_existing_ambiguity_and_self_maps_new_surfaces(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            candidate_dir = root / "candidate"
            output_dir = root / "output"
            candidate_dir.mkdir()
            output_dir.mkdir()

            candidate_path = candidate_dir / CANDIDATE_FILE_NAME
            candidate_path.write_text("a\nalma\nújszó\n", encoding="utf-8")
            checksum = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
            (candidate_dir / "audit.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "description": "candidate",
                        "counts": {"accepted": 3},
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
                ["a", "alma", "újszó"],
                (output_dir / ACTIVE_FILE_NAME).read_text(encoding="utf-8").splitlines(),
            )
            self.assertEqual(3, audit["lemma_index"]["surface_count"])
            self.assertEqual(4, audit["lemma_index"]["mapping_count"])
            self.assertEqual(
                2,
                audit["lemma_index"][
                    "self_mappings_added_for_unmapped_surfaces"
                ],
            )

            rows = {}
            for shard_path in (output_dir / LEMMA_RELATIVE_PATH).glob("*.tsv.gz"):
                with gzip.open(shard_path, "rt", encoding="utf-8") as source:
                    for line in source:
                        surface, lemmas = line.rstrip("\n").split("\t", 1)
                        rows[surface] = lemmas
            self.assertEqual(
                {"a": "a", "alma": "alm,alma", "újszó": "újszó"}, rows
            )

    def test_refuses_checksum_mismatch_before_replacing_active_output(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            candidate_dir = root / "candidate"
            output_dir = root / "output"
            candidate_dir.mkdir()
            (output_dir / LEMMA_RELATIVE_PATH).mkdir(parents=True)
            (candidate_dir / CANDIDATE_FILE_NAME).write_text("alma\n", encoding="utf-8")
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
