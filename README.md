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

Under MPL 1.1, the dictionary data and the preferred source used to produce it
are distributed in this public repository so that they remain open, while the
application code using them may remain proprietary. See [COPYING.MPL](COPYING.MPL)
for the full MPL 1.1 license text and [MODIFICATIONS.md](MODIFICATIONS.md) for a
dated summary of the ABCx3 changes.

The supplemental CsiSza source repository is GPLv3. Its author separately
granted ABCx3 written permission to use his tile-boundary annotations for
dictionary validation and improvement. ABCx3 imports only those annotations,
not CsiSza's word inventory or code; provenance and the exact permission scope
are retained with the imported data.

## Contents

`output/hungarian_hu_hu_ispell.txt` — the active standalone Hungarian word
forms, one per line, UTF-8, sorted. The exact count is recorded in
`output/audit.json`.

`output/hungarian_hu_hu_ispell_classic_tiles.tsv` — a separate compact
runtime lexicon for the optional classic 100-tile Hungarian mode. Each row
preserves the ordinary surface spelling and a canonical sequence of physical
tile identifiers. It is generated without modifying the ordinary word list.

Shortened doubles use the written physical tiles: `ccs → C | CS`,
`ggy → G | GY`, `lly → L | LY`, `nny → N | NY`, `ssz → S | SZ`,
`tty → T | TY`, and `zzs → Z | ZS`. For example, `petty` is `P | E | T | TY`.
Full doubling at compound boundaries remains unchanged. Generator 1.3 also
retains the previously accepted full-digraph arrangements as compatibility
aliases so existing boards remain valid; it does not change tile values or
historical scores. Runtime aliases precede the `# Preferred physical tile
sequences` section. The reviewable source has one preferred row per surface;
seed-player word lists select only those preferred rows. Audits distinguish
accepted surfaces, compatibility aliases, and total runtime entries.

`output/hungarian_hu_hu_ispell_classic_tiles.source.tsv.gz` and
`output/hungarian_hu_hu_ispell_classic_tiles.audit.json` — the reviewable
surface-to-token source and deterministic segmentation audit. Reviewed
exceptions live in `classic_tile_segmentation_overrides.tsv`. The generator
preserves explicit Magyar Ispell `hy:` morphology boundaries and permissioned
CsiSza `_` tile-boundary annotations before choosing physical tiles. Thus
compounds such as `méz|sör`, suffix boundaries such as `köz_ség`, and foreign
spellings such as `cit_y` cannot be collapsed into a crossing multigraph tile,
while simple words such as `gázsi` retain the single `ZS` tile. Boundaries on a
lemma are propagated to its accepted inflected forms. If a required spelling
needs an unavailable standalone tile, as `cit_y` needs `Y`, that surface is
excluded from the classic-tile artifact rather than accepted with a false `TY`.

`csi_sza_classic_tile_boundaries.txt` contains only CsiSza's underscore-marked
tile-boundary evidence, not its word list. Attila (`betuTboy`) confirmed in
writing on 2026-09-02 that he created these annotations and that ABCx3 may use
them for dictionary validation and improvement. They are applied only to
surfaces independently admitted by ABCx3's existing lexical sources, so they
never grant word validity. The pinned upstream file, commit, checksum, import
policy, and permission date are recorded in the generated annotation file and
`import_csi_sza_tile_boundaries.py`.

`output/definitions/hu/surface-lemma/v1/` — a deterministic, compressed
surface-form-to-lemma index for definition lookup. A surface may retain
multiple source lemmas when Magyar Ispell has ambiguous analyses. The index is
kept separate from the game word list so clients that only validate words do
not download it.

`COPYING.MPL`, `MPL-NOTICE`, and `MODIFICATIONS.md` — the complete license
text, required source notice, and dated record of changes for this modified
distribution.

### Evidence-scored candidate

`candidate/hungarian_hu_hu_evidence_candidate.txt` is a separately generated,
quality-first candidate; its matching audit records its word count. The candidate keeps
ordinary inflections when Magyar Ispell and morphdb.hu agree on the lemma,
while applying stronger clean-corpus requirements to prefixes, derivations,
possessives, and plural + possessive stacks. It also discovers strongly
attested safe inflections of already accepted external compound headwords.

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
8. Identifies accepted external compound headwords using the prior accepted
   output, a morphdb.hu self-lemma entry, an explicit multi-part Magyar Ispell
   compound analysis, and at least ten quality-4 corpus occurrences
9. Considers novel, strongly attested corpus surfaces accepted by Magyar
   Ispell, but adds one only when morphdb.hu independently analyzes it as a
   safe inflection of an identified external compound headword
10. Writes per-word evidence and rejection reasons alongside a deterministic
   audit and human-readable report
11. Applies traceable, explicitly reviewed gameplay additions from
   `_community_overrides/hungarian_hu_hu_ispell/additions.txt` and the portable,
   source-verified `reviewed_additions.json`
12. Applies traceable surface and lemma removals from the same override set;
    lemma removals discard the complete generated family while preserving a
    homographic surface when another allowed lemma still licenses it

### Native-review additions (2026-09-05)

The active list includes 572 explicitly reviewed surface forms verified against
the pinned Magyar Ispell sources and at least two occurrences in the cleanest
Webcorpus partition. `reviewed_additions.json` contains their source analyses,
frequencies, definition lemmas, and source checksums. This source-derived
manifest is loaded on every evidence build, including builds without the private
parent checkout. It does not import CsiSza's word inventory or establish any
new permission over that inventory. Native review supplies lexical judgment;
the existing source notices and distribution terms remain applicable.

`gameplay_overrides.json` carries the exact curated additions and surface/lemma
removals needed for public-only reproduction. It contains no private operator
identities, workbook rows, or review messages. The private review importer
refreshes this portable source manifest when corrections change; builds load
it even when the private parent checkout is absent.

Approvals apply only to the exact surfaces, not to new inflection families.
Explicit removal decisions and written-abbreviation exclusions remain
authoritative. An approved lexical reading may override a false proper-name
classification from the older morphdb analyzer. Lowercase `hm` (an interjection)
is a narrowly allowed homograph of uppercase `HM`; this does not allow units
such as `cm` or `kg`.

Definition lookup retains all earlier mappings. Reviewed inflections use the
source stem including verbal prefixes, compounds keep the complete headword,
and derived adjectives do not point at the capitalized proper-name root.
The new batch brings the standard vocabulary to 851,796 surfaces and the
classic-tile vocabulary to 846,161 surfaces. Four additions cannot be formed
with the classic mode's fixed physical tiles and remain in its exclusion audit.
No earlier word or canonical tile arrangement was removed.

```bash
python3 build_evidence_wordlist.py --offline --output-dir artifacts/native-review
python3 promote_evidence_wordlist.py --candidate-dir artifacts/native-review
python3 generate_classic_tile_lexicon.py
python3 -m unittest test_process_words test_build_evidence_wordlist test_promote_evidence_wordlist test_reviewed_additions test_generate_classic_tile_lexicon
```

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

# Preserve retained surface-to-lemma mappings, map discovered inflections to
# their external headwords, and promote the candidate to output/
python3 promote_evidence_wordlist.py

# Run the promotion regression tests as well
python3 -m unittest -v test_promote_evidence_wordlist.py
```

Promotion verifies the candidate checksum, builds a complete matching lemma
index under `candidate/definitions/`, maps newly discovered inflections to
their independently confirmed external headwords, and replaces the active word
list, lemma index, and audit. Re-running the ordinary generator restores the
full Magyar Ispell expansion; re-running the promotion step then reapplies the
evidence policy deterministically.

The first evidence build requires the `hunspell` executable and can take
several minutes. Subsequent builds reuse a checksum-keyed analysis cache.

Existing vocabulary follows the ordinary evidence policy; discovery through
the external-compound path must not reclassify an existing word. Promotion
persists `output/evidence.tsv.gz` so newly admitted compound inflections
continue to satisfy their stricter rule on subsequent builds, including builds
using another candidate directory.

To recover vocabulary after a provenance regression, the evidence generator
accepts `--retention-baseline <complete-prior-wordlist>` together with
`--retention-baseline-sha256 <verified-checksum>`. This is a full prior
vocabulary snapshot, not an exception allowlist: every recovered candidate is
still subject to ordinary evidence, source exclusions, and reviewed removals.
The snapshot checksum is recorded in the audit. After promotion, normal builds
need no recovery arguments.
If a regression also removed lemma mappings, promotion accepts
`--retention-lemma-index <prior-index-directory>`. It verifies the prior shard
checksums and uses that index only for accepted surfaces missing from the
current index; it never replaces retained mappings.

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
  are removed; lexicalized `taj` is retained. Gameplay-reviewed foreign or
  non-game entries `al`, `ál`, `as`, `aú`, `lex`, `mé`, `tá`, `vu`, and `zu`
  are also removed through the traceable override policy. The `as` removal
  applies to its complete generated lemma family; the others are reviewed
  surface removals except for the standalone `lex` lemma. The reviewed written
  symbols, mathematical notations, period-less abbreviations, misspellings, and
  foreign forms `cal`, `cimet`, `cos`, `cosec`, `ctg`, `dag`, `dzs`, `épit`,
  `jade`, `kcal`, `kib`, `márc`, `mbar`, `mmol`, `omega`, `org`, `sin`, `stb`,
  `words`, `yacht`, and `zsüri` are removed as exact surfaces. The additional
  native-speaker-reviewed lowercase surfaces `búék`, `gmk`, `jézus`, `kkv`,
  `las`, `levi`, `mgtsz`, `sanyi`, `sec`, `termo`, `thm`, `tszcs`, and `ühg`
  are likewise excluded without removing any complete inflectional family.
  The gameplay-reported unattested inflection `cöcögd` is also removed as an
  exact surface while retaining the documented lemma `cöcög`.
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
- Generated forms ending in the semantically selective temporal suffix `-kor`
  must occur at least once in the complete Webcorpus. Direct source headwords
  and already-attested forms are preserved. This prevents two agreeing
  morphology engines from admitting unattested combinations such as `exkor`.

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

# Generate and test the additive classic physical-tile lexicon
python3 import_csi_sza_tile_boundaries.py /path/to/CsiSza/szotar22a_kat.dic
python3 generate_classic_tile_lexicon.py
python3 -m unittest -v test_generate_classic_tile_lexicon.py

```

## Hungarian Alphabet

Hungarian uses 26 standard Latin letters plus 9 additional accented characters:
`á é í ó ö ő ú ü ű`

Full tile set for ABCx3: `a á b c cs d dz dzs e é f g gy h i í j k l ly m n ny o ó ö ő p r s sz t ty u ú ü ű v z zs`
