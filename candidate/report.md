# Hungarian evidence-scored candidate report

This is a local candidate for review. It does not replace or deploy the production dictionary.

## Summary

- Accepted words: **863,174**
- Current words removed by the candidate policy: **1,834,480**
- Strongly attested morphdb.hu headword additions: **7,323**
- Candidate SHA-256: `1c6898b97702fed07738241a0f77da7823ddac3962634184141eeeb83b4e80c5`

## Decisions by evidence rule

| Rule | Words |
|---|---:|
| `weak_plural_possessive` | 766,657 |
| `weak_possessive` | 596,423 |
| `quality_8_corpus_core` | 362,751 |
| `no_independent_evidence` | 320,129 |
| `cross_analyzer_basic_inflection` | 288,781 |
| `weak_derivation` | 88,200 |
| `insufficient_usage_or_risky_inflection` | 68,548 |
| `attested_possessive` | 62,723 |
| `attested_derivation` | 52,175 |
| `corroborated_corpus_singleton` | 50,135 |
| `attested_prefix_combination` | 20,083 |
| `strong_plural_possessive_usage` | 13,690 |
| `morphdb_proper_name_only` | 12,874 |
| `weak_prefix_combination` | 8,128 |
| `attested_morphdb_headword_addition` | 7,122 |
| `direct_source_form` | 5,709 |
| `written_abbreviation_shape` | 5 |
| `required_one_letter` | 4 |
| `reviewed_surface_addition` | 1 |

## Reported and diagnostic words

| Word | Decision | Reason | Quality-8 | Quality-4 |
|---|---|---|---:|---:|
| `beír` | accept | `quality_8_corpus_core` | 661 | 389 |
| `bement` | accept | `attested_prefix_combination` | 4690 | 3118 |
| `box` | accept | `reviewed_surface_addition` | 1905 | 400 |
| `faxos` | accept | `attested_derivation` | 56 | 40 |
| `kijött` | accept | `attested_prefix_combination` | 5619 | 3042 |
| `luki` | reject | `morphdb_proper_name_only` | 7 | 3 |
| `lófő` | accept | `quality_8_corpus_core` | 51 | 26 |
| `lófőm` | reject | `weak_possessive` | 0 | 0 |
| `mi` | accept | `quality_8_corpus_core` | 797905 | 478960 |
| `mii` | reject | `weak_plural_possessive` | 13 | 7 |
| `miibe` | reject | `weak_plural_possessive` | 0 | 0 |
| `miik` | reject | `weak_plural_possessive` | 0 | 0 |

## Limitations

- Corpus occurrence is evidence of usage, not proof of lexical validity.
- morphdb.hu partly incorporates Magyar Ispell, so it is corroborating rather than fully independent evidence.
- The public morphdb.hu release is from 2006; modern vocabulary depends primarily on Magyar Ispell and corpus evidence.
- Lowercased surfaces can hide some names. Proper-name-only morphdb analyses are rejected, but no automated method can identify every name collision.
