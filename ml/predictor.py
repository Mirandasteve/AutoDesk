"""
AutoDesk - Standalone ML predictor (command line)
==================================================

A thin CLI around the very same predictor the Flask API uses, so a ticket can
be classified straight from the terminal or a Jupyter notebook::

    python ml/predictor.py "My laptop cannot connect to the office WiFi."
    python ml/predictor.py --interactive
    python ml/predictor.py --json --batch "..." "..."

In a notebook::

    from predictor import predict_category
    predict_category("I forgot my company password.")
    # {'category': 'Login', 'confidence': 0.98, ...}

The model is loaded once per process. If it is missing the script reports the
keyword-fallback explicitly instead of pretending to be the classifier.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Dict, List

# Reuse the backend package so there is exactly one implementation of the
# DistilBERT inference path in the repository.
_BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

# Prefer the copy next to this script (ml/saved_model); fall back to the
# backend copy that the Flask app actually loads.
_LOCAL_MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saved_model")

from app.ml.predictor import (  # noqa: E402
    CATEGORIES,
    TicketClassifier,
    predict_category,
)

# The script defaults to its own checkpoint, then to the backend copy.
os.environ.setdefault("ML_MODEL_PATH", _LOCAL_MODEL)


def load_classifier() -> TicketClassifier:
    """Load the model once for this process."""
    if not os.path.isdir(_LOCAL_MODEL):
        os.environ["ML_MODEL_PATH"] = os.path.join(_BACKEND, "app", "ml", "saved_model")
    from app.ml.predictor import load_model

    return load_model()


def print_result(text: str, result: Dict[str, object], elapsed_ms: float) -> None:
    """Pretty-print one prediction."""
    label = str(result.get("category") or "??")
    confidence = float(result.get("confidence") or 0.0)
    source = result.get("source")

    bar_width = 28
    filled = int(round(confidence * bar_width))
    bar = "#" * filled + "." * (bar_width - filled)

    print(f"  text       : {text}")
    print(f"  category   : {label.upper()}")
    print(f"  confidence : {confidence:.4f}  [{bar}]")
    print(f"  engine     : {source} ({result.get('model')})")
    print(f"  latency    : {elapsed_ms:.0f} ms")
    top_k = result.get("top_k")
    if top_k:
        runners_up = ", ".join(
            f"{item['category']} {item['confidence_pct']:.1f}%" for item in top_k[1:]
        )
        if runners_up:
            print(f"  also       : {runners_up}")
    print()


def interactive(classifier: TicketClassifier) -> int:
    """Read descriptions from stdin until the user quits."""
    print("AutoDesk classifier - type a ticket description, 'quit' to exit.\n")
    while True:
        try:
            text = input("ticket> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text.lower() in ("quit", "exit", "q"):
            break
        started = time.time()
        result = classifier.predict(text)
        print_result(text, result, (time.time() - started) * 1000)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Classify IT ticket descriptions with the AutoDesk DistilBERT model"
    )
    parser.add_argument("text", nargs="*", help="one or more ticket descriptions")
    parser.add_argument("--interactive", action="store_true", help="read input until 'quit'")
    parser.add_argument("--json", action="store_true", help="emit raw JSON")
    parser.add_argument("--health", action="store_true", help="print model diagnostics only")
    args = parser.parse_args()

    classifier = load_classifier()

    if args.health:
        print(json.dumps(classifier.health(), indent=2))
        return 0

    if not args.interactive and not args.text:
        parser.print_help()
        print("\nNo description supplied. Try:\n")
        print('  python ml/predictor.py "VPN keeps disconnecting at home"')
        return 1

    if not classifier.is_ready:
        print(
            "WARNING: the fine-tuned checkpoint is not available.\n"
            f"         Running the development keyword fallback instead.\n"
            f"         Reason: {classifier.load_error}\n"
            f"         Fix:    python ml/train.py\n"
        )

    if args.interactive:
        return interactive(classifier)

    results: List[Dict[str, object]] = []
    for text in args.text:
        started = time.time()
        result = classifier.predict(text)
        elapsed_ms = (time.time() - started) * 1000
        result["latency_ms"] = round(elapsed_ms, 1)
        result["input"] = text
        results.append(result)
        if not args.json:
            print_result(text, result, elapsed_ms)

    if args.json:
        print(json.dumps(results if len(results) > 1 else results[0], indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
