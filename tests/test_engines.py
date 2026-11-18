"""
Unit tests for the two deterministic engines.

These are pure functions, so they are tested without a database or the model.
Both engines are deliberately auditable: routing and priority can both explain
exactly which rule fired, which is what the tests below pin down.
"""
import pytest

from app.services import priority_engine, routing_engine

pytestmark = pytest.mark.ml


# ---------------------------------------------------------------------------
# Routing engine (SRS section 7)
# ---------------------------------------------------------------------------
def test_routing_table_matches_the_srs():
    assert routing_engine.load_routing_table() == {
        "Software": "Software Team",
        "Hardware": "Hardware Team",
        "Network": "Network Team",
        "VPN": "Network Team",
        "Login": "Security Team",
        "Access": "Security Team",
    }


@pytest.mark.parametrize("category,team", [
    ("Software", "Software Team"),
    ("Hardware", "Hardware Team"),
    ("Network", "Network Team"),
    ("VPN", "Network Team"),
    ("Login", "Security Team"),
    ("Access", "Security Team"),
])
def test_every_srs_category_routes_correctly(category, team):
    assert routing_engine.route_ticket(category) == team


def test_routing_covers_all_six_categories_and_four_teams():
    table = routing_engine.load_routing_table()
    assert set(table) == set(routing_engine.CATEGORIES)
    assert len(routing_engine.CATEGORIES) == 6
    teams = routing_engine.all_teams()
    assert len(teams) == 4
    for team, description in teams.items():
        assert description


def test_unknown_category_falls_back_instead_of_raising():
    assert routing_engine.route_ticket("Nonsense") == routing_engine.FALLBACK_TEAM


def test_case_and_spacing_are_tolerated():
    assert routing_engine.route_ticket("  software ") == "Software Team"
    assert routing_engine.route_ticket("VPN") == "Network Team"


def test_route_and_describe_returns_the_team_and_its_description():
    result = routing_engine.route_and_describe("Login")
    assert result["assigned_team"] == "Security Team"
    assert result["team_description"]
    assert result["category"] == "Login"


def test_teams_for_category_is_the_inverse_of_the_table():
    assert routing_engine.teams_for_category("Network Team") == ("Network", "VPN")
    assert set(routing_engine.teams_for_category("Security Team")) == {"Login", "Access"}
    assert routing_engine.teams_for_category("Software Team") == ("Software",)


def test_every_team_has_a_description():
    for team in routing_engine.all_teams():
        assert routing_engine.TEAM_DESCRIPTIONS.get(team)


# ---------------------------------------------------------------------------
# Priority engine
# ---------------------------------------------------------------------------
def test_default_rules_cover_the_four_srs_priorities():
    rules = priority_engine.load_rules()
    assert priority_engine.PRIORITIES == ("Low", "Medium", "High", "Critical")
    assert set(rules.thresholds) <= set(priority_engine.PRIORITIES)


def test_explicit_impact_language_escalates():
    decision = priority_engine.predict_priority("the entire system is down and many users cannot work")
    assert decision["priority"] == "Critical"


def test_urgent_alone_is_high_not_critical():
    """Critical needs broad impact, not just the word 'urgent'."""
    decision = priority_engine.predict_priority("Urgent: I need my password reset")
    assert decision["priority"] == "High"


def test_casual_wording_stays_low():
    decision = priority_engine.predict_priority(
        "Could you please share the seating plan document?"
    )
    assert decision["priority"] == "Low"


def test_hardware_failure_is_at_least_medium():
    decision = priority_engine.predict_priority("My keyboard is not responding and I cannot type")
    assert decision["priority"] in {"Medium", "High"}


def test_full_outage_reaches_critical():
    decision = priority_engine.predict_priority(
        "The entire system is down and many users cannot work at all"
    )
    assert decision["priority"] == "Critical"


def test_prediction_is_deterministic():
    text = "VPN disconnects every few minutes and I cannot work from home"
    first = priority_engine.predict_priority(text)
    second = priority_engine.predict_priority(text)
    assert first == second


def test_explanation_names_the_triggering_rules():
    """Every decision must be traceable, per the SRS auditability requirement."""
    decision = priority_engine.predict_priority("URGENT: the whole office network is down")
    assert decision["explanation"]
    assert "Scored" in decision["explanation"]
    assert decision["matched_keywords"]


def test_title_and_description_both_influence_priority():
    plain = priority_engine.predict_priority("something is wrong", title="", description="")
    urgent = priority_engine.predict_priority(
        "something is wrong", title="URGENT outage affecting the whole office", description=""
    )
    assert urgent["score"] > plain["score"]


def test_empty_input_defaults_low_without_raising():
    decision = priority_engine.predict_priority("")
    assert decision["priority"] == "Low"
    assert decision["score"] == 0
    assert decision["explanation"]


def test_very_long_input_is_handled():
    decision = priority_engine.predict_priority("word " * 5000)
    assert decision["priority"] in priority_engine.PRIORITIES


def test_punctuation_and_case_do_not_change_the_outcome():
    lower = priority_engine.predict_priority("my keyboard is not responding")
    shouted = priority_engine.predict_priority("MY KEYBOARD IS NOT RESPONDING!!!")
    assert lower["priority"] == shouted["priority"]


def test_priority_is_monotonic_in_severity():
    rank = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    low = priority_engine.predict_priority("could you share the document please")
    high = priority_engine.predict_priority(
        "the entire system is down and many users cannot work"
    )
    assert rank[high["priority"]] <= rank[low["priority"]]


def test_score_matches_the_reported_priority_band():
    """The score and the label must not disagree, whatever the input."""
    rules = priority_engine.load_rules()
    samples = [
        "URGENT the entire system is down",
        "my keyboard is not responding",
        "the printer is not working",
        "could you share the seating plan",
        "urgent password reset needed",
        "cannot log in at all",
    ]
    for sample in samples:
        decision = priority_engine.predict_priority(sample)
        assert rules.score_to_priority(decision["score"]) == decision["priority"], (
            f"{sample!r}: score {decision['score']} -> {decision['priority']}, "
            f"threshold table says {rules.score_to_priority(decision['score'])}"
        )


def test_custom_rules_are_honoured(tmp_path):
    """Rules are data, not code, so a deployment can retune them."""
    import json

    config = {
        "base_score": 0,
        "keyword_tiers": {
            "critical": {"weight": 100, "phrases": ["cake"]},
            "high": {"weight": 10, "phrases": []},
            "medium": {"weight": 5, "phrases": []},
            "low": {"weight": 1, "phrases": []},
        },
        "modifiers": {},
        "thresholds": {"Critical": 100, "High": 10, "Medium": 5, "Low": 0},
    }
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    rules = priority_engine.load_rules(str(path))
    decision = priority_engine.predict_priority("I would like some cake", rules=rules)
    assert decision["priority"] == "Critical"


def test_prediction_is_a_superset_of_the_srs_contract():
    decision = priority_engine.predict_priority("the printer is not working")
    # The SRS only requires {"priority": ...}; the extras are for the UI audit.
    assert set(decision) >= {"priority", "score", "explanation", "matched_keywords"}
    assert decision["priority"] in priority_engine.PRIORITIES
    assert priority_engine.priority_is_valid(decision["priority"])