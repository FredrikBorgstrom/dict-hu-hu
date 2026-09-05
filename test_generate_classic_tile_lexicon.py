import gzip
import tempfile
import unittest
from pathlib import Path

from generate_classic_tile_lexicon import (
    BoundaryIndex,
    BoundaryUnrepresentableError,
    TOKEN_ID,
    artifact_value,
    boundaries_for_surface,
    enumerate_candidates,
    generate,
    load_ispell_boundary_index,
    load_overrides,
    load_supplemental_boundary_index,
    merge_boundary_indexes,
    parse_hyphenation_boundaries,
    parse_marked_boundary_surface,
    select_candidate,
)


ROOT = Path(__file__).resolve().parent


class ClassicTileLexiconTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.boundary_index = load_ispell_boundary_index(
            ROOT / ".cache/sources/hu_HU.aff",
            ROOT / ".cache/sources/hu_HU.dic",
        )
        cls.supplemental_boundary_index = load_supplemental_boundary_index(
            ROOT / "csi_sza_classic_tile_boundaries.txt",
        )
        cls.combined_boundary_index = merge_boundary_indexes(
            cls.boundary_index,
            cls.supplemental_boundary_index,
        )

    def test_game_5863_reported_surface_is_removed_from_both_outputs(self):
        standard_words = set(
            (ROOT / "output" / "hungarian_hu_hu_ispell.txt")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        classic_surfaces = {
            line.split("\t", 1)[1]
            for line in (
                ROOT / "output" / "hungarian_hu_hu_ispell_classic_tiles.tsv"
            )
            .read_text(encoding="utf-8")
            .splitlines()
            if line and not line.startswith("#")
        }

        self.assertIn("cöcög", standard_words)
        self.assertIn("cöcög", classic_surfaces)
        self.assertNotIn("cöcögd", standard_words)
        self.assertNotIn("cöcögd", classic_surfaces)

    def test_generated_artifact_preserves_reported_compound_boundaries(self):
        with gzip.open(
            ROOT / "output/hungarian_hu_hu_ispell_classic_tiles.source.tsv.gz",
            "rt",
            encoding="utf-8",
        ) as source:
            rows = {
                surface: tokens
                for raw_line in source
                if raw_line and not raw_line.startswith("#")
                for surface, tokens in [raw_line.rstrip("\n").split("\t", 1)]
            }

        self.assertEqual(rows["mézsör"], "m|é|z|s|ö|r")
        self.assertEqual(rows["mézsörben"], "m|é|z|s|ö|r|b|e|n")
        self.assertEqual(rows["házsor"], "h|á|z|s|o|r")
        self.assertEqual(rows["ősszülő"], "ő|s|sz|ü|l|ő")
        self.assertEqual(rows["gázsi"], "g|á|zs|i")
        self.assertEqual(rows["község"], "k|ö|z|s|é|g")
        self.assertEqual(rows["községi"], "k|ö|z|s|é|g|i")
        self.assertEqual(rows["nehézség"], "n|e|h|é|z|s|é|g")
        self.assertEqual(rows["egészséges"], "e|g|é|sz|s|é|g|e|s")
        self.assertEqual(rows["őzgida"], "ő|z|g|i|d|a")
        self.assertEqual(rows["őzgidák"], "ő|z|g|i|d|á|k")
        self.assertNotIn("city", rows)
        self.assertNotIn("nylon", rows)
        self.assertNotIn("zloty", rows)

    def test_all_applicable_csi_sza_annotations_are_enforced(self):
        standard_words = set(
            (ROOT / "output" / "hungarian_hu_hu_ispell.txt")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        with gzip.open(
            ROOT / "output/hungarian_hu_hu_ispell_classic_tiles.source.tsv.gz",
            "rt",
            encoding="utf-8",
        ) as source:
            accepted = {
                surface: tuple(tokens.split("|"))
                for raw_line in source
                if raw_line and not raw_line.startswith("#")
                for surface, tokens in [raw_line.rstrip("\n").split("\t", 1)]
            }
        with gzip.open(
            ROOT / "output/hungarian_hu_hu_ispell_classic_tiles.excluded.tsv.gz",
            "rt",
            encoding="utf-8",
        ) as source:
            excluded = {
                surface: reason
                for raw_line in source
                if raw_line and not raw_line.startswith("surface\t")
                for surface, reason in [raw_line.rstrip("\n").split("\t", 1)]
            }

        applicable = standard_words & set(self.supplemental_boundary_index.boundaries)
        # New reviewed words can add applicable annotations. Keep the original
        # coverage floor while checking every current annotation below.
        self.assertGreaterEqual(len(applicable), 131)
        for surface in applicable:
            if surface not in accepted:
                self.assertIn(
                    excluded.get(surface),
                    {
                        "authoritative_boundary_unrepresentable",
                        "canonical_key_collision",
                        "unrepresentable_token_sequence",
                        "unsupported_character",
                    },
                    surface,
                )
                continue
            accepted_candidate = next(
                candidate
                for candidate in enumerate_candidates(surface)
                if candidate.tokens == accepted[surface]
            )
            self.assertTrue(
                accepted_candidate.boundary_crossings.isdisjoint(
                    self.supplemental_boundary_index.boundaries[surface]
                ),
                surface,
            )

    def test_reviewed_orthography_fixtures(self):
        overrides = load_overrides(ROOT / "classic_tile_segmentation_overrides.tsv")
        expected = {
            "asszony": ("a", "s", "sz", "o", "ny"),
            "loccsan": ("l", "o", "c", "cs", "a", "n"),
            "díszszemle": ("d", "í", "sz", "sz", "e", "m", "l", "e"),
            "jegygyűrű": ("j", "e", "gy", "gy", "ű", "r", "ű"),
            "edző": ("e", "d", "z", "ő"),
            "bridzs": ("b", "r", "i", "d", "zs"),
        }
        for surface, tokens in expected.items():
            candidate, reason = select_candidate(surface, enumerate_candidates(surface), overrides, {})
            self.assertEqual(candidate.tokens, tokens)
            self.assertEqual(reason, "override")
            self.assertEqual(len(candidate.key), len(tokens))

    def test_all_seven_shortened_doubles_use_the_written_physical_tiles(self):
        cases = {
            "meccs": ("m|e|c|cs", "m|e|cs|cs"),
            "meggy": ("m|e|g|gy", "m|e|gy|gy"),
            "gally": ("g|a|l|ly", "g|a|ly|ly"),
            "mennyi": ("m|e|n|ny|i", "m|e|ny|ny|i"),
            "asszony": ("a|s|sz|o|ny", "a|sz|sz|o|ny"),
            "petty": ("p|e|t|ty", "p|e|ty|ty"),
            "rozzsal": ("r|o|z|zs|a|l", "r|o|zs|zs|a|l"),
            "asszonnyal": ("a|s|sz|o|n|ny|a|l", "a|sz|sz|o|ny|ny|a|l"),
        }
        for surface, (physical, legacy) in cases.items():
            with self.subTest(surface=surface):
                candidate, _ = select_candidate(surface, enumerate_candidates(surface), {}, {})
                self.assertEqual(candidate.tokens, tuple(physical.split("|")))
                self.assertEqual(candidate.comparison_tokens, tuple(legacy.split("|")))
                self.assertEqual("".join(candidate.tokens), surface)
                self.assertEqual(len(candidate.key), len(candidate.legacy_key))

    def test_full_doubling_and_real_boundaries_do_not_gain_shortened_aliases(self):
        for surface in ("díszszemle", "jegygyűrű", "ősszülő"):
            with self.subTest(surface=surface):
                candidate, _ = select_candidate(
                    surface, enumerate_candidates(surface), {}, {}, self.boundary_index,
                )
                self.assertEqual(candidate.key, candidate.legacy_key)
                self.assertEqual("".join(candidate.tokens), surface)

    def test_runtime_preserves_legacy_placements_but_source_prefers_physical_tiles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            words = root / "words.txt"
            words.write_text("petty\nasszonnyal\ndíszszemle\n", encoding="utf-8")
            args = (
                words, root / "runtime.tsv", root / "source.tsv.gz",
                root / "audit.json", root / "excluded.tsv.gz",
                ROOT / "classic_tile_segmentation_overrides.tsv", root / "missing-lemmas",
            )
            audit = generate(*args)
            runtime = args[1].read_text(encoding="utf-8")
            for surface in ("petty", "asszonnyal"):
                candidate, _ = select_candidate(surface, enumerate_candidates(surface), {}, {})
                old_row = f"{artifact_value(candidate.legacy_key)}\t{surface}"
                new_row = f"{artifact_value(candidate.key)}\t{surface}"
                self.assertIn(old_row, runtime)
                self.assertIn(new_row, runtime)
                self.assertLess(runtime.index(old_row), runtime.index(new_row))
            with gzip.open(args[2], "rt", encoding="utf-8") as source:
                self.assertIn("petty\tp|e|t|ty\n", source.read())
            self.assertEqual(audit["output"]["acceptedEntries"], 3)
            self.assertEqual(audit["output"]["runtimeEntries"], 5)
            self.assertEqual(audit["output"]["compatibilityAliases"], 2)
            self.assertEqual(audit["rendererDiagnosticMismatchCount"], 0)
            before = [path.read_bytes() for path in args[1:5]]
            generate(*args)
            self.assertEqual(before, [path.read_bytes() for path in args[1:5]])

    def test_magyar_ispell_compound_boundaries_drive_tile_segmentation(self):
        cases = {
            "mézsör": ("m", "é", "z", "s", "ö", "r"),
            "házsor": ("h", "á", "z", "s", "o", "r"),
            "ősszülő": ("ő", "s", "sz", "ü", "l", "ő"),
        }
        for surface, expected in cases.items():
            candidate, reason = select_candidate(
                surface,
                enumerate_candidates(surface),
                {},
                {},
                self.boundary_index,
            )
            self.assertEqual(candidate.tokens, expected, surface)
            self.assertEqual(reason, "authoritativeBoundary", surface)

        simple_candidate, simple_reason = select_candidate(
            "gázsi",
            enumerate_candidates("gázsi"),
            {},
            {},
            self.boundary_index,
        )
        self.assertEqual(simple_candidate.tokens, ("g", "á", "zs", "i"))
        self.assertEqual(simple_reason, "orthography")

    def test_compound_boundary_propagates_from_lemma_to_inflection(self):
        lemmas = {"mézsörben": ("mézsör",)}
        self.assertEqual(
            boundaries_for_surface("mézsörben", lemmas, self.boundary_index),
            frozenset({3}),
        )
        candidate, reason = select_candidate(
            "mézsörben",
            enumerate_candidates("mézsörben"),
            {},
            lemmas,
            self.boundary_index,
        )
        self.assertEqual(
            candidate.tokens,
            ("m", "é", "z", "s", "ö", "r", "b", "e", "n"),
        )
        self.assertEqual(reason, "authoritativeBoundary")

    def test_permissioned_csi_sza_boundaries_are_loaded_as_evidence_only(self):
        self.assertEqual(
            self.supplemental_boundary_index.supplemental_annotation_count,
            931,
        )
        self.assertEqual(
            self.supplemental_boundary_index.boundaries["község"],
            frozenset({3}),
        )
        self.assertEqual(
            parse_marked_boundary_surface("EGÉSZ_SÉGES"),
            ("egészséges", frozenset({5})),
        )

        candidate, reason = select_candidate(
            "község",
            enumerate_candidates("község"),
            {},
            {},
            self.combined_boundary_index,
        )
        self.assertEqual(candidate.tokens, ("k", "ö", "z", "s", "é", "g"))
        self.assertEqual(reason, "authoritativeBoundary")

    def test_permissioned_boundary_can_make_surface_unrepresentable(self):
        with self.assertRaises(BoundaryUnrepresentableError):
            select_candidate(
                "city",
                enumerate_candidates("city"),
                {},
                {},
                self.combined_boundary_index,
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "words.txt"
            boundary_path = root / "boundaries.txt"
            input_path.write_text("city\ngázsi\n", encoding="utf-8")
            boundary_path.write_text("cit_y\n", encoding="utf-8")
            audit = generate(
                input_path,
                root / "runtime.tsv",
                root / "source.tsv.gz",
                root / "audit.json",
                root / "excluded.tsv.gz",
                ROOT / "classic_tile_segmentation_overrides.tsv",
                root / "missing-lemmas",
                supplemental_boundary_path=boundary_path,
            )
            self.assertEqual(audit["output"]["acceptedEntries"], 1)
            self.assertEqual(
                audit["excludedReasonCounts"],
                {"authoritative_boundary_unrepresentable": 1},
            )

    def test_hyphenation_boundary_parser_accepts_inflected_stem_prefix(self):
        self.assertEqual(
            parse_hyphenation_boundaries("mézsör", "méz|sör"),
            (frozenset({3}), False),
        )
        self.assertEqual(
            parse_hyphenation_boundaries("őzsuta", "őz|sut"),
            (frozenset({2}), True),
        )
        self.assertEqual(
            parse_hyphenation_boundaries("gázsi", "z|s"),
            (None, False),
        )

    def test_authoritative_boundary_never_falls_back_to_crossing_token(self):
        with self.assertRaisesRegex(ValueError, "preserves authoritative boundaries"):
            select_candidate(
                "mézsör",
                [candidate for candidate in enumerate_candidates("mézsör") if "zs" in candidate.tokens],
                {},
                {},
                BoundaryIndex({"mézsör": frozenset({3})}),
            )

    def test_unavailable_standalone_letters_are_unrepresentable(self):
        for surface in ("q", "w", "x", "y"):
            self.assertEqual(enumerate_candidates(surface), [])
        self.assertEqual(
            select_candidate("dzs", enumerate_candidates("dzs"), {}, {})[0].tokens,
            ("d", "zs"),
        )

    def test_small_artifact_is_deterministic_and_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "words.txt"
            input_path.write_text("asszony\ndíszszemle\nyacht\n", encoding="utf-8")
            first = generate(
                input_path,
                root / "runtime.tsv",
                root / "source.tsv.gz",
                root / "audit.json",
                root / "excluded.tsv.gz",
                ROOT / "classic_tile_segmentation_overrides.tsv",
                root / "missing-lemmas",
            )
            self.assertEqual(first["output"]["acceptedEntries"], 2)
            self.assertEqual(first["input"]["path"], "words.txt")
            self.assertEqual(first["output"]["runtimePath"], "runtime.tsv")
            self.assertEqual(first["unrepresentableEntries"], 1)
            rows = [line for line in (root / "runtime.tsv").read_text(encoding="utf-8").splitlines() if not line.startswith("#")]
            self.assertEqual(len(rows), 3)
            self.assertTrue(all("\t" in row for row in rows))
            self.assertEqual(TOKEN_ID["sz"], 29)


if __name__ == "__main__":
    unittest.main()
