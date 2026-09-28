# Check Hungarian additions without an assistant

Double-click **Check Hungarian Words.command** in this folder. It checks every
word added since the saved published baseline and opens the results folder.
It uses Python 3 and its standard library, with no artificial intelligence
(AI) service, service key, subscription, or per-run charge. Python 3 must be installed.

The first run downloads approximately 590 MB of reference data. Later runs
reuse that snapshot, including after a restart. A full check takes about a
minute on the development Mac. The program never edits the active dictionary,
builds release artifacts, publishes, or contacts the game backend.

From Terminal, the equivalent command is:

```sh
cd /Users/fredrik/Documents/abcx3_dictionaries/hungarian_hu_hu_ispell
python3 validate_hungarian.py
```

## Read the results

Each run creates a dated directory under `artifacts/Hungarian Validation/`.

| File | Meaning |
| --- | --- |
| `Report.md` | Counts, interpretation, source and limitations |
| `supported.txt` | Candidates supported by both saved generator evidence and the additional published noun paradigm |
| `pending.txt` | Candidates whose noun use, stem, ending or reference coverage is unresolved |
| `excluded.txt` | Candidates excluded by explicit gameplay removals or word-format policy |
| `decisions.tsv` | One row per word, with reason, anchor, English base meaning, grammatical owner, case and source |
| `families.tsv` | Supported noun families and the number of matching candidates; **not** blanket approval of every form of each noun |
| `summary.json` | Source revision, policy version, input hashes, reference snapshot and output checksums |

The table files can be opened in a spreadsheet app. Keep pending words out of
an automatically approved addition set. Missing evidence does **not** mean a
word is invalid. The supported list is a review artifact, not a replacement
for the complete dictionary or its tile lexicons.

On 28 September 2026, Fredrik approved restricting the prepared update to the
164,271 supported surfaces from the first full audit. That exact selection and
the original 404,258-word scope are now pinned in `plural_possessive_review/`.
The evidence builder and promotion step prevent the 239,987 deferred words
from reappearing. Normal checks now inspect the narrowed candidate; the full
earlier audit and its pending words remain preserved. Running this checker
never updates the approved selection automatically.

## What the program checks

1. Read the current candidate word list and its ordinary/derived possessive
   evidence files. Require existing agreement between the two morphological
   analyzers and a non-proper lexical analysis.
2. Match the exact accepted noun or derived anchor to a **noun** entry in the
   English Wiktionary extraction distributed by [Kaikki](https://kaikki.org/dictionary/Hungarian/index.html).
   An adjective or underlying verb entry alone is insufficient.
3. Require all six owner columns for plural possessions within the same noun
   entry and the same documented stem variant. Inflection-only, alternate-only
   and explicitly restricted entries cannot supply the lexical noun evidence.
4. Match the candidate to a documented possessive form, optionally followed by
   **one** of the common case endings below. Vowel harmony comes from the
   documented paradigm, not a guess based on the root's spelling.
5. Apply explicit `gameplay_overrides.json` removals before supporting a form.
   Never expand or recursively generate new candidate words.

For example, **Hungarian:** `rügyeik`. **English translation:** “their buds.”
The noun's published paradigm supplies the exact possessive stem; its family
can also support common case forms when the candidate has matching generator
evidence. An undocumented alternate stem remains pending.

Supported cases: nominative (plain form), accusative (object), dative (to/for),
instrumental (with), translative (becoming), causal-final (for), terminative
(up to), essive-formal (as), and the nine in/on/at/to/from location cases.
The consonant-final possessions end in m, d or k; their instrumental and
translative endings assimilate that final consonant. Published examples of
these suffix paradigms are [-aim](https://en.wiktionary.org/wiki/-aim) and
[-eim](https://en.wiktionary.org/wiki/-eim) (English: “my …s”).
The third-person singular possession ends in i; see
[-ai](https://en.wiktionary.org/wiki/-ai#Hungarian) and
[-ei](https://en.wiktionary.org/wiki/-ei#Hungarian) (English: “his/her/its …s”).

Rare essive-modal endings meaning “as,” temporal endings, anaphoric possession
and further suffix stacks remain pending. Forms marked archaic, obsolete,
dated, dialectal, rare, historical, nonstandard, misspelled or proscribed are
held unless the same entry has unrestricted noun evidence. These are evidence
thresholds, not claims that such vocabulary is wrong.

**Limits:** this is a conservative check of plural-possessive additions, not a
general Hungarian grammar checker. Wiktionary coverage is incomplete and its
tables can contain errors; many are themselves generated. Agreement supplies
additional evidence, not a guarantee that every word is natural in every
context. No program here certifies all 404,258 additions. It deliberately
leaves a substantial pending set without requiring a Hungarian reviewer to
run the check.

## Other uses

Custom reference files use JavaScript Object Notation (JSON), one entry per line.

```sh
# Require an entirely offline run using the cached snapshot:
python3 validate_hungarian.py --offline

# Check an explicit one-word-per-line list against the existing build evidence:
python3 validate_hungarian.py --words /path/to/candidates.txt --offline

# Check the reported example (English: "their buds"):
python3 validate_hungarian.py --word rügyeik --offline

# Deliberately update the reference snapshot; earlier downloads are preserved:
python3 validate_hungarian.py --refresh-reference

# Supply another compatible JSON-lines reference, optionally compressed:
python3 validate_hungarian.py --reference /path/to/reference.jsonl.gz

# Use a different frozen, published baseline after an actual dictionary release:
python3 validate_hungarian.py --baseline /path/to/published-wordlist.txt --offline

# Run the small offline regression suite:
python3 -m unittest -v test_validate_hungarian
```

`validation_config.json` pins the last published baseline to
`01b37a4dd3372361af5a0700a59bde353dc45dfb`. It does not assume that the current
branch or a remote branch is published. After a future release, update that
configuration's `published_baseline_ref` to the actual published revision, or
pass `--baseline-ref`/`--baseline`. Keep the baseline until publication;
running the checker never advances it.

Use `--output` for a different candidate build directory with its matching
evidence files. Use `--out-dir` for a new named results directory. Existing
results are never overwritten. Exit status 0 means the audit completed, **not**
that every candidate passed; inspect the counts. Missing files, malformed
references and checksum mismatches stop with a nonzero status.

The Kaikki language-specific download is currently available but its
postprocessed format is deprecated upstream. A cached snapshot remains usable
offline. If the download is retired, supply a compatible Wiktextract reference
with `--reference` or update `reference_url` in the configuration. The parser
also accepts a multilingual raw extraction and filters for Hungarian. It
does not silently download the much larger multilingual dataset. A schema
change may require updating the parser; unsupported paradigms stay pending.

## Attribution and reproducibility

English noun meanings and inflection data are from English Wiktionary
contributors through Kaikki/Wiktextract. Reference-derived review data and
the small test reference retain [Creative Commons Attribution-ShareAlike 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
attribution. Candidate words retain the existing Ispell-source license.
Each supported result records a source entry link and its line in the
checksum-identified reference snapshot. The report records the current source
revision plus the checker, configuration and build-input hashes, so local
uncommitted edits are still identifiable. The full downloaded source and
generated reports are ignored build artifacts, not runtime dependencies.

No network requests occur on cached runs. Refreshing is explicit. Keep the
cached source alongside reports if exact reproduction of old results matters;
source pages can change. The six-entry test fixture's provenance is recorded
in `testdata/plural_possessive_reference.LICENSE.md`.
