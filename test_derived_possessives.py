"""Regressions for accepted derived nouns and their possessive families."""

import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from build_evidence_wordlist import CorpusEvidence, MorphEvidence, decide_word
from derived_possessives import (analysis_signatures, licensed_anchored_possessives,
                                 corroborate_paths, analyze_anchors_and_possessives)


class DerivedPossessiveSourceTests(unittest.TestCase):
    def source_paths(self, *, accepted=frozenset({"szörfös", "kerekes"}),
                     approvals=frozenset(), removals=frozenset()):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hu.aff").write_text("""SET UTF-8
FORBIDDENWORD w
NEEDAFFIX x
SFX S Y 1
SFX S 0 ös/P . ds:s_OCCUPATION_noun ts:NOM
SFX Q Y 1
SFX Q 0 ös/Pw . ds:s_OCCUPATION_noun ts:NOM
SFX V Y 1
SFX V 0 ös/P . ds:s_MANNER_adv
SFX P Y 7
SFX P 0 ük . is:POSS_PL_3 is:NOM
SFX P 0 ét . is:POSS_SG_3 is:ACC
SFX P 0 eik . is:PLUR is:POSS_PL_3
SFX P 0 üké . is:POSS_PL_3 is:POSSESSEE
SFX P 0 é/w . is:POSS_SG_3 is:NOM
SFX P 0 ém/x . is:POSS_SG_1 is:NOM
SFX P 0 ükös . ds:s_ATTRIBUTE_adj
""", encoding="utf-8")
            (root / "hu.dic").write_text("7\nszörf/S\tpo:noun\n"
                "kerekes/P\tst:kerék po:noun\n"
                "Péter/S\tpo:noun_prs\ntil/Sw\tpo:noun\n"
                "rossz/Q\tpo:noun\nmi/P\tpo:pron\nfut/V\tpo:verb\n", encoding="utf-8")
            candidates = frozenset({"szörfösük", "szörfösét", "szörföseik", "szörfösüké",
                "szörfösé", "szörfösém", "szörfösükös", "kerekesük",
                "péterösük", "rosszösük", "miük", "futösük", "szörfösükük", "tilösük"})
            return licensed_anchored_possessives(accepted, candidates, root / "hu.aff",
                                                 root / "hu.dic", approvals, removals)

    def test_accepted_derivation_licenses_only_ordinary_terminal_possessive(self):
        self.assertEqual({"szörfösük": frozenset({("szörfös", "szörf")}),
                          "szörfösét": frozenset({("szörfös", "szörf")}),
                          "kerekesük": frozenset({("kerekes", "kerék")})}, self.source_paths())

    def test_root_acceptance_alone_does_not_license_new_derivations(self):
        self.assertEqual({}, self.source_paths(accepted=frozenset({"szörf", "kerék"})))

    def test_surface_approval_and_lemma_removal_do_not_license_families(self):
        self.assertEqual({}, self.source_paths(approvals=frozenset({"szörfös", "kerekes"})))
        self.assertEqual({}, self.source_paths(removals=frozenset({"szörf", "kerék"})))
        self.assertEqual({}, self.source_paths(removals=frozenset({"szörfös", "kerekes"})))

    def test_proper_pronoun_forbidden_and_non_nominal_paths_stay_excluded(self):
        self.assertEqual({}, self.source_paths(accepted=frozenset({"péterös", "mi", "rosszös", "futös", "tilös"})))


class DerivedPossessiveAnalysisTests(unittest.TestCase):
    def signatures(self, tags="", *, word="szörfös", root="szörf", derivation="[ATTRIB]/ADJ", possessive=False):
        return analysis_signatures(word, [f"{word} st:{root} /NOUN {derivation} fl:dH {tags}"], possessive=possessive)

    def test_all_six_owners_preserve_the_accepted_lexical_analysis(self):
        bare = self.signatures()
        for tag in ("<POSS<1>>", "<POSS<2>>", "<POSS>", "<POSS<1><PLUR>>", "<POSS<2><PLUR>>", "<POSS<PLUR>>"):
            with self.subTest(tag=tag):
                child = self.signatures(tag + "<CAS<ACC>>", word="szörfösük", possessive=True)
                self.assertEqual(bare, child)
                paths = {"szörfösük": frozenset({("szörfös", "szörf")})}
                self.assertEqual(paths, corroborate_paths(paths, {"szörfös": (bare, frozenset()), "szörfösük": (frozenset(), child)}))

    def test_plural_objects_anaphoric_stacks_and_malformed_analyses_do_not_qualify(self):
        for tags in ("<PLUR><POSS>", "<POSS><ANP>", "<POSS><POSS>",
                     "<POSS><OTHER>", "<POSS<PLUR>", "<POSS>>", "<POSS>[DERIV]/NOUN"):
            with self.subTest(tags=tags):
                self.assertEqual(frozenset(), self.signatures(tags, possessive=True))

    def test_same_root_but_different_derivation_does_not_corroborate(self):
        paths = {"child": frozenset({("szörfös", "szörf")})}
        for child in (self.signatures("<POSS>", derivation="[ABSTRACT]/NOUN", possessive=True),
                      self.signatures("<POSS>", root="other", possessive=True)):
            self.assertEqual({}, corroborate_paths(paths, {"szörfös": (self.signatures(), frozenset()),
                                                          "child": (frozenset(), child)}))

    def test_bare_anchor_must_be_uninflected_nonproper_and_unprefixed(self):
        self.assertEqual(frozenset(), self.signatures("<PLUR>"))
        self.assertEqual(frozenset(), self.signatures(root="Péter"))
        self.assertEqual(frozenset(), self.signatures(derivation="/PREV+[ATTRIB]/ADJ"))

    def test_plain_adjective_does_not_broaden_the_derived_word_policy(self):
        bare = self.signatures(derivation="/ADJ")
        child = self.signatures("<POSS>", derivation="/ADJ", possessive=True)
        self.assertEqual({}, corroborate_paths({"child": {("szörfös", "szörf")}},
                         {"szörfös": (bare, frozenset()), "child": (frozenset(), child)}))

    def test_cache_reads_proof_and_dictionary_change_invalidates_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            aff, dic = root / "hu.aff", root / "hu.dic"
            aff.write_text("aff-v1"); dic.write_text("dic-v1")
            response = subprocess.CompletedProcess([], 0, "szörfös st:szörf /NOUN [ATTRIB]/ADJ\n\nszörfösük st:szörf /NOUN [ATTRIB]/ADJ <POSS<PLUR>>\n\n", "")
            with patch("derived_possessives.subprocess.run", return_value=response) as run:
                args = (frozenset({"szörfös", "szörfösük"}), aff, dic, "hunspell", root)
                first = analyze_anchors_and_possessives(*args)
                self.assertEqual(first, analyze_anchors_and_possessives(*args))
                self.assertEqual(1, run.call_count)
                aff.write_text("aff-v2")
                self.assertEqual(first, analyze_anchors_and_possessives(*args))
                self.assertEqual(2, run.call_count)


class DerivedPossessiveDecisionTests(unittest.TestCase):
    def decision(self, *, word="szörfösük", evidence=None, **overrides):
        evidence = evidence or MorphEvidence(recognized=True, nonproper=True, derivation_only=True,
                                             possessive_only=True, lemma_agreement=True)
        args = dict(current_candidate=True, current_direct=False, morphdb_direct=False, accepted_derived_possessive=True)
        args.update(overrides)
        return decide_word(word, CorpusEvidence(), evidence, **args)

    def test_verified_derived_possessive_does_not_need_surface_corpus_occurrences(self):
        self.assertEqual("cross_analyzer_possessive_of_accepted_derived_word", self.decision().reason)
        self.assertTrue(self.decision().accepted)
        self.assertFalse(self.decision(accepted_derived_possessive=False).accepted)

    def test_existing_rejections_and_temporal_gate_remain_authoritative(self):
        for flag in ("source_policy_blocked", "explicit_surface_removal", "explicit_lemma_removal"):
            self.assertFalse(self.decision(**{flag: True}).accepted)
        self.assertFalse(self.decision(word="szörfösömkor").accepted)
        self.assertFalse(self.decision(current_candidate=False).accepted)

    def test_cached_analyzer_corroboration_is_still_required(self):
        base = MorphEvidence(recognized=True, nonproper=True, derivation_only=True,
                             possessive_only=True, lemma_agreement=True)
        for overrides in ({"recognized": False}, {"nonproper": False}, {"proper_only": True},
                          {"lemma_agreement": False}, {"prefix_only": True}):
            self.assertFalse(self.decision(evidence=replace(base, **overrides)).accepted)


if __name__ == "__main__":
    unittest.main()
