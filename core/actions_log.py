"""Logs every Approve/Later/Reject decision on a Munshi action card.
Separate from core/logs.py (which logs the reorder-recommendation flow)
because these are discrete "card" decisions with an estimated rupee
impact -- the Value Meter sums only the approved ones.
"""
import csv
import os
from datetime import datetime

LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "actions_log.csv")
FIELDS = ["timestamp", "card_type", "title", "estimated_impact", "outcome"]


def _ensure_header():
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    if not os.path.exists(LOG_PATH):
        with open(LOG_PATH, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writeheader()


def log_action(card_type, title, estimated_impact, outcome):
    """outcome: "approved" | "later" | "rejected"."""
    _ensure_header()
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=FIELDS).writerow({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "card_type": card_type,
            "title": title,
            "estimated_impact": estimated_impact,
            "outcome": outcome,
        })


def read_actions(limit=100):
    _ensure_header()
    with open(LOG_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return list(reversed(rows))[:limit]


def approved_value_this_month():
    """Sum of estimated_impact for all "approved" actions logged (all
    rupee figures are estimates, by construction -- never claim actuals)."""
    total = 0.0
    for r in read_actions(10_000):
        if r["outcome"] == "approved":
            try:
                total += float(r["estimated_impact"])
            except (TypeError, ValueError):
                pass
    return round(total, 2)
