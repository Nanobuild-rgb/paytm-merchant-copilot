"""Growth-advisor insight cards: CFO view, Growth/demand view, Founder
snapshot. Every number here is computed directly in Python from the same
sales/stock/suppliers/cash data and the same recommendation log the core
flow uses -- these are a different lens on real numbers, never a fresh
LLM guess. Keeps the same "never invent numbers" guarantee as the main
reorder flow.
"""
from collections import defaultdict
from datetime import date

from core import data as data_mod


def _item_price(item, suppliers):
    sup_list = suppliers.get(item)
    if not sup_list:
        return None
    return data_mod.cheapest_supplier(sup_list)["price_per_unit"]


def cfo_view(plan, suppliers, lang="en"):
    available = plan["cash_summary"]["available"]
    planned = plan["cash_summary"]["planned_spend"]
    remaining = plan["cash_summary"]["remaining"]
    unmet_value = sum(c["cost"] for c in plan["deferred_items"])
    dead_value = sum(
        (_item_price(d["item"], suppliers) or 0) * d["current_stock"]
        for d in plan["dead_stock_items"]
    )
    pct_covered = round(100 * planned / available, 0) if available else 0

    if lang == "hi":
        lines = [
            f"Aaj aapke paas Rs.{available:.0f} hain. Is order cycle mein Rs.{planned:.0f} kharch ho raha hai ({pct_covered:.0f}% of available cash), Rs.{remaining:.0f} bach raha hai.",
            f"Jo order abhi afford nahi ho paya uski value Rs.{unmet_value:.0f} hai — yeh woh maal hai jo chahiye tha par cash kam pada.",
        ]
        if dead_value > 0:
            lines.append(f"Rs.{dead_value:.0f} ka dead stock bhi godaam mein pada hai (30 din mein bikri zero) — yeh cash wapas la sakta hai agar clear kiya jaaye.")
    else:
        lines = [
            f"Available cash today: Rs.{available:.0f}. This cycle plans to spend Rs.{planned:.0f} ({pct_covered:.0f}% of available cash), leaving Rs.{remaining:.0f}.",
            f"Rs.{unmet_value:.0f} of needed stock had to be deferred purely because of cash, not demand.",
        ]
        if dead_value > 0:
            lines.append(f"Rs.{dead_value:.0f} is sitting in dead stock (zero sales in 30 days) — clearing it would free up cash.")
    return {"title_key": "cfo_title", "lines": lines, "metrics": {
        "available": available, "planned": planned, "remaining": remaining,
        "unmet_value": round(unmet_value, 2), "dead_value": round(dead_value, 2),
    }}


def growth_view(sales, plan, lang="en"):
    by_item = defaultdict(list)
    for r in sales:
        by_item[r["item"]].append(r)

    movers = sorted(
        ({"item": item, "avg": sum(r["qty_sold"] for r in rows) / len(rows)} for item, rows in by_item.items() if rows),
        key=lambda x: -x["avg"],
    )[:3]

    weekend_signal = []
    for item, rows in by_item.items():
        weekend_vals, weekday_vals = [], []
        for r in rows:
            try:
                d = date.fromisoformat(r["date"])
            except ValueError:
                continue
            (weekend_vals if d.weekday() >= 5 else weekday_vals).append(r["qty_sold"])
        if weekend_vals and weekday_vals:
            we_avg, wd_avg = sum(weekend_vals) / len(weekend_vals), sum(weekday_vals) / len(weekday_vals)
            if wd_avg > 0 and we_avg / wd_avg >= 1.3:
                weekend_signal.append((item, round(we_avg / wd_avg, 1)))
    weekend_signal.sort(key=lambda x: -x[1])

    dead_items = [d["item"] for d in plan["dead_stock_items"]]

    if lang == "hi":
        lines = [f"Sabse zyada bikne wale: {', '.join(m['item'] for m in movers)}."]
        if weekend_signal:
            top = weekend_signal[0]
            lines.append(f"{top[0]} weekend par roz se {top[1]}x zyada bikta hai — Friday se pehle stock badha lo.")
        if dead_items:
            lines.append(f"{', '.join(dead_items)} mein 30 din se bikri nahi hui — discount ya return par vichaar karein.")
    else:
        lines = [f"Fastest-moving items: {', '.join(m['item'] for m in movers)}."]
        if weekend_signal:
            top = weekend_signal[0]
            lines.append(f"{top[0]} sells {top[1]}x more on weekends than weekdays — stock up before Friday.")
        if dead_items:
            lines.append(f"{', '.join(dead_items)} haven't sold at all in 30 days — consider a discount or a return to the supplier.")
    return {"title_key": "growth_title", "lines": lines, "metrics": {
        "top_movers": [m["item"] for m in movers], "weekend_signal": weekend_signal, "dead_items": dead_items,
    }}


def founder_snapshot(plan, log_rows, lang="en"):
    shown = [r for r in log_rows if r["event"] == "shown"]
    accepted = [r for r in log_rows if r["event"] == "accepted"]
    rejected = [r for r in log_rows if r["event"] == "rejected"]
    accept_rate = round(100 * len(accepted) / len(shown), 0) if shown else None

    n_reorder, n_deferred, n_dead = len(plan["reorder_list"]), len(plan["deferred_items"]), len(plan["dead_stock_items"])
    planned = plan["cash_summary"]["planned_spend"]

    if lang == "hi":
        lines = [
            f"Aaj: {n_reorder} item order ke liye ready (Rs.{planned:.0f}), {n_deferred} cash ki wajah se ruke, {n_dead} dead stock mein.",
        ]
        if accept_rate is not None:
            lines.append(f"Ab tak {len(shown)} recommendations dikhayi gayi, {len(accepted)} accept hui ({accept_rate:.0f}% accept rate), {len(rejected)} reject hui.")
        else:
            lines.append("Abhi tak koi recommendation log nahi hui.")
    else:
        lines = [
            f"Today: {n_reorder} item(s) ready to order (Rs.{planned:.0f}), {n_deferred} deferred for cash, {n_dead} sitting as dead stock.",
        ]
        if accept_rate is not None:
            lines.append(f"{len(shown)} recommendations shown so far, {len(accepted)} accepted ({accept_rate:.0f}% accept rate), {len(rejected)} rejected.")
        else:
            lines.append("No recommendations logged yet.")
    return {"title_key": "founder_title", "lines": lines, "metrics": {
        "n_reorder": n_reorder, "n_deferred": n_deferred, "n_dead": n_dead,
        "shown": len(shown), "accepted": len(accepted), "rejected": len(rejected), "accept_rate": accept_rate,
    }}
