"""Coverage for ordinary possessives without discarding the risky-form gates."""

import tempfile
import unittest
import gzip
from pathlib import Path

from build_evidence_wordlist import (
    CorpusEvidence, MorphEvidence, decide_word, licensed_possessives_of_accepted_nouns,
    parse_morphdb_block, top_level_morph_tags,
    iter_cached_morph_evidence,
)


class PossessiveMorphologyTests(unittest.TestCase):
    def parse(self, word, morphology, lemma="füge"):
        return parse_morphdb_block(word, [f"{word} st:{lemma} /NOUN {morphology}"], frozenset({lemma}))

    def test_several_owners_do_not_mean_several_possessions(self):
        for person in (1, 2, 3):
            with self.subTest(person=person):
                evidence = self.parse("fügétek", f"<POSS<{person}><PLUR>>")
                self.assertTrue(evidence.possessive_only)
                self.assertFalse(evidence.plural_possessive_only)
                self.assertEqual(("füge",), evidence.ordinary_possessive_lemmas)

    def test_plural_possession_is_distinct_and_preserves_cases(self):
        evidence = self.parse("fügéiteket", "<PLUR><POSS<2><PLUR>><CAS<ACC>>")
        self.assertTrue(evidence.plural_possessive_only)
        self.assertEqual(("füge",), evidence.ordinary_possessive_lemmas)

    def test_anaphoric_plural_keeps_strong_evidence_requirement(self):
        evidence = self.parse("fügééi", "<ANP<PLUR>>")
        self.assertTrue(evidence.plural_possessive_only)
        self.assertEqual((), evidence.ordinary_possessive_lemmas)

    def test_derivation_and_semantic_tags_do_not_qualify(self):
        for tags in ("[ATTRIB]/NOUN <POSS>", "<POSS><ANP>", "<POSS><POSS>",
                     "<POSS><OTHER>", "<POSS<2><PLUR>"):
            with self.subTest(tags=tags):
                self.assertEqual((), self.parse("example", tags).ordinary_possessive_lemmas)
        self.assertEqual((), top_level_morph_tags("<POSS>>"))

    def test_same_analysis_must_supply_noun_possessive_and_lemma(self):
        evidence = parse_morphdb_block("surface", [
            "surface st:füge /NOUN [DERIV]/NOUN <POSS>",
            "surface st:other /NOUN <POSS>",
        ], frozenset({"füge"}))
        self.assertTrue(evidence.lemma_agreement)
        self.assertEqual((), evidence.ordinary_possessive_lemmas)

    def test_cache_roundtrip_preserves_analysis_proof_and_rejects_old_schema(self):
        evidence = self.parse("fügétek", "<POSS<2><PLUR>>")
        self.assertEqual(evidence, MorphEvidence.from_cache_fields(list(evidence.as_cache_fields())))
        with self.assertRaises(ValueError):
            MorphEvidence.from_cache_fields(list(evidence.as_cache_fields())[:-1])

    def test_written_cache_can_be_read_and_old_header_is_rejected(self):
        evidence = self.parse("fügétek", "<POSS<2><PLUR>>")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "analysis.tsv.gz"
            for schema in (4, 3):
                with gzip.open(path, "wt") as output:
                    output.write(f"# schema={schema}\tcandidate_sha256=test\n")
                    output.write("\t".join(("fügétek", *evidence.as_cache_fields())) + "\n")
                if schema == 4:
                    self.assertEqual([("fügétek", evidence)], list(iter_cached_morph_evidence(path)))
                else:
                    with self.assertRaises(ValueError):
                        list(iter_cached_morph_evidence(path))


class PossessiveSourceProofTests(unittest.TestCase):
    def proof(self, *, accepted=frozenset({"füge", "kéz"}), approvals=frozenset(), removals=frozenset()):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "hu.aff").write_text("""SET UTF-8
FORBIDDENWORD w
NEEDAFFIX x
SFX P Y 7
SFX P e étek e is:POSS_PL_2 is:NOM
SFX P e éteket e is:POSS_PL_2 is:ACC
SFX P e éitek e is:PLUR is:POSS_PL_2 is:NOM
SFX P e éiteknek e is:PLUR is:POSS_PL_2 is:DAT
SFX P e éitekre e is:PLUR is:POSS_PL_2 is:SBL
SFX P e éteké e is:POSS_PL_2 is:POSSESSEE
SFX P e éteknek/w e is:POSS_PL_2 is:DAT
SFX K Y 1
SFX K 0 etek . is:POSS_PL_2
""", encoding="utf-8")
            (root / "hu.dic").write_text("5\nfüge/P\tpo:noun\nkez/Kx\tst:kéz po:noun\n"
                "tilte/Pw\tpo:noun\nneve/P\tpo:noun_prs\nmie/P\tpo:pron\n", encoding="utf-8")
            candidates = frozenset({"fügétek", "fügéteket", "fügéitek", "fügéiteknek", "fügéitekre", "fügéteké",
                                    "fügéteknek", "kezetek", "tiltétek", "nevétek", "miétek", "fügetek"})
            return licensed_possessives_of_accepted_nouns(
                accepted, candidates, root / "hu.aff", root / "hu.dic", approvals, removals)

    def test_licensed_vowel_change_case_and_internal_stem_preserve_stack_gates(self):
        self.assertEqual({"fügétek": frozenset({"füge"}), "fügéteket": frozenset({"füge"}),
                          "kezetek": frozenset({"kéz"})}, self.proof())

    def test_requires_independently_accepted_anchor(self):
        self.assertEqual({}, self.proof(accepted=frozenset()))
        self.assertEqual({}, self.proof(approvals=frozenset({"füge", "kéz"})))
        self.assertEqual({}, self.proof(removals=frozenset({"füge", "kéz"})))

    def test_rejected_flags_proper_names_and_pronouns_do_not_license_families(self):
        self.assertEqual({}, self.proof(accepted=frozenset({"tilte", "neve", "mie"})))


class PossessiveDecisionTests(unittest.TestCase):
    def decision(self, *, word="fügétek", evidence=None, **overrides):
        morph = evidence or parse_morphdb_block(word, [f"{word} st:füge /NOUN <POSS<2><PLUR>>"], frozenset({"füge"}))
        args = dict(current_candidate=True, current_direct=False, morphdb_direct=False,
                    licensed_possessive_lemmas=frozenset({"füge"}))
        args.update(overrides)
        return decide_word(word, CorpusEvidence(), morph, **args)

    def test_ordinary_possessive_needs_no_exact_surface_corpus_frequency(self):
        self.assertEqual("cross_analyzer_possessive_of_accepted_noun", self.decision().reason)
        self.assertTrue(self.decision().accepted)

    def test_source_path_same_lemma_and_independent_analysis_required(self):
        for changes in ({"licensed_possessive_lemmas": frozenset()},
                        {"licensed_possessive_lemmas": frozenset({"alma"})},
                        {"current_candidate": False}):
            with self.subTest(changes=changes):
                self.assertFalse(self.decision(**changes).accepted)
        for evidence in (MorphEvidence(), MorphEvidence(recognized=True, proper_only=True),
                         MorphEvidence(recognized=True, nonproper=True, possessive_only=True)):
            self.assertFalse(self.decision(evidence=evidence).accepted)

    def test_removal_and_temporal_suffix_rules_still_apply(self):
        for flag in ("source_policy_blocked", "explicit_surface_removal", "explicit_lemma_removal"):
            self.assertFalse(self.decision(**{flag: True}).accepted)
        self.assertFalse(self.decision(word="fügémkor").accepted)


if __name__ == "__main__":
    unittest.main()
