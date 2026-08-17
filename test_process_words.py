import gzip
import json
import tempfile
import unittest
from pathlib import Path

from process_words import expand_dictionary, parse_aff


class ParseAffTests(unittest.TestCase):
    def test_numeric_aliases_do_not_shift_following_aliases(self):
        aff = b"""\
AF 3
AF A
AF 2
AF BC
AM 2
AM po:noun
AM po:abr
SFX 2 Y 1
SFX 2 0 k .
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            aff_path = Path(temp_dir, "hu_HU.aff")
            aff_path.write_bytes(aff)
            af_aliases, am_aliases, pfx_rules, sfx_rules, _special = parse_aff(
                str(aff_path)
            )

        self.assertEqual({1: b"A", 2: b"2", 3: b"BC"}, af_aliases)
        self.assertEqual({1: "po:noun", 2: "po:abr"}, am_aliases)
        self.assertEqual({}, pfx_rules)
        self.assertIn(b"2", sfx_rules)

    def test_resolves_continuation_aliases_and_literal_class_hyphens(self):
        aff = b"""\
FORBIDDENWORD w
AF 2
AF A
AF w
SFX A Y 2
SFX A 0 x/2 .
SFX A 0 k [a-]
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            aff_path = Path(temp_dir, "hu_HU.aff")
            aff_path.write_bytes(aff)
            _af, _am, _pfx, sfx_rules, _special = parse_aff(str(aff_path))

        forbidden_rule, hyphen_rule = sfx_rules[b"A"]
        self.assertEqual(b"w", forbidden_rule[3])
        self.assertIsNotNone(hyphen_rule[2].search("a"))
        self.assertIsNotNone(hyphen_rule[2].search("-"))
        self.assertIsNone(hyphen_rule[2].search("z"))

    def test_parses_prefix_rules_with_start_conditions_and_cross_product(self):
        aff = b"""\
PFX P Y 1
PFX P a be a ip:PREF
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            aff_path = Path(temp_dir, "hu_HU.aff")
            aff_path.write_bytes(aff)
            _af, _am, pfx_rules, _sfx, _special = parse_aff(str(aff_path))

        rule = pfx_rules[b"P"][0]
        self.assertEqual("a", rule.strip)
        self.assertEqual("be", rule.add)
        self.assertTrue(rule.cross_product)
        self.assertIsNotNone(rule.condition_re.search("alma"))
        self.assertIsNone(rule.condition_re.search("malma"))


class StrictGenerationTests(unittest.TestCase):
    def test_attested_prefixes_and_prefix_suffix_cross_products_are_generated(self):
        aff = b"""\
SET UTF-8
PFX P Y 2
PFX P 0 be . ip:PREF
PFX P 0 ki . ip:PREF
SFX S Y 1
SFX S 0 t . is:PAST
SFX N N 1
SFX N 0 va . is:PART
"""
        dic = """\
1
ír/PSN
"""
        corpus_rows = """\
beír\t10\t10\t8\t6
beírt\t8\t8\t6\t4
beírva\t7\t7\t5\t3
kiír\t12\t12\t10\t8
kiírt\t0\t0\t0\t0
"""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            aff_path = root / "hu_HU.aff"
            dic_path = root / "hu_HU.dic"
            corpus_path = root / "web2.2-alfa-sorted.txt.gz"
            output_path = root / "output.txt"
            audit_path = root / "audit.json"
            aff_path.write_bytes(aff)
            dic_path.write_text(dic, encoding="utf-8")
            with gzip.open(
                corpus_path, "wt", encoding="iso-8859-2"
            ) as corpus_file:
                corpus_file.write(corpus_rows)

            expand_dictionary(
                str(aff_path),
                str(dic_path),
                str(output_path),
                audit_path=str(audit_path),
                corpus_path=str(corpus_path),
                minimum_risky_corpus_frequency=2,
            )
            words = output_path.read_text(encoding="utf-8").splitlines()
            audit = json.loads(audit_path.read_text(encoding="utf-8"))

        self.assertEqual(["beír", "beírt", "kiír", "ír", "írt", "írva"], words)
        self.assertNotIn("beírva", words)
        self.assertNotIn("kiírt", words)
        self.assertEqual(2, audit["counts"]["raw_prefix_generation_paths"])
        self.assertEqual(
            1,
            audit["counts"]["raw_prefix_suffix_generation_paths"],
        )
        self.assertTrue(audit["policy"]["hunspell_prefix_rules_supported"])
        self.assertTrue(
            audit["policy"]["hunspell_prefix_suffix_cross_products_supported"]
        )

    def test_includes_required_one_letter_policy_in_output_and_audit(self):
        aff = b"SET UTF-8\n"
        dic = "1\nalma\n"

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            aff_path = root / "hu_HU.aff"
            dic_path = root / "hu_HU.dic"
            output_path = root / "output.txt"
            audit_path = root / "audit.json"
            aff_path.write_bytes(aff)
            dic_path.write_text(dic, encoding="utf-8")

            count = expand_dictionary(
                str(aff_path),
                str(dic_path),
                str(output_path),
                audit_path=str(audit_path),
                required_one_letter_words=frozenset({"a", "ő"}),
            )
            words = output_path.read_text(encoding="utf-8").splitlines()
            audit = json.loads(audit_path.read_text(encoding="utf-8"))

        self.assertEqual(["a", "alma", "ő"], words)
        self.assertEqual(3, count)
        self.assertEqual(2, audit["counts"]["kept_required_one_letter_words"])
        self.assertEqual(["a", "ő"], audit["policy"]["required_one_letter_words"])

    def test_corpus_filter_targets_only_high_risk_generation(self):
        aff = b"""\
SET UTF-8
AF 2
AF A
AF B
AM 2
AM is:POSSESSEE is:NOM
AM ds:z_ACTION_vrb ts:PRES_INDIC_INDEF_SG_3
SFX A Y 1
SFX A 0 \xc3\xa9 . 1
SFX B Y 1
SFX B a \xc3\xa1z a 2
"""
        dic = """\
3
bar/1
cafra/2
alma/1
"""
        corpus_rows = """\
\t\t\t\t
baré\t1\t1\t0\t0
cafráz\t0\t0\t0\t0
almaé\t2\t2\t2\t2
BARÉ\t999\t999\t999\t999
"""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            aff_path = root / "hu_HU.aff"
            dic_path = root / "hu_HU.dic"
            corpus_path = root / "web2.2-alfa-sorted.txt.gz"
            output_path = root / "output.txt"
            audit_path = root / "audit.json"
            lemma_index_dir = (
                root / "definitions" / "hu" / "surface-lemma" / "v1"
            )
            aff_path.write_bytes(aff)
            dic_path.write_text(dic, encoding="utf-8")
            with gzip.open(
                corpus_path,
                "wt",
                encoding="iso-8859-2",
            ) as corpus_file:
                corpus_file.write(corpus_rows)

            count = expand_dictionary(
                str(aff_path),
                str(dic_path),
                str(output_path),
                audit_path=str(audit_path),
                lemma_index_dir=str(lemma_index_dir),
                corpus_path=str(corpus_path),
                minimum_risky_corpus_frequency=2,
            )
            words = output_path.read_text(encoding="utf-8").splitlines()
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            indexed_surfaces = set()
            for shard_path in lemma_index_dir.glob("*.tsv.gz"):
                with gzip.open(shard_path, "rt", encoding="utf-8") as shard:
                    indexed_surfaces.update(
                        line.split("\t", 1)[0] for line in shard
                    )

        self.assertEqual(["alma", "almaé", "bar", "baré", "cafra"], words)
        self.assertEqual(5, count)
        self.assertIn("baré", indexed_surfaces)
        self.assertNotIn("cafráz", indexed_surfaces)
        self.assertEqual(set(words), indexed_surfaces)
        self.assertEqual(3, audit["counts"]["approved_source_lemmas"])
        self.assertEqual(
            1, audit["counts"]["raw_risky_generation_paths"]
        )
        self.assertEqual(
            1, audit["counts"]["rejected_unattested_risky_generated_forms"]
        )
        self.assertEqual(
            "complete", audit["policy"]["corpus_frequency_field"]
        )
        self.assertEqual(
            2, audit["policy"]["minimum_risky_corpus_frequency"]
        )

    def test_proper_name_derivative_descendants_require_usage(self):
        aff = b"""\
SET UTF-8
AF 2
AF A
AF B
AM 3
AM po:noun_prs
AM po:adj
AM is:i_PLACE/TIME_adj
SFX A Y 1
SFX A 0 i . 3
SFX B Y 1
SFX B 0 \xc3\xa9i .
"""
        dic = """\
2
James/1\t1
jamesi/2\t2
"""
        corpus_rows = "jamesi\t4\t3\t2\t2\n"

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            aff_path = root / "hu_HU.aff"
            dic_path = root / "hu_HU.dic"
            corpus_path = root / "web2.2-alfa-sorted.txt.gz"
            output_path = root / "output.txt"
            aff_path.write_bytes(aff)
            dic_path.write_text(dic, encoding="utf-8")
            with gzip.open(
                corpus_path, "wt", encoding="iso-8859-2"
            ) as corpus_file:
                corpus_file.write(corpus_rows)

            expand_dictionary(
                str(aff_path),
                str(dic_path),
                str(output_path),
                corpus_path=str(corpus_path),
                minimum_risky_corpus_frequency=2,
            )
            words = output_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(["jamesi"], words)

    def test_reported_inflection_shapes_do_not_pass_on_noisy_usage(self):
        aff = b"""\
SET UTF-8
AF 5
AF A
AF B
AF C
AF D
AF E
AM 5
AM is:PLUR is:POSS_SG_3 is:SBL
AM is:PLUR is:POSS_PL_3 is:POSSESSEE is:NOM
AM is:POSS_SG_3 is:SUE
AM is:POSS_SG_1 is:NOM
AM is:PLUR is:NOM
SFX A Y 1
SFX A 0 ira . 1
SFX B Y 1
SFX B 0 aik\xc3\xa9 . 2
SFX C Y 1
SFX C 0 j\xc3\xa9n . 3
SFX D Y 1
SFX D 0 em . 4
SFX E Y 1
SFX E 0 ok . 5
"""
        dic = """\
5
büró/1
luc/2
mi/3
ép/4
boly/5
"""
        corpus_rows = """\
büróira\t0\t0\t0\t0
lucaiké\t0\t0\t0\t0
mijén\t7\t7\t6\t0
épem\t3\t3\t1\t0
bolyok\t10\t10\t5\t2
"""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            aff_path = root / "hu_HU.aff"
            dic_path = root / "hu_HU.dic"
            corpus_path = root / "web2.2-alfa-sorted.txt.gz"
            output_path = root / "output.txt"
            aff_path.write_bytes(aff)
            dic_path.write_text(dic, encoding="utf-8")
            with gzip.open(
                corpus_path, "wt", encoding="iso-8859-2"
            ) as corpus_file:
                corpus_file.write(corpus_rows)

            expand_dictionary(
                str(aff_path),
                str(dic_path),
                str(output_path),
                corpus_path=str(corpus_path),
                minimum_risky_corpus_frequency=2,
            )
            words = output_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(
            [
                "boly",
                "bolyok",
                "büró",
                "luc",
                "mi",
                "mijén",
                "ép",
                "épem",
            ],
            words,
        )

    def test_writes_ambiguous_surface_to_lemma_shards(self):
        aff = b"""\
SET UTF-8
AF 1
AF A
SFX A Y 1
SFX A 0 k .
"""
        dic = """\
3
alma/1
almak/1
alm/1
"""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            aff_path = root / "hu_HU.aff"
            dic_path = root / "hu_HU.dic"
            output_path = root / "output.txt"
            lemma_index_dir = root / "definitions" / "hu" / "surface-lemma" / "v1"
            aff_path.write_bytes(aff)
            dic_path.write_text(dic, encoding="utf-8")

            expand_dictionary(
                str(aff_path),
                str(dic_path),
                str(output_path),
                lemma_index_dir=str(lemma_index_dir),
            )
            manifest = json.loads(
                (lemma_index_dir / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            with gzip.open(
                lemma_index_dir / "616c.tsv.gz", "rt", encoding="utf-8"
            ) as shard_file:
                mappings = dict(
                    line.rstrip("\n").split("\t", 1)
                    for line in shard_file
                )

        self.assertEqual("alma,almak", mappings["almak"])
        self.assertEqual(5, manifest["surface_count"])
        self.assertEqual(6, manifest["mapping_count"])
        self.assertEqual(
            "UTF-8 hex of first two Unicode letters",
            manifest["sharding"],
        )

    def test_explicit_source_stem_metadata_skips_intermediate_inflection(self):
        aff = b"""\
SET UTF-8
AF 1
AF A
AM 1
AM st:h\xc3\xa1z po:noun ts:PLUR
SFX A Y 1
SFX A 0 ban .
"""
        dic = """\
1
házak/1\t1
"""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            aff_path = root / "hu_HU.aff"
            dic_path = root / "hu_HU.dic"
            output_path = root / "output.txt"
            lemma_index_dir = root / "definitions" / "hu" / "surface-lemma" / "v1"
            aff_path.write_bytes(aff)
            dic_path.write_text(dic, encoding="utf-8")

            expand_dictionary(
                str(aff_path),
                str(dic_path),
                str(output_path),
                lemma_index_dir=str(lemma_index_dir),
            )
            with gzip.open(
                lemma_index_dir / "68c3a1.tsv.gz",
                "rt",
                encoding="utf-8",
            ) as shard_file:
                mappings = dict(
                    line.rstrip("\n").split("\t", 1)
                    for line in shard_file
                )

        self.assertEqual("ház", mappings["házak"])
        self.assertEqual("ház", mappings["házakban"])

    def test_manual_abbreviations_and_invalid_standalone_stem(self):
        aff = b"""\
SET UTF-8
AF 1
AF A
SFX A Y 1
SFX A o \xc3\xb3k o
"""
        dic = """\
5
tsz/1
szja/1
uv/1
go/1
taj/1
"""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            aff_path = root / "hu_HU.aff"
            dic_path = root / "hu_HU.dic"
            output_path = root / "output.txt"
            audit_path = root / "audit.json"
            aff_path.write_bytes(aff)
            dic_path.write_text(dic, encoding="utf-8")

            count = expand_dictionary(
                str(aff_path),
                str(dic_path),
                str(output_path),
                audit_path=str(audit_path),
            )
            words = output_path.read_text(encoding="utf-8").splitlines()
            audit = json.loads(audit_path.read_text(encoding="utf-8"))

        self.assertEqual(["g\u00f3k", "taj"], words)
        self.assertEqual(2, count)
        self.assertEqual(3, audit["counts"]["skipped_abbreviation_entries"])
        self.assertEqual(1, audit["counts"]["rejected_blocked_source_surfaces"])
        self.assertEqual(
            ["szja", "tsz", "uv"],
            audit["policy"]["manual_written_abbreviations"],
        )
        self.assertEqual(
            ["go"], audit["policy"]["invalid_standalone_surfaces"]
        )

    def test_forbidden_entry_blocks_same_form_from_another_path(self):
        aff = b"""\
FORBIDDENWORD w
AF 2
AF A
AF Aw
SFX A Y 1
SFX A 0 k .
"""
        dic = """\
2
typo/2
typo/1
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            aff_path = root / "hu_HU.aff"
            dic_path = root / "hu_HU.dic"
            output_path = root / "output.txt"
            aff_path.write_bytes(aff)
            dic_path.write_text(dic, encoding="utf-8")

            count = expand_dictionary(
                str(aff_path), str(dic_path), str(output_path)
            )
            words = output_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(0, count)
        self.assertEqual([], words)

    def test_filters_source_metadata_and_generated_control_flags(self):
        aff = b"""\
SET UTF-8
FORBIDDENWORD w
KEEPCASE ?
NEEDAFFIX u
ONLYINCOMPOUND |
SUBSTANDARD &
AF 6
AF A
AF Aw
AF A|
AF A&
AF A?
AF Au
AM 2
AM po:noun
AM po:abr
SFX A Y 3
SFX A 0 k .
SFX A 0 x/w .
SFX A 0 z/| .
"""
        dic = """\
12
alma/1\t1
rossz/2\t1
prefix/3\t1
archaic/4\t1
mIX/1\t1
unit/5\t1
tő/6\t1
PDF\t2
pdf/1\t1
HAL\t2
hal/1\t1
cs\t1
"""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            aff_path = root / "hu_HU.aff"
            dic_path = root / "hu_HU.dic"
            output_path = root / "output.txt"
            audit_path = root / "audit.json"
            aff_path.write_bytes(aff)
            dic_path.write_text(dic, encoding="utf-8")

            count = expand_dictionary(
                str(aff_path),
                str(dic_path),
                str(output_path),
                audit_path=str(audit_path),
            )
            words = output_path.read_text(encoding="utf-8").splitlines()
            audit = json.loads(audit_path.read_text(encoding="utf-8"))

        self.assertEqual(["alma", "almak", "hal", "halk", "tők"], words)
        self.assertEqual(5, count)
        self.assertEqual(1, audit["counts"]["skipped_abbreviation_entries"])
        self.assertEqual(3, audit["counts"]["rejected_forbiddenword_generated_forms"])
        self.assertEqual(3, audit["counts"]["rejected_onlyincompound_generated_forms"])
        self.assertEqual(1, audit["counts"]["rejected_two_letter_abbreviations"])


class PublishedOutputRegressionTests(unittest.TestCase):
    def test_questioned_forms_follow_the_targeted_policy(self):
        output_path = (
            Path(__file__).parent
            / "output"
            / "hungarian_hu_hu_ispell.txt"
        )
        words = set(output_path.read_text(encoding="utf-8").splitlines())
        targeted_risky_forms = {
            "büróira",
            "ebeimé",
            "jamesiéi",
            "köblű",
            "lucaiké",
            "lucaikén",
            "nűmét",
            "számiékat",
        }
        ordinary_forms_preserved_by_this_policy = {
            "boyéit",
            "csapámhoz",
            "luxok",
            "mijén",
            "tömbéi",
            "vádin",
            "zápunk",
            "épem",
        }

        self.assertTrue(targeted_risky_forms.isdisjoint(words))
        self.assertTrue(ordinary_forms_preserved_by_this_policy.issubset(words))
        self.assertTrue({"boly", "clown"}.issubset(words))


if __name__ == "__main__":
    unittest.main()
