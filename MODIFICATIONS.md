# ABCx3 modifications

This repository contains a modified word-list distribution derived from
Magyar Ispell 1.9 by László Németh and Ferenc Godó. The original project is
available at <https://github.com/laszlonemeth/magyarispell>.

The modifications are distributed under the Mozilla Public License 1.1. The
complete license is in `COPYING.MPL`.

## Change history

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
