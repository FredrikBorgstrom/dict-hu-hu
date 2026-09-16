"""Regression coverage for ordinary endings after a derived adjective."""

import gzip
import json
import tempfile
import unittest
from pathlib import Path

from process_words import expand_dictionary
from build_evidence_wordlist import (
    CorpusEvidence, MorphEvidence, decide_word, licensed_inflections_of_accepted_words,
)
from dataclasses import replace


class SuffixContinuationTests(unittest.TestCase):
    def build(self, aff, dic, corpus=""):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "hu.aff").write_text(aff, encoding="utf-8")
            (root / "hu.dic").write_text(dic, encoding="utf-8")
            with gzip.open(root / "corpus.gz", "wt", encoding="iso-8859-2") as file:
                file.write(corpus)
            expand_dictionary(
                str(root / "hu.aff"), str(root / "hu.dic"), str(root / "words.txt"),
                audit_path=str(root / "audit.json"),
                corpus_path=str(root / "corpus.gz"),
                lemma_index_dir=str(root / "lemmas"),
            )
            mappings = {}
            for shard in (root / "lemmas").glob("*.tsv.gz"):
                with gzip.open(shard, "rt") as file:
                    for line in file:
                        word, lemmas = line.rstrip().split("\t")
                        mappings[word] = lemmas.split(",")
            return set((root / "words.txt").read_text().splitlines()), mappings, json.loads(
                (root / "audit.json").read_text()
            )

    def test_attested_participle_gets_licensed_unattested_case_and_plural_forms(self):
        words, mappings, audit = self.build("""SET UTF-8
SFX O Y 1
SFX O 0 ó/N . ds:Ó_PRESPART_adj ts:NOM
SFX N Y 4
SFX N 0 t ó is:ACC
SFX N 0 k ó is:PLUR
SFX N 0 kat ó is:PLUR is:ACC
SFX N 0 nak ó is:DAT
SFX X Y 1
SFX X 0 xyz . is:ACC
""", "1\nfáj/O\n", "fájó\t20\t20\t10\t8\n")
        self.assertEqual({"fáj", "fájó", "fájót", "fájók", "fájókat", "fájónak"}, words)
        self.assertEqual(["fáj"], mappings["fájót"])
        self.assertEqual(4, audit["counts"]["raw_suffix_continuation_paths"])

    def test_unattested_derivation_does_not_license_a_family(self):
        words, _, _ = self.build("""SET UTF-8
SFX O Y 1
SFX O 0 ó/N . ds:Ó_PRESPART_adj
SFX N Y 1
SFX N 0 t . is:ACC
""", "1\nfáj/O\n")
        self.assertEqual({"fáj"}, words)

    def test_two_step_limit_conditions_and_terminal_controls(self):
        words, _, _ = self.build("""SET UTF-8
FORBIDDENWORD w
SUBSTANDARD s
NEEDAFFIX x
ONLYINCOMPOUND c
KEEPCASE z
SFX O Y 1
SFX O 0 ó/N . ds:Ó_PRESPART_adj
SFX N Y 8
SFX N 0 t/R ó is:ACC
SFX N 0 k/w ó is:PLUR
SFX N 0 kat/s ó is:PLUR is:ACC
SFX N 0 nak/x ó is:DAT
SFX N 0 val/c ó is:INS
SFX N 0 ban/z ó is:INE
SFX N 0 ra a is:SBL
SFX N 0 s ó ds:S_adj
SFX R Y 1
SFX R 0 ra . is:SBL
""", "1\nfáj/O\n", "fájó\t20\t20\t10\t8\n")
        self.assertEqual({"fáj", "fájó", "fájót"}, words)

    def test_blocked_intermediate_and_blocked_source_descendants_stay_excluded(self):
        words, _, _ = self.build("""SET UTF-8
FORBIDDENWORD w
SFX O Y 1
SFX O 0 ó/N . ds:Ó_PRESPART_adj
SFX N Y 1
SFX N 0 t . is:ACC
""", "4\nfáj/O\nfájó/w\nmar/Ow\nmarót\n",
            "fájó\t20\t20\t10\t8\nmaró\t20\t20\t10\t8\n")
        self.assertEqual({"fáj"}, words)

    def test_possessive_stack_keeps_surface_evidence_gate(self):
        words, _, _ = self.build("""SET UTF-8
SFX O Y 1
SFX O 0 é/N . is:POSS_SG_3
SFX N Y 1
SFX N 0 i . is:POSSESSEE
""", "1\nalma/O\n")
        self.assertIn("almaé", words)
        self.assertNotIn("almaéi", words)

    def test_proper_derivative_family_keeps_surface_evidence_gate(self):
        words, _, _ = self.build("""SET UTF-8
SFX J Y 1
SFX J 0 i . ds:i_PLACE/TIME_adj
SFX O Y 1
SFX O 0 é/N . is:POSS_SG_3
SFX N Y 1
SFX N 0 t . is:ACC
""", "2\nJames/J\tpo:noun_prs\njamesi/O\tpo:adj\n",
            "jamesié\t4\t4\t3\t2\n")
        self.assertIn("jamesié", words)
        self.assertNotIn("jamesiét", words)

    def test_prefix_cross_products_require_both_suffix_rules_to_allow_them(self):
        aff = """SET UTF-8
PFX P Y 1
PFX P 0 el . ip:PREF
SFX O Y 1
SFX O 0 ó/N . ds:Ó_PRESPART_adj
SFX N {cross} 1
SFX N 0 t . is:ACC
"""
        corpus = "fájó\t20\t20\t10\t8\nelfájót\t2\t2\t2\t2\n"
        for cross in ("Y", "N"):
            with self.subTest(cross=cross):
                words, _, _ = self.build(aff.format(cross=cross), "1\nfáj/OP\n", corpus)
                self.assertIn("fájót", words)
                self.assertEqual(cross == "Y", "elfájót" in words)


class DerivedInflectionEvidenceTests(unittest.TestCase):
    def proof(self, accepted, *, approvals=frozenset()):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "test.aff").write_text("""SET UTF-8
FORBIDDENWORD w
SFX O Y 1
SFX O 0 ó/N . ds:Ó_PRESPART_adj
SFX N Y 3
SFX N 0 kat ó is:PLUR is:ACC
SFX N 0 r/R ó is:ACC
SFX N 0 nak/w ó is:DAT
SFX R Y 1
SFX R 0 a . is:ACC
""", encoding="utf-8")
            (root / "test.dic").write_text("1\nfáj/O\n", encoding="utf-8")
            return licensed_inflections_of_accepted_words(
                frozenset(accepted), frozenset({"fájókat", "fájónak", "fájóra", "fájóx"}),
                root / "test.aff", root / "test.dic", approvals,
            )

    def test_requires_accepted_anchor_licensed_path_and_terminal_flags(self):
        self.assertEqual({"fájókat": "fájó"}, self.proof({"fájó"}))
        self.assertEqual({}, self.proof({"fáj"}))

    def test_surface_approval_does_not_license_a_family(self):
        self.assertEqual({}, self.proof({"fájó"}, approvals=frozenset({"fájó"})))

    def decision(self, word="fájókat", *, morph=None, **overrides):
        evidence = MorphEvidence(recognized=True, nonproper=True, derivation_only=True, lemma_agreement=True)
        args = dict(current_candidate=True, current_direct=False, morphdb_direct=False,
                    accepted_derived_inflection=True)
        args.update(overrides)
        return decide_word(word, CorpusEvidence(), morph or evidence, **args)

    def test_licensed_inflection_is_not_a_new_unattested_derivation(self):
        self.assertTrue(self.decision().accepted)
        self.assertFalse(self.decision(accepted_derived_inflection=False).accepted)

    def test_removals_and_special_temporal_suffix_remain_authoritative(self):
        self.assertFalse(self.decision(explicit_surface_removal=True).accepted)
        self.assertFalse(self.decision(explicit_lemma_removal=True).accepted)
        self.assertFalse(self.decision(source_policy_blocked=True).accepted)
        self.assertFalse(self.decision(word="fájókor").accepted)

    def test_requires_corroboration_and_does_not_rescue_possessives_or_prefixes(self):
        base = MorphEvidence(recognized=True, nonproper=True, derivation_only=True, lemma_agreement=True)
        for changes in ({"proper_only": True, "nonproper": False}, {"lemma_agreement": False},
                        {"possessive_only": True}, {"plural_possessive_only": True}, {"prefix_only": True}):
            with self.subTest(changes=changes):
                self.assertFalse(self.decision(morph=replace(base, **changes)).accepted)


if __name__ == "__main__":
    unittest.main()
