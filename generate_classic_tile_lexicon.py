#!/usr/bin/env python3
"""Generate the separate classic Hungarian physical-tile lexicon.

The existing surface word list is read-only input. The compact runtime output
stores a base64url sequence of one-byte tile identifiers beside the exact NFC
surface spelling. A separately compressed, human-readable source artifact
retains ``surface<TAB>token|token`` rows for review and licensing compliance.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import io
import json
import unicodedata
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from process_words import parse_aff, parse_dictionary_line


SCHEMA_VERSION = 1
GENERATOR_VERSION = "1.3.0"
PLAYABLE_TOKENS = (
    "a", "á", "b", "c", "cs", "d", "e", "é", "f", "g", "gy", "h",
    "i", "í", "j", "k", "l", "ly", "m", "n", "ny", "o", "ó", "ö",
    "ő", "p", "r", "s", "sz", "t", "ty", "u", "ú", "ü", "ű", "v",
    "z", "zs",
)
TOKEN_ID = {token: index + 1 for index, token in enumerate(PLAYABLE_TOKENS)}
SHORTENED_DOUBLING = {
    "ccs": "cs",
    "ggy": "gy",
    "lly": "ly",
    "nny": "ny",
    "ssz": "sz",
    "tty": "ty",
    "zzs": "zs",
}
DEFAULT_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Candidate:
    tokens: tuple[str, ...]
    shortened: tuple[str, ...] = ()
    boundary_crossings: frozenset[int] = frozenset()
    # Retain the pre-1.3 tile interpretation only as a compatibility alias.
    # Ranking on that interpretation preserves prior morphology decisions.
    legacy_tokens: tuple[str, ...] | None = None

    @property
    def key(self) -> bytes:
        return bytes(TOKEN_ID[token] for token in self.tokens)

    @property
    def comparison_tokens(self) -> tuple[str, ...]:
        return self.legacy_tokens if self.legacy_tokens is not None else self.tokens

    @property
    def legacy_key(self) -> bytes:
        return bytes(TOKEN_ID[token] for token in self.comparison_tokens)


@dataclass(frozen=True)
class BoundaryIndex:
    boundaries: dict[str, frozenset[int]]
    explicit_analysis_count: int = 0
    prefix_analysis_count: int = 0
    ignored_analysis_count: int = 0
    conflicts: tuple[tuple[str, tuple[tuple[int, ...], ...]], ...] = ()
    supplemental_annotation_count: int = 0
    supplemental_boundary_count: int = 0


class BoundaryUnrepresentableError(ValueError):
    """Raised when authoritative boundaries cannot be made from game tiles."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def portable_audit_path(path: Path) -> str:
    """Keep audit manifests reproducible across checkout locations."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(DEFAULT_ROOT).as_posix()
    except ValueError:
        return path.name


@contextmanager
def deterministic_gzip_text_writer(path: Path):
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="\n") as text:
                yield text


def normalize_surface(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip()).lower()


def parse_marked_boundary_surface(value: str) -> tuple[str, frozenset[int]]:
    """Parse one surface whose mandatory physical-tile breaks use ``_``."""
    marked_surface = normalize_surface(value)
    if not marked_surface or marked_surface.startswith("_") or marked_surface.endswith("_"):
        raise ValueError(f"Invalid marked boundary surface: {value!r}")
    if "__" in marked_surface:
        raise ValueError(f"Repeated boundary marker in: {value!r}")
    if any(not (character.isalpha() or character == "_") for character in marked_surface):
        raise ValueError(f"Unsupported marked boundary character in: {value!r}")

    rendered: list[str] = []
    boundaries: set[int] = set()
    for character in marked_surface:
        if character == "_":
            boundaries.add(len(rendered))
        else:
            rendered.append(character)
    if not boundaries:
        raise ValueError(f"Missing boundary marker in: {value!r}")
    return "".join(rendered), frozenset(boundaries)


def load_supplemental_boundary_index(path: Path | None) -> BoundaryIndex:
    """Load permissioned CsiSza ``_`` annotations without importing words."""
    if path is None:
        return BoundaryIndex({})
    if not path.is_file():
        raise FileNotFoundError(f"Missing supplemental tile-boundary source: {path}")

    boundaries: dict[str, frozenset[int]] = {}
    boundary_count = 0
    with path.open("r", encoding="utf-8") as source:
        for line_number, raw_line in enumerate(source, 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            surface, marked_boundaries = parse_marked_boundary_surface(line)
            if surface in boundaries:
                raise ValueError(
                    f"Duplicate supplemental boundary surface {surface!r} "
                    f"at line {line_number} in {path}"
                )
            boundaries[surface] = marked_boundaries
            boundary_count += len(marked_boundaries)

    return BoundaryIndex(
        boundaries=boundaries,
        supplemental_annotation_count=len(boundaries),
        supplemental_boundary_count=boundary_count,
    )


def merge_boundary_indexes(*indexes: BoundaryIndex) -> BoundaryIndex:
    """Merge independent authoritative boundary sources additively."""
    combined: dict[str, set[int]] = defaultdict(set)
    conflicts: list[tuple[str, tuple[tuple[int, ...], ...]]] = []
    for index in indexes:
        for surface, boundaries in index.boundaries.items():
            combined[surface].update(boundaries)
        conflicts.extend(index.conflicts)
    return BoundaryIndex(
        boundaries={
            surface: frozenset(boundaries)
            for surface, boundaries in combined.items()
        },
        explicit_analysis_count=sum(index.explicit_analysis_count for index in indexes),
        prefix_analysis_count=sum(index.prefix_analysis_count for index in indexes),
        ignored_analysis_count=sum(index.ignored_analysis_count for index in indexes),
        conflicts=tuple(conflicts),
        supplemental_annotation_count=sum(
            index.supplemental_annotation_count for index in indexes
        ),
        supplemental_boundary_count=sum(
            index.supplemental_boundary_count for index in indexes
        ),
    )


def enumerate_candidates(surface: str) -> list[Candidate]:
    memo: dict[int, tuple[Candidate, ...]] = {}

    def visit(offset: int) -> tuple[Candidate, ...]:
        if offset == len(surface):
            return (Candidate(()),)
        if offset in memo:
            return memo[offset]
        results: set[Candidate] = set()
        for spelling, token in SHORTENED_DOUBLING.items():
            if surface.startswith(spelling, offset):
                for suffix in visit(offset + len(spelling)):
                    # A shortened double multigraph is one orthographic unit.
                    # A compound/morpheme boundary may not split that spelling;
                    # full forms such as SZ|SZ are enumerated separately.
                    results.add(Candidate(
                        (token[0], token) + suffix.tokens,
                        (token,) + suffix.shortened,
                        frozenset(range(offset + 1, offset + len(spelling)))
                        | suffix.boundary_crossings,
                        (token, token) + suffix.comparison_tokens,
                    ))
        for token in PLAYABLE_TOKENS:
            if surface.startswith(token, offset):
                for suffix in visit(offset + len(token)):
                    results.add(Candidate(
                        (token,) + suffix.tokens,
                        suffix.shortened,
                        frozenset(range(offset + 1, offset + len(token)))
                        | suffix.boundary_crossings,
                        (token,) + suffix.comparison_tokens if suffix.legacy_tokens is not None else None,
                    ))
        memo[offset] = tuple(results)
        return memo[offset]

    return list(visit(0))


def load_overrides(path: Path) -> dict[str, tuple[str, ...]]:
    overrides: dict[str, tuple[str, ...]] = {}
    with path.open("r", encoding="utf-8") as source:
        for line_number, raw_line in enumerate(source, 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                raw_surface, raw_tokens = line.split("\t", 1)
            except ValueError as error:
                raise ValueError(f"Invalid override row {line_number} in {path}") from error
            surface = normalize_surface(raw_surface)
            tokens = tuple(normalize_surface(token) for token in raw_tokens.split("|") if token.strip())
            if not tokens or any(token not in TOKEN_ID for token in tokens):
                raise ValueError(f"Override for {surface!r} contains an unplayable tile token")
            candidates = enumerate_candidates(surface)
            if tokens not in {candidate.tokens for candidate in candidates}:
                raise ValueError(f"Override for {surface!r} does not reproduce its written spelling")
            if surface in overrides:
                raise ValueError(f"Duplicate override for {surface!r}")
            overrides[surface] = tokens
    return overrides


def load_lemma_index(directory: Path) -> dict[str, tuple[str, ...]]:
    lemmas: dict[str, set[str]] = defaultdict(set)
    if not directory.is_dir():
        return {}
    for shard in sorted(directory.glob("*.tsv.gz")):
        with gzip.open(shard, "rt", encoding="utf-8") as source:
            for raw_line in source:
                fields = raw_line.rstrip("\n").split("\t")
                if len(fields) < 2:
                    continue
                surface = normalize_surface(fields[0])
                for raw_lemma in fields[1].split(","):
                    lemma = normalize_surface(raw_lemma)
                    if surface and lemma:
                        lemmas[surface].add(lemma)
    return {surface: tuple(sorted(values)) for surface, values in lemmas.items()}


def parse_hyphenation_boundaries(
    surface: str,
    raw_hyphenation: str,
) -> tuple[frozenset[int] | None, bool]:
    """Extract explicit ``|`` boundaries from one Magyar Ispell ``hy:`` field.

    Magyar Ispell may retain only the analyzed stem in ``hy:`` while the
    dictionary surface includes an ending. Therefore an exact spelling or a
    prefix spelling is accepted, but unrelated/encoded diagnostic fields are
    ignored. Hyphenation and syllable markers are not physical tile breaks.
    """
    normalized_surface = normalize_surface(surface)
    visible = raw_hyphenation.split(";", 1)[0].split("/", 1)[0]
    rendered: list[str] = []
    boundaries: set[int] = set()
    for character in unicodedata.normalize("NFC", visible):
        if character == "|":
            boundaries.add(len(rendered))
        elif character in "-=.":
            continue
        elif character == "_":
            rendered.append(" ")
        elif character.isalpha():
            rendered.append(character)

    analyzed_surface = normalize_surface("".join(rendered))
    is_prefix = analyzed_surface != normalized_surface
    if not analyzed_surface or not normalized_surface.startswith(analyzed_surface):
        return None, False

    usable = frozenset(
        boundary
        for boundary in boundaries
        if 0 < boundary < len(normalized_surface)
    )
    return (usable or None), is_prefix


def load_ispell_boundary_index(
    aff_path: Path | None,
    dic_path: Path | None,
) -> BoundaryIndex:
    if aff_path is None and dic_path is None:
        return BoundaryIndex({})
    if aff_path is None or dic_path is None:
        raise ValueError("Both Magyar Ispell .aff and .dic paths are required")
    if not aff_path.is_file() or not dic_path.is_file():
        raise FileNotFoundError(
            f"Missing Magyar Ispell boundary source: {aff_path} / {dic_path}"
        )

    _, morphology_aliases, _, _, _ = parse_aff(str(aff_path))
    analyses_by_surface: dict[str, set[frozenset[int]]] = defaultdict(set)
    explicit_analysis_count = 0
    prefix_analysis_count = 0
    ignored_analysis_count = 0

    with dic_path.open("r", encoding="utf-8", errors="replace") as source:
        next(source, None)
        for raw_line in source:
            parsed = parse_dictionary_line(raw_line, {}, morphology_aliases)
            if parsed is None:
                continue
            raw_surface, _, morphology = parsed
            surface = normalize_surface(raw_surface)
            for field in morphology.split():
                if not field.startswith("hy:") or "|" not in field:
                    continue
                boundaries, is_prefix = parse_hyphenation_boundaries(
                    surface,
                    field[3:],
                )
                if boundaries is None:
                    ignored_analysis_count += 1
                    continue
                explicit_analysis_count += 1
                if is_prefix:
                    prefix_analysis_count += 1
                analyses_by_surface[surface].add(boundaries)

    conflicts: list[tuple[str, tuple[tuple[int, ...], ...]]] = []
    boundaries: dict[str, frozenset[int]] = {}
    for surface, analyses in sorted(analyses_by_surface.items()):
        ordered_analyses = tuple(
            sorted(tuple(sorted(analysis)) for analysis in analyses)
        )
        if len(ordered_analyses) > 1:
            conflicts.append((surface, ordered_analyses))
        most_detailed = max(
            analyses,
            key=lambda analysis: (len(analysis), tuple(sorted(analysis))),
        )
        if any(not analysis.issubset(most_detailed) for analysis in analyses):
            raise ValueError(
                f"Conflicting non-nested Magyar Ispell boundaries for "
                f"{surface!r}: {ordered_analyses}"
            )
        boundaries[surface] = most_detailed

    return BoundaryIndex(
        boundaries=boundaries,
        explicit_analysis_count=explicit_analysis_count,
        prefix_analysis_count=prefix_analysis_count,
        ignored_analysis_count=ignored_analysis_count,
        conflicts=tuple(conflicts),
    )


def boundaries_for_surface(
    surface: str,
    lemmas: dict[str, tuple[str, ...]],
    boundary_index: BoundaryIndex,
) -> frozenset[int]:
    resolved = set(boundary_index.boundaries.get(surface, ()))
    for lemma in lemmas.get(surface, ()):
        lemma_boundaries = boundary_index.boundaries.get(lemma)
        if not lemma_boundaries:
            continue
        shared_prefix_length = 0
        for surface_character, lemma_character in zip(surface, lemma):
            if surface_character != lemma_character:
                break
            shared_prefix_length += 1
        resolved.update(
            boundary
            for boundary in lemma_boundaries
            if boundary <= shared_prefix_length and boundary < len(surface)
        )
    return frozenset(resolved)


def common_prefix_length(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    length = 0
    for left_token, right_token in zip(left, right):
        if left_token != right_token:
            break
        length += 1
    return length


def select_candidate(
    surface: str,
    candidates: list[Candidate],
    overrides: dict[str, tuple[str, ...]],
    lemmas: dict[str, tuple[str, ...]],
    boundary_index: BoundaryIndex | None = None,
) -> tuple[Candidate, str]:
    override = overrides.get(surface)
    if override is not None:
        return min(
            (candidate for candidate in candidates if candidate.tokens == override),
            key=lambda candidate: (-len(candidate.shortened), candidate.legacy_key),
        ), "override"

    boundary_index = boundary_index or BoundaryIndex({})
    required_boundaries = boundaries_for_surface(
        surface,
        lemmas,
        boundary_index,
    )
    boundary_candidates = [
        candidate
        for candidate in candidates
        if candidate.boundary_crossings.isdisjoint(required_boundaries)
    ]
    if required_boundaries and not boundary_candidates:
        raise BoundaryUnrepresentableError(
            f"No physical-tile sequence preserves authoritative boundaries "
            f"for {surface!r}: {sorted(required_boundaries)}"
        )
    candidates = boundary_candidates or candidates

    lemma_tokenizations: list[tuple[str, ...]] = []
    for lemma in lemmas.get(surface, ()):
        if lemma == surface:
            continue
        lemma_candidates = enumerate_candidates(lemma)
        if lemma_candidates:
            lemma_boundaries = boundaries_for_surface(
                lemma,
                lemmas,
                boundary_index,
            )
            boundary_safe_lemma_candidates = [
                candidate
                for candidate in lemma_candidates
                if candidate.boundary_crossings.isdisjoint(lemma_boundaries)
            ]
            lemma_tokenizations.append(
                min(
                    boundary_safe_lemma_candidates or lemma_candidates,
                    key=lambda candidate: (
                        -len(candidate.shortened),
                        len(candidate.tokens),
                        candidate.legacy_key,
                    ),
                ).comparison_tokens
            )

    def rank(candidate: Candidate) -> tuple[object, ...]:
        morphology_score = max(
            (common_prefix_length(candidate.comparison_tokens, lemma_tokens) for lemma_tokens in lemma_tokenizations),
            default=0,
        )
        return (-len(candidate.shortened), -morphology_score, len(candidate.tokens), candidate.legacy_key)

    selected = min(candidates, key=rank)
    if required_boundaries:
        reason = "authoritativeBoundary"
    else:
        reason = "morphology" if lemma_tokenizations and len(candidates) > 1 else "orthography"
    return selected, reason


def artifact_value(key: bytes) -> str:
    return base64.urlsafe_b64encode(key).decode("ascii").rstrip("=")


def generate(
    input_path: Path,
    runtime_path: Path,
    source_path: Path,
    audit_path: Path,
    excluded_path: Path,
    override_path: Path,
    lemma_directory: Path,
    ispell_aff_path: Path | None = None,
    ispell_dic_path: Path | None = None,
    supplemental_boundary_path: Path | None = None,
) -> dict[str, object]:
    overrides = load_overrides(override_path)
    lemmas = load_lemma_index(lemma_directory)
    ispell_boundary_index = load_ispell_boundary_index(
        ispell_aff_path,
        ispell_dic_path,
    )
    supplemental_boundary_index = load_supplemental_boundary_index(
        supplemental_boundary_path,
    )
    boundary_index = merge_boundary_indexes(
        ispell_boundary_index,
        supplemental_boundary_index,
    )
    raw_words = input_path.read_text(encoding="utf-8").splitlines()
    words = sorted({normalize_surface(word) for word in raw_words if normalize_surface(word)})

    accepted_by_key: dict[bytes, tuple[str, Candidate, str]] = {}
    excluded: list[tuple[str, str]] = []
    collisions: list[dict[str, object]] = []
    shortened_counts: Counter[str] = Counter()
    resolution_counts: Counter[str] = Counter()
    ambiguous_before = 0

    for surface in words:
        candidates = enumerate_candidates(surface)
        if not candidates:
            unsupported = sorted(set(surface) - set("".join(PLAYABLE_TOKENS)))
            reason = "unsupported_character" if unsupported else "unrepresentable_token_sequence"
            excluded.append((surface, reason))
            continue
        if len(candidates) > 1:
            ambiguous_before += 1
        try:
            selected, resolution = select_candidate(
                surface,
                candidates,
                overrides,
                lemmas,
                boundary_index,
            )
        except BoundaryUnrepresentableError:
            excluded.append((surface, "authoritative_boundary_unrepresentable"))
            continue
        resolution_counts[resolution] += 1
        shortened_counts.update(selected.shortened)
        # Keep the established surface collision policy while correcting tile
        # spelling; this release must not silently change the word inventory.
        existing = accepted_by_key.get(selected.legacy_key)
        if existing is not None and existing[0] != surface:
            preferred = min((existing, (surface, selected, resolution)), key=lambda item: (len(item[0]), item[0]))
            rejected = (surface, selected, resolution) if preferred is existing else existing
            accepted_by_key[selected.legacy_key] = preferred
            excluded.append((rejected[0], "canonical_key_collision"))
            collisions.append({
                "canonicalKey": artifact_value(selected.legacy_key),
                "keptSurface": preferred[0],
                "excludedSurface": rejected[0],
            })
            continue
        accepted_by_key[selected.legacy_key] = (surface, selected, resolution)

    accepted = sorted(accepted_by_key.values(), key=lambda item: (item[1].key, item[0]))
    aliases = sorted(
        ((candidate.legacy_key, surface) for surface, candidate, _ in accepted
         if candidate.legacy_key != candidate.key),
    )
    runtime_surfaces: dict[bytes, str] = {}
    for key, surface in [*aliases, *((candidate.key, surface) for surface, candidate, _ in accepted)]:
        previous = runtime_surfaces.get(key)
        if previous is not None and previous != surface:
            raise ValueError(f"Physical/compatibility tile-key collision: {previous!r}, {surface!r}")
        runtime_surfaces[key] = surface
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    with runtime_path.open("w", encoding="utf-8", newline="\n") as destination:
        destination.write("# ABCx3 canonical Hungarian classic-tile lexicon v1\n")
        destination.write("# key=base64url one-byte token identifiers; value=NFC surface\n")
        destination.write("# Compatibility aliases first; preferred physical spelling follows.\n")
        for key, surface in aliases:
            destination.write(f"{artifact_value(key)}\t{surface}\n")
        destination.write("# Preferred physical tile sequences\n")
        for surface, candidate, _ in accepted:
            destination.write(f"{artifact_value(candidate.key)}\t{surface}\n")

    with deterministic_gzip_text_writer(source_path) as destination:
        destination.write("# surface\tcanonical tile tokens\n")
        for surface, candidate, _ in sorted(accepted, key=lambda item: item[0]):
            destination.write(f"{surface}\t{'|'.join(candidate.tokens)}\n")

    with deterministic_gzip_text_writer(excluded_path) as destination:
        destination.write("surface\treason\n")
        for surface, reason in sorted(excluded):
            destination.write(f"{surface}\t{reason}\n")

    round_trip_failures = [
        surface
        for surface, candidate, _ in accepted
        if bytes(TOKEN_ID[token] for token in candidate.tokens) != candidate.key
    ]
    audit: dict[str, object] = {
        "schemaVersion": SCHEMA_VERSION,
        "generatorVersion": GENERATOR_VERSION,
        "input": {"path": portable_audit_path(input_path), "sha256": sha256_file(input_path), "wordCount": len(words)},
        "output": {
            "runtimePath": portable_audit_path(runtime_path),
            "runtimeSha256": sha256_file(runtime_path),
            "sourcePath": portable_audit_path(source_path),
            "sourceSha256": sha256_file(source_path),
            "acceptedEntries": len(accepted),
            "runtimeEntries": len(runtime_surfaces),
            "compatibilityAliases": len(aliases),
        },
        "playableTokens": list(PLAYABLE_TOKENS),
        "shortenedDoublingCounts": dict(sorted(shortened_counts.items())),
        "fullDoublingCounts": {
            token: sum(
                1
                for _, candidate, _ in accepted
                if any(candidate.tokens[index:index + 2] == (token, token) for index in range(len(candidate.tokens) - 1))
                and token not in candidate.shortened
            )
            for token in SHORTENED_DOUBLING.values()
        },
        "override": {"path": portable_audit_path(override_path), "sha256": sha256_file(override_path), "count": len(overrides)},
        "morphology": {
            "lemmaDirectory": portable_audit_path(lemma_directory),
            "surfaceCount": len(lemmas),
            "authoritativeBoundaries": {
                "affPath": portable_audit_path(ispell_aff_path) if ispell_aff_path else None,
                "affSha256": sha256_file(ispell_aff_path) if ispell_aff_path else None,
                "dicPath": portable_audit_path(ispell_dic_path) if ispell_dic_path else None,
                "dicSha256": sha256_file(ispell_dic_path) if ispell_dic_path else None,
                "combinedSurfaceCount": len(boundary_index.boundaries),
                "ispell": {
                    "surfaceCount": len(ispell_boundary_index.boundaries),
                    "explicitAnalysisCount": ispell_boundary_index.explicit_analysis_count,
                    "prefixAnalysisCount": ispell_boundary_index.prefix_analysis_count,
                    "ignoredAnalysisCount": ispell_boundary_index.ignored_analysis_count,
                },
                "supplemental": {
                    "path": portable_audit_path(supplemental_boundary_path)
                    if supplemental_boundary_path else None,
                    "sha256": sha256_file(supplemental_boundary_path)
                    if supplemental_boundary_path else None,
                    "annotationCount": supplemental_boundary_index.supplemental_annotation_count,
                    "boundaryCount": supplemental_boundary_index.supplemental_boundary_count,
                    "exactInputOverlapCount": len(
                        set(words) & set(supplemental_boundary_index.boundaries)
                    ),
                    "policy": "boundary evidence only; never imports word validity",
                },
                "conflicts": [
                    {
                        "surface": surface,
                        "boundaryAlternatives": [list(analysis) for analysis in analyses],
                        "policy": "mostDetailedSuperset",
                    }
                    for surface, analyses in boundary_index.conflicts
                ],
            },
        },
        "resolutionCounts": dict(sorted(resolution_counts.items())),
        "excludedReasonCounts": dict(sorted(Counter(reason for _, reason in excluded).items())),
        "excludedEntries": len(excluded),
        "unrepresentableEntries": sum(1 for _, reason in excluded if reason != "canonical_key_collision"),
        "ambiguousBeforeResolution": ambiguous_before,
        "ambiguousAfterResolution": 0,
        "collisionPolicy": "keep shortest surface, then Unicode code-point order",
        "collisions": collisions,
        "roundTripFailures": round_trip_failures,
        "rendererDiagnosticMismatchCount": sum(
            1 for surface, candidate, _ in accepted if "".join(candidate.tokens) != surface
        ),
    }
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if round_trip_failures:
        raise RuntimeError(f"Canonical token round-trip failures: {len(round_trip_failures)}")
    return audit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_ROOT / "output/hungarian_hu_hu_ispell.txt")
    parser.add_argument("--runtime", type=Path, default=DEFAULT_ROOT / "output/hungarian_hu_hu_ispell_classic_tiles.tsv")
    parser.add_argument("--source", type=Path, default=DEFAULT_ROOT / "output/hungarian_hu_hu_ispell_classic_tiles.source.tsv.gz")
    parser.add_argument("--audit", type=Path, default=DEFAULT_ROOT / "output/hungarian_hu_hu_ispell_classic_tiles.audit.json")
    parser.add_argument("--excluded", type=Path, default=DEFAULT_ROOT / "output/hungarian_hu_hu_ispell_classic_tiles.excluded.tsv.gz")
    parser.add_argument("--overrides", type=Path, default=DEFAULT_ROOT / "classic_tile_segmentation_overrides.tsv")
    parser.add_argument("--lemmas", type=Path, default=DEFAULT_ROOT / "output/definitions/hu/surface-lemma/v1")
    parser.add_argument("--ispell-aff", type=Path, default=DEFAULT_ROOT / ".cache/sources/hu_HU.aff")
    parser.add_argument("--ispell-dic", type=Path, default=DEFAULT_ROOT / ".cache/sources/hu_HU.dic")
    parser.add_argument(
        "--supplemental-boundaries",
        type=Path,
        default=DEFAULT_ROOT / "csi_sza_classic_tile_boundaries.txt",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    audit = generate(
        args.input,
        args.runtime,
        args.source,
        args.audit,
        args.excluded,
        args.overrides,
        args.lemmas,
        args.ispell_aff,
        args.ispell_dic,
        args.supplemental_boundaries,
    )
    print(
        f"Generated {audit['output']['acceptedEntries']} canonical Hungarian tile entries; "
        f"excluded {audit['excludedEntries']}."
    )


if __name__ == "__main__":
    main()
