"""
sentinel/alpr/voter.py
=======================
Multi-frame voter with RapidFuzz fuzzy matching.

Collects OCR reads across VOTE_WINDOW consecutive frames and
returns the consensus plate string. Handles common Indian plate
OCR confusion pairs (0/D, 1/I, 8/B, 5/S).

In SUMO mode this is bypassed (plates are already exact).
In real-camera mode this is the last denoising layer before a
plate string is committed to the event bus.
"""

import logging
from collections import defaultdict
from typing import Optional

from rapidfuzz import fuzz
from sentinel.config import VOTE_WINDOW, FUZZY_THRESHOLD, OCR_SUBSTITUTIONS

logger = logging.getLogger(__name__)


def normalize_plate(plate: str) -> str:
    """
    Normalize an Indian plate string:
    - Uppercase
    - Remove spaces and hyphens (e.g. 'UP 32 AB 1234' -> 'UP32AB1234')
    """
    return plate.upper().replace(" ", "").replace("-", "").strip()


def fuzzy_match(candidate: str, reference: str) -> float:
    """
    Return a fuzzy similarity score (0-100) between two plate strings
    using character-level token ratio, with OCR substitution tolerance.
    """
    base_score = fuzz.ratio(candidate, reference)
    if base_score >= FUZZY_THRESHOLD:
        return base_score

    # Try substituting known OCR confusion chars
    best = base_score
    for src, dst in OCR_SUBSTITUTIONS:
        mutated = candidate.replace(src, dst)
        score = fuzz.ratio(mutated, reference)
        if score > best:
            best = score
    return best


class PlateVoter:
    """
    Per-camera multi-frame voter.

    Collects (plate, confidence) pairs across frames for a given
    camera/vehicle. Once VOTE_WINDOW frames have accumulated,
    returns the highest-confidence consensus plate string.

    Usage:
        voter = PlateVoter(camera_id="J_042")
        result = voter.vote("UP32AB1234", confidence=0.91)
        # returns committed plate string or None if window not full yet
    """

    def __init__(self, camera_id: str, window: int = VOTE_WINDOW):
        self.camera_id = camera_id
        self.window = window
        self._buffer: list[tuple[str, float]] = []  # (plate, confidence)

    def vote(self, plate: str, confidence: float) -> Optional[str]:
        """
        Add a frame read and return the consensus plate if the window is full,
        otherwise return None.
        """
        plate = normalize_plate(plate)
        self._buffer.append((plate, confidence))

        if len(self._buffer) < self.window:
            return None

        committed = self._commit()
        self._buffer.clear()
        return committed

    def _commit(self) -> str:
        """
        Pick the plate that:
        1. Appears most frequently.
        2. Has the highest total confidence among tied candidates.
        """
        score_map: dict[str, float] = defaultdict(float)
        count_map: dict[str, int] = defaultdict(int)

        for plate, conf in self._buffer:
            # Check if this plate fuzzy-matches an already-seen candidate
            matched = False
            for existing in list(score_map.keys()):
                if fuzzy_match(plate, existing) >= FUZZY_THRESHOLD:
                    score_map[existing] += conf
                    count_map[existing] += 1
                    matched = True
                    break
            if not matched:
                score_map[plate] += conf
                count_map[plate] += 1

        # Sort: highest count first, break ties by highest confidence sum
        best = max(score_map.keys(), key=lambda p: (count_map[p], score_map[p]))
        logger.debug(
            f"[Voter:{self.camera_id}] Committed '{best}' "
            f"(count={count_map[best]}, conf_sum={score_map[best]:.2f})"
        )
        return best

    def reset(self):
        """Clear accumulated frames."""
        self._buffer.clear()


class VoterPool:
    """
    Manages one PlateVoter per camera. Voters are created lazily.

    Usage:
        pool = VoterPool()
        result = pool.submit(camera_id="J_042", plate="UP32AB1234", confidence=0.87)
    """

    def __init__(self, window: int = VOTE_WINDOW):
        self.window = window
        self._voters: dict[str, PlateVoter] = {}

    def submit(self, camera_id: str, plate: str, confidence: float) -> Optional[str]:
        if camera_id not in self._voters:
            self._voters[camera_id] = PlateVoter(camera_id, self.window)
        return self._voters[camera_id].vote(plate, confidence)

    def reset_camera(self, camera_id: str):
        if camera_id in self._voters:
            self._voters[camera_id].reset()
