"""
AutoDesk - Dataset preprocessing and splitting
==============================================

Turns the raw ``ml/dataset/tickets.csv`` into the three files consumed by
``train.py``::

    ml/dataset/train.csv        70 %
    ml/dataset/validation.csv   15 %
    ml/dataset/test.csv         15 %

Pipeline (SRS section 10)
-------------------------
1. Load the raw CSV.
2. Missing-value handling - drop rows with no text / no category, fill the
   optional priority column with the priority engine's answer.
3. Duplicate removal - exact duplicates plus normalised-text duplicates.
4. Whitespace normalisation and basic text cleaning (control characters,
   collapsed spacing, lower-casing for the text column only, URLs/emails
   masked).
5. Label encoding - category -> integer id using the canonical SRS order,
   written to ``ml/dataset/label_mappings.json`` and copied to
   ``backend/app/ml/label_mappings.json``.

Splitting is **stratified on the category label** so every split keeps the same
class balance, and the split is seeded for reproducibility. Test rows are never
written into ``train.csv`` - the guarantee is structural: the three files are
produced from disjoint index sets.

Usage::

    python ml/preprocess.py
    python ml/preprocess.py --val-size 0.2 --test-size 0.1 --seed 7
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from typing import Dict, List, Tuple

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_BACKEND = os.path.join(_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.services.priority_engine import predict_priority  # noqa: E402
from app.services.routing_engine import CATEGORIES  # noqa: E402

DATASET_DIR = os.path.join(_HERE, "dataset")
RAW_CSV = os.path.join(DATASET_DIR, "tickets.csv")
TRAIN_CSV = os.path.join(DATASET_DIR, "train.csv")
VAL_CSV = os.path.join(DATASET_DIR, "validation.csv")
TEST_CSV = os.path.join(DATASET_DIR, "test.csv")
LABEL_MAPPINGS_JSON = os.path.join(DATASET_DIR, "label_mappings.json")
BACKEND_LABEL_MAPPINGS_JSON = os.path.join(_BACKEND, "app", "ml", "label_mappings.json")

DEFAULT_SEED = 2025

_WHITESPACE = re.compile(r"[ \t\r\f\v]+")
_MULTI_NEWLINE = re.compile(r"\n{2,}")
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_URL = re.compile(r"\b(?:https?://|www\.)\S+", flags=re.IGNORECASE)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_TRAILING_PUNCT = re.compile(r"[^\w\s]+$", flags=re.UNICODE)


# ---------------------------------------------------------------------------
# Cleaning helpers
# ---------------------------------------------------------------------------
def clean_text(value: object) -> str:
    """
    Basic but conservative text cleaning.

    Deliberately **does not** remove punctuation, stop words or negation words:
    DistilBERT's WordPiece tokenizer is trained on natural text, and stripping
    tokens such as ``not`` destroys useful signals for hardware vs. software
    fault descriptions.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value)
    text = _CONTROL_CHARS.sub(" ", text)
    text = _URL.sub(" <url> ", text)
    text = _EMAIL.sub(" <email> ", text)
    text = text.replace("\n", " ")
    text = _WHITESPACE.sub(" ", text)
    text = _MULTI_NEWLINE.sub(" ", text)
    return text.strip()


def normalize_for_dedup(value: object) -> str:
    """Aggressive normalisation used only for duplicate detection."""
    text = clean_text(value).lower()
    text = _TRAILING_PUNCT.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def build_label_mappings() -> Dict[str, object]:
    """
    Build the canonical label map.

    Index order is fixed by the SRS and must never change, because the trained
    DistilBERT classification head bakes these ids into its weights::

        0 Software   1 Hardware   2 Network   3 Login   4 VPN   5 Access
    """
    id_to_label = {index: category for index, category in enumerate(CATEGORIES)}
    label_to_id = {category: index for index, category in id_to_label.items()}
    return {"id_to_label": id_to_label, "label_to_id": label_to_id}


def save_label_mappings(mappings: Dict[str, object]) -> List[str]:
    """Write ``label_mappings.json`` to the dataset dir *and* the backend dir."""
    written: List[str] = []

    dataset_path = LABEL_MAPPINGS_JSON
    os.makedirs(os.path.dirname(dataset_path), exist_ok=True)
    with open(dataset_path, "w", encoding="utf-8") as handle:
        json.dump(mappings, handle, indent=4, sort_keys=True)
    written.append(dataset_path)

    backend_path = BACKEND_LABEL_MAPPINGS_JSON
    os.makedirs(os.path.dirname(backend_path), exist_ok=True)
    with open(backend_path, "w", encoding="utf-8") as handle:
        json.dump(mappings, handle, indent=4, sort_keys=True)
    written.append(backend_path)
    return written


def copy_model_artifacts_to_backend(source_dir: str, target_dir: str) -> int:
    """
    Mirror the trained model checkpoint into the backend so Flask can load it
    from ``backend/app/ml/saved_model/``.

    Returns the number of files copied.
    """
    source_dir = os.path.abspath(source_dir)
    target_dir = os.path.abspath(target_dir)
    if not os.path.isdir(source_dir):
        return 0

    copied = 0
    for root, _dirs, files in os.walk(source_dir):
        rel = os.path.relpath(root, source_dir)
        destination_root = target_dir if rel == "." else os.path.join(target_dir, rel)
        os.makedirs(destination_root, exist_ok=True)
        for name in files:
            shutil.copy2(os.path.join(root, name), os.path.join(destination_root, name))
            copied += 1
    return copied


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def load_raw(path: str = RAW_CSV) -> pd.DataFrame:
    """Read the raw CSV and normalise its column names."""
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not found. Run `python ml/generate_data.py` first."
        )
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    frame.columns = [str(c).strip().lower() for c in frame.columns]

    missing = [c for c in ("text", "category") if c not in frame.columns]
    if missing:
        raise ValueError(
            f"{path} is missing required column(s): {', '.join(missing)}. "
            f"Found: {list(frame.columns)}"
        )
    return frame


def clean_frame(frame: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """Run missing-value handling, cleaning and de-duplication."""
    report: Dict[str, int] = {"raw_rows": int(len(frame))}

    # --- 1. missing-value handling -------------------------------------
    frame = frame.copy()
    frame["text"] = frame["text"].apply(clean_text)
    frame["category"] = frame["category"].astype(str).str.strip()

    before = len(frame)
    frame = frame[(frame["text"].str.len() > 0) & (frame["category"].str.len() > 0)]
    report["dropped_empty"] = before - len(frame)

    # Unknown / mis-cased category labels are folded onto the canonical six.
    canonical = {c.lower(): c for c in CATEGORIES}
    before = len(frame)
    frame["category"] = frame["category"].str.lower().map(canonical)
    frame = frame[frame["category"].notna()]
    report["dropped_bad_category"] = before - len(frame)

    # --- 2. text cleaning ----------------------------------------------
    frame["text"] = frame["text"].str.strip()
    before = len(frame)
    frame = frame[frame["text"].str.len() >= 10]
    report["dropped_too_short"] = before - len(frame)

    # --- 3. duplicate removal ------------------------------------------
    # One pass over the normalised key handles both cases: identical rows, and
    # rows whose text repeats under conflicting labels. The second case is a
    # labelling error - keeping both would teach the model a contradiction -
    # so it is counted separately for visibility and then collapsed by the same
    # `drop_duplicates` call rather than a redundant second one.
    before = len(frame)
    frame["_dedup_key"] = frame["text"].apply(normalize_for_dedup)

    label_counts = frame.groupby("_dedup_key")["category"].nunique()
    conflicting = int((label_counts > 1).sum())
    report["conflicting_labels"] = conflicting

    frame = frame.drop_duplicates(subset="_dedup_key", keep="first")
    removed = before - len(frame)
    report["dropped_duplicates"] = removed
    report["total_deduplicated"] = removed

    # --- 4. label encoding ---------------------------------------------
    mappings = build_label_mappings()
    frame["label"] = frame["category"].map(mappings["label_to_id"]).astype(int)

    # --- 5. priority column --------------------------------------------
    if "priority" not in frame.columns or frame["priority"].astype(str).str.len().eq(0).all():
        frame["priority"] = frame["text"].apply(
            lambda t: predict_priority(description=t)["priority"]
        )
    else:
        frame["priority"] = frame["priority"].apply(
            lambda p: p if p in ("Low", "Medium", "High", "Critical")
            else predict_priority(description=str(p))["priority"]
        )

    # --- 6. keep model text in lower case (WordPiece uncased model) ------
    frame["text"] = frame["text"].str.lower()

    frame = frame.drop(columns=["_dedup_key"]).reset_index(drop=True)
    report["clean_rows"] = int(len(frame))
    return frame, report


def stratified_split(
    frame: pd.DataFrame,
    train_size: float = 0.70,
    val_size: float = 0.15,
    test_size: float = 0.15,
    seed: int = DEFAULT_SEED,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Split on the ``label`` column so all three files keep the class balance.

    Implemented manually (rather than with ``train_test_split`` twice) so the
    three index sets are provably disjoint and cover every row exactly once.
    """
    total = train_size + val_size + test_size
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"split sizes must sum to 1.0, got {total}")

    train_frames: List[pd.DataFrame] = []
    val_frames: List[pd.DataFrame] = []
    test_frames: List[pd.DataFrame] = []

    for _label, group in frame.groupby("label", sort=True):
        group = group.sample(frac=1.0, random_state=seed).reset_index(drop=True)
        n = len(group)
        n_train = int(round(n * train_size))
        n_val = int(round(n * val_size))
        # Guarantee at least one row per split for any non-empty group.
        n_train = max(1, min(n_train, n - 2)) if n >= 3 else n
        n_val = max(1, min(n_val, n - n_train - 1)) if n >= 3 else 0
        n_test = n - n_train - n_val
        if n_test < 0:  # pragma: no cover - guarded by the clamps above
            n_val, n_test = n_val + n_test, 0

        train_frames.append(group.iloc[:n_train])
        val_frames.append(group.iloc[n_train : n_train + n_val])
        test_frames.append(group.iloc[n_train + n_val :])

    train = pd.concat(train_frames).sample(frac=1.0, random_state=seed).reset_index(drop=True)
    val = pd.concat(val_frames).sample(frac=1.0, random_state=seed).reset_index(drop=True)
    test = pd.concat(test_frames).sample(frac=1.0, random_state=seed).reset_index(drop=True)

    # Structural guarantee: no text may appear in more than one split.
    sets = [set(train["text"]), set(val["text"]), set(test["text"])]
    if sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2]:
        raise AssertionError("data leakage detected between train/val/test splits")
    return train, val, test


def save_splits(
    train: pd.DataFrame,
    val: pd.DataFrame,
    test: pd.DataFrame,
    columns: Tuple[str, ...] = ("text", "category", "label", "priority"),
) -> List[str]:
    """Write the three split CSVs with a stable column order."""
    paths = []
    for name, frame in (("train", train), ("validation", val), ("test", test)):
        path = os.path.join(DATASET_DIR, f"{name}.csv")
        frame[list(columns)].to_csv(path, index=False, encoding="utf-8")
        paths.append(path)
    return paths


def distribution_report(train: pd.DataFrame, val: pd.DataFrame, test: pd.DataFrame) -> str:
    """Render a console table of the split sizes and class balance."""
    lines = [
        "",
        "AutoDesk dataset preprocessed",
        "=" * 62,
        f"{'split':<12}{'rows':>7}{'share':>9}   " + " ".join(f"{c[:8]:>9}" for c in CATEGORIES),
        "-" * 62,
    ]
    total = len(train) + len(val) + len(test)
    for name, frame in (("train", train), ("validation", val), ("test", test)):
        share = len(frame) / total if total else 0
        counts = frame["category"].value_counts().to_dict()
        cells = " ".join(f"{counts.get(c, 0):>9}" for c in CATEGORIES)
        lines.append(f"{name:<12}{len(frame):>7}{share:>8.1%}   {cells}")
    lines += ["-" * 62, f"{'TOTAL':<12}{total:>7}{1.0:>8.1%}"]
    lines += ["=" * 62, ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean and split the AutoDesk dataset")
    parser.add_argument("--raw", default=RAW_CSV)
    parser.add_argument("--train-size", type=float, default=0.70)
    parser.add_argument("--val-size", type=float, default=0.15)
    parser.add_argument("--test-size", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    frame = load_raw(args.raw)
    cleaned, report = clean_frame(frame)
    train, val, test = stratified_split(
        cleaned, args.train_size, args.val_size, args.test_size, args.seed
    )

    mappings = build_label_mappings()
    written = save_label_mappings(mappings)
    written += save_splits(train, val, test)

    print(distribution_report(train, val, test))
    print("Cleaning report:")
    for key, value in report.items():
        print(f"  {key:<24} {value}")
    print("\nLabel mappings (DistilBERT class ids):")
    for index, category in mappings["id_to_label"].items():
        print(f"  {index} -> {category}")
    print("\nWritten files:")
    for path in written:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
