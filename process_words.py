#!/usr/bin/env python3
"""
Generate a strict Hungarian word list from the Magyar Ispell Hunspell files.

Source: Magyar Ispell 1.9 (hu_HU.aff + hu_HU.dic)
License of output: Mozilla Public License 1.1 (derived from Magyar Ispell)

The source is a spell-checking dictionary, so accepting every lowercase-looking
surface form is not sufficient for a word game.  This processor preserves valid
Hungarian inflections while excluding forms that Magyar Ispell marks as
forbidden, substandard, case-sensitive, affix-only, or compound-only.  It also
uses the source morphological metadata to remove written abbreviations.

Output:      output/hungarian_hu_hu_ispell.txt
Lemma index: output/definitions/hu/surface-lemma/v1/*.tsv.gz
Audit:       output/audit.json
"""

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import urllib.request
from collections import Counter, defaultdict
from typing import NamedTuple


# Hungarian vowels and valid single-code-point letters. Hungarian digraphs and
# trigraphs are represented by their constituent letters in the source files.
VOWELS = frozenset("aáeéiíoóöőuúüű")
VALID_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzáéíóöőúüű")

MAX_WORD_LEN = 10
MIN_WORD_LEN = 2

# Magyar Ispell also contains uppercase abbreviations whose lowercase spelling
# collides with a genuine Hungarian word. Preserve only the independently
# lexical lowercase readings; other normalized abbreviations are rejected.
ABBREVIATION_HOMONYMS = frozenset(
    {
        "abba",   # inflected demonstrative pronoun / verbal prefix
        "hal",    # fish; also "dies"
        "hm",     # lexical interjection, po:sentint; distinct from uppercase HM
        "hogyan", # how
        "ide",    # here
        "le",     # down
        "mi",     # we / what
        "min",    # inflected pronoun
        "rom",    # ruin
    }
)

# Magyar Ispell classifies these as nouns so they can receive Hungarian
# suffixes, but they remain written abbreviations rather than standalone words.
# Rejecting the source entries also prevents their inflected abbreviation forms
# from entering the game dictionary.
MANUAL_WRITTEN_ABBREVIATIONS = frozenset(
    {
        "szja",  # személyi jövedelemadó
        "tsz",   # termelőszövetkezet
        "uv",    # ultraibolya; conventionally written UV
    }
)

# Some source lemmas are internal stems whose unmodified surface is not a valid
# standalone Hungarian word. Keep their valid generated forms while rejecting
# only these exact surfaces. For example, ``go`` generates ``gót`` and ``gók``,
# while the standalone game name is written ``gó``.
INVALID_STANDALONE_SURFACES = frozenset({"go"})

SPECIAL_FLAG_DIRECTIVES = frozenset(
    {
        b"FORBIDDENWORD",
        b"KEEPCASE",
        b"NEEDAFFIX",
        b"ONLYINCOMPOUND",
        b"SUBSTANDARD",
    }
)

# These flags make an entire source entry unsuitable for the strict game list.
REJECT_ENTRY_FLAGS = (
    "FORBIDDENWORD",
    "ONLYINCOMPOUND",
    "KEEPCASE",
    "SUBSTANDARD",
)

# A generated form carrying one of these continuation flags is not a complete,
# standalone standard word. NEEDAFFIX marks an intermediate form that would
# require another affix application.
REJECT_CONTINUATION_FLAGS = REJECT_ENTRY_FLAGS + ("NEEDAFFIX",)

LEMMA_INDEX_SCHEMA_VERSION = 1

# Reproducible upstream inputs. The LibreOffice commit and all three checksums
# are deliberately pinned: rerunning the generator must not silently change the
# game dictionary because an upstream file changed.
LIBREOFFICE_DICTIONARIES_COMMIT = (
    "f2ff99058268502bdcf4cad25c1ca2935ad8aa7d"
)
PINNED_SOURCES = {
    "hu_HU.aff": {
        "url": (
            "https://raw.githubusercontent.com/LibreOffice/dictionaries/"
            f"{LIBREOFFICE_DICTIONARIES_COMMIT}/hu_HU/hu_HU.aff"
        ),
        "sha256": (
            "f3a2748dd535cfde2142ab17d0f7f8e4787b03fb25a60829c69ac8d493db4802"
        ),
    },
    "hu_HU.dic": {
        "url": (
            "https://raw.githubusercontent.com/LibreOffice/dictionaries/"
            f"{LIBREOFFICE_DICTIONARIES_COMMIT}/hu_HU/hu_HU.dic"
        ),
        "sha256": (
            "97293d670ad4a3b8e7eebef7e25c6e8e939b914c64b6b4672b2bf416b768f990"
        ),
    },
    "web2.2-alfa-sorted.txt.gz": {
        "url": (
            "ftp://ftp.mokk.bme.hu/Language/Hungarian/Freq/Web2.2/"
            "web2.2-alfa-sorted.txt.gz"
        ),
        "sha256": (
            "10383cd7ddd1f8e4b4c4f62126eb48a84584446498757e00464f755e75d8714f"
        ),
    },
}

# Web2.2 rows contain: token, complete, quality-40, quality-8, quality-4.
# Corpus evidence is required only for high-risk generation paths. The complete
# field is deliberately used so rare but genuinely used ordinary inflections
# are not removed merely because they are absent from the cleanest subcorpus.
WEB_CORPUS_ENCODING = "iso-8859-2"
WEB_CORPUS_USAGE_FIELD_INDEX = 1
WEB_CORPUS_USAGE_FIELD_NAME = "complete"
DEFAULT_MIN_RISKY_CORPUS_FREQUENCY = 2

# These are the root repository's reviewed Hungarian one-letter policy entries.
# They are not produced by the 2-10 character Hunspell expansion, so the
# standalone builder includes them explicitly and records them in its audit.
HUNGARIAN_REQUIRED_ONE_LETTER_WORDS = frozenset({"a", "s", "ó", "ő"})


# Magyar Ispell normally uses ``ds:`` for derivation and ``is:`` for ordinary
# inflection. These few ``is:`` tags nevertheless create a new semantic lexeme.
RISKY_INFLECTIONAL_WORD_FORMATION_TAGS = frozenset(
    {
        "is:i_PLACE/TIME_adj",
        "is:i_PLACETIME_adj",
        "is:jÚ_PROPERTY_adj",
        "is:ék_FAMILIAR_noun",
    }
)


class SuffixRule(NamedTuple):
    strip: str
    add: str
    condition_re: re.Pattern | None
    continuation_flags: bytes
    morphology: str
    cross_product: bool


class PrefixRule(NamedTuple):
    strip: str
    add: str
    condition_re: re.Pattern | None
    continuation_flags: bytes
    morphology: str
    cross_product: bool


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_pinned_source(
    source_name: str,
    cache_dir: str,
    offline: bool = False,
) -> str:
    """Return a verified cached source, downloading it atomically if needed."""
    source = PINNED_SOURCES[source_name]
    os.makedirs(cache_dir, exist_ok=True)
    destination = os.path.join(cache_dir, source_name)

    if os.path.isfile(destination):
        actual_digest = _sha256_file(destination)
        if actual_digest == source["sha256"]:
            print(f"Using verified cached source: {source_name}", flush=True)
            return destination
        print(
            f"Cached {source_name} failed checksum verification; refreshing it.",
            flush=True,
        )

    if offline:
        raise FileNotFoundError(
            f"A verified cached copy of {source_name} is required in {cache_dir} "
            "when --offline is used."
        )

    descriptor, temporary_path = tempfile.mkstemp(
        prefix=f".{source_name}.", suffix=".download", dir=cache_dir
    )
    os.close(descriptor)
    try:
        print(f"Downloading pinned source: {source_name}", flush=True)
        request = urllib.request.Request(
            source["url"],
            headers={"User-Agent": "ABCx3-Hungarian-Dictionary-Builder/1.0"},
        )
        downloaded_bytes = 0
        next_progress = 25 * 1024 * 1024
        with urllib.request.urlopen(request, timeout=60) as response, open(
            temporary_path, "wb"
        ) as destination_file:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                destination_file.write(chunk)
                downloaded_bytes += len(chunk)
                if downloaded_bytes >= next_progress:
                    print(
                        f"  {downloaded_bytes // (1024 * 1024)} MiB downloaded",
                        flush=True,
                    )
                    next_progress += 25 * 1024 * 1024

        actual_digest = _sha256_file(temporary_path)
        if actual_digest != source["sha256"]:
            raise ValueError(
                f"Checksum mismatch for {source_name}: expected "
                f"{source['sha256']}, got {actual_digest}"
            )
        os.replace(temporary_path, destination)
        return destination
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def load_risky_corpus_attestations(
    corpus_path: str,
    minimum_frequency: int = DEFAULT_MIN_RISKY_CORPUS_FREQUENCY,
) -> tuple[set[str], Counter]:
    """Load game-length tokens with credible Web2.2 usage evidence."""
    if minimum_frequency < 1:
        raise ValueError("minimum_frequency must be at least 1")

    attested_surfaces: set[str] = set()
    stats: Counter = Counter()
    # Read in binary mode so Web2.2's literal carriage-return token is not
    # interpreted as a line boundary by Python's universal-newline handling.
    with gzip.open(corpus_path, "rb") as corpus_file:
        for line_number, raw_line in enumerate(corpus_file, start=1):
            stats["corpus_rows"] += 1
            line = raw_line.removesuffix(b"\n").decode(
                WEB_CORPUS_ENCODING, errors="strict"
            )
            fields = line.split("\t")
            if len(fields) <= WEB_CORPUS_USAGE_FIELD_INDEX:
                raise ValueError(
                    f"Malformed Web2.2 row {line_number}: expected at least "
                    f"{WEB_CORPUS_USAGE_FIELD_INDEX + 1} tab-separated fields"
                )

            # Validate the token before its counts. Web2.2 intentionally has
            # rows for control characters (including an empty token with empty
            # counts); none can be game words and their numeric fields are
            # therefore irrelevant.
            surface = unicodedata.normalize("NFC", fields[0])
            if not is_valid_hu_word(surface):
                stats["corpus_rows_outside_game_alphabet_or_length"] += 1
                continue
            try:
                usage_frequency = int(fields[WEB_CORPUS_USAGE_FIELD_INDEX])
            except ValueError as error:
                raise ValueError(
                    f"Malformed Web2.2 frequency on row {line_number}"
                ) from error

            # Do not lowercase corpus tokens. Uppercase spellings must not be
            # allowed to provide accidental evidence for proper-name collisions.
            stats["corpus_eligible_hungarian_rows"] += 1
            if usage_frequency >= minimum_frequency:
                attested_surfaces.add(surface)

    stats["corpus_attested_risky_surfaces"] = len(attested_surfaces)
    return attested_surfaces, stats


def is_valid_hu_word(word: str) -> bool:
    """Return True for a game-length word made only of Hungarian letters."""
    return (
        MIN_WORD_LEN <= len(word) <= MAX_WORD_LEN
        and all(char in VALID_CHARS for char in word)
    )


def has_vowel(word: str) -> bool:
    """Return True if word contains at least one Hungarian vowel."""
    return any(char in VOWELS for char in word)


def is_written_abbreviation_shape(word: str) -> bool:
    """Keep the source-confirmed interjection hm without admitting units."""
    return len(word) == 2 and not has_vowel(word) and word != "hm"


def _parse_alias(
    token: bytes,
    aliases: dict,
    expected_count: int | None,
) -> tuple[int | None, bool]:
    """Parse an AF/AM header or alias, including aliases made only of digits."""
    if expected_count is None and not aliases and token.isdigit():
        return int(token), False
    if expected_count is None or len(aliases) < expected_count:
        return expected_count, True
    return expected_count, False


def _compile_hunspell_condition(condition: str, *, is_prefix: bool = False):
    """Compile Magyar Ispell's condition syntax without widening literal '-'."""
    if condition == ".":
        return None

    # In this dictionary, hyphens inside character classes represent a literal
    # hyphen. Python's regex engine would interpret e.g. ``[y-à]`` as a Unicode
    # range and incorrectly match ``z``. Escape class-local hyphens explicitly.
    translated = []
    in_character_class = False
    for char in condition:
        if char == "[":
            in_character_class = True
            translated.append(char)
        elif char == "]":
            in_character_class = False
            translated.append(char)
        elif char == "-" and in_character_class:
            translated.append(r"\-")
        else:
            translated.append(char)
    translated_condition = "".join(translated)
    if is_prefix:
        return re.compile("^" + translated_condition)
    return re.compile(translated_condition + "$")


def parse_aff(aff_path: str):
    """
    Parse the parts of a Magyar Ispell .aff file used by this generator.

    The file mixes UTF-8 word material with legacy single-byte affix flags, so
    it must be parsed as bytes. AF and AM aliases are counted from their declared
    headers; numeric-only aliases are data, not a second header.

    Returns:
        af_aliases: dict[int, bytes] -- dictionary flag aliases
        am_aliases: dict[int, str] -- morphological metadata aliases
        pfx_rules: dict[bytes, list] -- prefix rules and morphology metadata
        sfx_rules: dict[bytes, list] -- suffix rules and morphology metadata
        special_flags: dict[str, bytes] -- strict-filter control flags
    """
    with open(aff_path, "rb") as aff_file:
        lines = aff_file.read().splitlines()

    af_aliases: dict[int, bytes] = {}
    am_aliases: dict[int, str] = {}
    af_expected: int | None = None
    am_expected: int | None = None
    pfx_rules: defaultdict = defaultdict(list)
    sfx_rules: defaultdict = defaultdict(list)
    affix_cross_product: dict[tuple[bytes, bytes], bool] = {}
    special_flags: dict[str, bytes] = {}

    for raw_line in lines:
        line = raw_line.split(b"#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        directive = parts[0]

        if directive == b"AF" and len(parts) >= 2:
            af_expected, is_alias = _parse_alias(
                parts[1], af_aliases, af_expected
            )
            if is_alias:
                af_aliases[len(af_aliases) + 1] = parts[1]

        elif directive == b"AM" and len(parts) >= 2:
            # AM metadata can contain spaces; retain everything after "AM ".
            metadata = line.split(maxsplit=1)[1]
            am_expected, is_alias = _parse_alias(
                metadata, am_aliases, am_expected
            )
            if is_alias:
                am_aliases[len(am_aliases) + 1] = metadata.decode(
                    "utf-8", errors="replace"
                )

        elif directive in SPECIAL_FLAG_DIRECTIVES and len(parts) >= 2:
            special_flags[directive.decode("ascii")] = parts[1]

        elif (
            directive in (b"PFX", b"SFX")
            and len(parts) == 4
            and parts[2] in (b"Y", b"N")
            and parts[3].isdigit()
        ):
            affix_cross_product[(directive, parts[1])] = parts[2] == b"Y"

        elif directive in (b"PFX", b"SFX") and len(parts) >= 5:
            flag = parts[1]
            strip = parts[2].decode("utf-8", errors="replace")
            add_bytes, separator, continuation_flags = parts[3].partition(b"/")
            add = add_bytes.decode("utf-8", errors="replace")
            condition = parts[4].decode("utf-8", errors="replace")

            if strip == "0":
                strip = ""
            if add == "0":
                add = ""
            if "-" in add:
                continue

            try:
                condition_re = _compile_hunspell_condition(
                    condition,
                    is_prefix=directive == b"PFX",
                )
            except re.error:
                continue

            if separator and continuation_flags.isdigit():
                continuation_flags = af_aliases.get(
                    int(continuation_flags), b""
                )

            rule_morphology = ""
            if len(parts) >= 6:
                raw_morphology = b" ".join(parts[5:])
                if len(parts[5:]) == 1 and raw_morphology.isdigit():
                    rule_morphology = am_aliases.get(
                        int(raw_morphology), ""
                    )
                else:
                    rule_morphology = raw_morphology.decode(
                        "utf-8", errors="replace"
                    )

            rule_type = PrefixRule if directive == b"PFX" else SuffixRule
            rules = pfx_rules if directive == b"PFX" else sfx_rules
            rules[flag].append(
                rule_type(
                    strip,
                    add,
                    condition_re,
                    continuation_flags if separator else b"",
                    rule_morphology,
                    affix_cross_product.get((directive, flag), False),
                )
            )

    if af_expected is not None and len(af_aliases) != af_expected:
        raise ValueError(
            f"Expected {af_expected} AF aliases, parsed {len(af_aliases)}"
        )
    if am_expected is not None and len(am_aliases) != am_expected:
        raise ValueError(
            f"Expected {am_expected} AM aliases, parsed {len(am_aliases)}"
        )

    return af_aliases, am_aliases, pfx_rules, sfx_rules, special_flags


def parse_dictionary_line(
    line: str,
    af_aliases: dict[int, bytes],
    am_aliases: dict[int, str],
) -> tuple[str, bytes, str] | None:
    """Parse one .dic row into surface word, raw flags, and morphology."""
    line = line.strip()
    if not line:
        return None

    columns = line.split("\t")
    entry = columns[0]
    morphology_ref = columns[1] if len(columns) >= 2 else ""

    if "/" in entry:
        word, flags_ref = entry.split("/", 1)
        word = word.replace("\\/", "/")
        try:
            flags = af_aliases.get(int(flags_ref), b"")
        except ValueError:
            flags = flags_ref.encode("utf-8", errors="replace")
    else:
        word = entry
        flags = b""

    try:
        morphology = am_aliases.get(int(morphology_ref), "")
    except ValueError:
        morphology = morphology_ref

    return word, flags, morphology


def _has_flag(flags: bytes, special_flags: dict[str, bytes], name: str) -> bool:
    flag = special_flags.get(name)
    return bool(flag and flag in flags)


def _is_abbreviation_metadata(morphology: str) -> bool:
    return "po:abr" in morphology.split()


def _source_lemma(word: str, morphology: str) -> str:
    """Prefer Magyar Ispell's explicit stem metadata over intermediate forms."""
    for token in morphology.split():
        if token.startswith("st:") and len(token) > 3:
            candidate = unicodedata.normalize("NFC", token[3:]).lower()
            if is_valid_hu_word(candidate):
                return candidate
    return word


def _is_word_formation_morphology(morphology: str) -> bool:
    """Identify derivation or semantic word formation."""
    for token in morphology.split():
        if token.startswith("ds:"):
            return True
        if token in RISKY_INFLECTIONAL_WORD_FORMATION_TAGS:
            return True
    return False


def _is_high_risk_ordinary_inflection(morphology: str) -> bool:
    """Identify the narrow stacked possessives implicated by player reports."""
    inflections = {
        token
        for token in morphology.split()
        if token.startswith("is:") and token != "is:NOM"
    }
    has_possessive = any(
        token.startswith("is:POSS_") for token in inflections
    )
    if has_possessive and "is:POSSESSEE" in inflections:
        return True

    # ``büróira`` follows PLUR + POSS_SG_3 + SBL. Treat that specific
    # three-stage sublative family as risky; other case stacks, simple plurals,
    # possessives, and ordinary two-stage forms remain unchanged.
    return (
        has_possessive
        and "is:PLUR" in inflections
        and "is:SBL" in inflections
    )


def _is_risky_generation_morphology(morphology: str) -> bool:
    return _is_word_formation_morphology(
        morphology
    ) or _is_high_risk_ordinary_inflection(morphology)


def _collect_source_filters(
    dic_lines: list[str],
    af_aliases: dict[int, bytes],
    am_aliases: dict[int, str],
    pfx_rules: dict[bytes, list],
    sfx_rules: dict[bytes, list],
    special_flags: dict[str, bytes],
) -> tuple[set[str], set[str], set[str]]:
    """Collect abbreviations, blocked forms, and proper-name derivatives."""
    abbreviations: set[str] = set()
    blocked_surfaces: set[str] = set()
    proper_derived_surfaces: set[str] = set()
    lowercase_source_surfaces: set[str] = set()

    for line in dic_lines:
        parsed = parse_dictionary_line(line, af_aliases, am_aliases)
        if parsed is None:
            continue
        word, flags, morphology = parsed
        normalized = word.lower()
        if not is_valid_hu_word(normalized):
            continue
        if word == normalized:
            lowercase_source_surfaces.add(normalized)

        # Magyar Ispell can contain a lowercase adjective derived from a
        # capitalized proper noun as a separate source entry (James -> jamesi).
        # Record it so descendants cannot evade the proper-name policy.
        if word != normalized and "po:noun_prs" in morphology.split():
            for flag_byte in flags:
                flag = bytes([flag_byte])
                for rule in pfx_rules.get(flag, ()):
                    generated = _apply_prefix_rule(word, rule)
                    if (
                        generated
                        and generated == generated.lower()
                        and is_valid_hu_word(generated)
                    ):
                        proper_derived_surfaces.add(generated)
                for rule in sfx_rules.get(flag, ()):
                    if not _is_word_formation_morphology(rule.morphology):
                        continue
                    generated = _apply_suffix_rule(normalized, rule)
                    if generated and is_valid_hu_word(generated):
                        proper_derived_surfaces.add(generated)

        if _is_abbreviation_metadata(morphology):
            abbreviations.add(normalized)
        rejected_entry = any(
            _has_flag(flags, special_flags, name)
            for name in REJECT_ENTRY_FLAGS
        )
        if rejected_entry:
            blocked_surfaces.add(normalized)
            # Hunspell propagates a source entry's forbidden/substandard/etc.
            # status to its inflected descendants. Expand those descendants
            # into the block set so an equivalent path from another stem cannot
            # re-introduce a prohibited surface form.
            for flag_byte in flags:
                flag = bytes([flag_byte])
                for rule in pfx_rules.get(flag, ()):
                    generated = _apply_prefix_rule(normalized, rule)
                    if generated and is_valid_hu_word(generated):
                        blocked_surfaces.add(generated)
                for rule in sfx_rules.get(flag, ()):
                    generated = _apply_suffix_rule(normalized, rule)
                    if generated and is_valid_hu_word(generated):
                        blocked_surfaces.add(generated)

    abbreviations.update(MANUAL_WRITTEN_ABBREVIATIONS)
    abbreviations.difference_update(ABBREVIATION_HOMONYMS)
    blocked_surfaces.update(abbreviations)
    blocked_surfaces.update(INVALID_STANDALONE_SURFACES)
    proper_derived_surfaces.intersection_update(lowercase_source_surfaces)
    return abbreviations, blocked_surfaces, proper_derived_surfaces


def _continuation_rejection_reason(
    continuation_flags: bytes,
    special_flags: dict[str, bytes],
) -> str | None:
    for name in REJECT_CONTINUATION_FLAGS:
        if _has_flag(continuation_flags, special_flags, name):
            return name.lower()
    return None


def _apply_suffix_rule(word: str, rule) -> str | None:
    if rule.condition_re and not rule.condition_re.search(word):
        return None
    if rule.strip:
        if not word.endswith(rule.strip):
            return None
        stem = word[: -len(rule.strip)]
    else:
        stem = word
    return stem + rule.add


def _apply_prefix_rule(word: str, rule) -> str | None:
    if rule.condition_re and not rule.condition_re.search(word):
        return None
    if rule.strip:
        if not word.startswith(rule.strip):
            return None
        stem = word[len(rule.strip) :]
    else:
        stem = word
    return rule.add + stem


def _build_attested_prefix_index(
    attested_surfaces: set[str],
    pfx_rules: dict[bytes, list],
) -> dict[tuple[bytes, str], list[tuple[str, PrefixRule]]]:
    """Reverse corpus-attested prefixed forms to their unprefixed inputs.

    Enumerating every PFX x SFX cross-product from Magyar Ispell would require
    more than a billion rule-pair checks. The production build already requires
    corpus evidence for every prefix-derived surface, so invert the small set of
    attested game words instead. Each corpus token requires at most ten prefix
    lookups, while Hunspell strip and condition semantics are still verified by
    applying the rule forward before indexing it.
    """
    rules_by_add: defaultdict[str, list[tuple[bytes, PrefixRule]]] = defaultdict(
        list
    )
    empty_add_rules: list[tuple[bytes, PrefixRule]] = []
    for flag, rules in pfx_rules.items():
        for rule in rules:
            if rule.add:
                rules_by_add[rule.add].append((flag, rule))
            else:
                empty_add_rules.append((flag, rule))

    index: defaultdict[tuple[bytes, str], list[tuple[str, PrefixRule]]] = (
        defaultdict(list)
    )
    for surface in attested_surfaces:
        matching_rules = list(empty_add_rules)
        for prefix_length in range(1, len(surface) + 1):
            matching_rules.extend(rules_by_add.get(surface[:prefix_length], ()))
        for flag, rule in matching_rules:
            remainder = surface[len(rule.add) :]
            unprefixed = rule.strip + remainder
            if not is_valid_hu_word(unprefixed):
                continue
            if _apply_prefix_rule(unprefixed, rule) != surface:
                continue
            index[(flag, unprefixed)].append((surface, rule))
    return dict(index)


def _surface_is_final(
    word: str,
    blocked_surfaces: set[str],
    rejected_generated_surfaces: set[str] | None = None,
) -> bool:
    """Apply filters that operate on a fully generated surface form."""
    if word in blocked_surfaces or is_written_abbreviation_shape(word):
        return False
    return not (
        rejected_generated_surfaces is not None
        and word in rejected_generated_surfaces
    )


def _lemma_shard_key(surface: str) -> str:
    """Encode the first two Unicode letters as a URL-safe UTF-8 hex key."""
    return "".join(list(surface)[:2]).encode("utf-8").hex()


def _write_lemma_index(
    sorted_mapping_path: str,
    lemma_index_dir: str,
    blocked_surfaces: set[str],
    rejected_generated_surfaces: set[str] | None = None,
) -> dict:
    """
    Write deterministic compressed surface-to-lemma shards.

    The mapping input is already sorted by surface and lemma. Grouping therefore
    preserves ambiguity without retaining the multi-million-form index in RAM.
    Two-letter prefix sharding also keeps each backend lookup download small.
    """
    parent_dir = os.path.dirname(lemma_index_dir) or "."
    os.makedirs(parent_dir, exist_ok=True)
    temporary_dir = tempfile.mkdtemp(
        prefix=f".{os.path.basename(lemma_index_dir)}.",
        dir=parent_dir,
    )
    shard_counts: Counter = Counter()
    shard_digests: dict[str, str] = {}
    surface_count = 0
    mapping_count = 0
    current_surface: str | None = None
    current_lemmas: list[str] = []
    current_shard_key: str | None = None
    current_raw_file = None
    current_gzip_file = None

    def close_shard() -> None:
        nonlocal current_raw_file, current_gzip_file, current_shard_key
        if current_gzip_file is None or current_raw_file is None:
            return
        current_gzip_file.close()
        current_raw_file.close()
        shard_path = os.path.join(
            temporary_dir, f"{current_shard_key}.tsv.gz"
        )
        with open(shard_path, "rb") as shard_file:
            shard_digests[current_shard_key] = hashlib.sha256(
                shard_file.read()
            ).hexdigest()
        current_gzip_file = None
        current_raw_file = None
        current_shard_key = None

    def write_group(surface: str, lemmas: list[str]) -> None:
        nonlocal current_shard_key, current_raw_file, current_gzip_file
        nonlocal surface_count, mapping_count
        if not _surface_is_final(
            surface,
            blocked_surfaces,
            rejected_generated_surfaces=rejected_generated_surfaces,
        ):
            return
        unique_lemmas = sorted(set(lemmas))
        if not unique_lemmas:
            return
        shard_key = _lemma_shard_key(surface)
        if shard_key != current_shard_key:
            close_shard()
            shard_path = os.path.join(temporary_dir, f"{shard_key}.tsv.gz")
            current_raw_file = open(shard_path, "wb")
            current_gzip_file = gzip.GzipFile(
                filename="",
                mode="wb",
                fileobj=current_raw_file,
                mtime=0,
            )
            current_shard_key = shard_key
        encoded = (
            f"{surface}\t{','.join(unique_lemmas)}\n"
        ).encode("utf-8")
        current_gzip_file.write(encoded)
        shard_counts[shard_key] += 1
        surface_count += 1
        mapping_count += len(unique_lemmas)

    try:
        with open(
            sorted_mapping_path, "r", encoding="utf-8"
        ) as mapping_file:
            for line in mapping_file:
                surface, separator, lemma = line.rstrip("\n").partition("\t")
                if not separator:
                    continue
                if current_surface is None:
                    current_surface = surface
                if surface != current_surface:
                    write_group(current_surface, current_lemmas)
                    current_surface = surface
                    current_lemmas = []
                current_lemmas.append(lemma)
        if current_surface is not None:
            write_group(current_surface, current_lemmas)
        close_shard()

        manifest = {
            "schema_version": LEMMA_INDEX_SCHEMA_VERSION,
            "language_code": "hu",
            "format": "gzip TSV: surface<TAB>comma-separated lemmas",
            "sharding": "UTF-8 hex of first two Unicode letters",
            "surface_count": surface_count,
            "mapping_count": mapping_count,
            "shards": {
                shard_key: {
                    "surface_count": shard_counts[shard_key],
                    "sha256": shard_digests[shard_key],
                }
                for shard_key in sorted(shard_counts)
            },
        }
        with open(
            os.path.join(temporary_dir, "manifest.json"),
            "w",
            encoding="utf-8",
        ) as manifest_file:
            json.dump(
                manifest, manifest_file, ensure_ascii=False, indent=2
            )
            manifest_file.write("\n")

        if os.path.isdir(lemma_index_dir):
            shutil.rmtree(lemma_index_dir)
        os.replace(temporary_dir, lemma_index_dir)
        return manifest
    finally:
        close_shard()
        if os.path.isdir(temporary_dir):
            shutil.rmtree(temporary_dir)


def expand_dictionary(
    aff_path: str,
    dic_path: str,
    output_path: str,
    audit_path: str | None = None,
    lemma_index_dir: str | None = None,
    corpus_path: str | None = None,
    minimum_risky_corpus_frequency: int = (
        DEFAULT_MIN_RISKY_CORPUS_FREQUENCY
    ),
    required_one_letter_words: frozenset[str] = frozenset(),
) -> int:
    """Expand, strictly filter, sort, and write the Hungarian game word list."""
    print("Parsing .aff file...", flush=True)
    (
        af_aliases,
        am_aliases,
        pfx_rules,
        sfx_rules,
        special_flags,
    ) = parse_aff(aff_path)
    print(
        f"  {len(af_aliases)} AF aliases, {len(am_aliases)} AM aliases, "
        f"{len(pfx_rules)} PFX and {len(sfx_rules)} SFX flag groups",
        flush=True,
    )

    print("Parsing .dic file...", flush=True)
    with open(dic_path, "r", encoding="utf-8", errors="replace") as dic_file:
        dic_lines = dic_file.readlines()[1:]
    print(f"  {len(dic_lines)} entries in .dic", flush=True)

    abbreviations, blocked_surfaces, proper_derived_surfaces = _collect_source_filters(
        dic_lines,
        af_aliases,
        am_aliases,
        pfx_rules,
        sfx_rules,
        special_flags,
    )
    print(
        f"  {len(abbreviations)} written abbreviations and "
        f"{len(blocked_surfaces)} blocked source surfaces; "
        f"{len(proper_derived_surfaces)} lowercase proper-name derivatives",
        flush=True,
    )

    corpus_attested_risky_surfaces: set[str] | None = None
    attested_prefix_index: dict[
        tuple[bytes, str], list[tuple[str, PrefixRule]]
    ] | None = None
    corpus_stats: Counter = Counter()
    if corpus_path is not None:
        print(
            "Loading Hungarian Webcorpus evidence for risky generated forms "
            f"({WEB_CORPUS_USAGE_FIELD_NAME} frequency >= "
            f"{minimum_risky_corpus_frequency})...",
            flush=True,
        )
        (
            corpus_attested_risky_surfaces,
            corpus_stats,
        ) = load_risky_corpus_attestations(
            corpus_path,
            minimum_frequency=minimum_risky_corpus_frequency,
        )
        print(
            f"  {len(corpus_attested_risky_surfaces)} eligible attested surfaces",
            flush=True,
        )
        print("Indexing attested Hunspell prefix paths...", flush=True)
        attested_prefix_index = _build_attested_prefix_index(
            corpus_attested_risky_surfaces,
            pfx_rules,
        )
        print(
            f"  {len(attested_prefix_index)} prefix/input combinations",
            flush=True,
        )

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    output_dir = os.path.dirname(output_path) or "."
    output_name = os.path.basename(output_path)
    temporary_paths = []
    for stage in (
        "raw",
        "sorted",
        "final",
        "raw-mappings",
        "sorted-mappings",
        "raw-safe-paths",
        "sorted-safe-paths",
    ):
        descriptor, temporary_path = tempfile.mkstemp(
            prefix=f".{output_name}.{stage}.", suffix=".tmp", dir=output_dir
        )
        os.close(descriptor)
        temporary_paths.append(temporary_path)
    (
        raw_path,
        sorted_path,
        final_path,
        raw_mapping_path,
        sorted_mapping_path,
        raw_safe_path,
        sorted_safe_path,
    ) = temporary_paths
    stats: Counter = Counter()
    stats.update(corpus_stats)
    if attested_prefix_index is not None:
        stats["attested_prefix_index_inputs"] = len(attested_prefix_index)
        stats["attested_prefix_index_paths"] = sum(
            len(paths) for paths in attested_prefix_index.values()
        )
    approved_source_lemmas: set[str] = set()

    try:
        print("Expanding standard standalone forms...", flush=True)
        with open(
            raw_path, "w", encoding="utf-8"
        ) as output_file, open(
            raw_mapping_path, "w", encoding="utf-8"
        ) as mapping_file, open(
            raw_safe_path, "w", encoding="utf-8"
        ) as safe_path_file:
            def write_generated_path(
                surface: str,
                source_lemma: str,
                *,
                risky: bool,
                path_counter: str,
            ) -> None:
                output_file.write(surface + "\n")
                mapping_file.write(f"{surface}\t{source_lemma}\n")
                stats["raw_generated_forms"] += 1
                stats[path_counter] += 1
                if risky:
                    stats["raw_risky_generation_paths"] += 1
                else:
                    safe_path_file.write(surface + "\n")
                    stats["raw_ordinary_inflection_paths"] += 1

            def iter_prefix_candidates(
                unprefixed: str,
                flag: bytes,
                *,
                cross_product_only: bool,
            ):
                if attested_prefix_index is not None:
                    for surface, rule in attested_prefix_index.get(
                        (flag, unprefixed), ()
                    ):
                        if cross_product_only and not rule.cross_product:
                            continue
                        yield surface, rule
                    return
                for rule in pfx_rules.get(flag, ()):
                    if cross_product_only and not rule.cross_product:
                        continue
                    surface = _apply_prefix_rule(unprefixed, rule)
                    if surface is not None and is_valid_hu_word(surface):
                        yield surface, rule

            for word in required_one_letter_words:
                if len(word) != 1 or word not in VALID_CHARS:
                    raise ValueError(
                        f"Invalid required one-letter Hungarian word: {word!r}"
                    )
                output_file.write(word + "\n")
                safe_path_file.write(word + "\n")
            stats["kept_required_one_letter_words"] = len(
                required_one_letter_words
            )

            for index, line in enumerate(dic_lines):
                stats["source_entries"] += 1
                parsed = parse_dictionary_line(line, af_aliases, am_aliases)
                if parsed is None:
                    stats["skipped_empty_entries"] += 1
                    continue
                word, flags, morphology = parsed

                if " " in word or word.startswith("-"):
                    stats["skipped_non_word_entries"] += 1
                    continue
                if word != word.lower():
                    stats["skipped_case_sensitive_entries"] += 1
                    continue

                word_lower = word.lower()
                source_lemma = _source_lemma(word_lower, morphology)
                if not is_valid_hu_word(word_lower):
                    stats["skipped_invalid_char_or_length"] += 1
                    continue

                rejected = False
                for flag_name in REJECT_ENTRY_FLAGS:
                    if _has_flag(flags, special_flags, flag_name):
                        stats[f"skipped_{flag_name.lower()}_entries"] += 1
                        rejected = True
                        break
                if rejected:
                    continue

                if word_lower in abbreviations:
                    stats["skipped_abbreviation_entries"] += 1
                    continue

                if is_valid_hu_word(source_lemma):
                    approved_source_lemmas.add(source_lemma)

                has_needaffix = _has_flag(
                    flags, special_flags, "NEEDAFFIX"
                )
                if has_needaffix:
                    stats["skipped_needaffix_bases"] += 1
                else:
                    output_file.write(word_lower + "\n")
                    safe_path_file.write(word_lower + "\n")
                    mapping_file.write(
                        f"{word_lower}\t{source_lemma}\n"
                    )
                    stats["raw_base_forms"] += 1

                cross_product_suffix_forms: set[str] = set()
                for flag_byte in flags:
                    flag = bytes([flag_byte])
                    for rule in sfx_rules.get(flag, ()):
                        reason = _continuation_rejection_reason(
                            rule.continuation_flags, special_flags
                        )
                        if reason:
                            stats[f"rejected_{reason}_generated_forms"] += 1
                            continue
                        new_word = _apply_suffix_rule(
                            word_lower,
                            rule,
                        )
                        if new_word is None:
                            continue
                        if is_valid_hu_word(new_word):
                            risky_path = (
                                word_lower in proper_derived_surfaces
                                or _is_risky_generation_morphology(
                                    rule.morphology
                                )
                            )
                            write_generated_path(
                                new_word,
                                source_lemma,
                                risky=risky_path,
                                path_counter="raw_suffix_generation_paths",
                            )
                            if rule.cross_product:
                                cross_product_suffix_forms.add(new_word)

                prefix_flags = [
                    bytes([flag_byte])
                    for flag_byte in flags
                    if bytes([flag_byte]) in pfx_rules
                ]
                for prefix_flag in prefix_flags:
                    for new_word, prefix_rule in iter_prefix_candidates(
                        word_lower,
                        prefix_flag,
                        cross_product_only=False,
                    ):
                        reason = _continuation_rejection_reason(
                            prefix_rule.continuation_flags,
                            special_flags,
                        )
                        if reason:
                            stats[f"rejected_{reason}_generated_forms"] += 1
                            continue
                        write_generated_path(
                            new_word,
                            source_lemma,
                            risky=True,
                            path_counter="raw_prefix_generation_paths",
                        )

                    for suffix_form in cross_product_suffix_forms:
                        for new_word, prefix_rule in iter_prefix_candidates(
                            suffix_form,
                            prefix_flag,
                            cross_product_only=True,
                        ):
                            reason = _continuation_rejection_reason(
                                prefix_rule.continuation_flags,
                                special_flags,
                            )
                            if reason:
                                stats[
                                    f"rejected_{reason}_generated_forms"
                                ] += 1
                                continue
                            write_generated_path(
                                new_word,
                                source_lemma,
                                risky=True,
                                path_counter=(
                                    "raw_prefix_suffix_generation_paths"
                                ),
                            )

                if (index + 1) % 20_000 == 0:
                    raw_count = stats["raw_base_forms"] + stats["raw_generated_forms"]
                    print(
                        f"  {index + 1}/{len(dic_lines)} entries processed, "
                        f"{raw_count} candidate forms written",
                        flush=True,
                    )

        raw_count = stats["raw_base_forms"] + stats["raw_generated_forms"]
        stats["approved_source_lemmas"] = len(approved_source_lemmas)
        print(f"\nRaw candidate forms: {raw_count}", flush=True)
        print("Sorting, deduplicating, and applying final filters...", flush=True)

        sort_environment = os.environ.copy()
        sort_environment["LC_ALL"] = "C"
        subprocess.run(
            ["sort", "-u", "-o", sorted_path, raw_path],
            check=True,
            env=sort_environment,
        )
        subprocess.run(
            ["sort", "-u", "-o", sorted_safe_path, raw_safe_path],
            check=True,
            env=sort_environment,
        )
        subprocess.run(
            [
                "sort",
                "-u",
                "-t",
                "\t",
                "-k1,1",
                "-k2,2",
                "-o",
                sorted_mapping_path,
                raw_mapping_path,
            ],
            check=True,
            env=sort_environment,
        )

        digest = hashlib.sha256()
        final_count = 0
        rejected_risky_surfaces: set[str] = set()
        with open(sorted_path, "r", encoding="utf-8") as sorted_file, open(
            final_path, "w", encoding="utf-8"
        ) as output_file, open(
            sorted_safe_path, "r", encoding="utf-8"
        ) as safe_file:
            safe_word = safe_file.readline().rstrip("\n")
            for line in sorted_file:
                stats["unique_candidates_before_final_filters"] += 1
                word = line.rstrip("\n")
                if word in blocked_surfaces:
                    stats["rejected_blocked_source_surfaces"] += 1
                    continue
                if is_written_abbreviation_shape(word):
                    stats["rejected_two_letter_abbreviations"] += 1
                    continue
                while safe_word and safe_word < word:
                    safe_word = safe_file.readline().rstrip("\n")
                has_safe_path = safe_word == word
                if corpus_attested_risky_surfaces is not None:
                    if has_safe_path:
                        stats["kept_direct_or_ordinary_surfaces"] += 1
                    elif word in corpus_attested_risky_surfaces:
                        stats["kept_corpus_attested_risky_forms"] += 1
                    else:
                        stats["rejected_unattested_risky_generated_forms"] += 1
                        rejected_risky_surfaces.add(word)
                        continue
                encoded_line = (word + "\n").encode("utf-8")
                output_file.write(word + "\n")
                digest.update(encoded_line)
                final_count += 1

        os.replace(final_path, output_path)
        stats["final_unique_words"] = final_count

        lemma_index_manifest = None
        if lemma_index_dir:
            print("Writing sharded surface-to-lemma index...", flush=True)
            lemma_index_manifest = _write_lemma_index(
                sorted_mapping_path,
                lemma_index_dir,
                blocked_surfaces,
                rejected_generated_surfaces=(
                    rejected_risky_surfaces
                    if corpus_attested_risky_surfaces is not None
                    else None
                ),
            )
            stats["lemma_index_surfaces"] = lemma_index_manifest[
                "surface_count"
            ]
            stats["lemma_index_mappings"] = lemma_index_manifest[
                "mapping_count"
            ]
            stats["lemma_index_shards"] = len(
                lemma_index_manifest["shards"]
            )

        if audit_path:
            os.makedirs(os.path.dirname(audit_path) or ".", exist_ok=True)
            audit = {
                "schema_version": 7,
                "source": {
                    "aff": os.path.basename(aff_path),
                    "aff_sha256": _sha256_file(aff_path),
                    "dic": os.path.basename(dic_path),
                    "dic_sha256": _sha256_file(dic_path),
                },
                "policy": {
                    "minimum_length": MIN_WORD_LEN,
                    "maximum_length": MAX_WORD_LEN,
                    "lowercase_only": True,
                    "proper_nouns_removed": True,
                    "case_sensitive_entries_removed": True,
                    "hungarian_letters_only": True,
                    "rejected_source_flags": list(REJECT_ENTRY_FLAGS),
                    "rejected_generated_flags": list(
                        REJECT_CONTINUATION_FLAGS
                    ),
                    "written_abbreviations_from_source_metadata": True,
                    "manual_written_abbreviations": sorted(
                        MANUAL_WRITTEN_ABBREVIATIONS
                    ),
                    "invalid_standalone_surfaces": sorted(
                        INVALID_STANDALONE_SURFACES
                    ),
                    "abbreviation_homonyms_preserved": sorted(
                        ABBREVIATION_HOMONYMS
                    ),
                    "automatic_risky_generation_filter": (
                        corpus_path is not None
                    ),
                    "ordinary_inflections_preserved_without_surface_attestation": True,
                    "direct_source_forms_preserved_without_surface_attestation": True,
                    "proper_name_derivative_descendants_are_risky": True,
                    "word_formation_metadata_is_risky": True,
                    "hunspell_prefix_rules_supported": True,
                    "hunspell_prefix_suffix_cross_products_supported": True,
                    "prefix_derived_paths_are_risky": True,
                    "prefix_derived_paths_require_surface_attestation": (
                        corpus_path is not None
                    ),
                    "possessive_plus_possessee_stacks_are_risky": True,
                    "plural_possessive_sublative_stacks_are_risky": True,
                    "required_one_letter_words": sorted(
                        required_one_letter_words
                    ),
                },
                "counts": dict(sorted(stats.items())),
                "output_sha256": digest.hexdigest(),
            }
            if corpus_path is not None:
                audit["source"]["corpus"] = os.path.basename(corpus_path)
                audit["source"]["corpus_sha256"] = _sha256_file(corpus_path)
                audit["policy"]["corpus_frequency_field"] = (
                    WEB_CORPUS_USAGE_FIELD_NAME
                )
                audit["policy"]["minimum_risky_corpus_frequency"] = (
                    minimum_risky_corpus_frequency
                )
            if lemma_index_manifest is not None:
                audit["lemma_index"] = {
                    "schema_version": lemma_index_manifest[
                        "schema_version"
                    ],
                    "relative_path": os.path.relpath(
                        lemma_index_dir,
                        os.path.dirname(output_path) or ".",
                    ),
                    "surface_count": lemma_index_manifest[
                        "surface_count"
                    ],
                    "mapping_count": lemma_index_manifest[
                        "mapping_count"
                    ],
                    "shard_count": len(
                        lemma_index_manifest["shards"]
                    ),
                }
            with open(audit_path, "w", encoding="utf-8") as audit_file:
                json.dump(audit, audit_file, ensure_ascii=False, indent=2)
                audit_file.write("\n")

        print(f"Final unique words: {final_count}", flush=True)
        return final_count
    finally:
        for temporary_path in temporary_paths:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build the strict ABCx3 Hungarian dictionary from pinned, "
            "checksum-verified sources."
        )
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use only already downloaded and checksum-verified source files.",
    )
    parser.add_argument(
        "--cache-dir",
        help="Source cache directory (default: .cache/sources).",
    )
    parser.add_argument(
        "--minimum-risky-corpus-frequency",
        type=int,
        default=DEFAULT_MIN_RISKY_CORPUS_FREQUENCY,
        help=(
            "Minimum complete-Web2.2 frequency for a risky generated surface "
            f"(default: {DEFAULT_MIN_RISKY_CORPUS_FREQUENCY})."
        ),
    )
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    cache_dir = args.cache_dir or os.path.join(
        script_dir, ".cache", "sources"
    )
    try:
        aff_path = _ensure_pinned_source(
            "hu_HU.aff", cache_dir, offline=args.offline
        )
        dic_path = _ensure_pinned_source(
            "hu_HU.dic", cache_dir, offline=args.offline
        )
        corpus_path = _ensure_pinned_source(
            "web2.2-alfa-sorted.txt.gz", cache_dir, offline=args.offline
        )
    except (FileNotFoundError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    output_dir = os.path.join(script_dir, "output")
    output_path = os.path.join(output_dir, "hungarian_hu_hu_ispell.txt")
    audit_path = os.path.join(output_dir, "audit.json")
    lemma_index_dir = os.path.join(
        output_dir, "definitions", "hu", "surface-lemma", "v1"
    )

    count = expand_dictionary(
        aff_path,
        dic_path,
        output_path,
        audit_path=audit_path,
        lemma_index_dir=lemma_index_dir,
        corpus_path=corpus_path,
        minimum_risky_corpus_frequency=(
            args.minimum_risky_corpus_frequency
        ),
        required_one_letter_words=HUNGARIAN_REQUIRED_ONE_LETTER_WORDS,
    )
    print(f"\nDone. Wrote {count} words to {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
