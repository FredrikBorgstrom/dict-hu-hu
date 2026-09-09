import base64
from pathlib import Path
import tempfile
import unittest

from generate_mixed_tile_lexicon import arrangements, read_classic, write_runtime, PLAYABLE_TOKENS, TOKEN_ID


class MixedTileLexiconTest(unittest.TestCase):
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
