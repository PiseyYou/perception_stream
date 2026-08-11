"""Deterministic, server-side anonymous review state for A/B shadow runs."""
from __future__ import annotations

import hashlib
import random
import secrets
import time
from collections.abc import Mapping
from typing import Any

MAX_SAMPLES = 30
MIN_VALID_VOTES = 24
CHOICES = frozenset({"X better", "Y better", "tie", "undecidable"})


def _seed_value(seed: str) -> int:
    return int.from_bytes(hashlib.sha256(seed.encode("utf-8")).digest(), "big")


def create_review(common_manifest: Mapping[str, Any], *, seed: str) -> dict[str, Any]:
    """Create reproducible private mapping; never return it from public APIs."""
    images = common_manifest.get("images")
    if not isinstance(images, list):
        raise ValueError("common-success manifest images are required")
    candidates = [item for item in images if isinstance(item, dict) and isinstance(item.get("path"), str) and isinstance(item.get("branches"), dict) and {"A", "B"}.issubset(item["branches"])]
    if not candidates:
        raise ValueError("common-success manifest has no reviewable images")
    ordered = sorted(candidates, key=lambda item: item["path"])
    chosen = ordered if len(ordered) <= MAX_SAMPLES else random.Random(_seed_value(seed)).sample(ordered, MAX_SAMPLES)
    chosen.sort(key=lambda item: item["path"])
    private_samples: dict[str, dict[str, Any]] = {}
    samples: list[dict[str, str]] = []
    for index, item in enumerate(chosen, start=1):
        sample_id = f"s{index:03d}"
        x_branch = "A" if _seed_value(f"{seed}:{item['path']}") & 1 else "B"
        private_samples[sample_id] = {"path": item["path"], "branches": item["branches"], "X": x_branch, "Y": "B" if x_branch == "A" else "A"}
        samples.append({"sample_id": sample_id, "left": "X", "right": "Y"})
    return {
        "version": 1,
        "seed_sha256": hashlib.sha256(seed.encode("utf-8")).hexdigest(),
        "samples": samples,
        "private_samples": private_samples,
        "capabilities": {},
        "submissions": {},
        "decision": {"status": "pending", "valid_votes": 0, "candidate_wins": 0, "baseline_wins": 0},
    }


def public_payload(run_id: str, review: Mapping[str, Any]) -> dict[str, Any]:
    samples = review.get("samples")
    if not isinstance(samples, list):
        raise ValueError("invalid review state")
    return {"run_id": run_id, "samples": [{"sample_id": item["sample_id"], "left": "X", "right": "Y"} for item in samples if isinstance(item, dict)]}


def _decision(review: dict[str, Any]) -> dict[str, Any]:
    private_samples = review.get("private_samples", {})
    candidate_wins = baseline_wins = 0
    for submission in review.get("submissions", {}).values():
        for sample_id, choice in submission.get("answers", {}).items():
            if choice not in {"X better", "Y better"} or sample_id not in private_samples:
                continue
            winning_branch = private_samples[sample_id]["X" if choice == "X better" else "Y"]
            if winning_branch == "B":
                candidate_wins += 1
            else:
                baseline_wins += 1
    valid = candidate_wins + baseline_wins
    status = "no_decision"
    if valid >= MIN_VALID_VOTES:
        margin = (candidate_wins - baseline_wins) / valid
        if margin >= 0.20:
            status = "candidate_wins"
        elif margin <= -0.20:
            status = "baseline_wins"
    return {"status": status, "valid_votes": valid, "candidate_wins": candidate_wins, "baseline_wins": baseline_wins}


def issue_reviewer_capability(review: dict[str, Any]) -> str:
    """Mint one owner-issued, single-use reviewer capability; persist only its hash."""
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    review.setdefault("capabilities", {})[digest] = {"used": False}
    return token


def validate_reviewer_capability(review: Mapping[str, Any], capability: str, *, allow_used: bool = False) -> str:
    if not isinstance(capability, str) or len(capability) < 32:
        raise ValueError("valid reviewer capability is required")
    digest = hashlib.sha256(capability.encode("utf-8")).hexdigest()
    state = review.get("capabilities", {}).get(digest)
    if not isinstance(state, dict):
        raise ValueError("invalid reviewer capability")
    if state.get("used") and not allow_used:
        raise ValueError("reviewer already submitted")
    return digest


def consume_asset_quota(review: dict[str, Any], capability_digest: str, *, now: float | None = None) -> None:
    """Bound costly overlay renders per capability without keeping a global identity."""
    timestamp = time.time() if now is None else now
    capability = review.get("capabilities", {}).get(capability_digest)
    if not isinstance(capability, dict):
        raise ValueError("invalid reviewer capability")
    recent = [value for value in capability.get("asset_requests", []) if isinstance(value, (int, float)) and timestamp - value < 60]
    if len(recent) >= 120:
        raise ValueError("review asset rate limit exceeded")
    recent.append(timestamp)
    capability["asset_requests"] = recent


def submit_review(review: dict[str, Any], capability: str, answers: Mapping[str, str]) -> dict[str, Any]:
    capability_digest = validate_reviewer_capability(review, capability)
    private_samples = review.get("private_samples")
    if not isinstance(private_samples, dict) or not isinstance(answers, Mapping):
        raise ValueError("invalid review submission")
    normalized: dict[str, str] = {}
    for sample_id, choice in answers.items():
        if sample_id not in private_samples or choice not in CHOICES:
            raise ValueError("invalid review answer")
        normalized[str(sample_id)] = str(choice)
    if set(normalized) != set(private_samples):
        raise ValueError("every review sample requires one answer")
    review["capabilities"][capability_digest]["used"] = True
    review.setdefault("submissions", {})[capability_digest] = {"answers": normalized}
    review["decision"] = _decision(review)
    return dict(review["decision"])


def reveal(review: Mapping[str, Any]) -> dict[str, Any]:
    decision = review.get("decision")
    if not isinstance(decision, dict) or decision.get("status") == "pending":
        return {"allowed": False}
    private_samples = review.get("private_samples")
    if not isinstance(private_samples, dict):
        raise ValueError("invalid review state")
    return {"allowed": True, "decision": dict(decision), "mapping": {sample_id: {"X": item["X"], "Y": item["Y"]} for sample_id, item in private_samples.items()}}
