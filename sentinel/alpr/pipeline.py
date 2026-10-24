"""
sentinel/alpr/pipeline.py
==========================
ALPR pipeline abstraction.

Supports two modes:
  - "sumo": Sightings come from the SUMO TraCI injector (perfect accuracy).
            The pipeline is effectively a pass-through + voter bypass.
  - "video": Real camera frames are processed by YOLOv8 + PaddleOCR.
             The multi-frame voter denoises the read before emitting.

In both modes the output is a committed (plate, confidence) pair
that is pushed to the event bus by the caller (sumo_injector or video_reader).

This module handles the "video" path. YOLOv8 and PaddleOCR are imported
lazily so the package loads even when they are not installed (SUMO mode).
"""

import logging
from typing import Optional, Tuple
import numpy as np

from sentinel.alpr.voter import VoterPool, normalize_plate
from sentinel.config import ALPR_MODE, OCR_CONFIDENCE_MIN

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy import helpers (only needed in video mode)
# ---------------------------------------------------------------------------

_yolo_model = None
_ocr_model = None


def _get_yolo():
    global _yolo_model
    if _yolo_model is None:
        try:
            from ultralytics import YOLO
            _yolo_model = YOLO("yolov8n.pt")   # nano - fastest, ~4MB
            logger.info("[ALPR] YOLOv8-nano loaded")
        except ImportError:
            raise RuntimeError(
                "YOLOv8 not installed. Run: pip install ultralytics\n"
                "Or use ALPR_MODE='sumo' for simulation-only mode."
            )
    return _yolo_model


def _get_ocr():
    global _ocr_model
    if _ocr_model is None:
        try:
            from paddleocr import PaddleOCR
            _ocr_model = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
            logger.info("[ALPR] PaddleOCR loaded")
        except ImportError:
            raise RuntimeError(
                "PaddleOCR not installed. Run: pip install paddleocr\n"
                "Or use ALPR_MODE='sumo' for simulation-only mode."
            )
    return _ocr_model


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

class ALPRPipeline:
    """
    Full ALPR pipeline: detection -> OCR -> voter -> committed plate.

    Args:
        mode:     "sumo" or "video" (overrides config default).
        voter_pool: Shared VoterPool instance (optional, creates own if None).
    """

    def __init__(self, mode: str = ALPR_MODE, voter_pool: Optional[VoterPool] = None):
        self.mode = mode
        self.voter_pool = voter_pool or VoterPool()
        logger.info(f"[ALPRPipeline] Initialized in mode='{mode}'")

    # ------------------------------------------------------------------
    # SUMO mode (synthetic path)
    # ------------------------------------------------------------------

    def process_sumo_sighting(
        self,
        vehicle_id: str,
        camera_id: str,
        confidence: float = 1.0,
    ) -> Tuple[Optional[str], float]:
        """
        SUMO mode: vehicle_id is already the plate (exact).
        Bypass voter (no noise to denoise).

        Returns:
            (committed_plate, confidence) or (None, 0.0) if filtered.
        """
        plate = normalize_plate(vehicle_id)
        if not plate:
            return None, 0.0
        return plate, confidence

    # ------------------------------------------------------------------
    # Video mode (real camera path)
    # ------------------------------------------------------------------

    def process_frame(
        self,
        frame: np.ndarray,
        camera_id: str,
    ) -> Tuple[Optional[str], float]:
        """
        Video mode: run YOLOv8 plate detection + PaddleOCR + voter.

        Returns:
            (committed_plate, confidence) once the voter window is full,
            or (None, 0.0) if still accumulating.
        """
        plate_crop = self._detect_plate(frame)
        if plate_crop is None:
            return None, 0.0

        plate_text, ocr_conf = self._run_ocr(plate_crop)
        if plate_text is None or ocr_conf < OCR_CONFIDENCE_MIN:
            return None, 0.0

        committed = self.voter_pool.submit(camera_id, plate_text, ocr_conf)
        if committed is None:
            return None, 0.0   # voter window not yet full

        return committed, ocr_conf

    def _detect_plate(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """
        Run YOLOv8 on a frame and return the cropped plate region.
        Returns None if no plate detected with sufficient confidence.
        """
        model = _get_yolo()
        results = model(frame, verbose=False)
        for result in results:
            for box in result.boxes:
                conf = float(box.conf[0])
                if conf < 0.45:
                    continue
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                crop = frame[y1:y2, x1:x2]
                if crop.size > 0:
                    return crop
        return None

    def _run_ocr(self, crop: np.ndarray) -> Tuple[Optional[str], float]:
        """
        Run PaddleOCR on a plate crop. Returns (text, confidence).
        """
        ocr = _get_ocr()
        result = ocr.ocr(crop, cls=True)
        if not result or not result[0]:
            return None, 0.0

        # Collect all text lines above confidence threshold
        texts = []
        confs = []
        for line in result[0]:
            text, conf = line[1][0], line[1][1]
            texts.append(text)
            confs.append(conf)

        if not texts:
            return None, 0.0

        combined = "".join(texts).upper().replace(" ", "")
        avg_conf = sum(confs) / len(confs)
        return combined, avg_conf
