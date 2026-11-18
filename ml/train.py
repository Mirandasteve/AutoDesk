"""
AutoDesk - DistilBERT fine-tuning
=================================

Fine-tunes ``distilbert/distilbert-base-uncased`` into a 6-way sequence
classifier for IT ticket categories::

    0 Software | 1 Hardware | 2 Network | 3 Login | 4 VPN | 5 Access

Stages (SRS section 11)
------------------------
1. Load the preprocessed ``train.csv`` / ``validation.csv``.
2. Load the DistilBERT tokenizer.
3. Encode the category labels from ``label_mappings.json``.
4. Tokenize the ticket descriptions.
5. Wrap them in a ``torch.utils.data.Dataset``.
6. Load ``DistilBertForSequenceClassification``.
7. Fine-tune on the training split.
8. Validate after every epoch.
9. Keep the best checkpoint (highest validation accuracy).
10/11. Save the model, the tokenizer and the label mappings to
      ``ml/saved_model/`` **and** mirror them into
      ``backend/app/ml/saved_model/`` so Flask can serve inference.

Metrics are written to ``ml/saved_model/training_history.json``. Nothing is
fabricated - every number in that file is produced by this script.

Usage::

    python ml/train.py                       # 4 epochs, batch 16, lr 5e-5
    python ml/train.py --epochs 6 --batch-size 8
    python ml/train.py --max-length 128 --seed 42
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader, Dataset
from transformers import (
    AutoTokenizer,
    DistilBertForSequenceClassification,
    get_linear_schedule_with_warmup,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

DATASET_DIR = os.path.join(_HERE, "dataset")
TRAIN_CSV = os.path.join(DATASET_DIR, "train.csv")
VAL_CSV = os.path.join(DATASET_DIR, "validation.csv")
LABEL_MAPPINGS_JSON = os.path.join(DATASET_DIR, "label_mappings.json")
MODEL_OUT_DIR = os.path.join(_HERE, "saved_model")
BACKEND_MODEL_DIR = os.path.join(_ROOT, "backend", "app", "ml", "saved_model")
HISTORY_JSON = os.path.join(MODEL_OUT_DIR, "training_history.json")

BASE_MODEL = "distilbert/distilbert-base-uncased"
NUM_LABELS = 6


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------
def set_seed(seed: int) -> None:
    """Seed python / numpy / torch so two runs are comparable."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def get_device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
class TicketDataset(Dataset):
    """PyTorch dataset over pre-tokenized ticket descriptions."""

    def __init__(self, encodings: Dict[str, torch.Tensor], labels: List[int]) -> None:
        self.encodings = encodings
        self.labels = labels

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, index: int) -> Dict[str, torch.Tensor]:
        item = {key: value[index] for key, value in self.encodings.items()}
        item["labels"] = torch.tensor(self.labels[index], dtype=torch.long)
        return item


def load_label_mappings(path: str = LABEL_MAPPINGS_JSON) -> Dict[str, Dict[str, int]]:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not found. Run `python ml/preprocess.py` before training."
        )
    with open(path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return {
        "id_to_label": {int(k): v for k, v in raw["id_to_label"].items()},
        "label_to_id": {str(k): int(v) for k, v in raw["label_to_id"].items()},
    }


def read_split(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} not found. Run `python ml/preprocess.py` first.")
    frame = pd.read_csv(path)
    for column in ("text", "label"):
        if column not in frame.columns:
            raise ValueError(f"{path} is missing the '{column}' column")
    frame = frame.dropna(subset=["text", "label"])
    frame["label"] = frame["label"].astype(int)
    return frame.reset_index(drop=True)


def build_tokenizer(max_length: int):
    """Load the base DistilBERT tokenizer (WordPiece, uncased)."""
    print(f"Loading tokenizer: {BASE_MODEL}")
    return AutoTokenizer.from_pretrained(BASE_MODEL, model_max_length=max_length)


def tokenize_frames(
    tokenizer,
    frames: List[pd.DataFrame],
    max_length: int,
) -> List[Dict[str, torch.Tensor]]:
    """Tokenize a list of frames with dynamic padding."""
    encoded: List[Dict[str, torch.Tensor]] = []
    for frame in frames:
        enc = tokenizer(
            frame["text"].astype(str).tolist(),
            truncation=True,
            padding=True,          # pad to the longest sequence in the batch
            max_length=max_length,
            return_tensors="pt",
        )
        encoded.append({k: v for k, v in enc.items()})
    return encoded


# ---------------------------------------------------------------------------
# Train / evaluate
# ---------------------------------------------------------------------------
@torch.no_grad()
def evaluate(model, loader: DataLoader, device: torch.device) -> Dict[str, float]:
    """Return mean loss and accuracy over *loader*."""
    model.eval()
    total_loss = 0.0
    correct = 0
    seen = 0
    for batch in loader:
        batch = {k: v.to(device) for k, v in batch.items()}
        outputs = model(**batch)
        total_loss += outputs.loss.item() * batch["labels"].size(0)
        predictions = outputs.logits.argmax(dim=-1)
        correct += (predictions == batch["labels"]).sum().item()
        seen += batch["labels"].size(0)
    return {"loss": total_loss / max(seen, 1), "accuracy": correct / max(seen, 1)}


def train(args: argparse.Namespace) -> Dict[str, object]:
    set_seed(args.seed)
    device = get_device()
    os.makedirs(MODEL_OUT_DIR, exist_ok=True)

    print("=" * 68)
    print("AutoDesk - DistilBERT ticket category classifier")
    print("=" * 68)
    print(f"Base model   : {BASE_MODEL}")
    print(f"Device       : {device}")
    print(f"Max length   : {args.max_length}")
    print(f"Epochs       : {args.epochs}   Batch size: {args.batch_size}   LR: {args.lr}")
    print("-" * 68)

    mappings = load_label_mappings(args.label_mappings)
    train_frame = read_split(args.train_csv)
    val_frame = read_split(args.val_csv)
    print(f"Train rows   : {len(train_frame)}")
    print(f"Valid rows   : {len(val_frame)}")

    tokenizer = build_tokenizer(args.max_length)
    train_enc, val_enc = tokenize_frames(tokenizer, [train_frame, val_frame], args.max_length)

    train_ds = TicketDataset(train_enc, train_frame["label"].tolist())
    val_ds = TicketDataset(val_enc, val_frame["label"].tolist())

    train_loader = DataLoader(
        train_ds, batch_size=args.batch_size, shuffle=True, num_workers=0
    )
    val_loader = DataLoader(val_ds, batch_size=args.eval_batch_size, shuffle=False, num_workers=0)

    print(f"\nLoading model: {BASE_MODEL} (num_labels={NUM_LABELS})")
    model = DistilBertForSequenceClassification.from_pretrained(
        BASE_MODEL, num_labels=NUM_LABELS
    )
    model.to(device)

    no_decay = ["bias", "LayerNorm.weight"]
    grouped = [
        {
            "params": [
                p
                for n, p in model.named_parameters()
                if not any(nd in n for nd in no_decay)
            ],
            "weight_decay": 0.01,
        },
        {
            "params": [
                p for n, p in model.named_parameters() if any(nd in n for nd in no_decay)
            ],
            "weight_decay": 0.0,
        },
    ]
    optimizer = torch.optim.AdamW(grouped, lr=args.lr, eps=1e-8)
    total_steps = len(train_loader) * args.epochs
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=max(1, int(0.1 * total_steps)),
        num_training_steps=total_steps,
    )
    criterion = torch.nn.CrossEntropyLoss()

    best_accuracy = -1.0
    best_epoch = 0
    best_state: Dict[str, torch.Tensor] | None = None
    history: List[Dict[str, float]] = []

    for epoch in range(1, args.epochs + 1):
        model.train()
        epoch_start = time.time()
        running_loss = 0.0
        correct = 0
        seen = 0

        for step, batch in enumerate(train_loader, start=1):
            labels = batch.pop("labels").to(device)
            batch = {k: v.to(device) for k, v in batch.items()}
            outputs = model(**batch)
            loss = criterion(outputs.logits, labels)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()

            running_loss += loss.item() * labels.size(0)
            correct += (outputs.logits.argmax(dim=-1) == labels).sum().item()
            seen += labels.size(0)

            if step % args.log_every == 0 or step == len(train_loader):
                print(
                    f"  epoch {epoch}/{args.epochs} | step {step:>3}/{len(train_loader)}"
                    f" | loss {running_loss / seen:.4f}"
                    f" | train_acc {correct / seen:.4f}"
                    f" | lr {scheduler.get_last_lr()[0]:.2e}"
                )

        train_metrics = {
            "loss": running_loss / max(seen, 1),
            "accuracy": correct / max(seen, 1),
        }
        val_metrics = evaluate(model, val_loader, device)
        elapsed = time.time() - epoch_start

        history.append(
            {
                "epoch": epoch,
                "train_loss": round(train_metrics["loss"], 6),
                "train_accuracy": round(train_metrics["accuracy"], 6),
                "val_loss": round(val_metrics["loss"], 6),
                "val_accuracy": round(val_metrics["accuracy"], 6),
                "seconds": round(elapsed, 1),
            }
        )
        marker = ""
        if val_metrics["accuracy"] > best_accuracy:
            best_accuracy = val_metrics["accuracy"]
            best_epoch = epoch
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            marker = "  <- best so far"
        print(
            f"  [epoch {epoch}] train_loss={train_metrics['loss']:.4f}"
            f" train_acc={train_metrics['accuracy']:.4f}"
            f" val_loss={val_metrics['loss']:.4f}"
            f" val_acc={val_metrics['accuracy']:.4f}"
            f" ({elapsed:.1f}s){marker}"
        )

    if best_state is None:  # pragma: no cover - args.epochs >= 1 always sets it
        raise RuntimeError("training produced no checkpoint")

    print("-" * 68)
    print(f"Restoring best epoch {best_epoch} (val_acc={best_accuracy:.4f})")
    model.load_state_dict(best_state)

    print(f"Saving model + tokenizer to: {MODEL_OUT_DIR}")
    model.save_pretrained(MODEL_OUT_DIR)
    tokenizer.save_pretrained(MODEL_OUT_DIR)

    with open(LABEL_MAPPINGS_JSON, "r", encoding="utf-8") as handle:
        label_payload = json.load(handle)
    with open(os.path.join(MODEL_OUT_DIR, "label_mappings.json"), "w", encoding="utf-8") as handle:
        json.dump(label_payload, handle, indent=4, sort_keys=True)

    summary: Dict[str, object] = {
        "base_model": BASE_MODEL,
        "num_labels": NUM_LABELS,
        "max_length": args.max_length,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "learning_rate": args.lr,
        "seed": args.seed,
        "device": str(device),
        "train_rows": int(len(train_frame)),
        "validation_rows": int(len(val_frame)),
        "best_epoch": best_epoch,
        "best_val_accuracy": round(float(best_accuracy), 6),
        "train_time_seconds": round(sum(h["seconds"] for h in history), 1),
        "label_mappings": mappings,
        "history": history,
    }
    with open(HISTORY_JSON, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=4)

    print(f"Training history written to: {HISTORY_JSON}")
    print("Now run:  python ml/evaluate.py")
    print("=" * 68)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fine-tune DistilBERT for AutoDesk")
    parser.add_argument("--train-csv", default=TRAIN_CSV)
    parser.add_argument("--val-csv", default=VAL_CSV)
    parser.add_argument("--label-mappings", default=LABEL_MAPPINGS_JSON)
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--eval-batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=5e-5)
    parser.add_argument("--max-length", type=int, default=128)
    parser.add_argument("--seed", type=int, default=2025)
    parser.add_argument("--log-every", type=int, default=10)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    train(args)

    # Mirror the checkpoint into the backend so Flask can load it directly.
    try:
        from preprocess import copy_model_artifacts_to_backend

        count = copy_model_artifacts_to_backend(MODEL_OUT_DIR, BACKEND_MODEL_DIR)
        print(f"Mirrored {count} model file(s) -> {BACKEND_MODEL_DIR}")
    except Exception as exc:  # pragma: no cover - convenience step
        print(f"WARNING: could not mirror the model into the backend: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
