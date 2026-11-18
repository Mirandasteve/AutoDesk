"""
Replay ``docs/autodesk.postman_collection.json`` against the live API.

Runs the requests in collection order and applies the same variable capture the
Postman test scripts perform, so the documentation cannot drift from the API
without this failing. Used while writing the collection; kept as a repeatable
check because a reviewer should be able to trust the collection they import.

Usage (backend directory)::

    flask --app run.py reset-db --yes
    python replay_postman_collection.py

Note that the replay mutates data - it changes a demo password, promotes a user,
claims and resolves a ticket. Reseed afterwards.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Tuple
from urllib.parse import parse_qs, urlparse

from app import create_app

COLLECTION = os.path.join(os.path.dirname(__file__), "..", "docs", "autodesk.postman_collection.json")

# Register and logout are skipped: they create a duplicate account and revoke the
# admin token, which would break every request after them.
SKIP_SUFFIXES = ("/api/auth/register", "/api/auth/logout")


def substitute(value: str, variables: Dict[str, Any]) -> str:
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(variables.get(m.group(1), m.group(1))), value)


def main() -> int:
    with open(COLLECTION, encoding="utf-8") as handle:
        collection = json.load(handle)

    variables: Dict[str, Any] = {"baseUrl": "http://127.0.0.1:5000"}
    app = create_app("testing")
    results: List[Tuple[str, int, bool]] = []

    with app.test_client() as client:
        for folder in collection["item"]:
            print(f"\n{folder['name']}")
            for item in folder["item"]:
                request = item["request"]
                raw_url = request["url"]["raw"]

                if raw_url.endswith(SKIP_SUFFIXES):
                    print(f"  SKIP  {item['name']} (would mutate the demo accounts)")
                    continue

                raw = substitute(raw_url, variables)
                # Drop the `http://host:port` part and keep the path, so the test
                # client treats it as a Flask route rather than an absolute URL.
                parsed = urlparse(raw)
                path = parsed.path or "/"
                query = {
                    **{k: v[-1] for k, v in parse_qs(parsed.query).items()},
                    **{
                        q["key"]: substitute(str(q["value"]), variables)
                        for q in request["url"].get("query", [])
                    },
                }

                headers: Dict[str, str] = {}
                auth = request.get("auth")
                if auth:
                    # `substitute` returns the variable's value, not its name.
                    token = substitute(auth["bearer"][0]["value"], variables)
                    if token and not token.startswith("{{"):
                        headers["Authorization"] = f"Bearer {token}"

                body = None
                if request.get("body"):
                    body = json.loads(substitute(request["body"]["raw"], variables))

                response = client.open(
                    path,
                    method=request["method"].upper(),
                    query_string=query,
                    json=body,
                    headers=headers,
                )

                # Mirror the Postman test scripts' variable capture.
                data = (response.get_json() or {}).get("data") or {}
                if isinstance(data, dict):
                    token = data.get("access_token")
                    if token:
                        for role in ("employee", "agent", "admin"):
                            if role in item["name"].lower():
                                variables[f"{role}Token"] = token
                    if item["name"] == "Create ticket" and isinstance(data.get("ticket"), dict):
                        variables["ticketId"] = data["ticket"]["id"]
                    if item["name"] == "Users":
                        rows = data.get("items", data)
                        employee = next(
                            (u for u in rows if u.get("role") == "employee"),
                            None,
                        )
                        if employee:
                            variables["employeeUserId"] = employee["id"]

                # A request whose `expected` list contains this status is proving
                # that a rule is enforced, so a 4xx is the correct outcome.
                expected = item.get("expected", [200, 201])
                ok = response.status_code in expected
                results.append((f"{folder['name']} / {item['name']}", response.status_code, ok))
                marker = "ok  " if ok else "FAIL"
                print(f"  {marker} {response.status_code}  {item['name']}")

    failed = [r for r in results if not r[2]]
    print("\n" + "=" * 60)
    print(f"{len(results) - len(failed)}/{len(results)} collection requests behaved as documented")
    if failed:
        for name, status, _ in failed:
            print(f"  FAILED (got {status})  {name}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())