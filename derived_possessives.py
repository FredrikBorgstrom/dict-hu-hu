"""Corroborate possessives of independently accepted nominal derived words.

The source must license the exact inflection from an accepted noun/adjective.
The independent analyzer must give that anchor and its possessive the SAME
lexical analysis, differing only by an ordinary possessive and optional case.
"""

from __future__ import annotations

import concurrent.futures
import gzip
import hashlib
import json
import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path

from process_words import (
    REJECT_ENTRY_FLAGS, _apply_suffix_rule, _collect_source_filters,
    _continuation_rejection_reason, _has_flag, _is_risky_generation_morphology,
    _source_lemma, is_valid_hu_word,
    parse_aff, parse_dictionary_line,
)

# Each path records the independently accepted anchor and original source lemma.
SourcePath = tuple[str, str]
Signature = tuple[str, str]


def ordinary_possessive_rule(rule, special: dict) -> bool:
    tags = rule.morphology.split()
    return (sum(t.startswith("is:POSS_") for t in tags) == 1
            and "is:PLUR" not in tags and "is:POSSESSEE" not in tags
            and not _is_risky_generation_morphology(rule.morphology)
            and not _continuation_rejection_reason(rule.continuation_flags, special))


def licensed_anchored_possessives(
    accepted: frozenset[str], candidates: frozenset[str],
    aff_path: Path, dic_path: Path,
    surface_additions: frozenset[str] = frozenset(),
    lemma_removals: frozenset[str] = frozenset(),
) -> dict[str, frozenset[SourcePath]]:
    af, am, prefixes, suffixes, special = parse_aff(str(aff_path))
    lines = dic_path.read_text(encoding="utf-8").splitlines()[1:]
    abbreviations, blocked, proper_derived = _collect_source_filters(
        lines, af, am, prefixes, suffixes, special)
    anchors = accepted - surface_additions - blocked - proper_derived - lemma_removals
    excluded_sources = abbreviations | blocked | proper_derived
    excluded_lemmas = lemma_removals | blocked | proper_derived
    paths: dict[str, set[SourcePath]] = defaultdict(set)
    possessive_rules = {flag: [rule for rule in rules if ordinary_possessive_rule(rule, special)]
                        for flag, rules in suffixes.items()}
    possessive_ids = {id(rule) for rules in possessive_rules.values() for rule in rules}

    def nominal_derivation(rule):
        tags = rule.morphology.split()
        formation = [tag for tag in tags if tag.startswith("ds:")]
        return (len(formation) == 1 and formation[0].endswith(("_noun", "_adj"))
                and not any(tag.startswith("is:") and tag != "is:NOM" for tag in tags)
                and not _continuation_rejection_reason(rule.continuation_flags, special))

    derived_ids = {id(rule) for rules in suffixes.values() for rule in rules if nominal_derivation(rule)}
    eligible_ids = possessive_ids | derived_ids
    initial_rules = {flag: [rule for rule in rules if id(rule) in eligible_ids]
                     for flag, rules in suffixes.items()}

    def record(anchor, lemma, surface, rule):
        if (anchor in anchors and surface in candidates and surface not in blocked
                and is_valid_hu_word(surface) and id(rule) in possessive_ids):
            paths[surface].add((anchor, lemma))

    for line in lines:
        parsed = parse_dictionary_line(line, af, am)
        if parsed is None:
            continue
        word, flags, morphology = parsed
        lemma = _source_lemma(word, morphology)
        if (word != word.lower() or not is_valid_hu_word(word)
                or word in excluded_sources or lemma in excluded_lemmas
                or "po:noun_prs" in morphology.split()
                or any(_has_flag(flags, special, name) for name in REJECT_ENTRY_FLAGS)):
            continue
        nominal_entry = bool({"po:noun", "po:adj"}.intersection(morphology.split()))
        for flag in flags:
            for first in initial_rules.get(bytes([flag]), ()):
                intermediate = _apply_suffix_rule(word, first)
                # A lexical source entry may itself be analyzed as derived.
                if nominal_entry:
                    record(word, lemma, intermediate, first)
                if intermediate not in anchors or id(first) not in derived_ids:
                    continue
                # Source continuations enforce two suffix steps and terminal
                # flags. Never recurse over newly rescued forms.
                for continuation in first.continuation_flags:
                    for second in possessive_rules.get(bytes([continuation]), ()):
                        record(intermediate, lemma, _apply_suffix_rule(intermediate, second), second)
    return {surface: frozenset(proofs) for surface, proofs in paths.items()}


def _tags(tail: str) -> tuple[str, ...] | None:
    tags, depth, start = [], 0, 0
    for i, char in enumerate(tail):
        if char == "<":
            if depth == 0:
                start = i
            depth += 1
        elif char == ">":
            if depth == 0:
                return None
            depth -= 1
            if depth == 0:
                tags.append(tail[start:i + 1])
        elif depth == 0 and not char.isspace():
            return None
    return None if depth else tuple(tags)


def analysis_signatures(word: str, lines: list[str], *, possessive: bool) -> frozenset[Signature]:
    result = set()
    for line in lines:
        if not line.startswith(word + " "):
            continue
        analysis = " ".join(token for token in line[len(word):].split()
                            if not token.startswith("fl:"))
        base, separator, tail = analysis.partition("<")
        tags = _tags(separator + tail)
        if tags is None or "/PREV+" in analysis:
            continue
        if possessive:
            if (sum(tag.startswith("<POSS") for tag in tags) != 1
                    or any(not tag.startswith(("<POSS", "<CAS<")) for tag in tags)):
                continue
        elif tags and tags != ("<CAS<NOM>>",):
            continue
        # Ignore analyzer control flags, but retain the complete lexical path.
        # A different derivation of the same root is not corroboration.
        base = " ".join(token for token in base.split() if not token.startswith("fl:"))
        stems = re.findall(r"\bst:([^\s]+)", base)
        if (len(stems) != 1 or stems[0] != stems[0].lower()
                or not is_valid_hu_word(stems[0])
                or not re.search(r"/(?:NOUN|ADJ)$", base)):
            continue
        result.add((stems[0], base))
    return frozenset(result)


def analyze_anchors_and_possessives(
    words: frozenset[str], aff_path: Path, dic_path: Path,
    hunspell_binary: str, cache_dir: Path, workers: int = 4,
) -> dict[str, tuple[frozenset[Signature], frozenset[Signature]]]:
    ordered = sorted(words)
    source = "\n".join(ordered) + "\n"
    key = hashlib.sha256(b"anchored-possessive-signatures-v1\n" + source.encode()
                         + aff_path.read_bytes() + dic_path.read_bytes()).hexdigest()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"anchored-possessives-{key[:20]}.jsonl.gz"
    if cache.exists():
        with gzip.open(cache, "rt", encoding="utf-8") as f:
            assert json.loads(next(f)) == {"schema": 1, "sha256": key}
            rows = [json.loads(line) for line in f]
        assert [row[0] for row in rows] == ordered, "Incomplete anchored analysis cache"
        return {word: (frozenset(map(tuple, bare)), frozenset(map(tuple, possessed)))
                for word, bare, possessed in rows}

    def analyze(chunk):
        response = subprocess.run(
            [hunspell_binary, "-i", "utf-8", "-m", "-d", str(dic_path.with_suffix(""))],
            input="\n".join(chunk) + "\n", text=True, encoding="utf-8", errors="replace",
            capture_output=True, check=True)
        blocks = re.split(r"\n\s*\n", response.stdout.strip()) if response.stdout.strip() else []
        if len(blocks) != len(chunk):
            raise ValueError(f"Expected {len(chunk)} analysis blocks, got {len(blocks)}")
        return [(word, analysis_signatures(word, block.splitlines(), possessive=False),
                 analysis_signatures(word, block.splitlines(), possessive=True))
                for word, block in zip(chunk, blocks)]

    print(f"Corroborating {len(ordered):,} anchors and possessives with morphdb.hu...", flush=True)
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for chunk_rows in pool.map(analyze, (ordered[i:i + 10000] for i in range(0, len(ordered), 10000))):
            rows.extend(chunk_rows)
            print(f"  checked {len(rows):,}/{len(ordered):,} forms", flush=True)
    temporary = cache.with_suffix(".tmp.gz")
    with gzip.open(temporary, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"schema": 1, "sha256": key}) + "\n")
        for word, bare, possessed in rows:
            f.write(json.dumps([word, sorted(bare), sorted(possessed)], ensure_ascii=False) + "\n")
    os.replace(temporary, cache)
    return {word: (bare, possessed) for word, bare, possessed in rows}


def corroborate_paths(paths, analyses) -> dict[str, frozenset[SourcePath]]:
    verified = {}
    for surface, proofs in paths.items():
        possessed = analyses[surface][1]
        matches = frozenset((anchor, lemma) for anchor, lemma in proofs
                            if any(root == lemma and "[" in signature
                                   for root, signature in possessed & analyses[anchor][0]))
        if matches:
            verified[surface] = matches
    return verified
