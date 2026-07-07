from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

from lite_ml_service.domain.entities import BoundingBox, FaceEmbedding
from lite_ml_service.domain.interfaces import EmbeddingProvider

logger = logging.getLogger(__name__)

HEIC_EXTENSIONS = {".heic", ".heif"}


def _decode_image(image_bytes: bytes) -> np.ndarray:
    header = image_bytes[:12]
    is_heic = b"ftyp" in header or b"mif1" in header or b"heic" in header
    if is_heic:
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(image_bytes))
            img = img.convert("RGB")
            return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        except ImportError:
            logger.warning("pillow-heif not installed, cannot decode HEIC image")
            raise RuntimeError("HEIC support requires 'pillow-heif' package")
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)

MODEL_CACHE = Path.home() / ".cache" / "immich_ml"
HF_BASE = "https://huggingface.co/immich-app"


def _ensure_model_files(model_name: str) -> Path:
    model_dir = MODEL_CACHE / model_name
    det_candidates = [model_dir / "det_10g.onnx", model_dir / "detection" / "model.onnx"]
    rec_candidates = [model_dir / "w600k_r50.onnx", model_dir / "recognition" / "model.onnx"]

    all_found = any(p.exists() for p in det_candidates) and any(p.exists() for p in rec_candidates)
    if all_found:
        logger.info("Models already cached at %s", model_dir)
        return model_dir

    MODEL_CACHE.mkdir(parents=True, exist_ok=True)

    _try_extract_local_zip(model_name, model_dir)

    all_found = any(p.exists() for p in det_candidates) and any(p.exists() for p in rec_candidates)
    if all_found:
        return model_dir

    det_dest = model_dir / "detection" / "model.onnx"
    rec_dest = model_dir / "recognition" / "model.onnx"

    logger.info("Downloading detection model from HuggingFace...")
    _download_file(f"{HF_BASE}/{model_name}/resolve/main/detection/model.onnx", det_dest)
    logger.info("Downloading recognition model from HuggingFace...")
    _download_file(f"{HF_BASE}/{model_name}/resolve/main/recognition/model.onnx", rec_dest)

    logger.info("Models downloaded to %s", model_dir)
    return model_dir


def _try_extract_local_zip(model_name: str, dest: Path) -> None:
    import zipfile

    local_zip = Path(f"C:/Users/SHO/Downloads/Setups/{model_name}.zip")
    if not local_zip.exists():
        return
    logger.info("Found local zip at %s, extracting...", local_zip)
    with zipfile.ZipFile(local_zip, "r") as zf:
        zf.extractall(dest)
    logger.info("Extracted to %s", dest)


def _download_file(url: str, dest: Path) -> None:
    import requests

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return
    r = requests.get(url, stream=True, timeout=300)
    if r.status_code != 200:
        raise RuntimeError(f"Failed to download {url}: HTTP {r.status_code}")
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)


class InsightFaceEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model_name: str = "buffalo_s", detection_threshold: float = 0.5, ctx_id: int = 0) -> None:
        self._model_name = model_name
        self._detection_threshold = detection_threshold
        self._ctx_id = ctx_id
        self._detector = None
        self._recognizer = None
        self._loaded = False

    def _ensure_model(self):
        if self._loaded:
            return

        model_dir = _ensure_model_files(self._model_name)

        from insightface.model_zoo.arcface_onnx import ArcFaceONNX
        from insightface.model_zoo.retinaface import RetinaFace
        from insightface.utils.face_align import norm_crop

        self._norm_crop = norm_crop

        det_path = model_dir / "det_10g.onnx"
        if not det_path.exists():
            det_path = model_dir / "detection" / "model.onnx"
        if not det_path.exists():
            raise FileNotFoundError(f"Detection model not found in {model_dir}")

        rec_path = model_dir / "w600k_r50.onnx"
        if not rec_path.exists():
            rec_path = model_dir / "recognition" / "model.onnx"
        if not rec_path.exists():
            raise FileNotFoundError(f"Recognition model not found in {model_dir}")

        logger.info("Loading detection model: %s", det_path)
        det_session = ort.InferenceSession(
            str(det_path),
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )
        self._detector = RetinaFace(session=det_session)
        self._detector.prepare(ctx_id=self._ctx_id, det_thresh=self._detection_threshold, input_size=(640, 640))

        logger.info("Loading recognition model: %s", rec_path)
        rec_session = ort.InferenceSession(
            str(rec_path),
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )
        self._recognizer = ArcFaceONNX(str(rec_path), session=rec_session)

        self._loaded = True
        logger.info("Models loaded successfully")

    def detect_and_embed(self, image_bytes: bytes) -> list[FaceEmbedding]:
        self._ensure_model()

        img_array = _decode_image(image_bytes)

        bboxes, landmarks = self._detector.detect(img_array)
        if len(bboxes) == 0:
            return []

        embeddings = np.array([self._recognizer.get_feat(self._norm_crop(img_array, lm))[0] for lm in landmarks])

        results: list[FaceEmbedding] = []
        for i, bbox in enumerate(bboxes):
            b = bbox.astype(int)
            embedding = embeddings[i].astype(float).tolist()
            results.append(
                FaceEmbedding(
                    image_path="",
                    embedding=embedding,
                    bbox=BoundingBox(x1=int(b[0]), y1=int(b[1]), x2=int(b[2]), y2=int(b[3])),
                    face_score=float(bbox[4]),
                )
            )

        logger.debug("Detected %d face(s) in image", len(results))
        return results
