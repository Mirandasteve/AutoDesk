"""
AutoDesk - DistilBERT ticket category predictor
===============================================

The AI layer of the helpdesk. Turns a free-text ticket description into one of
the six SRS categories.

Design notes
------------
* **Loaded once at application start.** The Flask application factory calls
  :func:`load_model` during startup, so the ~260 MB checkpoint is read from disk
  and moved to CPU/GPU memory exactly once. Requests then re-use the warm
  in-memory model. Reloading per request would add seconds of latency and is
  explicitly avoided (SRS section 9 / 32).
* **Thread safety.** Torch inference is run under a lock because the Flask dev
  server handles requests on a thread pool and a shared model must not be
  entered concurrently.
* **No external API.** Everything runs locally (SRS section 9).
* **Graceful degradation.** If the checkpoint is missing or corrupt, the
  predictor logs loudly and switches to a clearly separated keyword classifier
  (see :class:`KeywordClassifier`) instead of 500-ing every ticket submission.

Checkpoint layout (``app/ml/saved_model/``)::

    config.json            transformers model config (num_labels = 6)
    model.safetensors      fine-tuned DistilBERT weights
    tokenizer.json         fast tokenizer
    vocab.txt              WordPiece vocabulary
    label_mappings.json    id <-> category name
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from huggingface_hub import snapshot_download

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical label contract - must match backend/app/ml/label_mappings.json
# ---------------------------------------------------------------------------
CATEGORIES: Tuple[str, ...] = ("Software", "Hardware", "Network", "Login", "VPN", "Access")
DEFAULT_ID_TO_LABEL: Dict[int, str] = {index: name for index, name in enumerate(CATEGORIES)}
NUM_LABELS = len(CATEGORIES)

MODEL_NAME = "distilbert/distilbert-base-uncased-finetuned-autodesk"


# ---------------------------------------------------------------------------
# Development fallback (never used once the checkpoint exists)
# ---------------------------------------------------------------------------
#: Hand-written keyword anchors per category. This exists **only** so a fresh
#: clone can run the full ticket flow before `ml/train.py` has been executed.
#: The response payload always reports ``source="keyword-fallback"`` so the
#: distinction can never be mistaken for a real model prediction.
KEYWORD_ANCHORS: Dict[str, List[str]] = {
    "Software": [
        "word", "excel", "outlook", "teams", "adobe", "acrobat", "autocad",
        "revit", "visual studio", "vs code", "vscode", "chrome", "browser",
        "firefox", "zoom", "powerpoint", "slack", "notion", "antivirus",
        "windows update", "application", "app ", "software", "program",
        "installation", "macro", "license", "licence", "crash", "python",
        "matlab", "sublime", "editor", "pdf", "spreadsheet", "update",
    ],
    "Hardware": [
        "keyboard", "monitor", "screen", "laptop", "desktop", "mouse",
        "printer", "scanner", "battery", "hard disk", "hard drive", "usb",
        "headset", "webcam", "microphone", "dock", "docking", "fan", "speaker",
        "touchpad", "screen", "device", "charger", "adapter", "cpu", "gpu",
        "memory", "ssd", "lens", "panel", "cable", "port", "overheat",
    ],
    "Network": [
        "wifi", "wi-fi", "wireless", "ethernet", "router", "switch", "dns",
        "ip address", "latency", "bandwidth", "internet", "network drive",
        "network share", "server name", "ping", "intranet", "access point",
        "network cable", "network adapter", "disconnected", "packet loss",
        "proxy", "gateway", "local network", "lan", "connection",
    ],
    "Login": [
        "password", "log in", "login", "sign in", "signin", "credential",
        "account locked", "locked out", "two factor", "two-factor", "2fa",
        "mfa", "authentication", "authenticate", "username", "reset email",
        "account suspended", "single sign on", "sso", "domain account",
        "forgot", "otp", "verification code", "pin", "auth error",
    ],
    "VPN": [
        "vpn", "tunnel", "virtual private", "remote access", "gateway",
        "disconnecting", "reconnect", "certificate", "profile",
        "error 809", "client", "ipsec", "ssl", "split tunnel",
        "remote worker", "work from home", "vpn server", "portal",
        "session", "always on", "global protect", "fortinet", "anyconnect",
    ],
    "Access": [
        "permission", "access", "authorised", "authorized", "privilege",
        "rights", "read only", "read-only", "write access", "approve",
        "approval", "group membership", "role", "forbidden", "denied",
        "entitled", "licence to", "license to", "sharepoint site",
        "confidential", "restricted", "grant", "revoke", "owner",
        "team membership", "admin right", "separation of duties",
    ],
}

_WORD = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    """a an and are as at be but by can do for from has have how i in is it its my
    me no not of on or our so that the their there they this to was we what when
    where which who why will with would you your""".split()
)


class KeywordClassifier:
    """
    Deterministic development-only classifier.

    Scores a description by counting how many distinct keyword anchors from
    each category appear, normalising by the description length, and returning
    the arg-max. It is deliberately simple and clearly separated from the
    DistilBERT code path so the two are never confused.
    """

    source = "keyword-fallback"

    def predict(self, text: str) -> Dict[str, Any]:
        tokens = set(_WORD.findall((text or "").lower()))
        significant = {t for t in tokens if t not in _STOPWORDS and len(t) > 2}

        scores: Dict[str, float] = {}
        for category, anchors in KEYWORD_ANCHORS.items():
            hits = 0
            for anchor in anchors:
                anchor = anchor.strip()
                if not anchor:
                    continue
                if " " in anchor:
                    if anchor in (text or "").lower():
                        hits += 2  # multi-word anchors are more specific
                elif anchor in significant:
                    hits += 1
            scores[category] = float(hits)

        best = max(scores, key=lambda c: scores[c])
        total = sum(scores.values())
        if scores[best] == 0:
            # No signal at all - return a deliberately low-confidence guess.
            return {
                "category": "Software",
                "confidence": 0.0,
                "source": self.source,
                "scores": scores,
                "is_fallback": True,
                "model": None,
            }

        # Confidence = the winning category's share of total hits, damped so a
        # single weak keyword can never look authoritative.
        share = scores[best] / total
        magnitude = min(1.0, scores[best] / 3.0)
        confidence = round(0.35 + 0.5 * share * magnitude, 4)

        return {
            "category": best,
            "confidence": confidence,
            "source": self.source,
            "scores": scores,
            "is_fallback": True,
            "model": None,
        }


# ---------------------------------------------------------------------------
# DistilBERT predictor
# ---------------------------------------------------------------------------
class TicketClassifier:
    """
    Loads the fine-tuned DistilBERT checkpoint once and serves predictions.

    Usage::

        classifier = TicketClassifier.from_env()
        classifier.predict("My VPN keeps disconnecting.")
    """

    def __init__(
        self,
        model_path: str,
        max_length: int = 256,
        allow_fallback: bool = True,
        device: Optional[str] = None,
    ) -> None:
        self.model_path = model_path
        self.max_length = max_length
        self.allow_fallback = allow_fallback
        self.device_name = device or ("cuda" if _cuda_available() else "cpu")

        self.model = None
        self.tokenizer = None
        self.id_to_label: Dict[int, str] = dict(DEFAULT_ID_TO_LABEL)
        self._fallback = KeywordClassifier()
        self._lock = threading.Lock()
        self._load_error: Optional[str] = None
        self._predict_calls = 0
        self._fallback_calls = 0

     # Lightweight deployment mode for memory-limited instances such as
        # Render Free. When enabled, do not download or load DistilBERT; use
        # the explicitly identified keyword fallback instead.
        skip_model_load = os.getenv("ML_SKIP_MODEL_LOAD", "False").strip().lower() in (
            "1", "true", "yes", "on"
        )
        if skip_model_load:
            self._load_error = "Model loading skipped by ML_SKIP_MODEL_LOAD."
            logger.warning("DistilBERT loading skipped. Using keyword fallback.")
        else:
            self.load()

    # -- loading ----------------------------------------------------------
    def load(self) -> bool:
        """Load the local checkpoint or download it from Hugging Face."""
        try:
            from transformers import AutoTokenizer, DistilBertForSequenceClassification
            import torch

            if os.path.isdir(self.model_path):
                resolved_model_path = self.model_path
            else:
                logger.info(
                    "Downloading model from Hugging Face: %s",
                    self.model_path,
                )
                resolved_model_path = snapshot_download(
                    repo_id=self.model_path,
                    repo_type="model",
                )

            logger.info(
                "Loading DistilBERT checkpoint from %s",
                resolved_model_path,
            )
            self.tokenizer = AutoTokenizer.from_pretrained(resolved_model_path)
            model = DistilBertForSequenceClassification.from_pretrained(
                resolved_model_path
            )

            self.model_path = resolved_model_path
            device = torch.device(self.device_name)
            model.to(device)
            model.eval()
            self.model = model

            self.id_to_label = self._read_label_mappings()
            logger.info(
                "DistilBERT ready on %s - labels: %s",
                self.device_name,
                sorted(self.id_to_label.values()),
            )
            self._load_error = None
            return True

        except Exception as exc:
            self.model = None
            self.tokenizer = None
            self._load_error = f"{type(exc).__name__}: {exc}"
            logger.exception("Could not load DistilBERT checkpoint (%s)", exc)
            if not self.allow_fallback:
                logger.error(
                    "ML_ALLOW_FALLBACK is disabled - predictions will fail."
                )
            return False

    def _read_label_mappings(self) -> Dict[int, str]:
        """
        Prefer the checkpoint's own ``label_mappings.json``.

        The order baked into the classification head is authoritative; if the
        file is missing we keep the SRS order, which is what ``train.py`` uses.
        """
        for candidate in (
            os.path.join(self.model_path, "label_mappings.json"),
            os.path.join(os.path.dirname(self.model_path), "label_mappings.json"),
        ):
            if not os.path.exists(candidate):
                continue
            try:
                with open(candidate, "r", encoding="utf-8") as handle:
                    raw = json.load(handle)
                mapping = {int(k): str(v) for k, v in raw["id_to_label"].items()}
                if set(mapping.values()) == set(CATEGORIES):
                    logger.info("Label mappings loaded from %s", candidate)
                    return mapping
                logger.warning(
                    "%s does not describe the six SRS categories; ignoring it.", candidate
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Could not read %s (%s)", candidate, exc)
        logger.info("Using the built-in SRS label order.")
        return dict(DEFAULT_ID_TO_LABEL)

    # -- properties -------------------------------------------------------
    @property
    def is_ready(self) -> bool:
        """``True`` when the real DistilBERT model is loaded."""
        return self.model is not None and self.tokenizer is not None

    @property
    def using_fallback(self) -> bool:
        return not self.is_ready

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error

    @property
    def model_name(self) -> str:
        return MODEL_NAME if self.is_ready else "keyword-fallback"

    # -- inference --------------------------------------------------------
    def predict(self, text: str) -> Dict[str, Any]:
        """
        Classify *text* into one of the six categories.

        Returns::

            {"category": "Network", "confidence": 0.93, "source": "distilbert", ...}

        Errors inside the model are caught and converted into a fallback
        prediction so that a ticket is never lost because of an ML glitch.
        """
        text = (text or "").strip()
        if not text:
            return {
                "category": None,
                "confidence": 0.0,
                "source": "empty",
                "is_fallback": False,
                "model": self.model_name,
                "error": "Empty description supplied to the classifier.",
            }

        if not self.is_ready:
            self._fallback_calls += 1
            if not self.allow_fallback:
                return {
                    "category": None,
                    "confidence": 0.0,
                    "source": "unavailable",
                    "is_fallback": False,
                    "model": None,
                    "error": self._load_error or "ML model unavailable",
                }
            return self._fallback.predict(text)

        try:
            import torch

            with self._lock:
                encoded = self.tokenizer(
                    text,
                    truncation=True,
                    padding=True,
                    max_length=self.max_length,
                    return_tensors="pt",
                )
                device = torch.device(self.device_name)
                encoded = {k: v.to(device) for k, v in encoded.items()}
                with torch.no_grad():
                    logits = self.model(**encoded).logits
                    probabilities = torch.softmax(logits, dim=-1)[0]

            index = int(torch.argmax(probabilities).item())
            confidence = float(probabilities[index].item())
            category = self.id_to_label.get(index, CATEGORIES[min(index, 5)])

            self._predict_calls += 1
            return {
                "category": category,
                "confidence": round(confidence, 4),
                "confidence_pct": round(confidence * 100, 2),
                "label_id": index,
                "source": "distilbert",
                "is_fallback": False,
                "model": self.model_name,
                "top_k": self._top_k(probabilities),
            }

        except Exception as exc:
            logger.exception("DistilBERT inference failed: %s", exc)
            self._fallback_calls += 1
            if not self.allow_fallback:
                return {
                    "category": None,
                    "confidence": 0.0,
                    "source": "error",
                    "is_fallback": False,
                    "model": MODEL_NAME,
                    "error": "Model inference failed",
                }
            result = self._fallback.predict(text)
            result["error"] = f"Fell back to keyword classification: {type(exc).__name__}"
            return result

    def _top_k(self, probabilities, k: int = 3) -> List[Dict[str, Any]]:
        """Return the top-k classes with their probabilities."""
        pairs = sorted(
            zip(self.id_to_label.items(), probabilities.tolist()),
            key=lambda pair: pair[1],
            reverse=True,
        )
        return [
            {
                "category": name,
                "confidence": round(float(score), 4),
                "confidence_pct": round(float(score) * 100, 2),
            }
            for (_index, name), score in pairs[:k]
        ]

    def health(self) -> Dict[str, Any]:
        """Diagnostics for ``GET /api/health`` and the admin ML panel."""
        return {
            "ready": self.is_ready,
            "using_fallback": self.using_fallback,
            "source": "distilbert" if self.is_ready else "keyword-fallback",
            "model": self.model_name,
            "base_model": "distilbert/distilbert-base-uncased",
            "model_path": self.model_path,
            "device": self.device_name,
            "max_length": self.max_length,
            "num_labels": NUM_LABELS,
            "labels": list(CATEGORIES),
            "predictions": self._predict_calls,
            "fallback_predictions": self._fallback_calls,
            "load_error": self._load_error,
            "allow_fallback": self.allow_fallback,
        }

    def warmup(self, rounds: int = 1) -> Dict[str, Any]:
        """
        Run a few throwaway inferences so the first real request is fast.

        Called once from the application factory after the model loads - the
        first torch forward pass allocates buffers and is noticeably slower
        than the rest.
        """
        if not self.is_ready:
            return {"warmed": False, "reason": "model not loaded"}
        started = time.time()
        for _ in range(max(1, rounds)):
            self.predict("warmup: my laptop cannot connect to the office wifi")
        return {
            "warmed": True,
            "rounds": max(1, rounds),
            "seconds": round(time.time() - started, 3),
        }


def _cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:  # pragma: no cover - torch always present in this project
        return False


# ---------------------------------------------------------------------------
# Module-level singleton - the one instance the Flask app uses
# ---------------------------------------------------------------------------
_CLASSIFIER: Optional[TicketClassifier] = None


def _backend_root() -> str:
    """
    Locate the ``backend/`` directory regardless of the current working
    directory or how the module was imported.

    Walks up from this file until it finds the directory that also contains
    ``config.py``, which is the project's backend root marker.
    """
    current = os.path.dirname(os.path.abspath(__file__))  # .../backend/app/ml
    for _ in range(6):
        if os.path.isfile(os.path.join(current, "config.py")):
            return current
        parent = os.path.dirname(current)
        if parent == current:  # reached the filesystem root
            break
        current = parent
    # Fallback: .../backend/app/ml -> .../backend
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _resolve_model_path(model_path: Optional[str] = None) -> str:
    """Resolve a local model directory or preserve a Hugging Face repo ID.

    Relative local paths are resolved against ``backend/``. A value such as
    ``Mirandasteve/autodesk-ticket-classifier`` is returned unchanged so
    ``snapshot_download`` can use it as a repository ID.
    """
    backend_root = _backend_root()
    candidate = model_path or os.getenv("ML_MODEL_PATH") or "app/ml/saved_model"

    if os.path.isabs(candidate):
        return candidate

    from_root = os.path.normpath(os.path.join(backend_root, candidate))
    if os.path.isdir(from_root):
        return from_root

    from_cwd = os.path.abspath(candidate)
    if os.path.isdir(from_cwd):
        return from_cwd

    # A Hugging Face repo ID has the form "owner/repository". Keep it as-is.
    if "/" in candidate and "\\" not in candidate:
        logger.info("Using Hugging Face model repository: %s", candidate)
        return candidate

    logger.warning(
        "ML_MODEL_PATH %r was not found locally; tried %s and %s",
        candidate,
        from_root,
        from_cwd,
    )
    return from_root


def load_model(
    model_path: Optional[str] = None,
    max_length: Optional[int] = None,
    allow_fallback: Optional[bool] = None,
    force: bool = False,
) -> TicketClassifier:
    """
    Create (or return) the process-wide classifier singleton.

    Called exactly once from the application factory. ``force=True`` rebuilds
    it, which the pytest suite uses to swap in a stub.
    """
    global _CLASSIFIER
    if _CLASSIFIER is not None and not force:
        return _CLASSIFIER

    if allow_fallback is None:
        allow_fallback = str(os.getenv("ML_ALLOW_FALLBACK", "True")).strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
    if max_length is None:
        try:
            max_length = int(os.getenv("ML_MAX_LENGTH", "256"))
        except ValueError:
            max_length = 256

    _CLASSIFIER = TicketClassifier(
        model_path=_resolve_model_path(model_path),
        max_length=max_length,
        allow_fallback=allow_fallback,
    )
    return _CLASSIFIER


def get_classifier() -> Optional[TicketClassifier]:
    """Return the active singleton, or ``None`` before the app has started."""
    return _CLASSIFIER


def unload_model() -> None:
    """Release the model (used by tests)."""
    global _CLASSIFIER
    _CLASSIFIER = None


# ---------------------------------------------------------------------------
# Module-level convenience API
# ---------------------------------------------------------------------------
def predict_category(text: str) -> Dict[str, Any]:
    """
    Classify *text* into one of the six SRS categories.

    The contract requested by the SRS::

        >>> predict_category("My laptop cannot connect to the office WiFi.")
        {'category': 'Network', 'confidence': 0.99, ...}

    The returned dict is a superset: it also carries ``source``, ``label_id``,
    ``model`` and ``top_k`` so the UI can be transparent about which engine
    answered.
    """
    classifier = get_classifier()
    if classifier is None:
        # Not initialised yet (e.g. a script importing this module directly).
        classifier = load_model()
    return classifier.predict(text)


def model_health() -> Dict[str, Any]:
    """Diagnostics for the health endpoint."""
    classifier = get_classifier()
    if classifier is None:
        return {
            "ready": False,
            "using_fallback": False,
            "source": "not-loaded",
            "model": None,
            "num_labels": NUM_LABELS,
            "labels": list(CATEGORIES),
        }
    return classifier.health()


if __name__ == "__main__":  # pragma: no cover - manual smoke test
    import json

    load_model()
    print(json.dumps(model_health(), indent=2))
    for sample in (
        "My office laptop cannot access the company network and WiFi keeps disconnecting.",
        "Microsoft Word closes immediately after opening.",
        "My keyboard is not responding.",
        "I forgot my company password.",
        "VPN keeps disconnecting when I connect remotely.",
        "I need permission to access the HR portal.",
    ):
        started = time.time()
        result = predict_category(sample)
        elapsed = (time.time() - started) * 1000
        print(
            f"{result['category']:<10} {result['confidence']:.3f}  "
            f"{elapsed:6.0f} ms  {sample}"
        )
