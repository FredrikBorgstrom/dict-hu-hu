import tempfile
import unittest
from pathlib import Path

from build_evidence_wordlist import (
    CorpusEvidence,
    MorphEvidence,
    decide_word,
    expand_lemma_removals,
    load_morphdb_source_inventory,
    parse_morphdb_block,
)
from process_words import _write_lemma_index


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


class MorphdbSourceInventoryTests(unittest.TestCase):
    def test_excludes_pseudoroot_only_tokens_but_preserves_homographs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            aff_path = root / "morphdb_hu.aff"
            dic_path = root / "morphdb_hu.dic"
            aff_path.write_text(
                "SET ISO8859-2\nFLAG long\nPSEUDOROOT ac\n",
                encoding="iso-8859-2",
            )
            dic_path.write_text(
                "7\n"
                "tüz/xyac\ttűz/NOUN\n"
                "ezr/ac\tezer/NUM\n"
                "ifj/zzac\tú/NOUN\n"
                "közl/ac\tközöl\n"
                "való/xy\tvaló/ADJ\n"
                "hom/ac\thom/NOUN\n"
                "hom/xy\thom/NOUN\n",
                encoding="iso-8859-2",
            )

            standalone, pseudoroot_only = load_morphdb_source_inventory(
                aff_path, dic_path
            )

        self.assertEqual(frozenset({"való", "hom"}), standalone)
        self.assertEqual(
            frozenset({"tüz", "ezr", "ifj", "közl"}), pseudoroot_only
        )


class LemmaRemovalTests(unittest.TestCase):
    def test_expands_lemma_family_but_preserves_allowed_homograph(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mappings_path = root / "mappings.tsv"
            mappings_path.write_text(
                "as\tas\n"
                "asok\tas\n"
                "hom\thom\n"
                "hom\tremoved\n"
                "lex\tlex\n",
                encoding="utf-8",
            )
            index_dir = root / "index"
            _write_lemma_index(
                str(mappings_path),
                str(index_dir),
                blocked_surfaces=set(),
            )

            removals, seen = expand_lemma_removals(
                index_dir,
                frozenset({"as", "lex", "removed"}),
            )

        self.assertEqual(frozenset({"as", "asok", "lex", "removed"}), removals)
        self.assertEqual(frozenset({"as", "lex", "removed"}), seen)


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

    def test_rejects_reviewed_surface_and_lemma_removals(self):
        surface = decide_word(
            "tá",
            CorpusEvidence(100, 100, 100, 100),
            MorphEvidence(recognized=True, nonproper=True),
            current_candidate=True,
            current_direct=False,
            morphdb_direct=True,
            explicit_surface_removal=True,
        )
        lemma = decide_word(
            "asok",
            CorpusEvidence(100, 100, 100, 100),
            MorphEvidence(recognized=True, nonproper=True),
            current_candidate=True,
            current_direct=False,
            morphdb_direct=False,
            explicit_lemma_removal=True,
        )
        self.assertEqual((False, "reviewed_surface_removal"), (surface.accepted, surface.reason))
        self.assertEqual((False, "reviewed_lemma_removal"), (lemma.accepted, lemma.reason))

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

    def test_rejects_source_policy_blocked_surface_despite_strong_evidence(self):
        decision = decide_word(
            "szja",
            CorpusEvidence(1293, 1285, 1193, 981),
            MorphEvidence(
                recognized=True,
                nonproper=True,
                safe_inflection=True,
            ),
            current_candidate=True,
            current_direct=False,
            morphdb_direct=False,
            source_policy_blocked=True,
        )
        self.assertEqual(
            (False, "source_policy_blocked_surface"),
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

    def test_rejects_unattested_generated_kor_form(self):
        decision = decide_word(
            "exkor",
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
            (False, "unattested_generated_kor_form"),
            (decision.accepted, decision.reason),
        )

    def test_accepts_attested_generated_kor_form(self):
        decision = decide_word(
            "ablakkor",
            CorpusEvidence(1, 0, 0, 0),
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

    def test_preserves_unattested_direct_headword_ending_in_kor(self):
        decision = decide_word(
            "kor",
            CorpusEvidence(),
            MorphEvidence(
                recognized=True,
                nonproper=True,
                safe_inflection=True,
                lemma_agreement=True,
                parts_of_speech=("NOUN",),
            ),
            current_candidate=True,
            current_direct=True,
            morphdb_direct=False,
        )
        self.assertEqual(
            (True, "direct_source_form"),
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

    def test_rejects_unrecognized_morphdb_source_token(self):
        decision = decide_word(
            "álstem",
            CorpusEvidence(1000, 1000, 1000, 1000),
            MorphEvidence(),
            current_candidate=False,
            current_direct=False,
            morphdb_direct=True,
        )
        self.assertEqual(
            (False, "no_independent_evidence"),
            (decision.accepted, decision.reason),
        )

    def test_rejects_promoted_pseudoroots_despite_strong_corpus_usage(self):
        for word in ("tüz", "ezr", "ifj", "közl"):
            with self.subTest(word=word):
                decision = decide_word(
                    word,
                    CorpusEvidence(1000, 1000, 1000, 1000),
                    MorphEvidence(),
                    current_candidate=True,
                    current_direct=False,
                    morphdb_direct=False,
                    morphdb_nonstandalone=True,
                )
                self.assertEqual(
                    (False, "morphdb_nonstandalone_source"),
                    (decision.accepted, decision.reason),
                )

    def test_preserves_valid_current_source_homograph(self):
        decision = decide_word(
            "hom",
            CorpusEvidence(),
            MorphEvidence(),
            current_candidate=True,
            current_direct=True,
            morphdb_direct=False,
            morphdb_nonstandalone=True,
        )
        self.assertEqual(
            (True, "direct_source_form"),
            (decision.accepted, decision.reason),
        )

    def test_preserves_pseudoroot_spelling_with_standalone_analysis(self):
        decision = decide_word(
            "hom",
            CorpusEvidence(10, 10, 10, 10),
            MorphEvidence(recognized=True, nonproper=True),
            current_candidate=True,
            current_direct=False,
            morphdb_direct=False,
            morphdb_nonstandalone=True,
        )
        self.assertEqual(
            (True, "quality_8_corpus_core"),
            (decision.accepted, decision.reason),
        )


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
            {
                "exkor",
                "go",
                "luki",
                "lófőm",
                "mii",
                "miibe",
                "miik",
                "szja",
                "tsz",
                "uv",
            }.isdisjoint(words)
        )
        self.assertIn("box", words)
        self.assertTrue(
            {
                "al",
                "as",
                "aú",
                "cal",
                "cimet",
                "cos",
                "cosec",
                "ctg",
                "dag",
                "dzs",
                "jade",
                "kcal",
                "kib",
                "lex",
                "mbar",
                "mmol",
                "márc",
                "mé",
                "omega",
                "org",
                "sin",
                "stb",
                "tá",
                "vu",
                "words",
                "yacht",
                "zu",
                "zsüri",
                "ál",
                "épit",
            }.isdisjoint(words)
        )


if __name__ == "__main__":
    unittest.main()
