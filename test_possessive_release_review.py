import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from build_evidence_wordlist import build_outputs, MorphEvidence
from possessive_release_review import load_possessive_review, DEFERRED_REASON
from promote_evidence_wordlist import promote, CANDIDATE_FILE_NAME


class PossessiveReleaseReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_exact_review_partition_and_no_family_expansion(self):
        review = load_possessive_review()
        self.assertEqual((len(review.scope), len(review.supported), len(review.deferred)),
                         (404258, 164271, 239987))
        self.assertIn("rügyeik", review.supported)
        self.assertIn("fűltjeimet", review.deferred)
        self.assertIn("szörföseik", review.deferred)
        self.assertNotIn("szörfösük", review.scope)
        self.assertEqual(review.scope, review.supported | review.deferred)
        self.assertFalse(review.supported & review.deferred)

    def test_corrupt_review_cannot_disable_filter(self):
        original = Path(__file__).parent / "plural_possessive_review"
        for name in ["manifest.json", "scope.txt.gz", "supported.txt.gz"]:
            (self.root / name).write_bytes((original / name).read_bytes())
        (self.root / "supported.txt.gz").write_bytes(gzip.compress("rügyeik\n".encode()))
        with self.assertRaisesRegex(ValueError, "checksum"):
            load_possessive_review(self.root)
        (self.root / "manifest.json").unlink()
        with self.assertRaises(FileNotFoundError):
            load_possessive_review(self.root)

    def build(self, direct):
        words = ["fa", "fűltjeimet", "rügyeik"]
        inventory = self.root / "words.txt"
        inventory.write_text("".join(w + "\n" for w in words))
        cache = self.root / "morph.gz"
        with gzip.open(cache, "wt") as stream:
            stream.write("# schema=4\ttest\n")
            for word in words:
                stream.write(word + "\t" + "\t".join(MorphEvidence().as_cache_fields()) + "\n")
        return build_outputs(
            merged_candidates_path=inventory, current_words=frozenset(words),
            ordinary_words=frozenset(words), current_direct=frozenset(direct),
            morphdb_direct=frozenset(), morphdb_nonstandalone=frozenset(),
            accepted_external_headwords=frozenset(), external_inflection_candidates=frozenset(),
            corpus_evidence={}, morph_cache_path=cache, surface_additions=frozenset(),
            surface_removals=frozenset(), lemma_removals=frozenset(),
            lemma_removed_surfaces=frozenset(), output_dir=self.root / "candidate", source_metadata={},
        )

    def test_builder_filters_stale_retained_words_and_recomputes_audit(self):
        audit = self.build({"fa", "fűltjeimet", "rügyeik"})
        self.assertEqual((self.root / "candidate" / CANDIDATE_FILE_NAME).read_text().splitlines(), ["fa", "rügyeik"])
        self.assertEqual(audit["counts"]["accepted"], 2)
        self.assertEqual(audit["reason_counts"][DEFERRED_REASON], 1)
        with gzip.open(self.root / "candidate/evidence.tsv.gz", "rt") as stream:
            self.assertIn("fűltjeimet\treject\t" + DEFERRED_REASON, stream.read())

    def test_supported_surface_still_needs_generator_evidence(self):
        audit = self.build({"fa"})
        self.assertEqual(audit["counts"]["accepted"], 1)
        self.assertEqual((self.root / "candidate" / CANDIDATE_FILE_NAME).read_text(), "fa\n")

    def test_promotion_refuses_stale_expansion_before_mutating_output(self):
        candidate, output = self.root / "candidate", self.root / "output"
        candidate.mkdir()
        output.mkdir()
        raw = "fűltjeimet\nrügyeik\n"
        (candidate / CANDIDATE_FILE_NAME).write_text(raw)
        (candidate / "audit.json").write_text(json.dumps({"output_sha256": hashlib.sha256(raw.encode()).hexdigest()}))
        sentinel = output / "unchanged.txt"
        sentinel.write_text("preserve")
        with self.assertRaisesRegex(ValueError, "deferred plural possessions"):
            promote(candidate, output)
        self.assertEqual(list(output.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_text(), "preserve")


if __name__ == "__main__":
    unittest.main()
