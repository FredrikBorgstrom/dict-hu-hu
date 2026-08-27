#!/usr/bin/env python3
"""Build a conservative, evidence-scored Hungarian word-game candidate list.

The production generator deliberately keeps ordinary Magyar Ispell inflections
without requiring each surface to occur in a corpus.  That is appropriate for
coverage, but it also admits mechanically possible forms which players may not
regard as words.  This companion build does not replace production output.  It
scores the existing candidates with independent morphological and corpus
evidence, adds only strongly attested morphdb.hu headwords, and writes a fully
auditable candidate list for review.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unicodedata
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from process_words import (
    HUNGARIAN_REQUIRED_ONE_LETTER_WORDS,
    INVALID_STANDALONE_SURFACES,
    MANUAL_WRITTEN_ABBREVIATIONS,
    REJECT_ENTRY_FLAGS,
    _collect_source_filters,
    _has_flag,
    _sha256_file,
    _source_lemma,
    has_vowel,
    is_valid_hu_word,
    parse_aff,
    parse_dictionary_line,
)


MORPHDB_ARCHIVE_NAME = "morphdb-hu-20060525.tgz"
MORPHDB_URL = (
    "ftp://ftp.mokk.bme.hu/Tool/Hunmorph/Resources/Morphdb.hu/"
    "morphdb-hu-20060525.tgz"
)
MORPHDB_SHA256 = (
    "638a932bb3f0c44d10336e7a0529e8e93203ea69ec3b57c0aa77be0fcc5afc39"
)
MORPHDB_LICENSE = "Creative Commons Attribution 2.5"
MORPHDB_LICENSE_URL = "https://creativecommons.org/licenses/by/2.5/"

CORPUS_FIELD_NAMES = ("complete", "quality_40", "quality_8", "quality_4")
CORPUS_ENCODING = "iso-8859-2"

# Evidence thresholds are intentionally conservative.  Quality-8 is a cleaner
# Webcorpus partition than the complete-web column used by the coverage build.
CORE_QUALITY_8_FREQUENCY = 2
POSSESSIVE_QUALITY_4_FREQUENCY = 2
PLURAL_POSSESSIVE_QUALITY_4_FREQUENCY = 20
DERIVATION_QUALITY_4_FREQUENCY = 2
MORPHDB_ADDITION_QUALITY_4_FREQUENCY = 10
GENERATED_KOR_COMPLETE_FREQUENCY = 1

QUESTIONED_WORDS = (
    "al",
    "as",
    "aú",
    "beír",
    "bement",
    "box",
    "exkor",
    "faxos",
    "kijött",
    "lex",
    "luki",
    "lófő",
    "lófőm",
    "mé",
    "mi",
    "mii",
    "miibe",
    "miik",
    "tá",
    "vu",
    "zu",
    "ál",
)

POS_RE = re.compile(r"/(NOUN|VERB|ADJ|ADV|NUM|DET|UTT-INT|POSTP|CONJ)")
STEM_RE = re.compile(r"(?:^|\s)st:([^\s]+)")
LEXEME_RE = re.compile(
    r"(?:^|[+\s])([^\s+\[<>]+)/(?:NOUN|VERB|ADJ|ADV|NUM|DET|UTT-INT|POSTP|CONJ)"
)


@dataclass(frozen=True)
class CorpusEvidence:
    complete: int = 0
    quality_40: int = 0
    quality_8: int = 0
    quality_4: int = 0

    def as_tuple(self) -> tuple[int, int, int, int]:
        return self.complete, self.quality_40, self.quality_8, self.quality_4


@dataclass(frozen=True)
class MorphEvidence:
    recognized: bool = False
    nonproper: bool = False
    proper_only: bool = False
    derivation_only: bool = False
    prefix_only: bool = False
    possessive_only: bool = False
    plural_possessive_only: bool = False
    safe_inflection: bool = False
    lemma_agreement: bool = False
    parts_of_speech: tuple[str, ...] = ()

    def as_cache_fields(self) -> tuple[str, ...]:
        return (
            _bool_field(self.recognized),
            _bool_field(self.nonproper),
            _bool_field(self.proper_only),
            _bool_field(self.derivation_only),
            _bool_field(self.prefix_only),
            _bool_field(self.possessive_only),
            _bool_field(self.plural_possessive_only),
            _bool_field(self.safe_inflection),
            _bool_field(self.lemma_agreement),
            ",".join(self.parts_of_speech),
        )

    @classmethod
    def from_cache_fields(cls, fields: list[str]) -> "MorphEvidence":
        if len(fields) != 10:
            raise ValueError(f"Expected 10 morphdb evidence fields, got {len(fields)}")
        return cls(
            recognized=_parse_bool(fields[0]),
            nonproper=_parse_bool(fields[1]),
            proper_only=_parse_bool(fields[2]),
            derivation_only=_parse_bool(fields[3]),
            prefix_only=_parse_bool(fields[4]),
            possessive_only=_parse_bool(fields[5]),
            plural_possessive_only=_parse_bool(fields[6]),
            safe_inflection=_parse_bool(fields[7]),
            lemma_agreement=_parse_bool(fields[8]),
            parts_of_speech=tuple(filter(None, fields[9].split(","))),
        )


@dataclass(frozen=True)
class Decision:
    accepted: bool
    reason: str


def _bool_field(value: bool) -> str:
    return "1" if value else "0"


def _parse_bool(value: str) -> bool:
    if value not in {"0", "1"}:
        raise ValueError(f"Invalid Boolean cache field: {value!r}")
    return value == "1"


def is_source_policy_blocked_surface(word: str) -> bool:
    """Return whether an exact surface is excluded by source-game policy."""
    return (
        word in MANUAL_WRITTEN_ABBREVIATIONS
        or word in INVALID_STANDALONE_SURFACES
    )


def _is_lower_lexeme(value: str) -> bool:
    letters = [character for character in value if character.isalpha()]
    return bool(letters) and value == value.lower()


def parse_morphdb_block(
    word: str,
    analysis_lines: Iterable[str],
    approved_source_lemmas: frozenset[str],
) -> MorphEvidence:
    """Reduce all morphdb analyses for one surface to policy-safe features."""
    recognized_lines = []
    for raw_line in analysis_lines:
        line = raw_line.rstrip("\n")
        if not line or line == word:
            continue
        prefix = word + " "
        if line.startswith(prefix):
            recognized_lines.append(line[len(prefix) :].strip())

    if not recognized_lines:
        return MorphEvidence()

    nonproper_lines: list[str] = []
    proper_stem_seen = False
    lexemes: set[str] = set()
    parts_of_speech: set[str] = set()
    for analysis in recognized_lines:
        stems = STEM_RE.findall(analysis)
        line_lexemes = LEXEME_RE.findall(analysis)
        lexemes.update(line_lexemes)
        parts_of_speech.update(POS_RE.findall(analysis))
        has_lower = any(_is_lower_lexeme(stem) for stem in stems)
        has_lower = has_lower or any(
            _is_lower_lexeme(lexeme) for lexeme in line_lexemes
        )
        if has_lower:
            nonproper_lines.append(analysis)
        if any(stem != stem.lower() for stem in stems):
            proper_stem_seen = True

    nonproper = bool(nonproper_lines)
    proper_only = not nonproper and proper_stem_seen
    policy_lines = nonproper_lines or recognized_lines

    def every(predicate) -> bool:
        return bool(policy_lines) and all(predicate(line) for line in policy_lines)

    derivation_only = every(lambda line: "[" in line)
    prefix_only = every(lambda line: "/PREV+" in line)
    def has_possessive(line: str) -> bool:
        # morphdb.hu uses POSS for ordinary possessors and ANP for the
        # possessee/anaphoric -é paradigm (including forms such as -éi and
        # -éinak).  Both create the high-risk semantic stacks at issue here.
        return "<POSS" in line or "<ANP" in line

    possessive_only = every(has_possessive)
    plural_possessive_only = every(
        lambda line: has_possessive(line) and "<PLUR" in line
    )
    safe_inflection = any(
        "[" not in line and "/PREV+" not in line and not has_possessive(line)
        for line in nonproper_lines
    )
    candidate_lemmas = {
        unicodedata.normalize("NFC", value.lower())
        for analysis in nonproper_lines
        for value in STEM_RE.findall(analysis) + LEXEME_RE.findall(analysis)
        if _is_lower_lexeme(value)
    }
    lemma_agreement = bool(candidate_lemmas & approved_source_lemmas)

    return MorphEvidence(
        recognized=True,
        nonproper=nonproper,
        proper_only=proper_only,
        derivation_only=derivation_only,
        prefix_only=prefix_only,
        possessive_only=possessive_only,
        plural_possessive_only=plural_possessive_only,
        safe_inflection=safe_inflection,
        lemma_agreement=lemma_agreement,
        parts_of_speech=tuple(sorted(parts_of_speech)),
    )


def decide_word(
    word: str,
    corpus: CorpusEvidence,
    morph: MorphEvidence,
    *,
    current_candidate: bool,
    current_direct: bool,
    morphdb_direct: bool,
    morphdb_nonstandalone: bool = False,
    source_policy_blocked: bool = False,
    explicit_addition: bool = False,
    explicit_surface_removal: bool = False,
    explicit_lemma_removal: bool = False,
) -> Decision:
    """Apply the conservative policy in priority order."""
    if word in HUNGARIAN_REQUIRED_ONE_LETTER_WORDS:
        return Decision(True, "required_one_letter")
    if len(word) == 2 and not has_vowel(word):
        return Decision(False, "written_abbreviation_shape")
    # Keep the source generator's exact-surface exclusions authoritative.  A
    # previously promoted output can otherwise make a blocked form sticky:
    # corpus or morphdb.hu evidence would re-admit it even after the source
    # inventory stopped treating it as a valid direct form (for example
    # ``szja``, a written abbreviation).
    if source_policy_blocked:
        return Decision(False, "source_policy_blocked_surface")
    if explicit_surface_removal:
        return Decision(False, "reviewed_surface_removal")
    if explicit_lemma_removal:
        return Decision(False, "reviewed_lemma_removal")
    if explicit_addition:
        return Decision(True, "reviewed_surface_addition")
    # morphdb.hu's compiled dictionary contains PSEUDOROOT entries such as
    # ``tüz`` (the inflectional stem of ``tűz``) and ``közl`` (the stem of
    # ``közöl``).  They are implementation details for suffix generation, not
    # playable standalone surfaces.  Keep a valid Magyar Ispell homograph or a
    # surface that morphdb.hu can independently analyze through another
    # lexical path, but never let an unrecognized, previously promoted
    # pseudoroot become sticky through corpus evidence on a later build.
    if (
        morphdb_nonstandalone
        and not current_direct
        and not (morph.recognized and morph.nonproper)
    ):
        return Decision(False, "morphdb_nonstandalone_source")
    if morph.proper_only:
        return Decision(False, "morphdb_proper_name_only")

    # These stacked or semantic transformations are exactly where mechanical
    # morphology most often outruns normal game vocabulary.  Strong evidence
    # from the cleanest corpus partition is required even when another
    # analyzer can construct the form.
    if morph.plural_possessive_only:
        if corpus.quality_4 >= PLURAL_POSSESSIVE_QUALITY_4_FREQUENCY:
            return Decision(True, "strong_plural_possessive_usage")
        return Decision(False, "weak_plural_possessive")
    if morph.possessive_only:
        if corpus.quality_4 >= POSSESSIVE_QUALITY_4_FREQUENCY:
            return Decision(True, "attested_possessive")
        if current_direct:
            return Decision(True, "direct_source_form")
        return Decision(False, "weak_possessive")
    if morph.derivation_only:
        if corpus.quality_4 >= DERIVATION_QUALITY_4_FREQUENCY:
            return Decision(True, "attested_derivation")
        if current_direct:
            return Decision(True, "direct_source_form")
        return Decision(False, "weak_derivation")
    if morph.prefix_only:
        if corpus.quality_8 >= CORE_QUALITY_8_FREQUENCY:
            return Decision(True, "attested_prefix_combination")
        if current_direct:
            return Decision(True, "direct_source_form")
        return Decision(False, "weak_prefix_combination")

    if current_candidate and corpus.quality_8 >= CORE_QUALITY_8_FREQUENCY:
        return Decision(True, "quality_8_corpus_core")
    if current_candidate and current_direct:
        return Decision(True, "direct_source_form")
    if (
        current_candidate
        and corpus.quality_8 >= 1
        and morph.nonproper
    ):
        return Decision(True, "corroborated_corpus_singleton")
    if (
        current_candidate
        and morph.safe_inflection
        and morph.lemma_agreement
    ):
        # ``-kor`` is semantically selective: two morphology engines can
        # mechanically attach it to nouns and adjectives even when the result
        # has no plausible temporal use (for example ``exkor``).  Direct
        # headwords and corpus-attested forms have already returned above, so
        # require at least one complete-corpus occurrence for the remaining
        # generated forms.
        if (
            word.endswith("kor")
            and corpus.complete < GENERATED_KOR_COMPLETE_FREQUENCY
        ):
            return Decision(False, "unattested_generated_kor_form")
        return Decision(True, "cross_analyzer_basic_inflection")
    if (
        not current_candidate
        and morphdb_direct
        and morph.recognized
        and morph.nonproper
        and corpus.quality_4 >= MORPHDB_ADDITION_QUALITY_4_FREQUENCY
    ):
        return Decision(True, "attested_morphdb_headword_addition")
    if morph.recognized and not morph.nonproper:
        return Decision(False, "morphdb_nonlexical_or_uncased")
    if morph.nonproper:
        return Decision(False, "insufficient_usage_or_risky_inflection")
    return Decision(False, "no_independent_evidence")


def ensure_morphdb(cache_dir: Path, *, offline: bool) -> tuple[Path, Path, Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    archive_path = cache_dir / MORPHDB_ARCHIVE_NAME
    if archive_path.exists() and _sha256_file(str(archive_path)) != MORPHDB_SHA256:
        raise ValueError(f"Checksum mismatch for cached {archive_path}")
    if not archive_path.exists():
        if offline:
            raise FileNotFoundError(f"Offline mode: missing {archive_path}")
        temporary_path = archive_path.with_suffix(".download")
        try:
            print(f"Downloading pinned morphdb.hu release to {archive_path}...", flush=True)
            with urllib.request.urlopen(MORPHDB_URL) as response, open(
                temporary_path, "wb"
            ) as output_file:
                shutil.copyfileobj(response, output_file)
            if _sha256_file(str(temporary_path)) != MORPHDB_SHA256:
                raise ValueError("Downloaded morphdb.hu archive checksum mismatch")
            os.replace(temporary_path, archive_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    extracted_dir = cache_dir / "morphdb-hu-20060525"
    aff_path = extracted_dir / "morphdb_hu.aff"
    dic_path = extracted_dir / "morphdb_hu.dic"
    license_path = extracted_dir / "LICENCE"
    if not all(path.exists() for path in (aff_path, dic_path, license_path)):
        temporary_dir = Path(
            tempfile.mkdtemp(prefix=".morphdb-extract.", dir=cache_dir)
        )
        try:
            members = {
                "morphdb.hu/morphdb_hu.aff": "morphdb_hu.aff",
                "morphdb.hu/morphdb_hu.dic": "morphdb_hu.dic",
                "morphdb.hu/LICENCE": "LICENCE",
            }
            with tarfile.open(archive_path, "r:gz") as archive:
                for source_name, target_name in members.items():
                    source = archive.extractfile(source_name)
                    if source is None:
                        raise ValueError(f"Missing {source_name} in morphdb archive")
                    with open(temporary_dir / target_name, "wb") as target:
                        shutil.copyfileobj(source, target)
            if extracted_dir.exists():
                shutil.rmtree(extracted_dir)
            os.replace(temporary_dir, extracted_dir)
        finally:
            if temporary_dir.exists():
                shutil.rmtree(temporary_dir)
    return aff_path, dic_path, license_path


def _load_morphdb_pseudoroot_flag(aff_path: Path) -> str:
    flag_mode = None
    pseudoroot_flag = None
    with open(aff_path, "r", encoding="iso-8859-2", errors="strict") as source:
        for raw_line in source:
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.split()
            if parts[0] == "FLAG" and len(parts) >= 2:
                flag_mode = parts[1]
            elif parts[0] == "PSEUDOROOT" and len(parts) >= 2:
                pseudoroot_flag = parts[1]

    if flag_mode != "long":
        raise ValueError(
            f"Expected morphdb.hu to use long flags, found {flag_mode!r}"
        )
    if pseudoroot_flag is None or len(pseudoroot_flag) != 2:
        raise ValueError("Missing two-character morphdb.hu PSEUDOROOT flag")
    return pseudoroot_flag


def _has_morphdb_long_flag(flags: str, expected: str) -> bool:
    if len(flags) % 2:
        raise ValueError(f"Malformed morphdb.hu long-flag sequence: {flags!r}")
    return any(
        flags[index : index + 2] == expected
        for index in range(0, len(flags), 2)
    )


def load_morphdb_source_inventory(
    aff_path: Path,
    dic_path: Path,
) -> tuple[frozenset[str], frozenset[str]]:
    """Return standalone source surfaces and pseudoroot-only source tokens."""
    pseudoroot_flag = _load_morphdb_pseudoroot_flag(aff_path)
    standalone_surfaces: set[str] = set()
    pseudoroot_surfaces: set[str] = set()
    with open(dic_path, "r", encoding="iso-8859-2", errors="strict") as source:
        next(source, None)
        for line in source:
            entry = line.split("\t", 1)[0]
            token, separator, flags = entry.partition("/")
            token = unicodedata.normalize("NFC", token)
            if token != token.lower() or not is_valid_hu_word(token):
                continue
            if separator and _has_morphdb_long_flag(flags, pseudoroot_flag):
                pseudoroot_surfaces.add(token)
            else:
                standalone_surfaces.add(token)

    # A spelling may have both a pseudoroot analysis and a genuine standalone
    # entry.  Only tokens whose source analyses are exclusively pseudoroots are
    # automatic rejections.
    pseudoroot_only = pseudoroot_surfaces - standalone_surfaces
    return frozenset(standalone_surfaces), frozenset(pseudoroot_only)


def load_current_source_inventory(
    aff_path: Path,
    dic_path: Path,
) -> tuple[frozenset[str], frozenset[str]]:
    af_aliases, am_aliases, pfx_rules, sfx_rules, special_flags = parse_aff(
        str(aff_path)
    )
    with open(dic_path, "r", encoding="utf-8", errors="replace") as source:
        lines = source.readlines()[1:]
    abbreviations, blocked_surfaces, _proper_derivatives = _collect_source_filters(
        lines,
        af_aliases,
        am_aliases,
        pfx_rules,
        sfx_rules,
        special_flags,
    )
    direct: set[str] = set()
    lemmas: set[str] = set()
    for line in lines:
        parsed = parse_dictionary_line(line, af_aliases, am_aliases)
        if parsed is None:
            continue
        word, flags, morphology = parsed
        if " " in word or word.startswith("-") or word != word.lower():
            continue
        surface = unicodedata.normalize("NFC", word.lower())
        if not is_valid_hu_word(surface):
            continue
        if any(_has_flag(flags, special_flags, name) for name in REJECT_ENTRY_FLAGS):
            continue
        if surface in abbreviations or surface in blocked_surfaces:
            continue
        lemma = _source_lemma(surface, morphology)
        if is_valid_hu_word(lemma):
            lemmas.add(lemma)
        if not _has_flag(flags, special_flags, "NEEDAFFIX"):
            direct.add(surface)
    direct.difference_update(MANUAL_WRITTEN_ABBREVIATIONS)
    direct.difference_update(INVALID_STANDALONE_SURFACES)
    return frozenset(direct), frozenset(lemmas)


def load_surface_overrides(path: Path | None) -> frozenset[str]:
    if path is None or not path.exists():
        return frozenset()
    removals = {
        unicodedata.normalize("NFC", line.strip())
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    return frozenset(removals)


def expand_lemma_removals(
    index_dir: Path,
    removed_lemmas: frozenset[str],
) -> tuple[frozenset[str], frozenset[str]]:
    """Resolve reviewed lemma removals while preserving valid homographs.

    A surface is removed only when every source lemma that licenses it is
    removed.  A lemma spelling absent from the current promoted index is still
    returned as a removal so a later morphdb merge cannot reintroduce the
    headword after its family has already been promoted out.
    """
    if not removed_lemmas:
        return frozenset(), frozenset()

    manifest_path = index_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"Lemma removals require a surface-to-lemma manifest: {manifest_path}"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    shards = manifest.get("shards")
    if not isinstance(shards, dict):
        raise ValueError(f"Malformed surface-to-lemma manifest: {manifest_path}")

    removals: set[str] = set()
    seen_lemmas: set[str] = set()
    mapped_surfaces: set[str] = set()
    for shard_key, metadata in sorted(shards.items()):
        shard_path = index_dir / f"{shard_key}.tsv.gz"
        if not shard_path.is_file():
            raise FileNotFoundError(f"Missing surface-to-lemma shard: {shard_path}")
        expected_sha256 = metadata.get("sha256") if isinstance(metadata, dict) else None
        if expected_sha256 != _sha256_file(str(shard_path)):
            raise ValueError(f"Surface-to-lemma shard checksum mismatch: {shard_path}")
        with gzip.open(shard_path, "rt", encoding="utf-8") as source:
            for line in source:
                surface, separator, lemmas_raw = line.rstrip("\n").partition("\t")
                if not separator or not surface or not lemmas_raw:
                    raise ValueError(f"Malformed lemma row in {shard_path}: {line!r}")
                lemmas = tuple(filter(None, lemmas_raw.split(",")))
                if not lemmas:
                    raise ValueError(f"Lemma row has no mappings in {shard_path}: {line!r}")
                mapped_surfaces.add(surface)
                seen_lemmas.update(removed_lemmas.intersection(lemmas))
                if all(lemma in removed_lemmas for lemma in lemmas):
                    removals.add(surface)

    # On repeat builds the removed family is no longer present in the promoted
    # index.  Keep blocking the headword itself if morphdb proposes it again.
    removals.update(removed_lemmas - mapped_surfaces)
    return frozenset(removals), frozenset(seen_lemmas)


def load_corpus_evidence(
    corpus_path: Path,
    candidates: frozenset[str],
) -> dict[str, CorpusEvidence]:
    evidence: dict[str, CorpusEvidence] = {}
    with gzip.open(corpus_path, "rb") as source:
        for raw_line in source:
            fields = raw_line.removesuffix(b"\n").decode(CORPUS_ENCODING).split("\t")
            if len(fields) < 5:
                continue
            word = unicodedata.normalize("NFC", fields[0])
            if word not in candidates:
                continue
            try:
                frequencies = tuple(int(field or 0) for field in fields[1:5])
            except ValueError:
                continue
            evidence[word] = CorpusEvidence(*frequencies)
    return evidence


def _analysis_cache_key(
    candidate_path: Path,
    morphdb_dic_path: Path,
    approved_source_lemmas: frozenset[str],
) -> str:
    digest = hashlib.sha256()
    for path in (candidate_path, morphdb_dic_path):
        digest.update(_sha256_file(str(path)).encode("ascii"))
    for lemma in sorted(approved_source_lemmas):
        digest.update(lemma.encode("utf-8"))
        digest.update(b"\n")
    digest.update(b"morph-evidence-schema-2")
    return digest.hexdigest()[:20]


def iter_cached_morph_evidence(cache_path: Path) -> Iterator[tuple[str, MorphEvidence]]:
    with gzip.open(cache_path, "rt", encoding="utf-8") as source:
        header = source.readline().rstrip("\n")
        if not header.startswith("# schema=2\t"):
            raise ValueError(f"Unsupported morphdb cache header in {cache_path}")
        for line in source:
            fields = line.rstrip("\n").split("\t")
            if len(fields) != 11:
                raise ValueError(f"Malformed morphdb cache row in {cache_path}")
            yield fields[0], MorphEvidence.from_cache_fields(fields[1:])


def build_morph_evidence_cache(
    candidates_path: Path,
    morphdb_aff_path: Path,
    morphdb_dic_path: Path,
    approved_source_lemmas: frozenset[str],
    cache_path: Path,
    hunspell_binary: str,
    worker_count: int,
) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    dictionary_stem = str(morphdb_dic_path.with_suffix(""))
    temporary_path = cache_path.with_suffix(".tmp.gz")
    command = [hunspell_binary, "-i", "utf-8", "-m", "-d", dictionary_stem]
    environment = os.environ.copy()
    environment["DICPATH"] = str(morphdb_aff_path.parent)
    worker_count = max(1, worker_count)
    print(
        "Analysing candidate forms with morphdb.hu "
        f"using {worker_count} workers (first run takes several minutes)...",
        flush=True,
    )

    work_dir = Path(
        tempfile.mkdtemp(prefix=".morphdb-analysis.", dir=cache_path.parent)
    )
    chunk_size = 100_000
    chunk_paths: list[Path] = []
    chunk_file = None
    total_candidates = 0
    try:
        with open(candidates_path, "r", encoding="utf-8") as source:
            for index, line in enumerate(source):
                total_candidates = index + 1
                if index % chunk_size == 0:
                    if chunk_file is not None:
                        chunk_file.close()
                    chunk_path = work_dir / f"chunk-{len(chunk_paths):05d}.txt"
                    chunk_paths.append(chunk_path)
                    chunk_file = open(chunk_path, "w", encoding="utf-8", newline="\n")
                assert chunk_file is not None
                chunk_file.write(line)
        if chunk_file is not None:
            chunk_file.close()
            chunk_file = None

        def analyse_chunk(chunk_path: Path) -> tuple[Path, int]:
            part_path = chunk_path.with_suffix(".tsv.gz")
            stderr_path = chunk_path.with_suffix(".stderr")
            expected_words = chunk_path.read_text(encoding="utf-8").splitlines()
            with open(chunk_path, "r", encoding="utf-8") as candidate_file, open(
                stderr_path, "w", encoding="utf-8"
            ) as stderr_file, gzip.open(
                part_path, "wt", encoding="utf-8", newline="\n"
            ) as part_file:
                process = subprocess.Popen(
                    command,
                    stdin=candidate_file,
                    stdout=subprocess.PIPE,
                    stderr=stderr_file,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=environment,
                )
                assert process.stdout is not None
                block: list[str] = []
                processed = 0

                def write_block() -> None:
                    nonlocal processed
                    if processed >= len(expected_words):
                        raise ValueError(
                            f"hunspell returned extra analysis block for {chunk_path}"
                        )
                    # Hunspell correctly emits UTF-8 for recognized ISO-8859-2
                    # dictionary words, but mojibakes the echoed surface for an
                    # unknown UTF-8 word.  Candidate order is authoritative and
                    # is already bound into the cache key, so never recover the
                    # surface from Hunspell's echo.
                    word = expected_words[processed]
                    evidence = parse_morphdb_block(
                        word, block, approved_source_lemmas
                    )
                    part_file.write(
                        "\t".join((word, *evidence.as_cache_fields())) + "\n"
                    )
                    processed += 1
                    block.clear()

                for line in process.stdout:
                    if line.strip():
                        block.append(line.rstrip("\n"))
                    elif block:
                        write_block()
                if block:
                    write_block()
                return_code = process.wait()
                if processed != len(expected_words):
                    raise ValueError(
                        f"hunspell returned {processed} blocks for "
                        f"{len(expected_words)} candidates in {chunk_path}"
                    )
            if return_code != 0:
                stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
                raise RuntimeError(
                    f"hunspell morphdb analysis failed with code {return_code}: "
                    f"{stderr.strip()}"
                )
            return part_path, processed

        results: dict[Path, tuple[Path, int]] = {}
        completed = 0
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=worker_count
        ) as executor:
            futures = {
                executor.submit(analyse_chunk, chunk_path): chunk_path
                for chunk_path in chunk_paths
            }
            for future in concurrent.futures.as_completed(futures):
                chunk_path = futures[future]
                part_path, processed = future.result()
                results[chunk_path] = (part_path, processed)
                completed += processed
                print(
                    f"  morphdb.hu analysed {completed:,}/{total_candidates:,} forms",
                    flush=True,
                )

        processed_total = 0
        with gzip.open(
            temporary_path, "wt", encoding="utf-8", newline="\n"
        ) as cache_file:
            cache_file.write(
                f"# schema=2\tcandidate_sha256={_sha256_file(str(candidates_path))}"
                f"\tmorphdb_sha256={MORPHDB_SHA256}\n"
            )
            for chunk_path in chunk_paths:
                part_path, processed = results[chunk_path]
                with gzip.open(part_path, "rt", encoding="utf-8") as part_file:
                    shutil.copyfileobj(part_file, cache_file)
                processed_total += processed
        os.replace(temporary_path, cache_path)
        print(
            f"  morphdb.hu analysis cached for {processed_total:,} forms",
            flush=True,
        )
    finally:
        if chunk_file is not None:
            chunk_file.close()
        if temporary_path.exists():
            temporary_path.unlink()
        shutil.rmtree(work_dir, ignore_errors=True)


def _merge_candidate_inventory(
    current_words_path: Path,
    morphdb_direct: frozenset[str],
    surface_additions: frozenset[str],
    cache_dir: Path,
) -> tuple[Path, frozenset[str]]:
    current_words = frozenset(
        line.rstrip("\n")
        for line in current_words_path.read_text(encoding="utf-8").splitlines()
        if line
    )
    merged_path = cache_dir / "merged-candidate-inventory.txt"
    merged_words = (
        current_words
        | morphdb_direct
        | surface_additions
        | HUNGARIAN_REQUIRED_ONE_LETTER_WORDS
    )
    digest = hashlib.sha256()
    temporary_path = merged_path.with_suffix(".tmp")
    with open(temporary_path, "w", encoding="utf-8", newline="\n") as output:
        for word in sorted(merged_words):
            line = word + "\n"
            output.write(line)
            digest.update(line.encode("utf-8"))
    expected_hash = digest.hexdigest()
    hash_path = merged_path.with_suffix(".sha256")
    if (
        merged_path.exists()
        and hash_path.exists()
        and hash_path.read_text(encoding="ascii").strip() == expected_hash
    ):
        temporary_path.unlink()
    else:
        os.replace(temporary_path, merged_path)
        hash_path.write_text(expected_hash + "\n", encoding="ascii")
    return merged_path, current_words


def _sample_score(word: str) -> str:
    return hashlib.sha256(word.encode("utf-8")).hexdigest()


def build_outputs(
    *,
    merged_candidates_path: Path,
    current_words: frozenset[str],
    current_direct: frozenset[str],
    morphdb_direct: frozenset[str],
    morphdb_nonstandalone: frozenset[str],
    corpus_evidence: dict[str, CorpusEvidence],
    morph_cache_path: Path,
    surface_additions: frozenset[str],
    surface_removals: frozenset[str],
    lemma_removals: frozenset[str],
    lemma_removed_surfaces: frozenset[str],
    output_dir: Path,
    source_metadata: dict,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = output_dir / "hungarian_hu_hu_evidence_candidate.txt"
    evidence_path = output_dir / "evidence.tsv.gz"
    rejected_path = output_dir / "rejected.tsv.gz"
    audit_path = output_dir / "audit.json"
    report_path = output_dir / "report.md"

    counts: Counter = Counter()
    reason_counts: Counter = Counter()
    length_counts: Counter = Counter()
    samples: dict[str, list[tuple[str, str]]] = defaultdict(list)
    questioned: dict[str, dict] = {}
    digest = hashlib.sha256()

    morph_iterator = iter_cached_morph_evidence(morph_cache_path)
    with open(candidate_path, "w", encoding="utf-8", newline="\n") as accepted_file, gzip.open(
        evidence_path, "wt", encoding="utf-8", newline="\n"
    ) as evidence_file, gzip.open(
        rejected_path, "wt", encoding="utf-8", newline="\n"
    ) as rejected_file:
        header = (
            "word\tdecision\treason\tcomplete\tquality_40\tquality_8\tquality_4"
            "\tmorphdb_recognized\tmorphdb_nonproper\tmorphdb_proper_only"
            "\tderivation_only\tprefix_only\tpossessive_only"
            "\tplural_possessive_only\tsafe_inflection\tlemma_agreement"
            "\tparts_of_speech\n"
        )
        evidence_file.write(header)
        rejected_file.write("word\treason\tcomplete\tquality_8\tquality_4\n")
        for expected_word in merged_candidates_path.read_text(encoding="utf-8").splitlines():
            try:
                word, morph = next(morph_iterator)
            except StopIteration as error:
                raise ValueError("Morphdb cache ended before candidate inventory") from error
            # Schema 1 caches created with Hunspell's unknown-word echo may
            # contain a mojibaked cached surface.  Cache order remains exact
            # because its candidate checksum matches the merged inventory.
            # Use the authoritative inventory spelling for all output.
            word = expected_word
            corpus = corpus_evidence.get(word, CorpusEvidence())
            decision = decide_word(
                word,
                corpus,
                morph,
                current_candidate=word in current_words,
                current_direct=word in current_direct,
                morphdb_direct=word in morphdb_direct,
                morphdb_nonstandalone=word in morphdb_nonstandalone,
                source_policy_blocked=is_source_policy_blocked_surface(word),
                explicit_addition=word in surface_additions,
                explicit_surface_removal=word in surface_removals,
                explicit_lemma_removal=word in lemma_removed_surfaces,
            )
            reason_counts[decision.reason] += 1
            counts["total_candidates"] += 1
            if word in current_words:
                counts["current_candidates"] += 1
            else:
                counts["external_candidates"] += 1
            if decision.accepted:
                counts["accepted"] += 1
                if word not in current_words:
                    counts["accepted_additions"] += 1
                line = word + "\n"
                accepted_file.write(line)
                digest.update(line.encode("utf-8"))
                length_counts[len(word)] += 1
                decision_label = "accept"
            else:
                counts["rejected"] += 1
                if word in current_words:
                    counts["rejected_from_current"] += 1
                rejected_file.write(
                    f"{word}\t{decision.reason}\t{corpus.complete}\t"
                    f"{corpus.quality_8}\t{corpus.quality_4}\n"
                )
                decision_label = "reject"

            row = (
                word,
                decision_label,
                decision.reason,
                *(str(value) for value in corpus.as_tuple()),
                *morph.as_cache_fields(),
            )
            evidence_file.write("\t".join(row) + "\n")
            ranked_samples = samples[decision.reason]
            ranked_samples.append((_sample_score(word), word))
            ranked_samples.sort()
            del ranked_samples[20:]
            if word in QUESTIONED_WORDS:
                questioned[word] = {
                    "decision": decision_label,
                    "reason": decision.reason,
                    "corpus": dict(zip(CORPUS_FIELD_NAMES, corpus.as_tuple())),
                    "morphdb": {
                        "recognized": morph.recognized,
                        "nonproper": morph.nonproper,
                        "proper_only": morph.proper_only,
                        "derivation_only": morph.derivation_only,
                        "prefix_only": morph.prefix_only,
                        "possessive_only": morph.possessive_only,
                        "plural_possessive_only": morph.plural_possessive_only,
                        "lemma_agreement": morph.lemma_agreement,
                        "parts_of_speech": list(morph.parts_of_speech),
                    },
                }
        try:
            extra_word, _extra_evidence = next(morph_iterator)
        except StopIteration:
            pass
        else:
            raise ValueError(f"Morphdb cache has unexpected extra row {extra_word!r}")

    audit = {
        "schema_version": 2,
        "description": "Conservative evidence-scored candidate; not production output",
        "source": source_metadata,
        "policy": {
            "core_quality_8_frequency": CORE_QUALITY_8_FREQUENCY,
            "possessive_quality_4_frequency": POSSESSIVE_QUALITY_4_FREQUENCY,
            "plural_possessive_quality_4_frequency": (
                PLURAL_POSSESSIVE_QUALITY_4_FREQUENCY
            ),
            "derivation_quality_4_frequency": DERIVATION_QUALITY_4_FREQUENCY,
            "morphdb_addition_quality_4_frequency": (
                MORPHDB_ADDITION_QUALITY_4_FREQUENCY
            ),
            "morphdb_pseudoroots_rejected": True,
            "morphdb_additions_require_standalone_analysis": True,
            "proper_name_only_rejected": True,
            "source_policy_blocked_surfaces": sorted(
                MANUAL_WRITTEN_ABBREVIATIONS | INVALID_STANDALONE_SURFACES
            ),
            "prefix_combinations_require_quality_8_usage": True,
            "cross_analyzer_basic_inflections_require_lemma_agreement": True,
            "generated_kor_complete_frequency": GENERATED_KOR_COMPLETE_FREQUENCY,
            "surface_additions": sorted(surface_additions),
            "surface_removals": sorted(surface_removals),
            "lemma_removals": sorted(lemma_removals),
            "lemma_removed_surface_count": len(lemma_removed_surfaces),
        },
        "counts": dict(sorted(counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "accepted_length_counts": {
            str(length): count for length, count in sorted(length_counts.items())
        },
        "questioned_words": questioned,
        "samples": {
            reason: [word for _score, word in ranked]
            for reason, ranked in sorted(samples.items())
        },
        "output_sha256": digest.hexdigest(),
        "artifacts": {
            "candidate": candidate_path.name,
            "evidence": evidence_path.name,
            "rejected": rejected_path.name,
            "report": report_path.name,
        },
    }
    audit_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_report(audit, report_path)
    return audit


def write_report(audit: dict, report_path: Path) -> None:
    counts = audit["counts"]
    lines = [
        "# Hungarian evidence-scored candidate report",
        "",
        "This is a local candidate for review. It does not replace or deploy "
        "the production dictionary.",
        "",
        "## Summary",
        "",
        f"- Accepted words: **{counts.get('accepted', 0):,}**",
        "- Current words removed by the candidate policy: "
        f"**{counts.get('rejected_from_current', 0):,}**",
        "- Strongly attested morphdb.hu headword additions: "
        f"**{counts.get('accepted_additions', 0):,}**",
        f"- Candidate SHA-256: `{audit['output_sha256']}`",
        "",
        "## Decisions by evidence rule",
        "",
        "| Rule | Words |",
        "|---|---:|",
    ]
    for reason, count in sorted(
        audit["reason_counts"].items(), key=lambda item: (-item[1], item[0])
    ):
        lines.append(f"| `{reason}` | {count:,} |")
    lines.extend(
        [
            "",
            "## Reported and diagnostic words",
            "",
            "| Word | Decision | Reason | Quality-8 | Quality-4 |",
            "|---|---|---|---:|---:|",
        ]
    )
    for word in QUESTIONED_WORDS:
        record = audit["questioned_words"].get(word)
        if record is None:
            lines.append(f"| `{word}` | not a candidate | — | 0 | 0 |")
            continue
        lines.append(
            f"| `{word}` | {record['decision']} | `{record['reason']}` | "
            f"{record['corpus']['quality_8']} | {record['corpus']['quality_4']} |"
        )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- Corpus occurrence is evidence of usage, not proof of lexical validity.",
            "- morphdb.hu partly incorporates Magyar Ispell, so it is "
            "corroborating rather than fully independent evidence.",
            "- The public morphdb.hu release is from 2006; modern vocabulary "
            "depends primarily on Magyar Ispell and corpus evidence.",
            "- Lowercased surfaces can hide some names. Proper-name-only "
            "morphdb analyses are rejected, but no automated method can "
            "identify every name collision.",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")


def _hunspell_version(binary: str) -> str:
    result = subprocess.run(
        [binary, "--version"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return (result.stdout or result.stderr).splitlines()[0]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the local evidence-scored Hungarian candidate list."
    )
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--cache-dir")
    parser.add_argument("--output-dir")
    parser.add_argument("--surface-removals")
    parser.add_argument("--surface-additions")
    parser.add_argument("--lemma-removals")
    parser.add_argument(
        "--morph-workers",
        type=int,
        default=min(4, os.cpu_count() or 1),
        help="Parallel hunspell processes used for morphdb.hu analysis (default: up to 4).",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    cache_dir = Path(args.cache_dir) if args.cache_dir else script_dir / ".cache" / "evidence"
    output_dir = Path(args.output_dir) if args.output_dir else script_dir / "candidate"
    current_output_path = script_dir / "output" / "hungarian_hu_hu_ispell.txt"
    current_aff_path = script_dir / ".cache" / "sources" / "hu_HU.aff"
    current_dic_path = script_dir / ".cache" / "sources" / "hu_HU.dic"
    current_lemma_index_dir = (
        script_dir / "output" / "definitions" / "hu" / "surface-lemma" / "v1"
    )
    corpus_path = script_dir / ".cache" / "sources" / "web2.2-alfa-sorted.txt.gz"
    for required_path in (
        current_output_path,
        current_aff_path,
        current_dic_path,
        corpus_path,
    ):
        if not required_path.exists():
            print(f"ERROR: missing prerequisite {required_path}", file=sys.stderr)
            return 1

    try:
        morphdb_aff_path, morphdb_dic_path, morphdb_license_path = ensure_morphdb(
            cache_dir / "sources", offline=args.offline
        )
        hunspell_binary = shutil.which("hunspell")
        if hunspell_binary is None:
            raise FileNotFoundError(
                "hunspell is required for morphdb.hu analysis but was not found"
            )
        current_direct, approved_source_lemmas = load_current_source_inventory(
            current_aff_path, current_dic_path
        )
        morphdb_direct, morphdb_nonstandalone = load_morphdb_source_inventory(
            morphdb_aff_path, morphdb_dic_path
        )
        default_overrides_dir = (
            script_dir.parent / "_community_overrides" / "hungarian_hu_hu_ispell"
        )
        surface_additions = load_surface_overrides(
            Path(args.surface_additions)
            if args.surface_additions
            else default_overrides_dir / "additions.txt"
        )
        surface_removals = load_surface_overrides(
            Path(args.surface_removals)
            if args.surface_removals
            else default_overrides_dir / "surface-removals.txt"
        )
        lemma_removals = load_surface_overrides(
            Path(args.lemma_removals)
            if args.lemma_removals
            else default_overrides_dir / "lemma-removals.txt"
        )
        conflicts = surface_additions & surface_removals
        if conflicts:
            raise ValueError(
                "Surfaces cannot be both added and removed: "
                + ", ".join(sorted(conflicts))
            )
        invalid_additions = {
            word
            for word in surface_additions
            if word not in HUNGARIAN_REQUIRED_ONE_LETTER_WORDS
            and not is_valid_hu_word(word)
        }
        if invalid_additions:
            raise ValueError(
                "Invalid reviewed surface additions: "
                + ", ".join(sorted(invalid_additions))
            )
        invalid_removals = {
            word
            for word in surface_removals | lemma_removals
            if not is_valid_hu_word(word)
        }
        if invalid_removals:
            raise ValueError(
                "Invalid reviewed removals: " + ", ".join(sorted(invalid_removals))
            )
        lemma_removed_surfaces, indexed_removed_lemmas = expand_lemma_removals(
            current_lemma_index_dir,
            lemma_removals,
        )
        unknown_removed_lemmas = lemma_removals - (
            indexed_removed_lemmas | approved_source_lemmas | morphdb_direct
        )
        if unknown_removed_lemmas:
            raise ValueError(
                "Reviewed lemma removals are absent from all source inventories: "
                + ", ".join(sorted(unknown_removed_lemmas))
            )
        effective_removal_conflicts = surface_additions & (
            surface_removals | lemma_removed_surfaces
        )
        if effective_removal_conflicts:
            raise ValueError(
                "Surfaces cannot be both added and removed: "
                + ", ".join(sorted(effective_removal_conflicts))
            )
        merged_path, current_words = _merge_candidate_inventory(
            current_output_path, morphdb_direct, surface_additions, cache_dir
        )
        merged_words = frozenset(merged_path.read_text(encoding="utf-8").splitlines())
        print(f"Loading corpus evidence for {len(merged_words):,} candidate forms...", flush=True)
        corpus_evidence = load_corpus_evidence(corpus_path, merged_words)
        print(f"  corpus evidence found for {len(corpus_evidence):,} forms", flush=True)

        cache_key = _analysis_cache_key(
            merged_path, morphdb_dic_path, approved_source_lemmas
        )
        morph_cache_path = cache_dir / f"morphdb-analysis-{cache_key}.tsv.gz"
        if not morph_cache_path.exists():
            build_morph_evidence_cache(
                merged_path,
                morphdb_aff_path,
                morphdb_dic_path,
                approved_source_lemmas,
                morph_cache_path,
                hunspell_binary,
                args.morph_workers,
            )
        else:
            print(f"Using cached morphdb.hu analysis {morph_cache_path.name}", flush=True)

        source_metadata = {
            "current_candidate": {
                "path": str(current_output_path.relative_to(script_dir)),
                "sha256": _sha256_file(str(current_output_path)),
            },
            "magyar_ispell": {
                "aff_sha256": _sha256_file(str(current_aff_path)),
                "dic_sha256": _sha256_file(str(current_dic_path)),
            },
            "webcorpus": {
                "path": corpus_path.name,
                "sha256": _sha256_file(str(corpus_path)),
                "fields": list(CORPUS_FIELD_NAMES),
            },
            "morphdb": {
                "archive": MORPHDB_ARCHIVE_NAME,
                "sha256": MORPHDB_SHA256,
                "license": MORPHDB_LICENSE,
                "license_url": MORPHDB_LICENSE_URL,
                "bundled_license_sha256": _sha256_file(str(morphdb_license_path)),
            },
            "hunspell": {
                "path": hunspell_binary,
                "version": _hunspell_version(hunspell_binary),
            },
        }
        audit = build_outputs(
            merged_candidates_path=merged_path,
            current_words=current_words,
            current_direct=current_direct,
            morphdb_direct=morphdb_direct,
            morphdb_nonstandalone=morphdb_nonstandalone,
            corpus_evidence=corpus_evidence,
            morph_cache_path=morph_cache_path,
            surface_additions=surface_additions,
            surface_removals=surface_removals,
            lemma_removals=lemma_removals,
            lemma_removed_surfaces=lemma_removed_surfaces,
            output_dir=output_dir,
            source_metadata=source_metadata,
        )
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(
        f"Done. Wrote {audit['counts']['accepted']:,} evidence-scored words to "
        f"{output_dir / 'hungarian_hu_hu_evidence_candidate.txt'}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
