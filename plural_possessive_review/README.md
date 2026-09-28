# September 2026 plural-possession release review

Fredrik requested on 28 September 2026 that the unpublished 404,258-word
expansion be replaced by its exact **164,271 reference-supported additions**.
The other **239,987** are deferred, not declared invalid.

`scope.txt.gz` is the complete original delta from published baseline
`01b37a4dd3372361af5a0700a59bde353dc45dfb`. `supported.txt.gz` is the approved
subset, copied exactly from the reproducible validator report. `decisions.tsv.gz`
preserves all supporting decisions and source-entry references. The manifest
pins counts, checksums, candidate/baseline/validator revisions and the reference
snapshot. These are versioned release-policy inputs, not disposable build logs.

Both evidence-build passes exclude `scope − supported`, regardless of any
alternate acceptance path or stale retained input. Promotion rejects an older
candidate containing a deferred surface before changing active files. The
supported list grants no new acceptance by itself: all existing source,
analyzer, exclusion and gameplay rules still apply. Ordinary published words
outside this review scope keep their existing policy.

No noun family is approved wholesale. In particular, an additional case form
or similar spelling does not inherit another surface's approval. Later lexical
review can update these pinned inputs deliberately; ordinary builds do not
download a moving reference or silently broaden this batch.

The release verifier requires the full ordinary delta to equal `supported`
exactly, retains every published word and mapping, and excludes deferred words
from every tile mode. The documented source-generator inventory may still
contain mechanically licensed forms: it is input to the evidence filter, not
the playable dictionary.

Attribution for reference-derived decisions: English Wiktionary contributors,
via [Kaikki](https://kaikki.org/dictionary/Hungarian/index.html), under
[Creative Commons Attribution-ShareAlike 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
The candidate word surfaces retain their existing Ispell-source license.
This evidence supports the narrowed release; it does not certify infallible
linguistic correctness or change the deployment approval requirement.
