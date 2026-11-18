"""
AutoDesk - Routing Engine
=========================

Maps a predicted ticket *category* onto the owning support team.

The mapping below is transcribed verbatim from the SRS (section 7) and is the
single source of truth for the whole application::

    Software  -> Software Team
    Hardware  -> Hardware Team
    Network   -> Network Team
    Login     -> Security Team
    VPN       -> Network Team
    Access    -> Security Team

Nothing else in the codebase is allowed to hardcode a category -> team pair.
"""

from __future__ import annotations

import logging
import os
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical categories (must match database CHECK constraint + label_mappings)
# ---------------------------------------------------------------------------
CATEGORIES: Tuple[str, ...] = ("Software", "Hardware", "Network", "Login", "VPN", "Access")
CATEGORY_SET = frozenset(CATEGORIES)

#: SRS support-team routing table.
DEFAULT_ROUTING_TABLE: Dict[str, str] = {
    "Software": "Software Team",
    "Hardware": "Hardware Team",
    "Network": "Network Team",
    "Login": "Security Team",
    "VPN": "Network Team",
    "Access": "Security Team",
}

#: Every team the helpdesk can route to, with a short description used by the
#: admin dashboard / team-performance analytics.
TEAM_DESCRIPTIONS: Dict[str, str] = {
    "Software Team": "Application installs, Office, IDEs and licensed software faults",
    "Hardware Team": "Laptops, desktops, monitors, printers and peripherals",
    "Network Team": "LAN, Wi-Fi, internet connectivity and VPN tunnels",
    "Security Team": "Accounts, credentials, MFA and access rights",
}

FALLBACK_TEAM = "Network Team"


def load_routing_table() -> Dict[str, str]:
    """
    Return the active routing table.

    ``ROUTING_TABLE_FILE`` may point at a JSON file of ``{category: team}`` to
    override the defaults without editing code.
    """
    path = os.getenv("ROUTING_TABLE_FILE")
    if not path:
        return dict(DEFAULT_ROUTING_TABLE)

    try:
        import json

        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        table = {str(k): str(v) for k, v in raw.items()}
        missing = [c for c in CATEGORIES if c not in table]
        if missing:
            raise ValueError(f"override is missing categories: {', '.join(missing)}")
        logger.info("Routing table loaded from %s", path)
        return table
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(
            "Could not load routing table from %s (%s); using SRS defaults", path, exc
        )
        return dict(DEFAULT_ROUTING_TABLE)


def route_ticket(category: str) -> str:
    """
    Return the support team that owns *category*.

    Unknown categories are routed to :data:`FALLBACK_TEAM` and logged, so a
    bad prediction can never crash ticket submission.
    """
    if not isinstance(category, str):
        logger.warning("route_ticket() received non-string category %r", type(category))
        return FALLBACK_TEAM

    key = category.strip()
    table = load_routing_table()

    # Case-insensitive lookup, exact match first.
    if key in table:
        return table[key]
    for known_category, team in table.items():
        if known_category.lower() == key.lower():
            return team

    logger.warning("Unknown category %r - routing to %s", category, FALLBACK_TEAM)
    return FALLBACK_TEAM


def route_and_describe(category: str) -> Dict[str, Optional[str]]:
    """Convenience wrapper returning the team plus its description."""
    team = route_ticket(category)
    return {
        "category": category if category in CATEGORY_SET else None,
        "assigned_team": team,
        "team_description": TEAM_DESCRIPTIONS.get(team),
    }


def all_teams() -> Dict[str, str]:
    """Every team present in the routing table, mapped to its description."""
    return {team: TEAM_DESCRIPTIONS.get(team, "") for team in load_routing_table().values()}


def teams_for_category(category: str) -> Tuple[str, ...]:
    """All categories handled by a team (e.g. Network Team -> Network, VPN)."""
    table = load_routing_table()
    return tuple(sorted(c for c, team in table.items() if team == category))
