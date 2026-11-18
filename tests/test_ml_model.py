"""
Tests for the real DistilBERT classifier.

These do not mock the model: they load the trained checkpoint and run real
inference. That is the point, because a mocked classifier would prove nothing
about the deliverable.
"""
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.ml

MODEL_DIR = Path(__file__).resolve().parents[1] / "backend" / "app" / "ml" / "saved_model"

# One representative complaint per SRS category. The label is what a reviewer
# would expect a competent model to produce for that text.
CASES = [
    ("Software", "Microsoft Word crashes on startup every time I launch it"),
    ("Software", "Excel will not open the shared spreadsheet from the network drive"),
    ("Hardware", "My keyboard is not responding and several keys are dead"),
    ("Hardware", "The mouse pointer jumps around the screen and I cannot select text"),
    ("Network", "The office network is down and nothing loads for anyone"),
    ("Network", "The wifi in the meeting room is extremely slow and video calls freeze"),
    ("Login", "I forgot my company password and cannot log in at all"),
    ("Login", "My account gets locked after three failed login attempts"),
    ("VPN", "The VPN disconnects every few minutes while I work from home"),
    ("VPN", "I cannot connect to the VPN tunnel from my laptop at home"),
    ("Access", "I need access to the HR portal but I get an access denied error"),
    ("Access", "Please grant me read access to the shared analytics dashboard"),
]


@pytest.fixture(scope="module")
def classifier():
    from app.ml import predictor

    model = predictor.load_model(allow_fallback=False)
    assert model is not None
    return model


def test_checkpoint_files_are_present():
    """The trained artefacts must actually be on disk, not just referenced."""
    for name in ("config.json", "model.safetensors", "tokenizer.json",
                 "label_mappings.json", "vocab.txt"):
        assert (MODEL_DIR / name).exists(), f"missing {name}"


def test_label_mappings_match_the_srs():
    data = json.loads((MODEL_DIR / "label_mappings.json").read_text(encoding="utf-8"))
    labels = data.get("id_to_label") or data.get("label_to_id")
    values = set(labels.values()) if isinstance(labels, dict) else set(labels)
    assert values == {"Software", "Hardware", "Network", "Login", "VPN", "Access"}


def test_evaluation_report_is_present_and_sane():
    report = json.loads((MODEL_DIR / "evaluation_report.json").read_text(encoding="utf-8"))
    assert report["split"] == "test"
    assert report["split_rows"] > 0
    assert 0.0 <= report["accuracy"] <= 1.0
    assert len(report["per_class"]) == 6
    assert report["inference_ms_per_ticket"] > 0


def test_model_loads_without_fallback(classifier):
    assert classifier.is_ready is True
    assert classifier.health()["source"] == "distilbert"


def test_classifier_predicts_all_six_categories(classifier):
    for expected, text in CASES:
        result = classifier.predict(text)
        assert result["category"] == expected, (
            f"{text!r} -> {result['category']} (expected {expected}), "
            f"confidence {result.get('confidence')}"
        )


def test_predictions_are_confident(classifier):
    for expected, text in CASES:
        result = classifier.predict(text)
        assert result["confidence"] > 0.5, f"{text!r} confidence {result['confidence']}"


def test_predictions_carry_the_model_identity(classifier):
    result = classifier.predict("The VPN disconnects every few minutes")
    assert result["model"]
    assert "distilbert" in result["model"].lower()


def test_classification_is_deterministic(classifier):
    text = "I cannot log in and the reset email never arrives"
    first = classifier.predict(text)
    second = classifier.predict(text)
    assert first["category"] == second["category"]
    assert abs(first["confidence"] - second["confidence"]) < 1e-6


def test_top_k_lists_several_candidates(classifier):
    result = classifier.predict("The printer is not working")
    assert len(result["top_k"]) == 3
    scores = [entry["confidence"] for entry in result["top_k"]]
    assert scores == sorted(scores, reverse=True)
    assert result["top_k"][0]["category"] == result["category"]
    assert abs(result["top_k"][0]["confidence"] - result["confidence"]) < 1e-6


def test_inference_is_well_inside_the_three_second_budget(classifier):
    """The SRS allows 3 seconds per ticket; CPU inference is ~120ms."""
    import time

    text = "The entire office network is down and nobody can work"
    start = time.perf_counter()
    classifier.predict(text)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 3000, f"took {elapsed_ms:.0f}ms"


def test_model_is_loaded_only_once(classifier):
    """The Flask app loads it at startup; a second load must not re-read disk."""
    from app.ml import predictor

    again = predictor.load_model(allow_fallback=False)
    assert again is classifier


def test_blank_input_is_refused_rather_than_guessed(classifier):
    """The validator rejects empty descriptions first; the model refuses too.

    Returning ``None`` here is deliberate. A ticket can never be classified
    without text, so silently returning "Software" would be a fabricated
    result dressed up as a prediction.
    """
    result = classifier.predict("")
    assert result["category"] is None
    assert result["source"] == "empty"
    assert result["confidence"] == 0.0


def test_gibberish_still_returns_a_valid_label(classifier):
    result = classifier.predict("zzzz qqqq xxxx vvvv nonsense tokens 12345")
    assert result["category"] in {"Software", "Hardware", "Network", "Login", "VPN", "Access"}


def test_very_long_input_is_truncated_not_rejected(classifier):
    result = classifier.predict("the printer is not working " * 500)
    assert result["category"] in {"Software", "Hardware", "Network", "Login", "VPN", "Access"}