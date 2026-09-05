# ABCx3 modifications

This repository contains a modified word-list distribution derived from
Magyar Ispell 1.9 by László Németh and Ferenc Godó. The original project is
available at <https://github.com/laszlonemeth/magyarispell>.

The modifications are distributed under the Mozilla Public License 1.1. The
complete license is in `COPYING.MPL`.

## Change history

- **2026-09-05 (native review):** Added 572 exact surface forms following
  native lexical review, pinned Magyar Ispell analysis, and clean Webcorpus
  corroboration. Recorded source-derived definition mappings in a portable
  review manifest; retained every existing mapping and word. Corrected the
  narrow `hm` interjection false rejection, kept abbreviation exclusions, and
  prevented surface approvals from expanding unreviewed inflection families.
  Regenerated classic physical-tile spellings with 568 additions, preserving
  all existing arrangements and enforcing all applicable permissioned boundaries.

- **2026-09-05:** Separated existing-word retention from external-compound
  admission, preserved promoted admission provenance, and added checksum-verified
  baseline recovery. Added regressions for the 42 valid published surfaces
  incorrectly caught by the compound-only filter; explicit removals and source
  safety exclusions remain authoritative.

- **2026-03-07:** Added the initial reproducible ABCx3 processor and generated
  standalone lowercase gameplay word list.
- **2026-08-17:** Added pinned-source verification, Hungarian Webcorpus
  evidence filtering, source audit records, quality reports, and the
  surface-form-to-lemma index used for definition lookup.
- **2026-08-18:** Refined source-metadata handling and gameplay-oriented word
  decisions while retaining ordinary valid inflections.
- **2026-08-27:** Promoted the evidence-scored list used by ABCx3, incorporated
  traceable community-reviewed additions and removals, strengthened filtering
  of high-risk generated forms, and regenerated the matching audit and lemma
  artifacts.

The detailed current processing rules, source versions, checksums, output
contents, and reproduction commands are documented in `README.md`,
`output/audit.json`, and the processing scripts in this repository. Git history
provides the corresponding file-level changes for each dated revision.

# 2026-08-28 — Optional classic Hungarian physical-tile lexicon

- Added a separately generated canonical tile-token artifact for the classic
  100-tile Hungarian distribution, including CS, GY, LY, NY, SZ, TY, and ZS as
  one board tile each.
- Preserved the existing surface word output unchanged.
- Added deterministic morphology-aware segmentation, shortened-doubling rules,
  reviewed overrides, exclusions, collision reporting, and reproducible audit
  checksums.

# 2026-08-29 — Gameplay-reported Hungarian surface removal

- Removed the exact unattested surface `cöcögd` after it was reported from game
  5863, while retaining the documented lemma `cöcög` and its other accepted
  forms.
- Regenerated both the standard Hungarian output and the classic physical-tile
  lexicon from the same reviewed override decision.

# 2026-09-02 — Compound-aware classic tile segmentation

- Preserved explicit Magyar Ispell `hy:` compound and morpheme boundaries in
  the classic physical-tile lexicon and propagated lemma boundaries to
  accepted inflected forms.
- Prevented CS, GY, LY, NY, SZ, TY, and ZS tiles, as well as shortened doubled
  multigraph spellings, from crossing an authoritative boundary.
- Added regression coverage for `mézsör` (`M | É | Z | S | Ö | R`), its
  inflections, `házsor`, `ősszülő`, and the non-compound control `gázsi`.

# 2026-09-02 — Permissioned CsiSza boundary evidence

- Added 931 physical-tile boundary annotations created by Attila (`betuTboy`),
  used with his written permission for ABCx3 dictionary validation and
  improvement.
- Kept CsiSza strictly as supplemental segmentation evidence: no CsiSza entry
  can add a word to the ABCx3 lexicon.
- Corrected compound and suffix boundaries not distinguished by the Magyar
  Ispell metadata alone, including `köz_ség`, `nehéz_ség`, and `egész_séges`.
- Excluded classic-mode spellings such as `cit_y`, `n_ylon`, and `zlot_y` when
  their correct segmentation requires a standalone tile unavailable in the
  classic ABCx3 bag.
- Added a checksum-pinned importer, provenance metadata, audit counts, and
  regression coverage for the supplemental source.

# 2026-09-03 — External compound-headword inflections

- Added the player-reported plural `őzgidák` through the traceable community
  override after confirming it as the plural of the accepted headword
  `őzgida` in Magyar Ispell, morphdb.hu, and the clean Webcorpus partition.
- Extended the evidence generator to discover strongly attested surfaces that
  Magyar Ispell accepts and admit them only when morphdb.hu independently
  confirms a safe inflection of an already accepted external headword that
  Magyar Ispell explicitly analyzes as a compound.
- Preserved the confirmed external headword in the promoted surface-to-lemma
  index instead of self-mapping newly discovered inflections.

# 2026-09-04 — Correct physical tiles for shortened doubles

- Corrected all seven shortened doubled digraphs to use their literal written
  physical tiles, including `petty` as `P | E | T | TY`.
- Preserved compound/morpheme boundary decisions and all 845,551 accepted
  surfaces. Retained every prior key/surface pair as either a preferred row or
  a compatibility alias, adding 12,056 corrected arrangements without removing
  any previously accepted placement.
- Kept the source artifact preferred-only and added deterministic runtime
  alias sections, audit counts, and regression tests for all seven cases.
