"""Calls an LLM (Claude, or Gemini if that's the key available) to turn
pre-computed facts into natural-language output, then validates/repairs
the JSON against the deterministic truth in Python.

The model is never trusted with arithmetic. Every numeric field in the
final output is either copied straight from core.data's computation or
recomputed here in Python; only text fields (spoken_summary, reason,
supplier_message.text) come from the model.
"""
import json
import os

from core import data as data_mod

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "prompts", "v1.md")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")

REQUIRED_KEYS = [
    "intent", "language", "spoken_summary", "stock_changes", "reorder_list",
    "deferred_items", "missed_opportunities", "supplier_message",
    "cash_summary", "needs_approval", "needs_human", "confidence",
]


def load_system_prompt():
    with open(PROMPT_PATH, encoding="utf-8") as f:
        return f.read()


def get_provider():
    """Claude is the spec'd default; Gemini is used instead if that's the
    key actually available. Never both -- whichever key is set wins,
    Claude taking priority if both happen to be set."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    return None


def get_client():
    provider = get_provider()
    if provider == "anthropic":
        try:
            import anthropic
        except ImportError:
            return None
        return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    if provider == "gemini":
        try:
            from google import genai
        except ImportError:
            return None
        return genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return None


def build_context(sales, stock, suppliers, available_cash, min_history_days=7):
    plan = data_mod.build_reorder_plan(sales, stock, suppliers, available_cash, min_history_days=min_history_days)
    context = {
        "available_cash": available_cash,
        "stock": {item: rec["current_stock"] for item, rec in stock.items()},
        "stock_units": {item: rec["unit"] for item, rec in stock.items()},
        "reorder_plan": {
            "reorder_list": plan["reorder_list"],
            "deferred_items": plan["deferred_items"],
            "dead_stock_items": plan["dead_stock_items"],
            "missed_opportunities": plan["missed_opportunities"],
            "cash_summary": plan["cash_summary"],
        },
        "data_flags": {"needs_human": plan["needs_human"], "warnings": plan["warnings"]},
        "known_items": sorted(stock.keys()),
    }
    return context, plan


def _extract_json(raw_text):
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in model output")
    return json.loads(text[start:end + 1])


def call_model(client, merchant_message, context):
    system_prompt = load_system_prompt()
    user_payload = json.dumps({"merchant_message": merchant_message, "context": context}, ensure_ascii=False)
    provider = get_provider()

    if provider == "anthropic":
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=800,
            temperature=0.2,
            system=system_prompt,
            messages=[{"role": "user", "content": user_payload}],
        )
        raw_text = "".join(block.text for block in resp.content if getattr(block, "type", None) == "text")
        return _extract_json(raw_text)

    if provider == "gemini":
        from google.genai import types
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=user_payload,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.2,
                max_output_tokens=800,
                response_mime_type="application/json",
            ),
        )
        return _extract_json(resp.text)

    raise RuntimeError("no LLM provider configured")


def fallback_template(merchant_message, context, plan):
    """No-LLM deterministic fallback so a missing/failed API call never
    breaks the demo. Produces the same schema with plain, code-generated
    text (not localized, but accurate)."""
    reorder_list = [
        {"item": c["item"], "qty": c["qty"], "unit": c["unit"], "cost": c["cost"],
         "reason": f"{c['days_left']} days of stock left", "urgency": c["urgency"], "fits_cash": True}
        for c in plan["reorder_list"]
    ]
    deferred = [c["item"] for c in plan["deferred_items"]]
    missed = [c["item"] for c in plan["missed_opportunities"]]
    supplier_groups = {}
    for c in plan["reorder_list"]:
        supplier_groups.setdefault(c["supplier"], []).append(f"{c['qty']} {c['unit']} {c['item']}")
    if supplier_groups:
        supplier, items = next(iter(supplier_groups.items()))
        text = f"Please send: {', '.join(items)}. Thank you."
    else:
        supplier, text = "", ""
    return {
        "intent": "reorder_query",
        "language": "en",
        "spoken_summary": "(offline mode) Showing today's reorder plan from your sales and stock data.",
        "stock_changes": [],
        "reorder_list": reorder_list,
        "deferred_items": deferred,
        "missed_opportunities": missed,
        "supplier_message": {"supplier": supplier, "text": text},
        "cash_summary": plan["cash_summary"],
        "needs_approval": True,
        "needs_human": plan["needs_human"],
        "confidence": 0.5,
        "_source": "fallback_template",
    }


def _reorder_item_by_name(plan_items, name):
    for c in plan_items:
        if c["item"] == name:
            return c
    return None


def validate_and_repair(result, plan, stock):
    """Schema check + overwrite every numeric field with the authoritative
    Python-computed truth. Returns (repaired_result, rejections:list[str])."""
    rejections = []
    if not isinstance(result, dict):
        return fallback_template("", {}, plan), ["model output was not a JSON object"]

    for key in REQUIRED_KEYS:
        if key not in result:
            rejections.append(f"missing key: {key}")
            result[key] = [] if key in ("stock_changes", "reorder_list", "deferred_items", "missed_opportunities") else None

    # needs_approval is always True, no exceptions.
    if result.get("needs_approval") is not True:
        rejections.append("model set needs_approval != true; forced to true")
    result["needs_approval"] = True

    # needs_human must reflect the code-computed data flags (never trust model to lower it).
    if plan["needs_human"] and not result.get("needs_human"):
        rejections.append("model omitted needs_human despite data_flags.needs_human")
    result["needs_human"] = bool(plan["needs_human"] or result.get("needs_human"))

    # cash_summary: always the authoritative plan value.
    if result.get("cash_summary") != plan["cash_summary"]:
        rejections.append(f"cash_summary mismatch, overwritten with computed values: {plan['cash_summary']}")
    result["cash_summary"] = plan["cash_summary"]

    # reorder_list only applies to intent == "reorder_query". For
    # stock_update / other, the computed plan is not the point of the
    # reply, so an empty list is correct and must not be "repaired" back in.
    if result.get("intent") == "reorder_query":
        dead_names = {d["item"] for d in plan["dead_stock_items"]}
        plan_reorder_names = {c["item"] for c in plan["reorder_list"]}
        repaired_list = []
        for entry in result.get("reorder_list") or []:
            name = entry.get("item")
            if name in dead_names:
                rejections.append(f"model put dead-stock item '{name}' in reorder_list; removed")
                continue
            truth = _reorder_item_by_name(plan["reorder_list"], name)
            if truth is None:
                rejections.append(f"model invented reorder item '{name}' not in computed plan; removed")
                continue
            reason = str(entry.get("reason", ""))[:120]
            repaired_list.append({
                "item": truth["item"], "qty": truth["qty"], "unit": truth["unit"],
                "cost": truth["cost"], "reason": reason, "urgency": truth["urgency"], "fits_cash": True,
            })
        missing_from_model = plan_reorder_names - {e["item"] for e in repaired_list}
        for name in missing_from_model:
            truth = _reorder_item_by_name(plan["reorder_list"], name)
            rejections.append(f"model dropped computed reorder item '{name}'; re-added")
            repaired_list.append({
                "item": truth["item"], "qty": truth["qty"], "unit": truth["unit"],
                "cost": truth["cost"], "reason": f"{truth['days_left']} days of stock left",
                "urgency": truth["urgency"], "fits_cash": True,
            })
        total_cost = sum(e["cost"] for e in repaired_list)
        if total_cost > plan["cash_summary"]["available"]:
            rejections.append("repaired reorder_list still exceeds available cash; truncating")
            repaired_list = plan["reorder_list"]
        result["reorder_list"] = repaired_list
    else:
        if result.get("reorder_list"):
            rejections.append(f"intent={result.get('intent')} but model filled reorder_list; cleared")
        result["reorder_list"] = []

    # stock_changes: recompute new_stock in code; never trust the model's arithmetic.
    raw_changes = result.get("stock_changes") or []
    _, applied, rejected_changes = data_mod.apply_stock_changes(stock, raw_changes)
    for r in rejected_changes:
        rejections.append(f"stock_change rejected for '{r['item']}': {r['reason']}")
    result["stock_changes"] = applied
    if rejected_changes:
        result["needs_human"] = True

    try:
        result["confidence"] = max(0.0, min(1.0, float(result.get("confidence") or 0)))
    except (TypeError, ValueError):
        result["confidence"] = 0.0

    return result, rejections


def process_message(merchant_message, data_dir=None, force_fallback=False):
    sales = data_mod.load_sales(os.path.join(data_dir, "sales.csv") if data_dir else None)
    stock = data_mod.load_stock(os.path.join(data_dir, "stock.csv") if data_dir else None)
    suppliers = data_mod.load_suppliers(os.path.join(data_dir, "suppliers.csv") if data_dir else None)
    cash = data_mod.load_cash(os.path.join(data_dir, "cash.json") if data_dir else None)

    context, plan = build_context(sales, stock, suppliers, cash)

    client = None if force_fallback else get_client()
    used_fallback = False
    if client is None:
        result = fallback_template(merchant_message, context, plan)
        used_fallback = True
        rejections = []
    else:
        try:
            raw = call_model(client, merchant_message, context)
            result, rejections = validate_and_repair(raw, plan, stock)
        except Exception as exc:  # API error, bad JSON, etc. -- never break the demo
            result = fallback_template(merchant_message, context, plan)
            rejections = [f"model call failed, used fallback: {exc}"]
            used_fallback = True

    applied_changes = result.get("stock_changes") or []
    new_stock, _, _ = data_mod.apply_stock_changes(stock, applied_changes)
    if applied_changes:
        data_mod.save_stock(new_stock, os.path.join(data_dir, "stock.csv") if data_dir else None)

    return {"result": result, "plan": plan, "rejections": rejections, "used_fallback": used_fallback}
