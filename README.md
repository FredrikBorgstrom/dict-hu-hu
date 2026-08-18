# dict-hu-hu

Hungarian word list for the ABCx3 word game.

## Source

**Magyar Ispell 1.9** — Hungarian hunspell spell-checking dictionary
Homepage: <http://magyarispell.sourceforge.net>
GitHub: <https://github.com/laszlonemeth/magyarispell>
Dictionary files: <https://github.com/LibreOffice/dictionaries/tree/master/hu_HU>
Authors: László Németh <nemeth@numbertext.org> and Ferenc Godó
Version: Magyar Ispell 1.9, December 2025

Generated forms are automatically checked against the **Hungarian Webcorpus
2.2** frequency list from the Budapest University of Technology and Economics
Media Research Centre: <https://mokk.bme.hu/resources/webcorpus/>. The corpus is
used only as a reproducible lexical-evidence filter; corpus text is not
redistributed in this repository.

## License

This word list is derived from Magyar Ispell, which is published under a
**GPL / LGPL / MPL triple-license**. We use the **Mozilla Public License 1.1 (MPL 1.1)** option.

Under MPL 1.1, the dictionary data (this word list file) is distributed in this public repository
so that it remains open, while the application code using it may remain proprietary.
See [COPYING.MPL](https://github.com/laszlonemeth/magyarispell/blob/master/COPYING.MPL) in the
Magyar Ispell repository for the full MPL 1.1 license text.

## Contents

`output/hungarian_hu_hu_ispell.txt` — the active standalone Hungarian word
forms, one per line, UTF-8, sorted. The exact count is recorded in
`output/audit.json`.

`output/definitions/hu/surface-lemma/v1/` — a deterministic, compressed
surface-form-to-lemma index for definition lookup. A surface may retain
multiple source lemmas when Magyar Ispell has ambiguous analyses. The index is
kept separate from the game word list so clients that only validate words do
not download it.

### Evidence-scored candidate

`candidate/hungarian_hu_hu_evidence_candidate.txt` is a separately generated,
quality-first candidate containing **863,174 words**. The candidate keeps
ordinary inflections when Magyar Ispell and morphdb.hu agree on the lemma,
while applying stronger clean-corpus requirements to prefixes, derivations,
possessives, and plural + possessive stacks.

The companion build is implemented in `build_evidence_wordlist.py`. It:

1. Starts from the complete current Magyar Ispell output
2. Downloads the pinned 2006 morphdb.hu release and verifies its SHA-256
3. Runs morphdb.hu through Hunspell and caches analysis features by input and
   source checksums
4. Uses all four Webcorpus quality columns, with the cleaner quality-8 and
   quality-4 partitions controlling acceptance
5. Rejects proper-name-only analyses even when their lowercase spelling occurs
   in web text
6. Treats both morphdb.hu `POSS` and `ANP` possessee paradigms as high risk
7. Adds morphdb.hu headwords missing from Magyar Ispell only when morphdb.hu
   recognizes them as non-proper standalone forms and they occur at least ten
   times in the cleanest quality-4 corpus partition; internal `PSEUDOROOT`
   stems used only for suffix generation are rejected
8. Writes per-word evidence and rejection reasons alongside a deterministic
   audit and human-readable report
9. Applies traceable, explicitly reviewed gameplay additions from
   `_community_overrides/hungarian_hu_hu_ispell/additions.txt`; `box` is
   currently included through this policy

The [morphdb.hu](https://mokk.bme.hu/en/resources/hunmorph/) archive contains a
Creative Commons Attribution 2.5 license. The archive credits Eszter Simon,
Péter Rebrus, András Rung, Viktor Trón, and Péter Vajda. It partly incorporates
Magyar Ispell, so it is corroborating rather than fully independent evidence;
its morphological grammar and two other incorporated lexicons still provide
useful disagreement and proper-name signals.

Artifacts:

- `candidate/audit.json` — source checksums, policy thresholds, category counts,
  diagnostic decisions, and output checksum
- `candidate/evidence.tsv.gz` — the decision and evidence features for every
  candidate surface
- `candidate/rejected.tsv.gz` — rejected surfaces with reason and corpus counts
- `candidate/report.md` — concise comparison and reported-word decisions
- `candidate/quality_audit/` — structural audit comparing the current and
  evidence-scored lists

To regenerate after the ordinary list has been built:

```bash
python3 build_evidence_wordlist.py

# Reuse only checksum-verified cached inputs and analyses
python3 build_evidence_wordlist.py --offline

# Run both generator and evidence-policy tests
python3 -m unittest -v test_process_words.py test_build_evidence_wordlist.py

# Preserve retained surface-to-lemma mappings, self-map accepted external
# headwords, and promote the candidate to output/
python3 promote_evidence_wordlist.py

# Run the promotion regression tests as well
python3 -m unittest -v test_promote_evidence_wordlist.py
```

Promotion verifies the candidate checksum, builds a complete matching lemma
index under `candidate/definitions/`, and replaces the active word list, lemma
index, and audit. Re-running the ordinary generator restores the full Magyar
Ispell expansion; re-running the promotion step then reapplies the evidence
policy deterministically.

The first evidence build requires the `hunspell` executable and can take
several minutes. Subsequent builds reuse a checksum-keyed analysis cache.

Coverage:
- Generated words are 2–10 characters long; the four separately approved
  one-letter words `a`, `s`, `ó`, and `ő` are also included
- Standard Hungarian alphabet: `a á b c cs d dz dzs e é f g gy h i í j k l ly m n ny o ó ö ő p r s sz t ty u ú ü ű v z zs`
- Lowercase only (no proper nouns)
- No hyphens, no spaces, no numbers
- Includes inflected forms (noun cases, verb conjugations, plural forms, possessives)
- Consonant-only 2-letter abbreviations removed (e.g. cm, kg, cs, gy, ny, sz, dz)
- Written abbreviations, case-sensitive units, compound-only roots, forbidden
  spellings, and forms marked substandard by Magyar Ispell are removed
- Reviewed non-word surfaces such as `tsz`, `szja`, `uv`, and standalone `go`
  are removed; lexicalized `taj` is retained
- Direct source headwords and ordinary inflections are retained without an
  exact-surface corpus requirement.
- Higher-risk paths must occur at least twice in the complete Webcorpus. These
  paths include derivational word formation, descendants of proper-name
  derivatives, all prefix-derived forms, possessive + possessee stacks, and
  plural + possessive forms carrying the sublative `-ra/-re` case. Prefix rules
  are treated as high-risk because a mechanically possible Hungarian verbal
  prefix is not necessarily meaningful with every verb. The last category
  covers forms such as `büróira` without applying a corpus gate to other
  ordinary case stacks.

This rule is fully automatic. A normal build has no native-speaker review gate,
no model judgement, and no unpinned network input. For example, it removes
unattested risky forms such as `cafráz`, `lucaiké`, and `büróira`, while
preserving ordinary inflections even when their exact surface is rare.

## Generation

The word list is generated by `process_words.py`, which:
1. Downloads the pinned Magyar Ispell and Webcorpus files into `.cache/sources`
   and verifies their SHA-256 checksums before using them
2. Parses AF/AM aliases, source metadata, and both PFX (prefix) and SFX (suffix)
   rules
3. Applies suffix rules and Hunspell-permitted PFX × SFX cross-products. Common
   prefixed verbs such as `beír`, `kiad`, `leír`, and `feláll`, together with
   their attested inflections, are therefore generated correctly
4. Preserves Hunspell continuation flags and propagates forbidden source forms
   to their inflected descendants
5. Filters to standard standalone Hungarian words of length 2–10, excluding
   metadata-identified written abbreviations
6. Preserves direct headwords and ordinary inflections; requires two complete-
   corpus occurrences for the documented high-risk generation paths. Prefix
   cross-products are resolved through a reverse corpus index so the build does
   not enumerate more than a billion impossible or unattested rule pairs
7. Sorts and deduplicates deterministically (`LC_ALL=C`)
8. Writes reproducible source checksums, counts, policy, and an output checksum to
   `output/audit.json`
9. Writes gzip-compressed two-letter-prefix shards that connect every accepted
   surface form to its source lemma or lemmas, avoiding runtime morphology work

To regenerate:
```bash
# First run downloads and verifies all pinned inputs automatically
python3 process_words.py

# Later runs can be forced to use only verified cached inputs
python3 process_words.py --offline

# Run the processor regression tests
python3 -m unittest -v test_process_words.py
```

## Hungarian Alphabet

Hungarian uses 26 standard Latin letters plus 9 additional accented characters:
`á é í ó ö ő ú ü ű`

Full tile set for ABCx3: `a á b c cs d dz dzs e é f g gy h i í j k l ly m n ny o ó ö ő p r s sz t ty u ú ü ű v z zs`
