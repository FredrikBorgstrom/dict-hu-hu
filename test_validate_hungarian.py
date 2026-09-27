"""Offline tests of the independent evidence gate; no live service required."""

import copy
import csv
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import validate_hungarian as validator


FIXTURE = Path(__file__).parent / "testdata/plural_possessive_reference.jsonl"


class ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = {e["word"]: e for e in map(json.loads, FIXTURE.read_text().splitlines())}

    def setUp(self):
        self.removals = {"surfaceRemovals": set(), "lemmaRemovals": set()}
        work = validator.ROOT / "artifacts/Hungarian Validation/Tests"
        work.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="Test ", dir=work)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def check_words(self, mapping):
        matches, coverage = validator.reference_matches(FIXTURE, set(mapping.values()), set(mapping))
        proofs = {word: [anchor] for word, anchor in mapping.items()}
        return {w: validator.classify(w, proofs, matches, coverage, self.removals) for w in mapping}

    def test_reported_word_and_regular_cases(self):
        words = {w: "rügy" for w in ["rügyeik", "rügyeiket", "rügyeiknek", "rügyeikkel",
                                    "rügyeikké", "rügyeiken", "rügyei", "rügyeit", "rügyeivel"]}
        result = self.check_words(words)
        self.assertTrue(all(v[0] == "supported" for v in result.values()), result)
        self.assertEqual(result["rügyeik"][2]["owner"], "their")
        self.assertEqual(result["rügyeikkel"][2]["case"], "instrumental")
        self.assertIn("bud", result["rügyeik"][2]["base_meaning"])

    def test_wrong_harmony_not_approved_from_root_vowel(self):
        result = self.check_words({w: "gyík" for w in ["gyíkjaiknak", "gyíkjaikkal", "gyíkjaiknek", "gyíkjeik"]})
        self.assertEqual(result["gyíkjaiknak"][0], "supported")
        self.assertEqual(result["gyíkjaikkal"][0], "supported")
        self.assertEqual(result["gyíkjaiknek"][0], "pending")
        self.assertEqual(result["gyíkjeik"][0], "pending")

    def test_irregular_stems_and_final_vowel_lengthening(self):
        result = self.check_words({"kölykeim": "kölyök", "kölyökeim": "kölyök",
                                   "fügéik": "füge", "fügeik": "füge"})
        self.assertEqual([result[w][0] for w in result], ["supported", "pending", "supported", "pending"])

    def test_published_alternatives_not_guessed_variants(self):
        result = self.check_words({"rabbiik": "rabbi", "rabbijaik": "rabbi", "rabbijeik": "rabbi"})
        self.assertEqual(result["rabbiik"][0], "supported")
        self.assertEqual(result["rabbijaik"][0], "supported")
        self.assertEqual(result["rabbijeik"][0], "pending")
        self.assertEqual(validator.variants("rabbiim (archaic)"), [])
        self.assertEqual(validator.variants("rabbiim / rabbijaim"), [])

    def test_adjective_is_not_a_noun(self):
        result = self.check_words({"híreseim": "híres"})
        self.assertEqual(result["híreseim"][:2], ("pending", "no_published_noun_entry_for_anchor"))

    def test_no_rare_cases_anaphoric_or_recursive_expansion(self):
        result = self.check_words({w: "rügy" for w in ["rügyeikül", "rügyeiké", "rügyeikének", "rügyeikbennek", "rügyeikkor"]})
        self.assertTrue(all(v[0] == "pending" for v in result.values()))

    def test_exact_anchor_match_required(self):
        result = self.check_words({"rügyeik": "gyík"})
        self.assertEqual(result["rügyeik"][0], "pending")

    def test_source_lookup_cannot_replace_generator_proof(self):
        matches, coverage = validator.reference_matches(FIXTURE, {"rügy"}, {"rügyeik"})
        self.assertEqual(validator.classify("rügyeik", {}, matches, coverage, self.removals)[0], "pending")

    def test_explicit_removals_override_both_sources(self):
        self.removals["surfaceRemovals"].add("rügyeik")
        self.assertEqual(self.check_words({"rügyeik": "rügy"})["rügyeik"][0], "excluded")
        self.removals["surfaceRemovals"].clear()
        self.removals["lemmaRemovals"].add("rügy")
        self.assertEqual(self.check_words({"rügyeik": "rügy"})["rügyeik"][0], "excluded")

    def test_incomplete_qualified_and_nonlexical_entries_fail_closed(self):
        for mutation in ("incomplete", "error", "rare", "form_of", "alt_of", "proper"):
            with self.subTest(mutation=mutation):
                entry = copy.deepcopy(self.entries["rügy"])
                if mutation == "incomplete":
                    entry["forms"] = [f for f in entry["forms"] if "second-person" not in f.get("tags", [])]
                elif mutation == "error":
                    for f in entry["forms"]:
                        f.setdefault("tags", []).append("error-unrecognized-form")
                elif mutation == "rare":
                    entry["tags"] = ["rare"]
                elif mutation == "proper":
                    entry["pos"] = "name"
                else:
                    for sense in entry["senses"]:
                        sense[mutation] = [{"word": "other"}]
                self.assertEqual(validator.noun_paradigms(entry), [])

    def test_source_entries_cannot_supply_each_others_missing_columns(self):
        entry = copy.deepcopy(self.entries["rügy"])
        first, second = copy.deepcopy(entry), copy.deepcopy(entry)
        first["forms"] = [f for f in entry["forms"] if "singular" in f.get("tags", [])]
        second["forms"] = [f for f in entry["forms"] if "plural" in f.get("tags", [])]
        source = self.root / "split.jsonl"
        source.write_text("\n".join(json.dumps(e) for e in [first, second]))
        matches, _ = validator.reference_matches(source, {"rügy"}, {"rügyeik"})
        self.assertFalse(matches)

    def test_malformed_or_wrong_language_reference_stops(self):
        source = self.root / "bad.jsonl"
        for content in ['{"word":', '{"word":"bud","lang_code":"en"}', '[]']:
            with self.subTest(content=content):
                source.write_text(content)
                with self.assertRaises(ValueError):
                    validator.reference_matches(source, {"rügy"}, {"rügyeik"})

    def test_compressed_reference_has_identical_matches(self):
        source = self.root / "reference.jsonl.gz"
        with gzip.open(source, "wt") as stream:
            stream.write(FIXTURE.read_text())
        args = ({"rügy"}, {"rügyeik"})
        self.assertEqual(validator.reference_matches(source, *args), validator.reference_matches(FIXTURE, *args))

    def test_offline_cache_checksum_and_no_network(self):
        cache = self.root / "cache"
        with patch("urllib.request.urlopen", side_effect=AssertionError("Network used")):
            with self.assertRaisesRegex(ValueError, "No cached reference"):
                validator.cached_reference(cache, "https://example.invalid", offline=True)
            cache.mkdir()
            source = cache / "Reference.jsonl"
            source.write_text(FIXTURE.read_text())
            data = {"filename": source.name, "sha256": validator.sha256(source)}
            (cache / "reference.json").write_text(json.dumps(data))
            self.assertEqual(validator.cached_reference(cache, "https://example.invalid", offline=True)[0], source)
            source.write_text("changed")
            with self.assertRaisesRegex(ValueError, "checksum"):
                validator.cached_reference(cache, "https://example.invalid", offline=True)

    def test_truncated_download_preserves_previous_cache(self):
        source = self.root / "reference.json"
        source.write_text('{"original":true}')
        response = io.BytesIO(b'{"word":"bud"}\n')
        response.headers = {"Content-Length": "999"}
        with patch("urllib.request.urlopen", return_value=response):
            with self.assertRaisesRegex(ValueError, "Incomplete"):
                validator.cached_reference(self.root, "https://example.invalid", refresh=True)
        self.assertEqual(json.loads(source.read_text()), {"original": True})
        self.assertFalse(list(self.root.glob("*.part")))

    def test_saved_evidence_requires_matching_ordinary_lemma_and_nonproper(self):
        fields = ["word", "decision", "reason", "morphdb_recognized", "morphdb_nonproper",
                  "morphdb_proper_only", "lemma_agreement", "ordinary_possessive_lemmas"]
        rows = [["rügyeik", "accept", validator.ORDINARY, "1", "1", "0", "1", "rügy"],
                ["rügyeim", "accept", validator.ORDINARY, "1", "1", "0", "1", "gyík"],
                ["rügyeid", "accept", validator.ORDINARY, "1", "0", "1", "1", "rügy"],
                ["rügyeink", "accept", validator.DERIVED, "1", "1", "0", "1", ""],
                ["rügyeitek", "accept", validator.DERIVED, "1", "1", "0", "1", ""]]
        with gzip.open(self.root / "evidence.tsv.gz", "wt") as stream:
            writer = csv.writer(stream, delimiter="\t")
            writer.writerow(fields)
            writer.writerows(rows)
        with gzip.open(self.root / "ordinary-possessive-evidence.tsv.gz", "wt") as stream:
            stream.write("surface\taccepted_noun_lemmas\nrügyeik\trügy\nrügyeim\trügy\nrügyeid\trügy\n")
        with gzip.open(self.root / "derived-possessive-evidence.tsv.gz", "wt") as stream:
            stream.write("surface\taccepted_anchor\tsource_lemma\tmorphdb_lexical_analysis\n"
                         "rügyeink\trügy\trügy\t/NOUN\nrügyeitek\trügy\t\t/NOUN\n")
        result = validator.load_proofs({r[0] for r in rows}, self.root)
        self.assertEqual(result["rügyeik"], ["rügy"])
        self.assertFalse(result.get("rügyeim"))
        self.assertFalse(result.get("rügyeid"))
        self.assertEqual(result["rügyeink"], ["rügy"])
        self.assertFalse(result.get("rügyeitek"))

    def test_complete_partition_determinism_and_overwrite_protection(self):
        words = {"rügyeik", "rügyeikül", "RÜGYEIK"}
        proofs = {w: ["rügy"] for w in words}
        matches, coverage = validator.reference_matches(FIXTURE, {"rügy"}, words)
        metadata = {"source_revision": "test", "reference": {"sha256": validator.sha256(FIXTURE)}}
        first, second = self.root / "First", self.root / "Second"
        a = validator.write_results(first, words, proofs, matches, coverage, self.removals, metadata)
        b = validator.write_results(second, words, proofs, matches, coverage, self.removals, metadata)
        self.assertEqual(a["counts"], {"supported": 1, "pending": 1, "excluded": 1})
        self.assertEqual(a["result_sha256"], b["result_sha256"])
        found = []
        for status in a["counts"]:
            found.extend((first / f"{status}.txt").read_text().splitlines())
        self.assertEqual(set(found), words)
        self.assertEqual(len(found), len(words))
        with self.assertRaises(FileExistsError):
            validator.write_results(first, words, proofs, matches, coverage, self.removals, metadata)


if __name__ == "__main__":
    unittest.main()
