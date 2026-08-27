# Hungarian evidence-scored candidate report

This is a local candidate for review. It does not replace or deploy the production dictionary.

## Summary

- Accepted words: **846,384**
- Current words removed by the candidate policy: **13**
- Strongly attested morphdb.hu headword additions: **0**
- Candidate SHA-256: `c301020e41b4caa74cfabfcbf3693c68ecef7d7ab139b2fe44a0387cd9c7713b`

## Decisions by evidence rule

| Rule | Words |
|---|---:|
| `quality_8_corpus_core` | 369,556 |
| `cross_analyzer_basic_inflection` | 272,350 |
| `attested_possessive` | 62,718 |
| `attested_derivation` | 52,146 |
| `corroborated_corpus_singleton` | 50,128 |
| `attested_prefix_combination` | 20,083 |
| `strong_plural_possessive_usage` | 13,690 |
| `direct_source_form` | 5,708 |
| `weak_prefix_combination` | 2,627 |
| `insufficient_usage_or_risky_inflection` | 238 |
| `reviewed_surface_removal` | 18 |
| `written_abbreviation_shape` | 5 |
| `required_one_letter` | 4 |
| `reviewed_surface_addition` | 1 |

## Reported and diagnostic words

| Word | Decision | Reason | Quality-8 | Quality-4 |
|---|---|---|---:|---:|
| `al` | not a candidate | — | 0 | 0 |
| `as` | not a candidate | — | 0 | 0 |
| `aú` | reject | `reviewed_surface_removal` | 23 | 11 |
| `beír` | accept | `quality_8_corpus_core` | 661 | 389 |
| `bement` | accept | `attested_prefix_combination` | 4690 | 3118 |
| `box` | accept | `reviewed_surface_addition` | 1905 | 400 |
| `exkor` | not a candidate | — | 0 | 0 |
| `faxos` | accept | `attested_derivation` | 56 | 40 |
| `kijött` | accept | `attested_prefix_combination` | 5619 | 3042 |
| `lex` | not a candidate | — | 0 | 0 |
| `luki` | not a candidate | — | 0 | 0 |
| `lófő` | accept | `quality_8_corpus_core` | 51 | 26 |
| `lófőm` | not a candidate | — | 0 | 0 |
| `mé` | reject | `reviewed_surface_removal` | 632 | 178 |
| `mi` | accept | `quality_8_corpus_core` | 797905 | 478960 |
| `mii` | not a candidate | — | 0 | 0 |
| `miibe` | not a candidate | — | 0 | 0 |
| `miik` | not a candidate | — | 0 | 0 |
| `tá` | reject | `reviewed_surface_removal` | 537 | 149 |
| `vu` | not a candidate | — | 0 | 0 |
| `zu` | reject | `reviewed_surface_removal` | 696 | 181 |
| `ál` | not a candidate | — | 0 | 0 |

## Limitations

- Corpus occurrence is evidence of usage, not proof of lexical validity.
- morphdb.hu partly incorporates Magyar Ispell, so it is corroborating rather than fully independent evidence.
- The public morphdb.hu release is from 2006; modern vocabulary depends primarily on Magyar Ispell and corpus evidence.
- Lowercased surfaces can hide some names. Proper-name-only morphdb analyses are rejected, but no automated method can identify every name collision.
