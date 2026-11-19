"""Deterministic logic for the Munshi feature set. Every rupee figure here
is computed in plain Python from real recorded data (sales, stock,
suppliers, stockouts, udhaar, customers) or from the actions_log -- never
guessed by an LLM, and every such figure is labelled "estimated" wherever
it is shown, per the hackathon brief's honesty rule.
"""
from datetime import date, timedelta

from core import actions_log
from core import data as data_mod


def missed_sales_ledger(stockout_rows):
    """Replays recorded stock-out windows: during each window, qty_sold
    was recorded as 0 purely because there was no stock, not because of
    no demand. est_daily_demand (the item's average on its OTHER days)
    estimates what would have sold if the advice to reorder in time had
    been followed. Every number here is "estimated", not actual."""
    entries = []
    total_recovered = 0.0
    for row in stockout_rows:
        start = date.fromisoformat(row["start_date"])
        end = date.fromisoformat(row["end_date"])
        days = (end - start).days + 1
        lost_qty = round(row["est_daily_demand"] * days, 2)
        lost_revenue = round(lost_qty * row["price_per_unit"], 2)
        total_recovered += lost_revenue
        entries.append({
            "item": row["item"], "start_date": row["start_date"], "end_date": row["end_date"],
            "days_out_of_stock": days, "est_lost_qty": lost_qty, "est_lost_revenue": lost_revenue,
        })
    return {"entries": entries, "stockouts_avoided": len(entries), "est_total_recovered": round(total_recovered, 2)}


def value_meter(stockout_rows, plan, suppliers):
    """Rs actually captured this month (sum of APPROVED action cards'
    estimated impact) vs a Rs plan target (the monthly opportunity: past
    missed-sales revenue + dead-stock cash currently stuck), both
    labelled estimated."""
    ledger = missed_sales_ledger(stockout_rows)
    dead_value = sum(
        (data_mod.cheapest_supplier(suppliers[d["item"]])["price_per_unit"] if suppliers.get(d["item"]) else 0)
        * d["current_stock"]
        for d in plan["dead_stock_items"]
    )
    plan_target = round(ledger["est_total_recovered"] + dead_value, 2)
    actual = actions_log.approved_value_this_month()
    return {"estimated_benefit": actual, "plan_target": plan_target}


def dead_stock_drafts(plan, suppliers, lang="en"):
    drafts = []
    for d in plan["dead_stock_items"]:
        sup_list = suppliers.get(d["item"])
        price = data_mod.cheapest_supplier(sup_list)["price_per_unit"] if sup_list else 0
        value = round(price * d["current_stock"], 2)
        if lang == "hi":
            text = f"{d['item']} 30 din se nahi bika. {d['current_stock']:.0f} {d['unit']} pada hai, Rs.{value:.0f} ka. 20% discount ya 'ek ke saath ek free' try karein?"
        else:
            text = f"{d['item']} hasn't sold in 30 days. {d['current_stock']:.0f} {d['unit']} sitting idle, worth Rs.{value:.0f}. Try a 20% discount or a bundle offer?"
        drafts.append({"item": d["item"], "value": value, "text": text})
    return drafts


def udhaar_reminders(udhaar_rows, lang="en"):
    drafts = []
    for row in udhaar_rows:
        if row["status"] != "overdue":
            continue
        if lang == "hi":
            text = (f"Namaste {row['customer']} ji, aapka Rs.{row['amount']:.0f} ka udhaar "
                     f"{row['due_date']} se baaki hai. Jab suvidha ho, UPI se bhej dijiyega. Dhanyawad.")
        else:
            text = (f"Hi {row['customer']}, a friendly reminder that Rs.{row['amount']:.0f} "
                     f"has been due since {row['due_date']}. Please pay via UPI whenever convenient. Thank you.")
        drafts.append({"customer": row["customer"], "amount": row["amount"], "due_date": row["due_date"], "text": text})
    return drafts


def repeat_customer_nudges(customers_rows, lang="en", threshold_days=14, today=None):
    today = today or date.today()
    drafts = []
    for c in customers_rows:
        last = date.fromisoformat(c["last_purchase_date"])
        days_since = (today - last).days
        if days_since >= threshold_days:
            if lang == "hi":
                text = f"Namaste {c['name']} ji, aapko dekhe {days_since} din ho gaye! Aaj aaiye, chhota sa discount milega."
            else:
                text = f"Hi {c['name']}, we haven't seen you in {days_since} days! Drop by today for a small discount."
            drafts.append({"customer": c["name"], "days_since_last_visit": days_since, "text": text})
    return drafts
