import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from generate_mixed_tile_lexicon import (
    arrangements, read_classic, write_runtime, generate, resolve_segmentation,
    PLAYABLE_TOKENS, TOKEN_ID, LOWER_TOKENS,
)
from generate_classic_tile_lexicon import (
    AmbiguousSegmentationError, BoundaryIndex, enumerate_candidates, load_overrides,
    load_supplemental_boundary_index, select_candidate,
)


class MixedTileLexiconTest(unittest.TestCase):
    def test_mixed_inventory_accepts_combined_sz_before_x(self):
        self.assertEqual(
            arrangements("szex", ("SZ", "E", "X")),
            [("SZ", "E", "X"), ("S", "Z", "E", "X")],
        )

    def test_missing_multigraph_analysis_cannot_silently_fall_back(self):
        with self.assertRaisesRegex(ValueError, "segmentation"):
            arrangements("szex", None)

    def test_mixed_inventory_applies_to_candidates_keys_and_lemma_analysis(self):
        self.assertEqual(enumerate_candidates("szex"), [])
        canonical, evidence = resolve_segmentation("szex", {}, {"szex": ("szex",)}, BoundaryIndex({}))
        self.assertEqual(canonical, ("SZ", "E", "X"))
        self.assertEqual(evidence["resolution"], "orthography")
        candidate, reason = select_candidate(
            "szexszel", enumerate_candidates("szexszel", LOWER_TOKENS), {},
            {"szexszel": ("szex",)}, playable_tokens=LOWER_TOKENS, require_unambiguous=True,
        )
        self.assertEqual(reason, "morphology")
        self.assertEqual(candidate.tokens, ("sz", "e", "x", "sz", "e", "l"))
        self.assertEqual(candidate.key, bytes(TOKEN_ID[t.upper()] for t in candidate.tokens))
        self.assertEqual(len(arrangements("szexszel", tuple(t.upper() for t in candidate.tokens))), 4)

    def test_standalone_y_with_genuine_digraph_and_foreign_boundaries(self):
        canonical, _ = resolve_segmentation("yardnyi", {}, {"yardnyi": ("yard",)}, BoundaryIndex({}))
        self.assertEqual(canonical, ("Y", "A", "R", "D", "NY", "I"))
        self.assertEqual(len(arrangements("yardnyi", canonical)), 2)
        root = Path(__file__).resolve().parent
        boundaries = load_supplemental_boundary_index(root / "mixed_tile_boundaries.txt")
        for surface, lemma in [("royalty", "royalty"), ("royaltyból", "royalty"), ("lymphocyta", "lymphocyta")]:
            canonical, evidence = resolve_segmentation(surface, {}, {surface: (lemma,)}, boundaries)
            self.assertEqual(arrangements(surface, canonical), [tuple(surface.upper())])
            self.assertEqual(evidence["resolution"], "authoritativeBoundary")

    def test_boundary_prevents_merging_and_override_cannot_bypass_it(self):
        boundaries = BoundaryIndex({"gázspray": frozenset({3})})
        canonical, _ = resolve_segmentation("gázspray", {}, {"gázspray": ("gázspray",)}, boundaries)
        self.assertEqual(canonical, tuple("GÁZSPRAY"))
        with self.assertRaisesRegex(ValueError, "crosses"):
            resolve_segmentation("gázspray", {"gázspray": ("g", "á", "zs", "p", "r", "a", "y")}, {}, boundaries)

    def test_competing_analyses_and_missing_evidence_require_override(self):
        with self.assertRaises(AmbiguousSegmentationError):
            resolve_segmentation("szs", {}, {"szs": ("szs",)}, BoundaryIndex({}))
        with self.assertRaisesRegex(ValueError, "Missing source lemma"):
            resolve_segmentation("szex", {}, {}, BoundaryIndex({}))
        canonical, evidence = resolve_segmentation("szs", {"szs": ("sz", "s")}, {}, BoundaryIndex({}))
        self.assertEqual(canonical, ("SZ", "S"))
        self.assertEqual(evidence["resolution"], "override")

    def test_mixed_overrides_do_not_expand_classic_inventory(self):
        path = Path(__file__).resolve().parent / "mixed_tile_segmentation_overrides.tsv"
        self.assertEqual(load_overrides(path, LOWER_TOKENS)["szex"], ("sz", "e", "x"))
        with self.assertRaisesRegex(ValueError, "unplayable"):
            load_overrides(path)

    def test_ambiguous_lemma_requires_review_and_its_override_is_inherited(self):
        with self.assertRaisesRegex(AmbiguousSegmentationError, "lemma segmentation"):
            resolve_segmentation("szsz", {}, {"szsz": ("szs",)}, BoundaryIndex({}))
        canonical, reason = resolve_segmentation(
            "szsa", {"szs": ("s", "zs")}, {"szsa": ("szs",)}, BoundaryIndex({}),
        )
        self.assertEqual(canonical, ("S", "ZS", "A"))
        self.assertEqual(reason["resolution"], "morphology")

    def test_unresolved_analysis_and_failed_seed_write_leave_outputs_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            words, classic, seed = (root / name for name in ("words.txt", "classic.tsv", "seed.txt"))
            words.write_text("szex\n"); seed.write_text("szex\n"); classic.write_text("")
            targets = [root / name for name in ("mixed.tsv", "mixed-seed.tsv", "audit.json")]
            for target in targets:
                target.write_text("prior release\n")
            failure = {"unresolved": [{"surface": "szex", "error": "review required"}]}
            with patch("generate_mixed_tile_lexicon.complete_segmentations", return_value=(failure, {})):
                with self.assertRaisesRegex(ValueError, "Unresolved segmentation"):
                    generate(words, classic, seed, *targets)
            self.assertTrue(targets[2].with_suffix(".unresolved.json").exists())
            with patch("generate_mixed_tile_lexicon.complete_segmentations", return_value=({"unresolved": []}, {})), \
                 patch("generate_mixed_tile_lexicon.write_runtime", side_effect=[{}, OSError("seed write failed")]):
                with self.assertRaisesRegex(OSError, "seed write failed"):
                    generate(words, classic, seed, *targets)
            self.assertEqual([target.read_text() for target in targets], ["prior release\n"] * 3)
            self.assertEqual(list(root.glob("*.pending*")), [])

    def test_szex_generated_keys_are_distinct_and_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "mixed.tsv"
            audit = write_runtime(output, {"szex"}, {"szex": ("SZ", "E", "X")})
            self.assertEqual(audit["entryCount"], 2)
            rows = [line.split("\t") for line in output.read_text().splitlines() if not line.startswith("#")]
            self.assertEqual(rows, [["HQcn", "szex"], ["HCUHJw", "szex"]])

    def test_classic_reader_skips_only_legacy_contractions(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "classic.tsv"
            rows = []
            for tokens in [("A", "SZ", "SZ", "O", "NY"), ("A", "S", "SZ", "O", "NY")]:
                key = base64.urlsafe_b64encode(bytes(TOKEN_ID[t] for t in tokens)).decode().rstrip("=")
                rows.append(f"{key}\tasszony\n")
            source.write_text("".join(rows))
            self.assertEqual(read_classic(source), {"asszony": ("A", "S", "SZ", "O", "NY")})

    def test_user_example_and_independent_digraph_choices(self):
        self.assertEqual(arrangements("szem", ("SZ", "E", "M")), [("SZ", "E", "M"), ("S", "Z", "E", "M")])
        variants = arrangements("szegény", ("SZ", "E", "G", "É", "NY"))
        self.assertEqual(len(variants), 4)
        self.assertIn(("S", "Z", "E", "G", "É", "N", "Y"), variants)
        self.assertIn(("SZ", "E", "G", "É", "N", "Y"), variants)

    def test_all_seven_digraphs_can_be_split(self):
        for token in ["CS", "GY", "LY", "NY", "SZ", "TY", "ZS"]:
            self.assertIn(tuple(token), arrangements(token.lower(), (token,)))

    def test_doubled_letters_and_morpheme_boundaries(self):
        variants = arrangements("asszony", ("A", "S", "SZ", "O", "NY"))
        self.assertIn(tuple("ASSZONY"), variants)
        self.assertNotIn(("A", "SZ", "SZ", "O", "NY"), variants)
        self.assertEqual(arrangements("mézsör", ("M", "É", "Z", "S", "Ö", "R")), [tuple("MÉZSÖR")])
        self.assertIn(tuple("PETTY"), arrangements("petty", ("P", "E", "T", "TY")))

    def test_foreign_letters_and_normalization(self):
        self.assertEqual(arrangements("extra", None), [tuple("EXTRA")])
        self.assertEqual(arrangements(" E\u0301N ", None), [("É", "N")])
        with self.assertRaises(ValueError):
            arrangements("qwerty", None)
        with self.assertRaises(ValueError):
            arrangements("szem", ("ZS", "E", "M"))

    def test_generated_rows_are_deterministic_and_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "fixture.tsv"
            classic = {"szem": ("SZ", "E", "M")}
            first = write_runtime(output, {"szem", "extra"}, classic)
            self.assertEqual(first, write_runtime(output, {"extra", "szem"}, classic))
            self.assertEqual(first["entryCount"], 3)
            for row in output.read_text().splitlines()[1:]:
                key, surface = row.split("\t")
                tokens = [PLAYABLE_TOKENS[i - 1] for i in base64.urlsafe_b64decode(key + "=" * (-len(key) % 4))]
                self.assertEqual("".join(tokens).lower(), surface)


if __name__ == "__main__":
    unittest.main()
