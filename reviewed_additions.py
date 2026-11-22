"""Source-derived evidence for explicitly reviewed surface additions.

The review selects candidates; Magyar Ispell supplies morphology and Webcorpus
supplies frequency evidence. This file does not treat a review as a licence.
"""
import json
import re
from pathlib import Path

import process_words
from process_words import PINNED_SOURCES, is_valid_hu_word, _is_word_formation_morphology

DEFAULT_REVIEWED_ADDITIONS = Path(__file__).resolve().parent / "reviewed_additions.json"
DEFAULT_GAMEPLAY_OVERRIDES = Path(__file__).resolve().parent / "gameplay_overrides.json"

# Reviewed surfaces may be as long as the longest graph source (12 letters since
# 17 November 2026). Each build keeps only those within its own length cap, so
# the 10-letter lists leave the longer ones to build_long_graph_sources.py.
LONGEST_REVIEWED_SURFACE = 12


def is_reviewed_surface(word: str) -> bool:
    """A Hungarian-letter surface no longer than the longest graph source."""
    return (process_words.MIN_WORD_LEN <= len(word) <= LONGEST_REVIEWED_SURFACE
            and all(char in process_words.VALID_CHARS for char in word))


def within_build_cap(words) -> frozenset[str]:
    """Drop valid reviewed surfaces longer than this build's cap; refuse invalid ones."""
    longer = {word for word in words if len(word) > process_words.MAX_WORD_LEN}
    invalid = sorted(word for word in longer if not is_reviewed_surface(word))
    if invalid:
        raise ValueError("Reviewed surfaces too long for any build: " + ", ".join(invalid))
    return frozenset(words) - longer


def load_gameplay_overrides(path: Path = DEFAULT_GAMEPLAY_OVERRIDES) -> dict:
    """Portable curated corrections; never publish private operator records."""
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schemaVersion") != 1:
        raise ValueError("Unsupported gameplay-override schema")
    result = {}
    for field in ("additions", "surfaceRemovals", "lemmaRemovals"):
        values = document[field]
        if values != sorted(set(values)) or not all(is_reviewed_surface(w) for w in values):
            raise ValueError(f"Invalid public gameplay overrides: {field}")
        result[field] = within_build_cap(values)
    if result["additions"] & (result["surfaceRemovals"] | result["lemmaRemovals"]):
        raise ValueError("Conflicting public gameplay overrides")
    return result


def lexical_analyses(surface: str, lines: list[str]) -> list[str]:
    """Require a lexical reading, permitting reviewed proper-name derivatives."""
    accepted = []
    for line in lines:
        if not line.startswith(surface + " ") or "st:" not in line:
            continue
        if "po:abr" in line.split():
            continue
        if "po:noun_prs" in line.split() and not _is_word_formation_morphology(line):
            continue
        accepted.append(line)
    return sorted(set(accepted))


def definition_lemmas(surface: str, analyses: list[str]) -> list[str]:
    """Preserve headword/derived readings, and unambiguous inflected stems.

    Never map a compound to its last component or a derived adjective to a
    capitalized name. Verbal prefixes belong on the lookup lemma.
    """
    lemmas = set()
    for line in analyses:
        if "pa:" in line or _is_word_formation_morphology(line):
            lemmas.add(surface)
            continue
        stems = re.findall(r"\bst:([^\s]+)", line)
        prefixes = re.findall(r"\bsp:([^\s]+)", line)
        if len(stems) == 1 and len(prefixes) <= 1:
            lemma = "".join(prefixes) + stems[0]
            if lemma == lemma.lower() and is_valid_hu_word(lemma):
                lemmas.add(lemma)
    return sorted(lemmas or {surface})


def load_reviewed_additions(path: Path = DEFAULT_REVIEWED_ADDITIONS) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schemaVersion") != 1:
        raise ValueError("Unsupported reviewed-addition schema")
    expected = {name: source["sha256"] for name, source in PINNED_SOURCES.items()}
    if document.get("sourceChecksumsSha256") != expected:
        raise ValueError("Reviewed additions must be reverified after source changes")
    entries = {}
    for entry in document["entries"]:
        word = entry["word"]
        if word in entries or not is_valid_hu_word(word):
            raise ValueError(f"Invalid/duplicate reviewed surface: {word}")
        analyses = lexical_analyses(word, entry["magyarIspellAnalyses"])
        if not analyses or entry["quality4Frequency"] < 2:
            raise ValueError(f"Missing lexical evidence for {word}")
        if entry["lemmas"] != definition_lemmas(word, analyses):
            raise ValueError(f"Unverified definition mapping for {word}")
        entries[word] = entry
    return entries
