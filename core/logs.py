"""Append-only log of every recommendation shown/accepted/rejected, with a
timestamp. This is the traction-proof data: recommendations accepted,
stock-outs avoided, time saved."""
import csv
import os
from datetime import datetime

LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "logs", "recommendations.csv")
FIELDS = ["timestamp", "event", "intent", "merchant_message", "items", "total_cost", "needs_human", "used_fallback"]


def _ensure_header():
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    if not os.path.exists(LOG_PATH):
        with open(LOG_PATH, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writeheader()


def log_event(event, intent, merchant_message, items, total_cost, needs_human, used_fallback):
    """event: "shown" | "accepted" | "rejected". items: list of item names."""
    _ensure_header()
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=FIELDS).writerow({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "event": event,
            "intent": intent,
            "merchant_message": merchant_message,
            "items": ";".join(items or []),
            "total_cost": total_cost,
            "needs_human": needs_human,
            "used_fallback": used_fallback,
        })


def read_log(limit=20):
    _ensure_header()
    with open(LOG_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return list(reversed(rows))[:limit]
