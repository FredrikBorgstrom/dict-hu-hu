# Exact-surface corrections: csúr and molyné

Prepared locally on 17 October 2026. Publication is a separate operation.

## Add csúr

The Research Centre for Linguistics' academic dictionary explicitly lists
`csúr` as an archaic variant of the verb `csűr`, meaning to twist or wring.
Its entry includes historical usage from 1792 and 1810. This is a lowercase
verb, independently of the unrelated capitalized place name.

Primary source: <https://nagyszotar.nytud.hu/dictsearch.html?entryid=13536>.

Neither pinned Magyar Ispell nor morphdb.hu recognizes the exact surface, and
the active word list omits it. Admit only `csúr` through the existing portable
exact-addition path. This does not license an inferred conjugation family.
All three Hungarian alphabets can represent the word; classic spelling is
CS | Ú | R, and mixed mode also permits C | S | Ú | R.

## Exclude molyné as an accepted anchor

A player report showed the practice bot playing `molyné` after `moly` had
been played in a mixed-tile Hungarian game.

The pinned Magyar Ispell analysis is:

    molyné st:moly po:noun ts:NOM ds:né_MRS_noun ts:NOM

morphdb.hu likewise constructs `moly /NOUN [MRS]/NOUN`. This is the wife-name
derivation, not a normal case or possessive ending of `moly` (English: moth).
The active evidence file admits it as `attested_derivation`, with only two
occurrences in each corpus quality partition. Analyzer construction and two
uncontextualized frequency counts do not establish common-noun usage.

A bounded search found no independent Hungarian common-noun entry or clear
ordinary usage of the exact surface. A seemingly relevant historical match
is **Molyné**, a married personal name paired with **Moly úr** (English:
Mr Moly). The original newspaper scan was visually checked: *Budapesti
Napló*, 18 March 1904, printed page 5, bottom-of-page fiction columns.

Primary scan:
<https://epa.oszk.hu/04300/04337/01864/pdf/EPA04337_budapesti_naplo_1904_078.pdf>.
The filename's issue identifier does not supply the publication date; the
printed masthead supplies 18 March 1904.

Apply the existing exclusion of proper names to this false positive through
an exact surface override. Preserve `moly`, its normal inflections, other
`-né` roots, and the unrelated `agyagiak` and `box` decisions. This correction
is not a claim to have exhaustively reviewed all wife-name derivations.

The full rebuild also withdraws 86 inflections whose accepted anchor was
`molyné`. Every removed analysis in both pinned analyzers is the same
wife-name derivation of `moly`; all 86 dependent forms have zero occurrences
in the cleanest corpus partition. There are no unrelated removals. This is
the normal source-based admission result, not a prefix-based deletion.

Against the preserved 2,081,364-word baseline, the candidate has 2,081,279
surfaces: `csúr` and the previously prepared `rex` are added; the 87-member
`molyné` family is removed. All other existing words remain. Full counts,
per-word admission evidence and both analyzers' complete removed-family
analyses are preserved in the protected task artifacts.

## Durable implementation and evidence

Both changes are encoded in `gameplay_overrides.json` and the parent
`_community_overrides/hungarian_hu_hu_ispell/` decision register and manifest.
The normal build applies these explicit choices before corpus-based
acceptance, so rebuilding cannot silently restore `molyné` or lose `csúr`.
The previously prepared `rex` addition remains intact.

Player correspondence, production evidence and local validation are kept privately.
