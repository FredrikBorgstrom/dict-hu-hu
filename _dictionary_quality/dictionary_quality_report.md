# Dictionary word-list quality ranking

Generated 2026-08-27T13:29:57+00:00 from `/Users/fredrik/Documents/abcx3_dictionaries/hungarian_hu_hu_ispell`. Audited 1 output list.

## Ranked summary

| Rank | Dictionary output | Quality | Score | Words | Observed suspect | Proper candidates* | Abbreviation candidates* | Filter evidence |
|---:|---|:---:|---:|---:|---:|---:|---:|:---:|
| 1 | [Hungarian (HU, ispell)](../output/hungarian_hu_hu_ispell.txt) | A — excellent | 94.0 | 846,397 | 0 (0.0000%) | 0 (0.0000%) | 0 (0.0000%) | machine-audited |

\* Candidate counts are exact pattern/watch-list hits in the current files, not exact semantic inventories. They may contain false positives and miss lowercase or otherwise unobservable cases.

## Reading the ranking

The score combines surface cleanliness (60 points), quantity word count (30), and strength of proper-noun/abbreviation filtering evidence (10). A large list helps, but observed contamination and weak evidence reduce its rank. Evidence strength describes the audit trail, not confidence that a list is clean.

Grade distribution: A: 1.

Filter-evidence distribution: machine-audited: 1.

`CD` belongs in a spoken allowlist when it is accepted as a spoken initialism. Written shorthands such as `ETC`, `IE`, and `EG` belong in a language-specific written-only list. The bundled defaults apply those examples only to English to avoid false positives in other languages.

## Data-shape notes

- All lists are Unicode-code-point sorted and contain no adjacent duplicates.

## Lists with observable candidates

No observable candidates were found.

## Limitations

An exact proper-noun or spoken-vs-written abbreviation count is impossible after lowercasing without language-specific lexical annotations. Zero candidates therefore means “none observable by this audit,” not “semantically proven zero.” Candidate patterns can also flag valid spoken initialisms. Machine audit records and documented source filters strengthen the audit trail but do not replace native-speaker review. Inspect weak-evidence lists and close rankings before making release decisions.

Exact machine-readable metrics are in `dictionary_quality_results.json`; a flat comparison table is in `dictionary_quality_ranking.csv`.
