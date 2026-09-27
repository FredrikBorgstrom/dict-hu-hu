#!/usr/bin/env python3
"""Conservative, repeatable review of Hungarian plural-possessive additions.

Uses only Python's standard library. Never changes a dictionary or publishes it.
See HUNGARIAN_VALIDATION.md for the evidence policy and its limitations.
"""

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parent
POLICY_VERSION = "1.0"
WORD = re.compile(r"[a-záéíóöőúüű]+\Z")
ORDINARY = "cross_analyzer_possessive_of_accepted_noun"
DERIVED = "cross_analyzer_possessive_of_accepted_derived_word"
OWNERS = {
    ("first-person", "singular"): ("my", "m"),
    ("second-person", "singular"): ("your (one owner)", "d"),
    ("third-person", "singular"): ("his/her/its", ""),
    ("first-person", "plural"): ("our", "nk"),
    ("second-person", "plural"): ("your (multiple owners)", None),
    ("third-person", "plural"): ("their", "k"),
}
# Hold restricted registers and alternate-only entries; never label them invalid.
RESTRICTED = {"archaic", "obsolete", "dated", "dialectal", "nonstandard",
              "misspelling", "rare", "historical", "proscribed"}
SOURCE_URL = "https://kaikki.org/dictionary/Hungarian/index.html"
GRAMMAR_URLS = ["https://en.wiktionary.org/wiki/-aim",
                "https://en.wiktionary.org/wiki/-eim",
                "https://en.wiktionary.org/wiki/-ai",
                "https://en.wiktionary.org/wiki/-ei"]


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def words_from_text(text):
    return {line.strip() for line in text.splitlines()
            if line.strip() and not line.startswith("#")}


def open_text(path):
    return gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz" else path.open(encoding="utf-8")


def tsv_rows(path, required):
    with open_text(path) as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if not required <= set(reader.fieldnames or ()):
            raise ValueError(f"Missing evidence columns in {path}: {sorted(required)}")
        yield from reader


def load_proofs(words, output):
    """Require existing admission proof, with an exact independently checked anchor."""
    admission, seen = {}, set()
    columns = {"word", "decision", "reason", "morphdb_recognized", "morphdb_nonproper",
               "morphdb_proper_only", "lemma_agreement", "ordinary_possessive_lemmas"}
    for row in tsv_rows(output / "evidence.tsv.gz", columns):
        word = row["word"]
        if word not in words:
            continue
        if word in seen:
            raise ValueError(f"Duplicate admission evidence: {word}")
        seen.add(word)
        if (row["decision"] == "accept" and row["reason"] in {ORDINARY, DERIVED}
                and all(row[k] == "1" for k in ("morphdb_recognized", "morphdb_nonproper", "lemma_agreement"))
                and row["morphdb_proper_only"] == "0"):
            admission[word] = (row["reason"], set(row["ordinary_possessive_lemmas"].split(",")))
    proofs = defaultdict(set)
    for row in tsv_rows(output / "ordinary-possessive-evidence.tsv.gz", {"surface", "accepted_noun_lemmas"}):
        reason, lemmas = admission.get(row["surface"], (None, set()))
        if reason == ORDINARY:
            proofs[row["surface"]].update(lemmas & set(row["accepted_noun_lemmas"].split(",")))
    for row in tsv_rows(output / "derived-possessive-evidence.tsv.gz",
                        {"surface", "accepted_anchor", "source_lemma", "morphdb_lexical_analysis"}):
        reason, _ = admission.get(row["surface"], (None, set()))
        if reason == DERIVED and row["source_lemma"] and row["morphdb_lexical_analysis"]:
            proofs[row["surface"]].add(row["accepted_anchor"])
    return {word: sorted(a for a in anchors if WORD.fullmatch(a))
            for word, anchors in proofs.items()}


def variants(value):
    """Parse only the source's simple 'x (or y)' / 'x or y' notation."""
    value = value.strip()
    if WORD.fullmatch(value):
        return [value]
    match = re.fullmatch(r"(.+) \(or (.+)\)", value)
    parts = [match[1], match[2]] if match else value.split(" or ")
    return parts if len(parts) > 1 and all(WORD.fullmatch(p) for p in parts) else []


def noun_paradigms(entry):
    """Keep six matching owner columns within one noun entry and one stem variant.

    The documented second-person plural selects harmony (itek/itok). Guessing
    it from the root's vowels would incorrectly handle words such as gyík.
    """
    if entry.get("pos") != "noun" or set(entry.get("tags", ())) & RESTRICTED:
        return []
    senses = [s for s in entry.get("senses", []) if s.get("glosses")
              and not s.get("form_of") and not s.get("alt_of")
              and not set(s.get("tags", ())) & (RESTRICTED | {"form-of", "alt-of"})]
    if not senses:
        return []
    groups = defaultdict(lambda: defaultdict(set))
    for form in entry.get("forms", []):
        tags = set(form.get("tags", ()))
        if form.get("source") != "declension" or not {"possessive", "possessed-many"} <= tags:
            continue
        slots = [slot for slot in OWNERS if set(slot) <= tags]
        if len(slots) != 1:
            continue
        slot = slots[0]
        if tags != {"possessive", "possessed-many", *slot}:
            continue  # Unknown qualifiers, case stacks, or extraction errors.
        _, ending = OWNERS[slot]
        for surface in variants(form.get("form", "")):
            if ending is None:
                ending_here = "tek" if surface.endswith("itek") else "tok" if surface.endswith("itok") else None
                if ending_here is None:
                    continue
            else:
                ending_here = ending
            stem = surface[:-len(ending_here)] if ending_here else surface
            if stem.endswith("i") and surface == stem + ending_here:
                groups[stem][slot].add(surface)
    result = []
    for stem, slots in sorted(groups.items()):
        if set(slots) != set(OWNERS):
            continue
        for second_plural in sorted(slots[("second-person", "plural")]):
            harmony = "front" if second_plural.endswith("itek") else "back"
            forms = {slot: sorted(values)[0] for slot, values in slots.items()}
            forms[("second-person", "plural")] = second_plural
            result.append({"stem": stem, "harmony": harmony, "forms": forms,
                           "gloss": senses[0]["glosses"][0]})
    return result


def case_forms(surface, harmony):
    """A closed set of single common case endings, after a documented possession.

    No recursive suffixing, new noun stems, nominalizations, -ul/-ül, -kor,
    anaphoric possessions, or speculative word formation.
    """
    if harmony not in {"front", "back"} or not surface or surface[-1] not in "imdk":
        raise ValueError("Unsupported possessive ending or harmony")
    back = harmony == "back"
    low, long = ("a", "á") if back else ("e", "é")
    vowel = surface.endswith("i")
    endings = {
        "nominative": "",
        "accusative": "t" if vowel else low + "t",
        "dative": "nak" if back else "nek",
        "instrumental": ("v" if vowel else surface[-1]) + low + "l",
        "translative": ("v" if vowel else surface[-1]) + long,
        "causal-final": "ért", "terminative": "ig", "essive-formal": "ként",
        "inessive": "ban" if back else "ben", "illative": "ba" if back else "be",
        "elative": "ból" if back else "ből", "adessive": "nál" if back else "nél",
        "allative": "hoz" if back else "hez", "ablative": "tól" if back else "től",
        "superessive": "n" if vowel else "on" if back else "en",
        "sublative": "ra" if back else "re", "delative": "ról" if back else "ről",
    }
    return {surface + suffix: case for case, suffix in endings.items()}


def reference_matches(path, anchors, words):
    matches = defaultdict(dict)
    seen, noun_entries, paradigms = set(), set(), set()
    hu_entries = 0
    with open_text(path) as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if not isinstance(entry, dict):
                    raise ValueError("Entry must be an object")
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Malformed reference at line {line_number}: {exc}") from exc
            if entry.get("lang_code") != "hu":
                continue
            hu_entries += 1
            anchor = entry.get("word")
            if anchor not in anchors:
                continue
            seen.add(anchor)
            if entry.get("pos") == "noun":
                noun_entries.add(anchor)
            for paradigm in noun_paradigms(entry):
                paradigms.add(anchor)
                for slot, possessive in paradigm["forms"].items():
                    for surface, case in case_forms(possessive, paradigm["harmony"]).items():
                        if surface in words and anchor not in matches[surface]:
                            matches[surface][anchor] = {
                                "anchor": anchor, "base_meaning": paradigm["gloss"],
                                "possessive": possessive, "owner": OWNERS[slot][0],
                                "case": case, "harmony": paradigm["harmony"],
                                "source_line": line_number,
                                "source_url": "https://en.wiktionary.org/wiki/" + urllib.parse.quote(anchor, safe="") + "#Hungarian",
                            }
    if not hu_entries:
        raise ValueError("Reference contains no Hungarian entries; refusing an empty-source audit")
    return matches, {"seen": seen, "nouns": noun_entries, "paradigms": paradigms}


def classify(word, proofs, matches, coverage, removals):
    anchors = proofs.get(word, [])
    if word in removals["surfaceRemovals"]:
        return "excluded", "explicit_gameplay_removal", {}
    if not WORD.fullmatch(word):
        return "excluded", "not_a_lowercase_hungarian_game_word", {}
    eligible = [a for a in anchors if a not in removals["lemmaRemovals"]]
    if anchors and not eligible:
        return "excluded", "all_proven_anchors_explicitly_removed", {}
    for anchor in eligible:
        if anchor in matches.get(word, {}):
            return "supported", "published_noun_paradigm_and_bounded_case_rule", matches[word][anchor]
    if not eligible:
        reason = "no_matching_generator_admission_proof"
    elif set(eligible) & coverage["paradigms"]:
        reason = "form_outside_supported_paradigm_or_case_policy"
    elif set(eligible) & coverage["nouns"]:
        reason = "no_complete_unrestricted_noun_paradigm"
    elif set(eligible) & coverage["seen"]:
        reason = "no_published_noun_entry_for_anchor"
    else:
        reason = "anchor_missing_from_reference"
    return "pending", reason, {}


def cached_reference(cache, url, offline=False, refresh=False):
    manifest = cache / "reference.json"
    if manifest.exists() and not refresh:
        data = json.loads(manifest.read_text())
        path = cache / data["filename"]
        if path.parent != cache or sha256(path) != data["sha256"]:
            raise ValueError("Reference cache checksum/path mismatch; use --refresh-reference")
        return path, data
    if offline:
        raise ValueError("No cached reference. Run once online, or supply --reference FILE")
    cache.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H-%M-%S-%f UTC")
    path = cache / f"Hungarian Reference {stamp}.jsonl"
    part = path.with_suffix(".part")
    print("Downloading the Hungarian reference once (approximately 590 MB)...", flush=True)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "ABCx3-Hungarian-Validator/1.0"})
        with urllib.request.urlopen(request, timeout=30) as response, part.open("xb") as target:
            expected = response.headers.get("Content-Length")
            count, last_report = 0, 0
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                target.write(chunk)
                count += len(chunk)
                if count - last_report >= 50 * 1024 * 1024:
                    print(f"  Downloaded {count // (1024 * 1024)} MB", flush=True)
                    last_report = count
            if expected and count != int(expected):
                raise ValueError("Incomplete reference download; cache was not replaced")
            modified = response.headers.get("Last-Modified")
        with part.open(encoding="utf-8") as check:
            if not isinstance(json.loads(check.readline()), dict):
                raise ValueError("Download is not a dictionary reference")
        part.replace(path)
        data = {"filename": path.name, "sha256": sha256(path), "bytes": count,
                "url": url, "retrieved_utc": stamp, "last_modified": modified}
        temp = manifest.with_suffix(".tmp")
        temp.write_text(json.dumps(data, indent=2) + "\n")
        temp.replace(manifest)
        return path, data
    finally:
        part.unlink(missing_ok=True)


def write_results(destination, words, proofs, matches, coverage, removals, metadata):
    # Create only after all sources parsed successfully; never overwrite a review.
    destination.mkdir(parents=True, exist_ok=False)
    counts, reasons, families = Counter(), Counter(), Counter()
    columns = ["word", "status", "reason", "candidate_anchors", "anchor", "base_meaning",
               "possessive", "owner", "case", "harmony", "source_line", "source_url"]
    files = {status: (destination / f"{status}.txt").open("w", encoding="utf-8")
             for status in ("supported", "pending", "excluded")}
    try:
        with (destination / "decisions.tsv").open("w", encoding="utf-8", newline="") as table:
            writer = csv.DictWriter(table, fieldnames=columns, delimiter="\t")
            writer.writeheader()
            for word in sorted(words):
                status, reason, evidence = classify(word, proofs, matches, coverage, removals)
                counts[status] += 1
                reasons[reason] += 1
                files[status].write(word + "\n")
                writer.writerow(dict(word=word, status=status, reason=reason,
                                     candidate_anchors=",".join(proofs.get(word, [])), **evidence))
                if evidence:
                    families[(evidence["anchor"], evidence["base_meaning"], evidence["source_url"])] += 1
    finally:
        for stream in files.values():
            stream.close()
    with (destination / "families.tsv").open("w", encoding="utf-8", newline="") as table:
        writer = csv.writer(table, delimiter="\t")
        writer.writerow(["anchor", "base_meaning", "supported_candidates", "source_url"])
        for (anchor, gloss, url), count in sorted(families.items()):
            writer.writerow([anchor, gloss, count, url])
    summary = {**metadata, "counts": {s: counts[s] for s in files}, "reasons": dict(sorted(reasons.items())),
               "supported_families": len(families),
               "reference_coverage": {k: len(v) for k, v in coverage.items()},
               "result_sha256": {name: sha256(destination / name) for name in
                                 ("supported.txt", "pending.txt", "excluded.txt", "decisions.tsv", "families.tsv")}}
    (destination / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    report = ["# Hungarian dictionary validation", "",
              f"Checked **{len(words):,}** candidate words using policy {POLICY_VERSION}.", "",
              f"- Supported: **{counts['supported']:,}**, across {len(families):,} noun families.",
              f"- Pending: **{counts['pending']:,}**.", f"- Excluded by game policy: **{counts['excluded']:,}**.", "",
              "Supported means the saved generator evidence and a published noun paradigm match, "
              "with at most one of this checker's common case endings. It is not a guarantee of natural "
              "usage or an independent human review. Published tables can contain mistakes and are "
              "themselves often generated. Pending means insufficient evidence, not an invalid word.", "",
              "See [decisions.tsv](decisions.tsv) for every decision, English base meanings, owner, case "
              "and source; [families.tsv](families.tsv) lists only the supported words' families. "
              "A supported family does not clear all possible words built from that noun.", "",
              "No dictionary files were changed or published. These lists are review artifacts, not release artifacts.", "",
              f"Source revision: `{metadata['source_revision']}`. Baseline: `{metadata.get('baseline', 'explicit word selection')}`.",
              f"Reference checksum: `{metadata['reference']['sha256']}`.",
              "Input hashes, source details and output checksums are in [summary.json](summary.json).", "",
              "## Attribution", "",
              f"Noun meanings and paradigms: English Wiktionary contributors, via [Kaikki]({SOURCE_URL}). "
              "Reference-derived review data is attributed under [Creative Commons Attribution-ShareAlike 4.0]"
              "(https://creativecommons.org/licenses/by-sa/4.0/). Each supported decision links to its entry. "
              "Case rules are documented in HUNGARIAN_VALIDATION.md. The existing Ispell-derived candidate "
              "words retain their repository license. Preserve attribution if sharing these reports.", ""]
    (destination / "Report.md").write_text("\n".join(report), encoding="utf-8")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--words", type=Path, help="Check this one-word-per-line list instead of new additions")
    selection.add_argument("--word", action="append", help="Check a word; repeat for several words")
    baseline = parser.add_mutually_exclusive_group()
    baseline.add_argument("--baseline", type=Path, help="Published baseline word list")
    baseline.add_argument("--baseline-ref", help="Published baseline Git revision")
    parser.add_argument("--output", type=Path, default=ROOT / "output", help="Candidate build and its evidence files")
    parser.add_argument("--reference", type=Path, help="Local Kaikki/Wiktextract JSON lines, optionally gzip compressed")
    parser.add_argument("--offline", action="store_true", help="Never access the network")
    parser.add_argument("--refresh-reference", action="store_true", help="Explicitly download a fresh reference snapshot")
    parser.add_argument("--out-dir", type=Path, help="New directory for results (must not already exist)")
    parser.add_argument("--open-results", action="store_true", help="Open the results folder in Finder on macOS")
    args = parser.parse_args(argv)
    if args.refresh_reference and (args.offline or args.reference):
        parser.error("--refresh-reference cannot be combined with --offline or --reference")
    config = json.loads((ROOT / "validation_config.json").read_text())
    if config.get("schema_version") != 1:
        raise ValueError("Unsupported validation configuration")
    wordlist = args.output / Path(config["wordlist"]).name
    metadata = {"policy_version": POLICY_VERSION,
                "source_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "validator_sha256": sha256(Path(__file__)), "config_sha256": sha256(ROOT / "validation_config.json"),
                "grammar_sources": GRAMMAR_URLS}
    input_paths = [wordlist, args.output / "evidence.tsv.gz", args.output / "ordinary-possessive-evidence.tsv.gz",
                   args.output / "derived-possessive-evidence.tsv.gz", ROOT / "gameplay_overrides.json"]
    metadata["inputs"] = {str(p.resolve()): sha256(p) for p in input_paths}
    active_words = words_from_text(wordlist.read_text(encoding="utf-8"))
    if args.words:
        words = words_from_text(args.words.read_text(encoding="utf-8"))
        metadata["selection"] = {"path": str(args.words.resolve()), "sha256": sha256(args.words)}
    elif args.word:
        words = set(args.word)
        metadata["selection"] = {"words": sorted(words)}
    else:
        if args.baseline:
            baseline_text = args.baseline.read_text(encoding="utf-8")
            metadata["baseline"] = str(args.baseline.resolve())
        else:
            revision = args.baseline_ref or config["published_baseline_ref"]
            baseline_text = subprocess.check_output(["git", "show", f"{revision}:{config['wordlist']}"], cwd=ROOT, text=True)
            metadata["baseline"] = revision
        metadata["baseline_sha256"] = hashlib.sha256(baseline_text.encode()).hexdigest()
        words = active_words - words_from_text(baseline_text)
    if not words:
        print("No new words to check.")
        return 0
    metadata["selection_sha256"] = hashlib.sha256("".join(w + "\n" for w in sorted(words)).encode()).hexdigest()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H-%M-%S-%f UTC")
    destination = args.out_dir or ROOT / "artifacts/Hungarian Validation" / f"Review {stamp}"
    if destination.exists():
        raise ValueError(f"Results directory already exists: {destination}")
    print(f"Checking saved admission evidence for {len(words):,} words...", flush=True)
    proofs = load_proofs(words & active_words, args.output)
    removals = json.loads((ROOT / "gameplay_overrides.json").read_text())
    removals = {k: set(removals[k]) for k in ("surfaceRemovals", "lemmaRemovals")}
    if args.reference:
        reference = args.reference
        reference_info = {"path": str(reference.resolve()), "sha256": sha256(reference), "url": "user-supplied local reference"}
    else:
        reference, reference_info = cached_reference(ROOT / "artifacts/Hungarian Validation/Reference Cache",
                                                     config["reference_url"], args.offline, args.refresh_reference)
    print("Matching published noun paradigms and common case endings...", flush=True)
    anchors = {a for values in proofs.values() for a in values} - removals["lemmaRemovals"]
    matches, coverage = reference_matches(reference, anchors, words)
    # A build running concurrently must not leave a mixed-input review.
    if any(sha256(Path(p)) != digest for p, digest in metadata["inputs"].items()):
        raise ValueError("Build inputs changed during validation; rerun after the build finishes")
    if sha256(reference) != reference_info["sha256"]:
        raise ValueError("Reference changed during validation; no results written")
    metadata["reference"] = reference_info
    summary = write_results(destination, words, proofs, matches, coverage, removals, metadata)
    print("\n" + ", ".join(f"{status}: {count:,}" for status, count in summary["counts"].items()))
    print(f"Results: {destination.resolve() / 'Report.md'}")
    if args.open_results and sys.platform == "darwin":
        subprocess.run(["open", str(destination.resolve())], check=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f"Validation stopped: {error}", file=sys.stderr)
        sys.exit(1)
