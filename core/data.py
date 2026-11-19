"""Deterministic data loading and reorder-plan computation.

All arithmetic (averages, order quantities, costs, cash-fit) happens here
in plain Python -- never inside the LLM. reasoning.py only asks the model
to turn these already-computed numbers into natural-language text.
"""
import csv
import json
import os
from collections import defaultdict
from math import ceil

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def load_sales(path=None):
    path = path or os.path.join(DATA_DIR, "sales.csv")
    rows = []
    with open(path) as f:
        for r in csv.DictReader(f):
            rows.append({"item": r["item"], "date": r["date"], "qty_sold": int(r["qty_sold"])})
    return rows


def load_stock(path=None):
    path = path or os.path.join(DATA_DIR, "stock.csv")
    stock = {}
    with open(path) as f:
        for r in csv.DictReader(f):
            stock[r["item"]] = {"unit": r["unit"], "current_stock": float(r["current_stock"])}
    return stock


def save_stock(stock, path=None):
    path = path or os.path.join(DATA_DIR, "stock.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["item", "unit", "current_stock"])
        w.writeheader()
        for item, rec in stock.items():
            w.writerow({"item": item, "unit": rec["unit"], "current_stock": rec["current_stock"]})


def load_suppliers(path=None):
    path = path or os.path.join(DATA_DIR, "suppliers.csv")
    suppliers = defaultdict(list)
    with open(path) as f:
        for r in csv.DictReader(f):
            lead = r["lead_time_days"]
            suppliers[r["item"]].append({
                "supplier": r["supplier"],
                "unit": r["unit"],
                "price_per_unit": float(r["price_per_unit"]),
                "pack_size": float(r["pack_size"]),
                "lead_time_days": int(lead) if lead not in (None, "") else None,
            })
    return dict(suppliers)


def load_stockouts(path=None):
    path = path or os.path.join(DATA_DIR, "stockouts.csv")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [
            {
                "item": r["item"], "start_date": r["start_date"], "end_date": r["end_date"],
                "est_daily_demand": float(r["est_daily_demand"]), "price_per_unit": float(r["price_per_unit"]),
            }
            for r in csv.DictReader(f)
        ]


def load_udhaar(path=None):
    path = path or os.path.join(DATA_DIR, "udhaar.csv")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [
            {"customer": r["customer"], "amount": float(r["amount"]), "due_date": r["due_date"], "status": r["status"]}
            for r in csv.DictReader(f)
        ]


def load_customers(path=None):
    path = path or os.path.join(DATA_DIR, "customers.csv")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [
            {"name": r["name"], "phone": r["phone"], "last_purchase_date": r["last_purchase_date"],
             "total_spend_30d": float(r["total_spend_30d"])}
            for r in csv.DictReader(f)
        ]


def load_cash(path=None):
    path = path or os.path.join(DATA_DIR, "cash.json")
    with open(path) as f:
        return float(json.load(f)["available_cash"])


def load_cash_full(path=None):
    """Full cash.json dict (available_cash, as_of, emi_due_amount, emi_due_date)."""
    path = path or os.path.join(DATA_DIR, "cash.json")
    with open(path) as f:
        return json.load(f)


def compute_emi_reserve(cash_data, today=None, window_days=7):
    """Set aside the EMI only if it's due within `window_days` -- otherwise
    today's reorder decision doesn't need to worry about it yet.

    Returns (reserved_amount, usable_cash). usable_cash is never negative;
    if the EMI exceeds available cash, the whole available amount is
    reserved and usable_cash is 0 (nothing left to reorder with).
    """
    from datetime import date as _date

    available = float(cash_data.get("available_cash", 0) or 0)
    emi_amount = float(cash_data.get("emi_due_amount", 0) or 0)
    emi_date_str = cash_data.get("emi_due_date")

    if today is None:
        as_of = cash_data.get("as_of")
        today = _date.fromisoformat(as_of) if as_of else _date.today()
    elif isinstance(today, str):
        today = _date.fromisoformat(today)

    if not emi_amount or not emi_date_str:
        return 0.0, round(available, 2)

    emi_date = _date.fromisoformat(emi_date_str)
    days_until = (emi_date - today).days
    if 0 <= days_until <= window_days:
        reserved = min(emi_amount, available)
        return round(reserved, 2), round(max(0.0, available - reserved), 2)
    return 0.0, round(available, 2)


def avg_daily_sales(sales_rows, item):
    vals = [r["qty_sold"] for r in sales_rows if r["item"] == item]
    if not vals:
        return 0.0, 0
    return sum(vals) / len(vals), len(vals)


def cheapest_supplier(suppliers_for_item):
    """Lowest price per unit; ties broken by shorter lead time."""
    return sorted(
        suppliers_for_item,
        key=lambda s: (s["price_per_unit"], s["lead_time_days"] if s["lead_time_days"] is not None else 999),
    )[0]


def build_reorder_plan(sales_rows, stock, suppliers, available_cash, buffer_days=2, min_history_days=7):
    """Returns a fully-computed, deterministic plan. No LLM involved.

    Keys: reorder_list, deferred_items, dead_stock_items, missed_opportunities,
    cash_summary, warnings, needs_human.
    """
    all_items = sorted(set(stock.keys()) | {r["item"] for r in sales_rows})
    candidates = []
    dead_stock = []
    warnings = []
    needs_human = False

    for item in all_items:
        avg, n_days = avg_daily_sales(sales_rows, item)

        if item not in stock:
            warnings.append(f"{item}: no stock record on file")
            needs_human = True
            continue

        cur_stock = stock[item]["current_stock"]
        unit = stock[item]["unit"]

        if cur_stock < 0:
            warnings.append(f"{item}: negative stock ({cur_stock}) -- data conflict")
            needs_human = True
            continue

        sup_list = suppliers.get(item)
        if not sup_list:
            warnings.append(f"{item}: no supplier on file, cannot reorder")
            needs_human = True
            continue

        if n_days == 0:
            warnings.append(f"{item}: no sales history at all")
            needs_human = True
            continue
        if n_days < min_history_days:
            warnings.append(f"{item}: only {n_days} day(s) of sales history (<{min_history_days})")
            needs_human = True

        if avg == 0.0:
            dead_stock.append({"item": item, "unit": unit, "current_stock": cur_stock})
            continue

        days_left = cur_stock / avg
        sup = cheapest_supplier(sup_list)
        lead = sup["lead_time_days"]
        if lead is None:
            warnings.append(f"{item}: missing lead time from supplier, assumed {buffer_days}d")
            needs_human = True
            lead = buffer_days

        need_qty = avg * (lead + buffer_days) - cur_stock
        if need_qty <= 0:
            continue  # already holds more than needed

        packs = ceil(need_qty / sup["pack_size"])
        order_qty = packs * sup["pack_size"]
        cost = round(order_qty * sup["price_per_unit"], 2)
        urgency = "high" if days_left <= 2 else ("medium" if days_left <= 5 else "low")

        candidates.append({
            "item": item,
            "unit": unit,
            "qty": order_qty,
            "unit_cost": sup["price_per_unit"],
            "cost": cost,
            "urgency": urgency,
            "days_left": round(days_left, 1),
            "supplier": sup["supplier"],
            "avg_daily_sales": round(avg, 2),
            "history_days": n_days,
        })

    candidates.sort(key=lambda c: c["days_left"])

    # Hard stop: once an item (in urgency order) would push planned_spend over
    # available cash, stop adding entirely -- that item and everything after
    # it go to deferred_items, even if a later item would individually fit.
    reorder_list, deferred = [], []
    planned_spend = 0.0
    stopped = False
    for c in candidates:
        if not stopped and planned_spend + c["cost"] <= available_cash:
            c["fits_cash"] = True
            reorder_list.append(c)
            planned_spend += c["cost"]
        else:
            stopped = True
            c["fits_cash"] = False
            deferred.append(c)

    missed_opportunities = deferred[:2]

    cash_summary = {
        "available": round(available_cash, 2),
        "planned_spend": round(planned_spend, 2),
        "remaining": round(available_cash - planned_spend, 2),
    }

    return {
        "reorder_list": reorder_list,
        "deferred_items": deferred,
        "dead_stock_items": dead_stock,
        "missed_opportunities": missed_opportunities,
        "cash_summary": cash_summary,
        "warnings": warnings,
        "needs_human": needs_human,
    }


def apply_stock_changes(stock, changes):
    """changes: list of {"item": str, "change": float}. Returns (new_stock, applied, rejected).

    applied: list of {"item","change","new_stock"}. rejected: list of {"item","reason"}.
    Unknown items or changes that would drive stock negative are rejected, never applied.
    """
    new_stock = {k: dict(v) for k, v in stock.items()}
    applied, rejected = [], []
    for ch in changes:
        item = ch.get("item")
        delta = ch.get("change")
        if item not in new_stock:
            rejected.append({"item": item, "reason": "unknown item, not in stock file"})
            continue
        try:
            delta = float(delta)
        except (TypeError, ValueError):
            rejected.append({"item": item, "reason": "invalid change amount"})
            continue
        proposed = new_stock[item]["current_stock"] + delta
        if proposed < 0:
            rejected.append({"item": item, "reason": f"would go negative ({proposed})"})
            continue
        new_stock[item]["current_stock"] = proposed
        applied.append({"item": item, "change": delta, "new_stock": proposed})
    return new_stock, applied, rejected
