import gzip
import json
import tempfile
from pathlib import Path
import unittest

from reviewed_additions import lexical_analyses, definition_lemmas, load_reviewed_additions, load_gameplay_overrides
from process_words import is_written_abbreviation_shape, expand_dictionary, PINNED_SOURCES
from build_evidence_wordlist import decide_word, CorpusEvidence, MorphEvidence
from promote_evidence_wordlist import load_external_inflection_mappings


class ReviewedAdditionTests(unittest.TestCase):
    def test_reviewed_fazokat_preserves_the_weak_derivation_gate(self):
        corpus = CorpusEvidence(complete=3, quality_40=3, quality_8=3, quality_4=1)
        morph = MorphEvidence(recognized=True, nonproper=True,
                              derivation_only=True, parts_of_speech=("ADJ", "VERB"))
        options = dict(current_candidate=True, current_direct=False, morphdb_direct=False)
        before = decide_word("fázókat", corpus, morph, **options)
        self.assertEqual((False, "weak_derivation"), (before.accepted, before.reason))
        overrides = load_gameplay_overrides()
        after = decide_word("fázókat", corpus, morph,
                            explicit_addition="fázókat" in overrides["additions"], **options)
        self.assertEqual((True, "reviewed_surface_addition"), (after.accepted, after.reason))
        withdrawn = decide_word("fázókat", corpus, morph, explicit_addition=True,
                                explicit_surface_removal=True, **options)
        self.assertFalse(withdrawn.accepted)

    def test_reviewed_kombo_family_is_admitted_without_analyser_support(self):
        corpus = CorpusEvidence(complete=1534, quality_40=1524, quality_8=189, quality_4=16)
        unknown = MorphEvidence()
        options = dict(current_candidate=False, current_direct=False, morphdb_direct=False)
        before = decide_word("kombó", corpus, unknown, **options)
        self.assertFalse(before.accepted)
        additions = load_gameplay_overrides()["additions"]
        for word in ("kombó", "kombót", "kombók", "kombóval", "kombójával", "kombós", "gitárkombó"):
            with self.subTest(word=word):
                self.assertIn(word, additions)
                after = decide_word(word, corpus, unknown, explicit_addition=True, **options)
                self.assertEqual((True, "reviewed_surface_addition"), (after.accepted, after.reason))
        self.assertNotIn("kombózik", additions)

    def test_rare_i_adjective_removals_keep_real_and_held_words(self):
        # 2026-11-12: rare place/time "-i" adjectives (quality-4 count below 5)
        # are removed; real words, held words, reviewed additions and
        # homographs with an ordinary possessive reading must stay playable.
        overrides = load_gameplay_overrides()
        removals = overrides["surfaceRemovals"]
        # 2026-11-13 native review: odahazai, legeleji, hóolvadási and the
        # unconfirmed held words (betyári, kisgazdai, ramadáni ...) are removed.
        for word in ("kíni", "hibai", "neszi", "pályai", "öblien", "cími", "híri", "máji",
                     "odahazai", "legeleji", "hóolvadási", "betyári", "kisgazdai", "ramadáni"):
            with self.subTest(removed=word):
                if word == "öblien":
                    # An inflection: withdrawn with its anchor, not listed.
                    self.assertNotIn(word, removals)
                    self.assertIn("öbli", removals)
                else:
                    self.assertIn(word, removals)
        kept = ("pampai", "idefönti", "nehézvízi", "brakkvízi",
                "termálvízi", "árterületi", "délszigeti", "háryjánosi", "édesatyai",
                "nagybátyai", "jogsegélyi", "magánbanki", "citokémiai", "oxiológiai")
        held = ("nyúltagyi", "permkori", "hússzori", "zsoltári", "öregemberi", "admirálisi",
                "gettói", "sajtói")
        for word in kept + held + ("fain", "adóügyi", "munkaadói", "adui", "almai",
                                   "vaki", "lati", "éni", "csődi"):
            with self.subTest(kept=word):
                self.assertNotIn(word, removals)
        self.assertIn("fain", overrides["additions"])

    def test_portable_gameplay_overrides_validate_and_preserve_removals(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "overrides.json"
            document = {"schemaVersion": 1, "additions": ["box"],
                        "surfaceRemovals": ["cm", "szja"], "lemmaRemovals": ["lex"]}
            path.write_text(json.dumps(document))
            self.assertEqual(frozenset({"lex"}), load_gameplay_overrides(path)["lemmaRemovals"])
            document["additions"].append("lex")
            path.write_text(json.dumps(document))
            with self.assertRaisesRegex(ValueError, "Conflicting"):
                load_gameplay_overrides(path)

    def test_missing_or_changed_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "reviewed.json"
            with self.assertRaises(FileNotFoundError):
                load_reviewed_additions(path)
            path.write_text(json.dumps({"schemaVersion": 1, "sourceChecksumsSha256": {}, "entries": []}))
            with self.assertRaisesRegex(ValueError, "reverified"):
                load_reviewed_additions(path)

    def test_unverified_lemma_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "reviewed.json"
            path.write_text(json.dumps({"schemaVersion": 1,
                "sourceChecksumsSha256": {n: s["sha256"] for n, s in PINNED_SOURCES.items()},
                "entries": [{"word": "adatbank", "quality4Frequency": 10,
                    "magyarIspellAnalyses": ["adatbank pa:adat st:adat pa:bank st:bank"],
                    "lemmas": ["bank"]}]}))
            with self.assertRaisesRegex(ValueError, "definition mapping"):
                load_reviewed_additions(path)

    def test_inflected_stem_preserves_verbal_prefix(self):
        self.assertEqual(["megérez"], definition_lemmas("megérzik", [
            "megérzik ip:PREF sp:meg st:érez po:vrb is:PRES_INDIC_DEF_PL_3"]))

    def test_compound_never_maps_to_last_component(self):
        self.assertEqual(["adatbank"], definition_lemmas("adatbank", [
            "adatbank pa:adat st:adat po:noun pa:bank st:bank po:noun"]))

    def test_proper_name_is_not_lexical_but_reviewed_adjective_is(self):
        self.assertEqual([], lexical_analyses("irak", ["irak st:Irak po:noun_prs"]))
        line = "iraki st:Irak po:noun_prs is:i_PLACE/TIME_adj ts:NOM"
        self.assertEqual([line], lexical_analyses("iraki", [line]))
        self.assertEqual(["iraki"], definition_lemmas("iraki", [line]))
        self.assertEqual([], lexical_analyses("log", ["log st:log po:abr"]))

    def test_hm_exception_does_not_admit_units(self):
        for word in ("cm", "kg", "db", "sz"):
            self.assertTrue(is_written_abbreviation_shape(word))
        self.assertFalse(is_written_abbreviation_shape("hm"))
        for word, accepted in (("hm", True), ("cm", False), ("kg", False)):
            decision = decide_word(word, CorpusEvidence(), MorphEvidence(),
                                   current_candidate=False, current_direct=False,
                                   morphdb_direct=False, explicit_addition=True)
            self.assertEqual(accepted, decision.accepted)

    def test_source_generation_keeps_lowercase_hm_not_uppercase_abbreviation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "hu.aff").write_text("SET UTF-8\nAM 2\nAM po:abr\nAM po:sentint\n")
            (root / "hu.dic").write_text("4\nHM\t1\nhm\t2\ncm\t1\nkg\t1\n")
            expand_dictionary(str(root / "hu.aff"), str(root / "hu.dic"), str(root / "words.txt"))
            generated = (root / "words.txt").read_text().splitlines()
            self.assertIn("hm", generated)
            self.assertNotIn("cm", generated)
            self.assertNotIn("kg", generated)

    def test_review_never_overrides_explicit_removal(self):
        for option in ("explicit_surface_removal", "explicit_lemma_removal", "source_policy_blocked"):
            result = decide_word("alma", CorpusEvidence(), MorphEvidence(),
                                 current_candidate=False, current_direct=False,
                                 morphdb_direct=False, explicit_addition=True, **{option: True})
            self.assertFalse(result.accepted)

    def test_reviewed_mapping_overrides_external_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            evidence = Path(folder) / "evidence.tsv.gz"
            with gzip.open(evidence, "wt") as output:
                output.write("word\tdecision\texternal_headword_lemmas\treviewed_lemmas\n")
                output.write("megérzik\taccept\térez\tmegérez\n")
                output.write("log\treject\tlog\tlog\n")
            self.assertEqual({"megérzik": ("megérez",)},
                             load_external_inflection_mappings(evidence, frozenset({"megérzik", "log"})))


if __name__ == "__main__":
    unittest.main()
