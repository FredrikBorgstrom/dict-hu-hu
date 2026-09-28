"""Pinned, exact-surface release scope for the September plural-possession review.

This narrows the generator's eligibility; it never grants acceptance by itself.
Missing or corrupt review data must stop a build or promotion.
"""

from dataclasses import dataclass
import gzip
import hashlib
import json
from pathlib import Path


REVIEW_DIR = Path(__file__).resolve().parent / "plural_possessive_review"
DEFERRED_REASON = "pending_plural_possessive_review"


@dataclass(frozen=True)
class PossessiveReview:
    scope: frozenset[str]
    supported: frozenset[str]
    deferred: frozenset[str]
    provenance: dict

    def require_publishable(self, words):
        held = self.deferred.intersection(words)
        if held:
            raise ValueError(f"Candidate contains {len(held):,} deferred plural possessions; "
                             f"rebuild with the current review policy. Examples: {sorted(held)[:5]}")


def load_possessive_review(directory=REVIEW_DIR):
    manifest_path = directory / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported plural-possession review schema")

    def read_words(filename, count_key):
        compressed = (directory / filename).read_bytes()
        expected = manifest["files"][filename]
        if hashlib.sha256(compressed).hexdigest() != expected["sha256"]:
            raise ValueError(f"Plural-possession review checksum mismatch: {filename}")
        raw = gzip.decompress(compressed)
        if hashlib.sha256(raw).hexdigest() != expected["content_sha256"]:
            raise ValueError(f"Plural-possession review content mismatch: {filename}")
        words = raw.decode("utf-8").splitlines()
        if len(words) != manifest[count_key] or words != sorted(set(words)) or any(not w for w in words):
            raise ValueError(f"Invalid plural-possession review inventory: {filename}")
        return frozenset(words)

    scope = read_words("scope.txt.gz", "scope_count")
    supported = read_words("supported.txt.gz", "supported_count")
    if not supported <= scope or len(scope - supported) != manifest["deferred_count"]:
        raise ValueError("Plural-possession review does not partition its scope")
    provenance = {"manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                  "review_date": manifest["review_date"], "scope_count": len(scope),
                  "supported_count": len(supported), "deferred_count": len(scope - supported),
                  "baseline_commit": manifest["baseline_commit"],
                  "policy": "Hold every scoped surface without pinned reference support; no new acceptance override"}
    return PossessiveReview(scope, supported, scope - supported, provenance)
