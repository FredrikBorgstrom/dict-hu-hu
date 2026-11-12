# Exact-surface corrections: rare `-i` adjectives

Prepared and published on 12 November 2026 to the production Hungarian standard, classic and mixed dictionaries (lexicon versions 42, 33 and 29).

## Problem

Hungarian players repeatedly report that the game accepts meaningless words
(feedback since July 2026; most recently 12 November). A large share of these
are adjectives formed with the place/time suffix `-i` from almost any noun,
for example `vaki`, `cími`, `híri`, `máji` and `kíni`. Pinned Magyar Ispell
analyses them only through that suffix:

    vaki  st:vak po:noun ts:NOM is:i_PLACE/TIME_adj ts:NOM

The suffix is semantically selective in real Hungarian (`budapesti`,
`reggeli`, `kerti`), but the analyzer applies it to nearly every noun. The
evidence build then admits the form as `attested_derivation` with as few as
two quality-4 Webcorpus occurrences, or through the quality-8 corpus core,
and the admitted form licenses its ordinary inflections (`vakiak`).

## Selection

1. Every active surface whose analyses in pinned Magyar Ispell all contain
   `is:i_PLACE/TIME_adj` (55,604 surfaces).
2. Each surface is mapped to its own base adjective: the longest prefix ending
   in `i` that is itself an active surface. Compounds therefore keep their own
   base (`adóügyi`, not `ügyi`).
3. Base adjectives with fewer than five exact lowercase occurrences in the
   quality-4 Webcorpus 2.2 partition were reviewed one by one
   (2,019 bases, 15,847 surfaces). Fredrik chose this threshold on
   12 November 2026.
4. Excluded from removal:
   - existing reviewed additions (`fain`, `faszari`);
   - 17 real words found in the review: `pampai`, `idefönti`, `odahazai`,
     `legeleji`, `nehézvízi`, `brakkvízi`, `termálvízi`, `árterületi`,
     `délszigeti`, `háryjánosi`, `édesatyai`, `nagybátyai`, `jogsegélyi`,
     `magánbanki`, `citokémiai`, `oxiológiai`, `hóolvadási`;
   - 59 uncertain bases held for native-speaker review (requested on
     12 November 2026), listed in the review artifact;
   - 318 bases that are also ordinary inflections of another word, such as
     `adui`, `almai` and `akkui` (possessive plurals). Only their `-i`
     adjective descendants are candidates.

The remaining 1,625 base adjectives are removed as exact surfaces. As with
`molyné`, removing an accepted anchor withdraws the inflections it licensed.
A second pass lists 2,898 further surfaces explicitly: inflections of the
`-i` adjective reading of the 318 homograph bases (`aduiak`, `kenuiak`,
`őrletiben`), and inflections that morphdb.hu admitted through a plain
reading of a removed base (`bobiba`, `hordaiban`). In total 4,523 exact
surfaces are listed.

Ninety-six candidate surfaces with their own corpus evidence are kept, because
many are real words through a reading the analyzer does not model: minerals
(`dacit`, `mullit`, `cementit`), dialect possessives (`tetejibe`, `zsebibe`,
`kincsinek`) and adverbs such as `stílusilag` and `hőileg`.

## Result

The standard list shrinks from 2,195,267 to 2,180,088 surfaces: 15,179
removed, none added. Every removed surface is one of the reviewed candidate
forms; no unrelated word is withdrawn.

## Validation

All candidate surfaces were checked against both pinned analyzers: every
Magyar Ispell analysis is the `-i` adjective path. No player-requested word,
in-app add proposal or reviewed addition is removed. The change also resolves
player-reported words such as `hibai`, `kíni`, `neszi`, `pályai`, `pályain`
and `öblien`.

Review data: `artifacts/Rare i-Adjective Cleanup 2026-11-12/` in the
dictionaries workspace.
