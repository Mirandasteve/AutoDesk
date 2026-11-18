"""
AutoDesk - DistilBERT evaluation
================================

Loads the trained checkpoint and scores it on the **held-out test split**
(``ml/dataset/test.csv``), which is never seen during training.

Reported metrics (SRS section 11):

* Accuracy
* Precision (per class, macro & weighted)
* Recall (per class, macro & weighted)
* F1 score (per class, macro & weighted)
* Confusion matrix

Every number printed here is computed from an actual forward pass through the
fine-tuned DistilBERT weights. Nothing is hardcoded or estimated. The results
are also written to ``ml/saved_model/evaluation_report.json`` so the README and
the report can quote real figures.

Usage::

    python ml/evaluate.py
    python ml/evaluate.py --split validation
    python ml/evaluate.py --show-samples 10
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Dict, List

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    precision_recall_fscore_support,
)
from transformers import AutoTokenizer, DistilBertForSequenceClassification

_HERE = os.path.dirname(os.path.abspath(__file__))

DATASET_DIR = os.path.join(_HERE, "dataset")
MODEL_DIR = os.path.join(_HERE, "saved_model")
REPORT_JSON = os.path.join(MODEL_DIR, "evaluation_report.json")

SPLIT_FILES = {
    "train": os.path.join(DATASET_DIR, "train.csv"),
    "validation": os.path.join(DATASET_DIR, "validation.csv"),
    "test": os.path.join(DATASET_DIR, "test.csv"),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_label_mappings() -> Dict[int, str]:
    """Read ``label_mappings.json`` from the checkpoint directory."""
    path = os.path.join(MODEL_DIR, "label_mappings.json")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not found. Run `python ml/train.py` before evaluating."
        )
    with open(path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return {int(k): v for k, v in raw["id_to_label"].items()}


def load_split(name: str) -> pd.DataFrame:
    if name not in SPLIT_FILES:
        raise ValueError(f"unknown split '{name}'; choose from {sorted(SPLIT_FILES)}")
    path = SPLIT_FILES[name]
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} not found. Run `python ml/preprocess.py` first.")
    frame = pd.read_csv(path)
    return frame.dropna(subset=["text", "label"]).reset_index(drop=True)


@torch.no_grad()
def predict(
    frame: pd.DataFrame,
    tokenizer,
    model,
    device: torch.device,
    max_length: int,
    batch_size: int = 32,
) -> tuple[np.ndarray, np.ndarray]:
    """Run inference over *frame* and return ``(predictions, confidences)``."""
    model.eval()
    texts = frame["text"].astype(str).tolist()

    all_preds: List[int] = []
    all_conf: List[float] = []

    for start in range(0, len(texts), batch_size):
        chunk = texts[start : start + batch_size]
        enc = tokenizer(
            chunk,
            truncation=True,
            padding=True,
            max_length=max_length,
            return_tensors="pt",
        )
        enc = {k: v.to(device) for k, v in enc.items()}
        logits = model(**enc).logits
        probs = torch.softmax(logits, dim=-1)
        conf, preds = probs.max(dim=-1)
        all_preds.extend(preds.cpu().numpy().tolist())
        all_conf.extend(conf.cpu().numpy().tolist())

    return np.array(all_preds), np.array(all_conf)


def print_confusion_matrix(
    matrix: np.ndarray, id_to_label: Dict[int, str], labels: List[int]
) -> None:
    """Render an aligned, readable confusion matrix."""
    names = [id_to_label[i] for i in labels]
    width = max(len(n) for n in names) + 2

    header = " " * (width + 3) + "".join(f"{n[:9]:>11}" for n in names)
    print(header)
    print(" " * (width + 3) + "-" * (11 * len(names)))
    for index, row in zip(labels, matrix):
        cells = "".join(f"{value:>11}" for value in row)
        print(f"{id_to_label[index]:<{width}} |{cells}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def evaluate(args: argparse.Namespace) -> Dict[str, object]:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    print("=" * 74)
    print("AutoDesk - DistilBERT ticket classifier evaluation")
    print("=" * 74)
    print(f"Checkpoint : {MODEL_DIR}")
    print(f"Split      : {args.split}")
    print(f"Device     : {device}")

    if not os.path.exists(os.path.join(MODEL_DIR, "config.json")):
        raise FileNotFoundError(
            f"No trained model in {MODEL_DIR}. Run `python ml/train.py` first."
        )

    frame = load_split(args.split)
    id_to_label = load_label_mappings()
    labels = sorted(id_to_label)

    print(f"Rows       : {len(frame)}")
    print("-" * 74)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
    model = DistilBertForSequenceClassification.from_pretrained(MODEL_DIR)
    model.to(device)

    started = time.time()
    predictions, confidences = predict(frame, tokenizer, model, device, args.max_length)
    elapsed = time.time() - started

    y_true = frame["label"].to_numpy(dtype=int)
    y_pred = predictions

    accuracy = accuracy_score(y_true, y_pred)
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0
    )
    matrix = confusion_matrix(y_true, y_pred, labels=labels)

    per_class = {}
    for position, label_id in enumerate(labels):
        per_class[id_to_label[label_id]] = {
            "label_id": int(label_id),
            "precision": round(float(precision[position]), 4),
            "recall": round(float(recall[position]), 4),
            "f1": round(float(f1[position]), 4),
            "support": int(support[position]),
        }

    weighted = {
        "precision": round(float(np.average(precision, weights=support)), 4),
        "recall": round(float(np.average(recall, weights=support)), 4),
        "f1": round(float(np.average(f1, weights=support)), 4),
    }

    print(f"\nAccuracy  : {accuracy:.4f}  ({int(round(accuracy * len(frame)))}/{len(frame)} correct)")
    print(f"Macro F1  : {float(np.mean(f1)):.4f}")
    print(f"Weighted  : P={weighted['precision']:.4f}  R={weighted['recall']:.4f}  "
          f"F1={weighted['f1']:.4f}")
    print(f"Mean conf : {float(np.mean(confidences)):.4f}")
    print(f"Inference : {elapsed:.2f}s total, "
          f"{elapsed / max(len(frame), 1) * 1000:.1f} ms/ticket "
          f"(SRS target: < 3000 ms/ticket)")

    print("\nPer-class metrics")
    print("-" * 74)
    print(f"{'class':<12}{'precision':>11}{'recall':>10}{'f1':>10}{'support':>10}")
    print("-" * 74)
    for label_id in labels:
        row = per_class[id_to_label[label_id]]
        print(
            f"{id_to_label[label_id]:<12}{row['precision']:>11.4f}"
            f"{row['recall']:>10.4f}{row['f1']:>10.4f}{row['support']:>10}"
        )
    print("-" * 74)
    print(
        f"{'macro avg':<12}{float(np.mean(precision)):>11.4f}"
        f"{float(np.mean(recall)):>10.4f}{float(np.mean(f1)):>10.4f}{int(support.sum()):>10}"
    )
    print(
        f"{'weighted':<12}{weighted['precision']:>11.4f}"
        f"{weighted['recall']:>10.4f}{weighted['f1']:>10.4f}{int(support.sum()):>10}"
    )

    print("\nClassification report")
    print("-" * 74)
    print(
        classification_report(
            y_true, y_pred, labels=labels, target_names=[id_to_label[i] for i in labels],
            zero_division=0,
        )
    )

    print("Confusion matrix (rows = actual, columns = predicted)")
    print("-" * 74)
    print_confusion_matrix(matrix, id_to_label, labels)

    errors = np.where(y_true != y_pred)[0]
    if args.show_samples and len(errors):
        print(f"\nSample misclassifications ({min(args.show_samples, len(errors))} of {len(errors)})")
        print("-" * 74)
        for index in errors[: args.show_samples]:
            text = str(frame.iloc[int(index)]["text"])
            snippet = text if len(text) <= 90 else text[:87] + "..."
            print(
                f"  actual={id_to_label[int(y_true[index])]:<9} "
                f"pred={id_to_label[int(y_pred[index])]:<9} "
                f"conf={confidences[index]:.3f}  {snippet}"
            )
    elif len(errors) == 0:
        print("\nNo misclassified rows on this split.")

    report: Dict[str, object] = {
        "model_path": MODEL_DIR,
        "split": args.split,
        "split_rows": int(len(frame)),
        "device": str(device),
        "accuracy": round(float(accuracy), 6),
        "macro_precision": round(float(np.mean(precision)), 6),
        "macro_recall": round(float(np.mean(recall)), 6),
        "macro_f1": round(float(np.mean(f1)), 6),
        "weighted_precision": weighted["precision"],
        "weighted_recall": weighted["recall"],
        "weighted_f1": weighted["f1"],
        "mean_confidence": round(float(np.mean(confidences)), 6),
        "inference_seconds_total": round(elapsed, 3),
        "inference_ms_per_ticket": round(elapsed / max(len(frame), 1) * 1000, 2),
        "per_class": per_class,
        "confusion_matrix": {
            "labels": [id_to_label[i] for i in labels],
            "matrix": matrix.tolist(),
        },
        "misclassified": int(len(errors)),
    }
    with open(REPORT_JSON, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=4)

    print(f"\nReport written to: {REPORT_JSON}")
    print("=" * 74)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate the AutoDesk DistilBERT classifier")
    parser.add_argument("--split", choices=sorted(SPLIT_FILES), default="test")
    parser.add_argument("--max-length", type=int, default=128)
    parser.add_argument("--show-samples", type=int, default=8)
    return parser


def main() -> int:
    sys.path.insert(0, _HERE)
    return 0 if evaluate(build_parser().parse_args()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
