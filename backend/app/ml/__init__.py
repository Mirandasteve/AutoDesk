"""
AutoDesk - Machine learning layer
================================

Wraps the fine-tuned DistilBERT classifier used for ticket categorisation.

Contents
--------
``predictor``
    :class:`~app.ml.predictor.TicketClassifier` plus the module-level
    :func:`~app.ml.predictor.predict_category` convenience function the routes
    call. The model is loaded exactly once, at application start.
``label_mappings.json``
    ``id -> category`` and ``category -> id``. The order is fixed by the SRS:

    =============  =========
    id            category
    =============  =========
    0             Software
    1             Hardware
    2             Network
    3             Login
    4             VPN
    5             Access
    =============  =========
``saved_model/``
    The checkpoint produced by ``ml/train.py`` (``config.json``,
    ``model.safetensors``, tokenizer files, ``label_mappings.json``,
    ``training_history.json``, ``evaluation_report.json``).

Priority is **not** predicted here. DistilBERT classifies the category; the
separate, deterministic keyword engine in
:mod:`app.services.priority_engine` decides the priority (SRS section 12).
"""

from __future__ import annotations

import json
import os
from typing import Dict

#: ``<repo>/backend/app/ml``
ML_DIR = os.path.dirname(os.path.abspath(__file__))
#: Canonical label order - the contract shared with ``ml/train.py``.
CATEGORIES = ("Software", "Hardware", "Network", "Login", "VPN", "Access")
#: Default location of the fine-tuned checkpoint.
DEFAULT_MODEL_DIR = os.path.join(ML_DIR, "saved_model")
#: Default location of the label mappings.
DEFAULT_LABEL_MAPPINGS = os.path.join(ML_DIR, "label_mappings.json")


def load_label_mappings(path: str | None = None) -> Dict[str, Dict]:
    """
    Read ``label_mappings.json``.

    Falls back to the canonical SRS order when the file is absent, so the
    application still starts on a fresh clone.
    """
    candidate = path or DEFAULT_LABEL_MAPPINGS
    if os.path.exists(candidate):
        try:
            with open(candidate, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            id_to_label = {int(k): str(v) for k, v in raw["id_to_label"].items()}
            if set(id_to_label.values()) == set(CATEGORIES):
                return {
                    "id_to_label": id_to_label,
                    "label_to_id": {v: k for k, v in id_to_label.items()},
                }
        except Exception:  # pragma: no cover - defensive
            pass

    id_to_label = {index: name for index, name in enumerate(CATEGORIES)}
    return {"id_to_label": id_to_label, "label_to_id": {v: k for k, v in id_to_label.items()}}


__all__ = [
    "CATEGORIES",
    "DEFAULT_LABEL_MAPPINGS",
    "DEFAULT_MODEL_DIR",
    "ML_DIR",
    "load_label_mappings",
]
