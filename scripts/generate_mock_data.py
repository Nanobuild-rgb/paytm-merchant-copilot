"""Generates the mock kirana dataset: data/sales.csv, data/stock.csv,
data/suppliers.csv, data/cash.json. Deterministic (seeded) so re-running
reproduces the same numbers.

20 items, 30 days of sales with weekday variation, 2 suppliers, 2 items
about to stock out, 2 dead-stock items (zero sales in 30 days), and
available cash too low to cover every reorder.
"""
import csv
import json
import os
import random
from datetime import date, timedelta

random.seed(42)

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(OUT_DIR, exist_ok=True)

SUPPLIER_A = "Sharma Kirana Wholesale"
SUPPLIER_B = "Gupta General Stores"

# item: unit, avg_daily_sales, weekend_multiplier, price_per_unit, pack_size,
#       supplier, lead_time_days, current_stock
ITEMS = {
    "Atta":            dict(unit="kg",    avg=8.0,  wk=1.0, price=45,  pack=10,  sup=SUPPLIER_A, lead=1, stock=10),
    "Chini":           dict(unit="kg",    avg=5.0,  wk=1.0, price=44,  pack=10,  sup=SUPPLIER_A, lead=2, stock=40),
    "Chawal":          dict(unit="kg",    avg=6.0,  wk=1.0, price=38,  pack=25,  sup=SUPPLIER_A, lead=2, stock=55),
    "Toor Dal":        dict(unit="kg",    avg=3.0,  wk=1.0, price=140, pack=10,  sup=SUPPLIER_A, lead=2, stock=25),
    "Chana Dal":       dict(unit="kg",    avg=2.0,  wk=1.0, price=90,  pack=10,  sup=SUPPLIER_A, lead=2, stock=18),
    "Namak":           dict(unit="kg",    avg=1.0,  wk=1.0, price=20,  pack=10,  sup=SUPPLIER_A, lead=2, stock=22),
    "Sunflower Tel":   dict(unit="litre", avg=4.0,  wk=1.0, price=150, pack=15,  sup=SUPPLIER_A, lead=3, stock=30),
    "Maida":           dict(unit="kg",    avg=2.0,  wk=1.0, price=42,  pack=10,  sup=SUPPLIER_A, lead=1, stock=20),
    "Besan":           dict(unit="kg",    avg=1.5,  wk=1.0, price=85,  pack=10,  sup=SUPPLIER_A, lead=2, stock=15),
    "Chai Patti":      dict(unit="kg",    avg=1.0,  wk=1.0, price=320, pack=5,   sup=SUPPLIER_B, lead=2, stock=8),
    "Sabun":           dict(unit="piece", avg=10.0, wk=1.0, price=35,  pack=12,  sup=SUPPLIER_B, lead=2, stock=8),
    "Detergent":       dict(unit="kg",    avg=3.0,  wk=1.0, price=60,  pack=5,   sup=SUPPLIER_B, lead=2, stock=12),
    "Parle-G Biscuit": dict(unit="piece", avg=15.0, wk=1.2, price=10,  pack=100, sup=SUPPLIER_B, lead=3, stock=60),
    "Maggi":           dict(unit="piece", avg=12.0, wk=1.2, price=14,  pack=48,  sup=SUPPLIER_B, lead=3, stock=45),
    "Lays Chips":      dict(unit="piece", avg=8.0,  wk=1.8, price=20,  pack=48,  sup=SUPPLIER_B, lead=3, stock=40),
    "Cold Drink":      dict(unit="bottle",avg=6.0,  wk=1.8, price=40,  pack=24,  sup=SUPPLIER_B, lead=3, stock=36),
    "Maachis":         dict(unit="piece", avg=0.0,  wk=1.0, price=1,   pack=100, sup=SUPPLIER_A, lead=5, stock=200),
    "Agarbatti":       dict(unit="piece", avg=2.0,  wk=1.0, price=25,  pack=50,  sup=SUPPLIER_B, lead=4, stock=35),
    "Toothpaste":      dict(unit="piece", avg=3.0,  wk=1.1, price=55,  pack=24,  sup=SUPPLIER_B, lead=3, stock=28),
    "Shampoo Sachet":  dict(unit="piece", avg=0.0,  wk=1.0, price=2,   pack=100, sup=SUPPLIER_A, lead=5, stock=150),
}

# Chini also available from Supplier B at a slightly different price/lead time
# (covers the "two suppliers for one item" test case).
EXTRA_SUPPLIER_ROWS = [
    dict(item="Chini", unit="kg", price=46, pack=10, sup=SUPPLIER_B, lead=1),
]

TODAY = date(2026, 11, 19)
START = TODAY - timedelta(days=30)


def gen_sales():
    rows = []
    for item, cfg in ITEMS.items():
        for d in range(30):
            day = START + timedelta(days=d)
            if cfg["avg"] == 0.0:
                qty = 0
            else:
                is_weekend = day.weekday() >= 5  # Sat/Sun
                mult = cfg["wk"] if is_weekend else 1.0
                noise = random.uniform(0.75, 1.25)
                qty = max(0, round(cfg["avg"] * mult * noise))
            rows.append({"item": item, "date": day.isoformat(), "qty_sold": qty})
    with open(os.path.join(OUT_DIR, "sales.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["item", "date", "qty_sold"])
        w.writeheader()
        w.writerows(rows)
    return rows


def gen_stock():
    with open(os.path.join(OUT_DIR, "stock.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["item", "unit", "current_stock"])
        w.writeheader()
        for item, cfg in ITEMS.items():
            w.writerow({"item": item, "unit": cfg["unit"], "current_stock": cfg["stock"]})


def gen_suppliers():
    with open(os.path.join(OUT_DIR, "suppliers.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["supplier", "item", "unit", "price_per_unit", "pack_size", "lead_time_days"])
        w.writeheader()
        for item, cfg in ITEMS.items():
            w.writerow({
                "supplier": cfg["sup"], "item": item, "unit": cfg["unit"],
                "price_per_unit": cfg["price"], "pack_size": cfg["pack"],
                "lead_time_days": cfg["lead"],
            })
        for row in EXTRA_SUPPLIER_ROWS:
            w.writerow({
                "supplier": row["sup"], "item": row["item"], "unit": row["unit"],
                "price_per_unit": row["price"], "pack_size": row["pack"],
                "lead_time_days": row["lead"],
            })


def gen_cash():
    # Sum of what a naive "buy everything that's needed" would cost, then
    # deliberately fund well under that so the reasoning step must prioritise.
    total_need_cost = 0
    for item, cfg in ITEMS.items():
        if cfg["avg"] == 0.0:
            continue
        need_qty = cfg["avg"] * (cfg["lead"] + 2) - cfg["stock"]
        if need_qty > 0:
            packs = -(-need_qty // cfg["pack"])  # ceil
            total_need_cost += packs * cfg["pack"] * cfg["price"]
    available = round(total_need_cost * 0.45, -2)  # ~45% of full need, rounded to nearest 100
    with open(os.path.join(OUT_DIR, "cash.json"), "w") as f:
        json.dump({"available_cash": available, "as_of": TODAY.isoformat()}, f, indent=2)
    return total_need_cost, available


if __name__ == "__main__":
    gen_sales()
    gen_stock()
    gen_suppliers()
    total_need, available = gen_cash()
    print(f"Full reorder need would cost ~Rs.{total_need:.0f}; available cash funded at Rs.{available:.0f}")
    print("Mock data written to data/")
