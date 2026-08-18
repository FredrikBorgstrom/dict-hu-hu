# Hungarian evidence-scored candidate report

This is a local candidate for review. It does not replace or deploy the production dictionary.

## Summary

- Accepted words: **862,910**
- Current words removed by the candidate policy: **264**
- Strongly attested morphdb.hu headword additions: **0**
- Candidate SHA-256: `70022b2168bd31c3e5ddf84ba488222c16d23dd8393e3aa772301d3f2e14e9aa`

## Decisions by evidence rule

| Rule | Words |
|---|---:|
| `quality_8_corpus_core` | 369,609 |
| `cross_analyzer_basic_inflection` | 288,781 |
| `attested_possessive` | 62,723 |
| `attested_derivation` | 52,175 |
| `corroborated_corpus_singleton` | 50,135 |
| `attested_prefix_combination` | 20,083 |
| `strong_plural_possessive_usage` | 13,690 |
| `direct_source_form` | 5,709 |
| `weak_prefix_combination` | 2,627 |
| `morphdb_nonstandalone_source` | 264 |
| `insufficient_usage_or_risky_inflection` | 238 |
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
| `luki` | not a candidate | — | 0 | 0 |
| `lófő` | accept | `quality_8_corpus_core` | 51 | 26 |
| `lófőm` | not a candidate | — | 0 | 0 |
| `mi` | accept | `quality_8_corpus_core` | 797905 | 478960 |
| `mii` | not a candidate | — | 0 | 0 |
| `miibe` | not a candidate | — | 0 | 0 |
| `miik` | not a candidate | — | 0 | 0 |

## Limitations

- Corpus occurrence is evidence of usage, not proof of lexical validity.
- morphdb.hu partly incorporates Magyar Ispell, so it is corroborating rather than fully independent evidence.
- The public morphdb.hu release is from 2006; modern vocabulary depends primarily on Magyar Ispell and corpus evidence.
- Lowercased surfaces can hide some names. Proper-name-only morphdb analyses are rejected, but no automated method can identify every name collision.
