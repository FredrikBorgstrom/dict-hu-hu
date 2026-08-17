import unittest
from pathlib import Path

from build_evidence_wordlist import (
    CorpusEvidence,
    MorphEvidence,
    decide_word,
    parse_morphdb_block,
)


class MorphdbParsingTests(unittest.TestCase):
    def test_identifies_proper_name_only_derivation(self):
        evidence = parse_morphdb_block(
            "luki",
            [
                "luki  fl:aH st:Luki /NOUN [MET_ATTRIB]/ADJ fl:gs",
                "luki  fl:bŠ st:Luk /NOUN [MET_ATTRIB]/ADJ fl:ao",
            ],
            frozenset({"luk"}),
        )

        self.assertTrue(evidence.recognized)
        self.assertTrue(evidence.proper_only)
        self.assertFalse(evidence.nonproper)
        self.assertFalse(evidence.lemma_agreement)

    def test_identifies_plural_possessive_stack(self):
        evidence = parse_morphdb_block(
            "miibe",
            ["miibe  st:mi /NOUN <PLUR><POSS><CAS<ILL>>"],
            frozenset({"mi"}),
        )

        self.assertTrue(evidence.nonproper)
        self.assertTrue(evidence.possessive_only)
        self.assertTrue(evidence.plural_possessive_only)
        self.assertTrue(evidence.lemma_agreement)
        self.assertFalse(evidence.safe_inflection)

    def test_ordinary_analysis_wins_over_possessive_homograph(self):
        evidence = parse_morphdb_block(
            "almát",
            [
                "almát  st:alm alom/NOUN <POSS><CAS<ACC>>",
                "almát  st:alma /NOUN <CAS<ACC>>",
            ],
            frozenset({"alma"}),
        )

        self.assertTrue(evidence.safe_inflection)
        self.assertFalse(evidence.possessive_only)
        self.assertTrue(evidence.lemma_agreement)

    def test_anaphoric_possessee_stack_is_high_risk(self):
        evidence = parse_morphdb_block(
            "atyákéinak",
            ["atyákéinak  st:atya /NOUN <PLUR><ANP<PLUR>><CAS<DAT>>"],
            frozenset({"atya"}),
        )

        self.assertTrue(evidence.possessive_only)
        self.assertTrue(evidence.plural_possessive_only)
        self.assertFalse(evidence.safe_inflection)

    def test_unknown_word_has_no_analysis(self):
        evidence = parse_morphdb_block("box", ["box"], frozenset())
        self.assertEqual(MorphEvidence(), evidence)


class EvidencePolicyTests(unittest.TestCase):
    def test_accepts_reviewed_surface_addition_without_source_evidence(self):
        decision = decide_word(
            "box",
            CorpusEvidence(),
            MorphEvidence(),
            current_candidate=False,
            current_direct=False,
            morphdb_direct=False,
            explicit_addition=True,
        )
        self.assertEqual(
            (True, "reviewed_surface_addition"),
            (decision.accepted, decision.reason),
        )

    def test_rejects_two_letter_consonant_abbreviation_shape(self):
        decision = decide_word(
            "sz",
            CorpusEvidence(1000, 1000, 1000, 1000),
            MorphEvidence(recognized=True, nonproper=True, safe_inflection=True),
            current_candidate=False,
            current_direct=False,
            morphdb_direct=True,
        )
        self.assertEqual(
            (False, "written_abbreviation_shape"),
            (decision.accepted, decision.reason),
        )

    def test_rejects_proper_name_only_even_with_corpus_usage(self):
        decision = decide_word(
            "luki",
            CorpusEvidence(21, 15, 7, 3),
            MorphEvidence(recognized=True, proper_only=True),
            current_candidate=True,
            current_direct=False,
            morphdb_direct=False,
        )
        self.assertEqual((False, "morphdb_proper_name_only"), (decision.accepted, decision.reason))

    def test_rejects_weak_plural_possessive(self):
        decision = decide_word(
            "mii",
            CorpusEvidence(286, 49, 13, 7),
            MorphEvidence(
                recognized=True,
                nonproper=True,
                possessive_only=True,
                plural_possessive_only=True,
                lemma_agreement=True,
            ),
            current_candidate=True,
            current_direct=False,
            morphdb_direct=False,
        )
        self.assertEqual((False, "weak_plural_possessive"), (decision.accepted, decision.reason))

    def test_accepts_strongly_attested_prefixed_verb(self):
        decision = decide_word(
            "bement",
            CorpusEvidence(5593, 5552, 4690, 3118),
            MorphEvidence(
                recognized=True,
                nonproper=True,
                prefix_only=True,
                lemma_agreement=True,
                parts_of_speech=("VERB",),
            ),
            current_candidate=True,
            current_direct=False,
            morphdb_direct=False,
        )
        self.assertEqual(
            (True, "attested_prefix_combination"),
            (decision.accepted, decision.reason),
        )

    def test_accepts_cross_analyzer_basic_inflection_without_usage(self):
        decision = decide_word(
            "almának",
            CorpusEvidence(),
            MorphEvidence(
                recognized=True,
                nonproper=True,
                safe_inflection=True,
                lemma_agreement=True,
                parts_of_speech=("NOUN",),
            ),
            current_candidate=True,
            current_direct=False,
            morphdb_direct=False,
        )
        self.assertEqual(
            (True, "cross_analyzer_basic_inflection"),
            (decision.accepted, decision.reason),
        )

    def test_requires_strong_clean_usage_for_morphdb_only_addition(self):
        weak = decide_word(
            "újszó",
            CorpusEvidence(100, 50, 20, 9),
            MorphEvidence(recognized=True, nonproper=True),
            current_candidate=False,
            current_direct=False,
            morphdb_direct=True,
        )
        strong = decide_word(
            "újszó",
            CorpusEvidence(100, 50, 20, 10),
            MorphEvidence(recognized=True, nonproper=True),
            current_candidate=False,
            current_direct=False,
            morphdb_direct=True,
        )
        self.assertFalse(weak.accepted)
        self.assertEqual("attested_morphdb_headword_addition", strong.reason)
        self.assertTrue(strong.accepted)


class PublishedCandidateRegressionTests(unittest.TestCase):
    def test_reported_words_follow_evidence_policy(self):
        candidate_path = (
            Path(__file__).parent
            / "candidate"
            / "hungarian_hu_hu_evidence_candidate.txt"
        )
        words = set(candidate_path.read_text(encoding="utf-8").splitlines())

        self.assertTrue(
            {"beír", "bement", "faxos", "kijött", "lófő", "mi"}.issubset(words)
        )
        self.assertTrue(
            {"luki", "lófőm", "mii", "miibe", "miik"}.isdisjoint(words)
        )
        self.assertIn("box", words)


if __name__ == "__main__":
    unittest.main()
