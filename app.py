import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st

try:
    for _k in ("ANTHROPIC_API_KEY", "SARVAM_API_KEY", "GEMINI_API_KEY", "CLAUDE_MODEL",
               "GEMINI_MODEL", "SARVAM_STT_MODEL", "SARVAM_TTS_MODEL"):
        if _k in st.secrets and not os.environ.get(_k):
            os.environ[_k] = st.secrets[_k]
except (FileNotFoundError, st.errors.StreamlitAPIException):
    pass  # no secrets.toml present locally -- fine, falls back to plain env vars

from core import actions_log
from core import advisors
from core import data as data_mod
from core import i18n
from core import logs
from core import munshi
from core import reasoning
from core import voice
from core import whatsapp

st.set_page_config(page_title="Kirana for Business", layout="wide")

reasoning_provider = reasoning.get_provider()
reasoning_ok = reasoning_provider is not None
sarvam_ok = voice.has_key()

query_params = st.query_params
if query_params.get("health") is not None:
    st.json({
        "status": "ok",
        "claude_api_key_set": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "gemini_api_key_set": bool(os.environ.get("GEMINI_API_KEY")),
        "sarvam_api_key_set": sarvam_ok,
        "active_reasoning_provider": reasoning_provider,
    })
    st.stop()

for key, default in [
    ("ui_lang", "en"), ("reply_lang", "auto"), ("nav", "home"),
    ("last_result", None), ("last_plan", None), ("last_message", ""),
    ("used_fallback", False), ("tts_audio", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


def t(key):
    return i18n.t(st.session_state.ui_lang, key)


# ---------------------------------------------------------------- styling
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"], .stMarkdown, .stButton button, input, textarea, select {
        font-family: 'Poppins', sans-serif !important;
    }
    .block-container { padding-top: 3.2rem; max-width: 1200px; }
    [data-testid="stHeader"] { background: transparent; }

    :root {
        --ptm-cyan: #00BAF2;
        --ptm-navy: #0B2447;
        --ptm-muted: #6B7280;
        --ptm-border: #E7EAF0;
    }

    /* ---- top bar ---- */
    .kgc-topbar { display:flex; align-items:center; gap:1.5rem; border-bottom:1px solid var(--ptm-border); padding-bottom:0.8rem; margin-bottom:0.3rem; }
    .kgc-wordmark { font-size:1.7rem; font-weight:800; line-height:1.05; }
    .kgc-wordmark .k1 { color: var(--ptm-navy); }
    .kgc-wordmark .k2 { color: var(--ptm-cyan); }
    .kgc-wordmark-sub { font-size:0.8rem; font-weight:600; color: var(--ptm-navy); letter-spacing:0.5px; }
    .kgc-navlinks { display:flex; gap:1.6rem; color:#7A8699; font-size:0.78rem; font-weight:600; letter-spacing:0.6px; white-space:nowrap; }
    .kgc-avatar { width:38px; height:38px; border-radius:50%; background:#E9ECF1; color:var(--ptm-navy); display:flex; align-items:center; justify-content:center; font-weight:700; }

    /* ---- sidebar section labels ---- */
    .kgc-sidebar-section { font-weight:700; font-size:0.95rem; color: var(--ptm-navy); margin: 0.9rem 0 0.2rem 0; }
    .kgc-sidebar-static { color:#9AA3B2; font-size:0.9rem; padding:0.35rem 0 0.35rem 0.4rem; }
    .kgc-sidebar-static.indent { padding-left: 1.2rem; font-size: 0.85rem; }
    .kgc-sidebar-new-badge { background: var(--ptm-cyan); color:white; font-size:0.65rem; font-weight:700; padding:1px 7px; border-radius:8px; margin-left:6px; vertical-align:middle; }

    [data-testid="stSidebar"] button {
        background: transparent !important; border: none !important; box-shadow: none !important;
        text-align:left !important; color: var(--ptm-navy) !important; font-weight:500 !important;
        padding: 0.4rem 0.5rem !important; border-radius: 8px !important; width:100%;
    }
    [data-testid="stSidebar"] button[kind="primary"] {
        background: #E7F7FD !important; color: var(--ptm-cyan) !important; font-weight:700 !important;
        border-left: 3px solid var(--ptm-cyan) !important;
    }

    /* ---- pill badge ---- */
    .kgc-pill { display:inline-block; background:#F1F3F7; color:var(--ptm-navy); font-weight:600; font-size:0.85rem; padding:0.4rem 0.9rem; border-radius:999px; }

    /* ---- overview cards ---- */
    .kgc-card { border-radius: 16px; padding: 1.2rem 1.4rem 1rem 1.4rem; }
    .kgc-card-blue { background: linear-gradient(135deg,#E8F7FD,#D7EFFB); }
    .kgc-card-green { background: linear-gradient(135deg,#E8F8EE,#D7F0E1); }
    .kgc-card-red { background: linear-gradient(135deg,#FDEAEA,#FADADA); }
    .kgc-card-top { display:flex; justify-content:space-between; align-items:flex-start; }
    .kgc-card-label { font-size: 1rem; color: var(--ptm-navy); font-weight:500; }
    .kgc-card-icon { background:white; border-radius:50%; width:34px; height:34px; display:flex; align-items:center; justify-content:center; font-weight:700; color: var(--ptm-cyan); }
    .kgc-card-value { font-size: 2.1rem; font-weight: 800; color: var(--ptm-navy); margin-top:0.6rem; }
    .kgc-card-divider { border-top:1px solid rgba(0,0,0,0.08); margin:0.7rem 0 0.5rem 0; }
    .kgc-card-sub { color: var(--ptm-muted); font-size:0.9rem; }

    .kgc-advisor-card { border: 1px solid var(--ptm-border); border-radius: 16px; padding: 1.1rem 1.3rem; margin-bottom: 1rem; background: #fff; }
    .kgc-advisor-title { font-weight: 700; font-size: 1.05rem; color: var(--ptm-cyan); margin-bottom: 0.5rem; }
    .urgency-high { color: #C0392B; font-weight: 700; }
    .urgency-medium { color: #B7791F; font-weight: 600; }
    .urgency-low { color: #1C8A5A; font-weight: 500; }
    .cash-bar-bg { background:#EEF1F5; border-radius:8px; height:22px; width:100%; overflow:hidden; margin-top:4px; }
    .cash-bar-fill { background: var(--ptm-cyan); height:22px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------- top bar
col_logo, col_search, col_links, col_avatar = st.columns([1.6, 3.2, 2.4, 0.4])
with col_logo:
    st.markdown(
        '<div class="kgc-wordmark"><span class="k1">Kirana</span><span class="k2">.</span></div>'
        '<div class="kgc-wordmark-sub">for Business</div>',
        unsafe_allow_html=True,
    )
with col_search:
    st.text_input("search", placeholder=t("search_placeholder"), label_visibility="collapsed")
with col_links:
    st.markdown(
        '<div class="kgc-navlinks" style="margin-top:0.6rem;">'
        '<span>PRODUCTS</span><span>PRICING</span><span>DEVELOPER</span><span>NEED HELP?</span>'
        '</div>', unsafe_allow_html=True,
    )
with col_avatar:
    initial = t("shop_name")[0]
    st.markdown(f'<div class="kgc-avatar">{initial}</div>', unsafe_allow_html=True)

st.markdown('<div style="border-bottom:1px solid var(--ptm-border); margin: 0.6rem 0 1rem 0;"></div>', unsafe_allow_html=True)
st.caption(
    f"{t('status_line')}: {t('ready') + ' (' + reasoning_provider + ')' if reasoning_ok else t('not_ready')}  |  "
    f"Sarvam voice: {'ready' if sarvam_ok else 'not set (type instead)'}"
)

# ---------------------------------------------------------------- sidebar
def nav_button(page_key, label):
    if st.button(label, key=f"nav_{page_key}", type="primary" if st.session_state.nav == page_key else "secondary"):
        st.session_state.nav = page_key
        st.rerun()


with st.sidebar:
    st.markdown(f'<div class="kgc-sidebar-section">{t("nav_group_dashboard")}</div>', unsafe_allow_html=True)
    nav_button("home", "Home")
    for label in ["Payments", "Settlements", "Refunds", "Disputes"]:
        st.markdown(f'<div class="kgc-sidebar-static">{label}</div>', unsafe_allow_html=True)
    st.markdown('<div class="kgc-sidebar-static">Reports &amp; Invoices</div>', unsafe_allow_html=True)
    st.markdown('<div class="kgc-sidebar-static indent">Reports</div>', unsafe_allow_html=True)
    st.markdown('<div class="kgc-sidebar-static indent">Invoices</div>', unsafe_allow_html=True)
    st.markdown('<div class="kgc-sidebar-static">Bank Downtimes</div>', unsafe_allow_html=True)

    st.markdown('<div class="kgc-sidebar-section">Accept Payments</div>', unsafe_allow_html=True)
    st.markdown('<div class="kgc-sidebar-static">My QR Code</div>', unsafe_allow_html=True)

    st.markdown('<div class="kgc-sidebar-section">Developer Settings</div>', unsafe_allow_html=True)
    st.markdown('<div class="kgc-sidebar-static">API Keys</div>', unsafe_allow_html=True)
    st.markdown('<div class="kgc-sidebar-static">API Documentation</div>', unsafe_allow_html=True)

    st.markdown('<div class="kgc-sidebar-section">My Services</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="kgc-sidebar-section">{t("settings")}</div>', unsafe_allow_html=True)
    nav_button("settings", t("settings"))

    st.markdown(
        f'<div class="kgc-sidebar-section">AI Growth Copilot <span class="kgc-sidebar-new-badge">NEW</span></div>',
        unsafe_allow_html=True,
    )
    nav_button("copilot_home", t("nav_home"))
    nav_button("order", t("nav_order"))
    nav_button("stock", t("nav_stock"))
    nav_button("advisors", t("nav_advisors"))
    nav_button("log", t("nav_log"))

    st.markdown(
        '<div class="kgc-sidebar-section">Munshi <span class="kgc-sidebar-new-badge">NEW</span></div>',
        unsafe_allow_html=True,
    )
    nav_button("briefing", "Closing Briefing")
    nav_button("inbox", "Approval Inbox")
    nav_button("ledger", "Missed-Sales Ledger")
    nav_button("concepts", "Concept Cards")

sales = data_mod.load_sales()
stock = data_mod.load_stock()
suppliers = data_mod.load_suppliers()
cash_data = data_mod.load_cash_full()
emi_reserved, usable_cash = data_mod.compute_emi_reserve(cash_data)
plan = data_mod.build_reorder_plan(sales, stock, suppliers, usable_cash)
log_rows = logs.read_log(100)
stockouts = data_mod.load_stockouts()
udhaar_rows = data_mod.load_udhaar()
customer_rows = data_mod.load_customers()

# ---------------------------------------------------------------- Home (faithful Paytm-for-Business replica)
if st.session_state.nav == "home":
    st.markdown(f'<div style="font-size:2.4rem; font-weight:700; color:var(--ptm-navy);">{t("shop_name")}</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="color:var(--ptm-muted);">{t("shop_id")}: KGC-{str(abs(hash(t("shop_name"))))[:13]}</div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    today_str = date.today().strftime("%d %b")
    st.markdown(f'{t("business_overview_for")} <span class="kgc-pill">{t("today")}, {today_str} &#9662;</span>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    for col, bg, label, n in [
        (c1, "kgc-card-blue", "Payments", "0 Payments"),
        (c2, "kgc-card-green", "Settlement", "0 Payments"),
        (c3, "kgc-card-red", "Refunds", "0 Payments"),
    ]:
        with col:
            st.markdown(
                f"""<div class="kgc-card {bg}">
                <div class="kgc-card-top"><div class="kgc-card-label">{label}</div><div class="kgc-card-icon">Rs</div></div>
                <div class="kgc-card-value">Rs.0 &rarr;</div>
                <div class="kgc-card-divider"></div>
                <div class="kgc-card-sub">{n}</div>
                </div>""", unsafe_allow_html=True,
            )
    st.caption("No real payment integration in this MVP (out of scope per the hackathon brief) -- these mirror the live dashboard's own empty state honestly, at Rs.0.")

    st.markdown("<br>", unsafe_allow_html=True)
    rc1, rc2, rc3 = st.columns([2, 2, 1.2])
    with rc1:
        st.markdown(f'<div style="font-size:1.3rem; font-weight:700; color:var(--ptm-navy);">{t("activity_report")}</div>', unsafe_allow_html=True)
    with rc2:
        st.markdown(f'<span class="kgc-pill">1 {date.today().strftime("%b")} - {date.today().strftime("%d %b")} &#9662;</span>', unsafe_allow_html=True)
    with rc3:
        log_csv = "\n".join([",".join(logs.FIELDS)] + [",".join(str(r.get(f, "")) for f in logs.FIELDS) for r in log_rows])
        st.download_button(t("download_log"), data=log_csv, file_name="kirana_activity_report.csv", mime="text/csv", type="primary")

# ---------------------------------------------------------------- Settings
elif st.session_state.nav == "settings":
    st.subheader(t("settings"))
    ui_lang_labels = {code: label for code, label in i18n.UI_LANGUAGES}
    chosen_ui = st.selectbox(t("ui_language"), options=list(ui_lang_labels.keys()),
                              format_func=lambda c: ui_lang_labels[c],
                              index=list(ui_lang_labels.keys()).index(st.session_state.ui_lang))
    st.session_state.ui_lang = chosen_ui
    reply_lang_labels = {code: label for code, label in i18n.REPLY_LANGUAGES}
    chosen_reply = st.selectbox(t("reply_language"), options=list(reply_lang_labels.keys()),
                                 format_func=lambda c: reply_lang_labels[c],
                                 index=list(reply_lang_labels.keys()).index(st.session_state.reply_lang))
    st.session_state.reply_lang = chosen_reply

# ---------------------------------------------------------------- Our Dashboard
elif st.session_state.nav == "copilot_home":
    st.subheader(t("business_overview"))
    n_alerts = sum(1 for c in plan["reorder_list"] + plan["deferred_items"] if c["urgency"] == "high")
    c1, c2, c3 = st.columns(3)
    with c1:
        emi_note = (f"Rs.{emi_reserved:.0f} EMI reserved (due {cash_data.get('emi_due_date')}), Rs.{usable_cash:.0f} usable"
                     if emi_reserved else f"{len(stock)} {t('items')}")
        st.markdown(
            f"""<div class="kgc-card kgc-card-blue">
            <div class="kgc-card-top"><div class="kgc-card-label">{t('card_cash')}</div><div class="kgc-card-icon">Rs</div></div>
            <div class="kgc-card-value">Rs.{cash_data.get('available_cash', 0):.0f}</div>
            <div class="kgc-card-divider"></div>
            <div class="kgc-card-sub">{emi_note}</div>
            </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(
            f"""<div class="kgc-card kgc-card-green">
            <div class="kgc-card-top"><div class="kgc-card-label">{t('card_reorder')}</div><div class="kgc-card-icon">+</div></div>
            <div class="kgc-card-value">Rs.{plan['cash_summary']['planned_spend']:.0f}</div>
            <div class="kgc-card-divider"></div>
            <div class="kgc-card-sub">{len(plan['reorder_list'])} {t('items')}</div>
            </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(
            f"""<div class="kgc-card kgc-card-red">
            <div class="kgc-card-top"><div class="kgc-card-label">{t('card_alerts')}</div><div class="kgc-card-icon">!</div></div>
            <div class="kgc-card-value">{n_alerts}</div>
            <div class="kgc-card-divider"></div>
            <div class="kgc-card-sub">{t('items')}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    vm = munshi.value_meter(stockouts, plan, suppliers)
    if st.session_state.ui_lang == "hi":
        vm_text = f"Is mahine Munshi se takreeban Rs.{vm['estimated_benefit']:.0f} ka fayda (estimated) vs plan Rs.{vm['plan_target']:.0f}."
    else:
        vm_text = f"This month, Munshi got you approximately Rs.{vm['estimated_benefit']:.0f} (estimated) vs a Rs.{vm['plan_target']:.0f} plan target."
    st.markdown(
        f'<div class="kgc-advisor-card"><div class="kgc-advisor-title">AI Value Meter</div>{vm_text}</div>',
        unsafe_allow_html=True,
    )
    st.caption("Computed only from actions you've Approved in the Approval Inbox. Figures are estimates, not actuals.")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button(t("go_to_order"), type="primary"):
        st.session_state.nav = "order"
        st.rerun()

    st.markdown("---")
    fs = advisors.founder_snapshot(plan, log_rows, st.session_state.ui_lang)
    st.markdown(f'<div class="kgc-advisor-card"><div class="kgc-advisor-title">{t(fs["title_key"])}</div>'
                + "".join(f"<div>{line}</div>" for line in fs["lines"]) + "</div>", unsafe_allow_html=True)

# ---------------------------------------------------------------- Order Assistant
elif st.session_state.nav == "order":
    st.subheader(t("bolo_ya_likho"))
    transcript_from_voice = None
    if sarvam_ok:
        audio_value = st.audio_input(t("mic_label"))
        if audio_value is not None:
            with st.spinner("..."):
                stt_result = voice.speech_to_text(audio_value.getvalue())
            if stt_result and stt_result.get("transcript"):
                transcript_from_voice = stt_result["transcript"]
                st.success(transcript_from_voice)
            else:
                st.warning(t("voice_off"))
    else:
        st.info(t("voice_off"))

    merchant_message = st.text_area(
        t("text_label"), value=transcript_from_voice or "", placeholder=t("example_text"), height=80,
    )

    with st.expander("Zero-entry stock: shelf photo (Munshi)"):
        st.caption("Upload a shelf photo for a stock estimate -- you must confirm it before anything changes.")
        shelf_photo = st.file_uploader("Shelf photo", type=["jpg", "jpeg", "png"], key="shelf_photo_uploader")
        if shelf_photo is not None and st.button("Read photo"):
            with st.spinner("..."):
                proposals, needs_human_photo, rej = reasoning.read_shelf_photo(
                    shelf_photo.getvalue(), sorted(stock.keys()), mime_type=shelf_photo.type or "image/jpeg",
                )
            st.session_state.shelf_proposals = proposals
            st.session_state.shelf_needs_human = needs_human_photo
        if st.session_state.get("shelf_proposals"):
            if st.session_state.get("shelf_needs_human"):
                st.warning("Munshi isn't fully sure about this photo -- please check the estimates below.")
            for p in st.session_state.shelf_proposals:
                st.write(f"- {p['item']}: ~{p['estimated_qty']:.0f} {stock.get(p['item'], {}).get('unit', '')} (confidence {p['confidence']:.0%})")
            if st.button("Confirm and update stock", type="primary"):
                # A shelf photo shows an ABSOLUTE count on the shelf, not a delta --
                # convert to a change relative to current stock so it SETS, not adds.
                changes = [
                    {"item": p["item"], "change": p["estimated_qty"] - stock[p["item"]]["current_stock"]}
                    for p in st.session_state.shelf_proposals if p["item"] in stock
                ]
                new_stock, applied, rejected = data_mod.apply_stock_changes(stock, changes)
                if applied:
                    data_mod.save_stock(new_stock)
                    st.success(f"Stock updated for: {', '.join(a['item'] for a in applied)}.")
                if rejected:
                    st.warning(f"Could not apply: {rejected}")
                st.session_state.shelf_proposals = None

    col_a, col_b = st.columns([1, 1])
    with col_a:
        ask_clicked = st.button(t("ask_button"), type="primary", width="stretch")
    with col_b:
        example_clicked = st.button(t("example_button"), width="stretch")

    if example_clicked:
        merchant_message = t("example_text")
        ask_clicked = True

    if ask_clicked and merchant_message.strip():
        with st.spinner("..."):
            out = reasoning.process_message(merchant_message.strip(), preferred_language=st.session_state.reply_lang)
        result = out["result"]
        st.session_state.last_result = result
        st.session_state.last_plan = out["plan"]
        st.session_state.last_message = merchant_message.strip()
        st.session_state.used_fallback = out["used_fallback"]
        logs.log_event(
            "shown", result.get("intent"), merchant_message.strip(),
            [c["item"] for c in result.get("reorder_list", [])],
            result.get("cash_summary", {}).get("planned_spend"),
            result.get("needs_human"), out["used_fallback"],
        )
        if sarvam_ok and result.get("spoken_summary"):
            st.session_state.tts_audio = voice.text_to_speech(
                result["spoken_summary"], result.get("language", "hi-IN")
            )
        else:
            st.session_state.tts_audio = None

    result = st.session_state.last_result
    if result:
        st.markdown("---")
        if st.session_state.used_fallback:
            st.caption(t("offline_banner"))
        if result.get("needs_human"):
            st.warning(t("needs_human_banner"))

        st.markdown(f"**{result.get('spoken_summary', '')}**")
        if st.session_state.tts_audio:
            st.audio(st.session_state.tts_audio, format="audio/wav")

        intent = result.get("intent")

        if intent == "stock_update" and result.get("stock_changes"):
            for ch in result["stock_changes"]:
                sign = "+" if ch["change"] >= 0 else ""
                st.write(f"- {ch['item']}: {sign}{ch['change']} -> {ch['new_stock']}")

        if result.get("reorder_list"):
            st.subheader(t("reorder_list"))
            cash_s = result.get("cash_summary", {})
            available_s = cash_s.get("available") or 0
            spend_s = cash_s.get("planned_spend") or 0
            pct = min(100, int(100 * spend_s / available_s)) if available_s else 0
            st.markdown(
                f"""<div class="cash-bar-bg"><div class="cash-bar-fill" style="width:{pct}%;"></div></div>
                <p>Rs.{available_s:.0f} | Rs.{spend_s:.0f} | Rs.{cash_s.get('remaining', 0):.0f}</p>""",
                unsafe_allow_html=True,
            )

            for item in result["reorder_list"]:
                urgency_class = f"urgency-{item.get('urgency', 'low')}"
                st.markdown(
                    f"**{item['item']}** — {item['qty']} {item['unit']} (Rs.{item['cost']:.0f}) "
                    f"<span class='{urgency_class}'>[{item.get('urgency', '').upper()}]</span><br>"
                    f"<small>{item.get('reason', '')}</small>",
                    unsafe_allow_html=True,
                )

            if result.get("deferred_items"):
                st.caption(t("deferred") + ": " + ", ".join(result["deferred_items"]))
            if result.get("missed_opportunities"):
                st.caption(t("missed") + ": " + ", ".join(result["missed_opportunities"]))

            sm = result.get("supplier_message") or {}
            if sm.get("text"):
                st.subheader(f"{t('supplier_message')} — {sm.get('supplier', '')}")
                st.text_area("WhatsApp", value=sm["text"], height=100, key="wa_text", disabled=True)
                phone = st.text_input(t("wa_number"), value="", key="wa_phone")

                col1, col2 = st.columns(2)
                with col1:
                    if st.button(t("approve"), type="primary", width="stretch"):
                        link = whatsapp.build_wa_link(phone, sm["text"])
                        logs.log_event(
                            "accepted", intent, st.session_state.last_message,
                            [i["item"] for i in result["reorder_list"]],
                            result.get("cash_summary", {}).get("planned_spend"),
                            result.get("needs_human"), st.session_state.used_fallback,
                        )
                        st.markdown(f"[WhatsApp]({link})")
                        st.success(t("approved_note"))
                with col2:
                    if st.button(t("reject"), width="stretch"):
                        logs.log_event(
                            "rejected", intent, st.session_state.last_message,
                            [i["item"] for i in result["reorder_list"]],
                            result.get("cash_summary", {}).get("planned_spend"),
                            result.get("needs_human"), st.session_state.used_fallback,
                        )
                        st.info(t("rejected_note"))

# ---------------------------------------------------------------- Stock
elif st.session_state.nav == "stock":
    st.subheader(t("current_stock"))
    st.dataframe(
        [{"Item": k, "Unit": v["unit"], "Stock": v["current_stock"]} for k, v in stock.items()],
        width="stretch", hide_index=True,
    )

# ---------------------------------------------------------------- Growth Advisors
elif st.session_state.nav == "advisors":
    st.subheader(t("nav_advisors"))
    lang = st.session_state.ui_lang
    for view in (advisors.cfo_view(plan, suppliers, lang),
                 advisors.growth_view(sales, plan, lang),
                 advisors.founder_snapshot(plan, log_rows, lang)):
        st.markdown(
            f'<div class="kgc-advisor-card"><div class="kgc-advisor-title">{t(view["title_key"])}</div>'
            + "".join(f"<div>{line}</div>" for line in view["lines"]) + "</div>",
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------- Activity Log
elif st.session_state.nav == "log":
    st.subheader(t("activity_log"))
    if log_rows:
        st.dataframe(log_rows, width="stretch", hide_index=True)
    else:
        st.caption(t("no_log"))

    st.markdown("---")
    st.subheader("Munshi Actions Log (Approve / Later / Reject)")
    action_rows = actions_log.read_actions(100)
    if action_rows:
        st.dataframe(action_rows, width="stretch", hide_index=True)
    else:
        st.caption("No Munshi actions logged yet.")

# ---------------------------------------------------------------- Closing Briefing
elif st.session_state.nav == "briefing":
    st.subheader("Closing Briefing")
    st.caption('"Shop band karo" -- a ~20-second spoken summary of today, plus your top 3 actions.')

    if st.button("Shop band karo", type="primary"):
        # Mock data has no literal "today" row (it covers the 30 days up to
        # and including yesterday) -- Munshi briefs on the close of the most
        # recent recorded business day, not an empty, not-yet-happened one.
        price_by_item = {
            item: data_mod.cheapest_supplier(sup_list)["price_per_unit"]
            for item, sup_list in suppliers.items() if sup_list
        }
        all_days = sorted({r["date"] for r in sales})
        today_str = all_days[-1] if all_days else date.today().isoformat()
        prior_days = all_days[-8:-1] if len(all_days) >= 8 else all_days[:-1]
        today_sales_total = sum(r["qty_sold"] * price_by_item.get(r["item"], 0) for r in sales if r["date"] == today_str)
        usual_avg = (
            sum(r["qty_sold"] * price_by_item.get(r["item"], 0) for r in sales if r["date"] in prior_days) / max(1, len(prior_days))
            if prior_days else 0
        )
        ledger = munshi.missed_sales_ledger(stockouts)
        missed_line = ""
        if ledger["entries"]:
            e = ledger["entries"][0]
            missed_line = (
                f"{e['item']} out of stock for {e['days_out_of_stock']} days, "
                f"an estimated Rs.{e['est_lost_revenue']:.0f} in lost sales."
            )
        cards = munshi.build_approval_cards(plan, suppliers, udhaar_rows, customer_rows, st.session_state.ui_lang)
        top3 = cards[:3]
        briefing_facts = {
            "today_sales_total": round(today_sales_total, 2),
            "usual_daily_sales_avg": round(usual_avg, 2),
            "missed_sales_line": missed_line,
            "top_cards": [{"title": c["title"], "reason": c["computed_reason"], "estimated_impact": c["estimated_impact"]} for c in top3],
        }
        text, used_fb, rej, detected_lang = reasoning.generate_closing_briefing(briefing_facts, preferred_language=st.session_state.reply_lang)
        st.session_state.briefing_text = text
        st.session_state.briefing_fallback = used_fb
        if sarvam_ok:
            st.session_state.briefing_audio = voice.text_to_speech(text, detected_lang)
        else:
            st.session_state.briefing_audio = None

    if st.session_state.get("briefing_text"):
        if st.session_state.get("briefing_fallback"):
            st.caption("Offline/fallback mode: deterministic summary shown below (text is always the fallback, even if voice fails).")
        st.markdown(f"**{st.session_state.briefing_text}**")
        if st.session_state.get("briefing_audio"):
            st.audio(st.session_state.briefing_audio, format="audio/wav")
        else:
            st.caption("(Voice unavailable -- text above is the always-visible fallback.)")

# ---------------------------------------------------------------- Approval Inbox
elif st.session_state.nav == "inbox":
    st.subheader("Approval Inbox")
    st.caption("Every card is data-based. Approve / Later / Reject -- nothing is sent automatically.")

    cards = munshi.build_approval_cards(plan, suppliers, udhaar_rows, customer_rows, st.session_state.ui_lang)
    if not cards:
        st.caption("No action cards right now.")
    card_ids = [c["id"] for c in cards]
    if st.session_state.get("inbox_card_ids") != card_ids:
        texts, used_fb, rej = reasoning.generate_card_texts(cards, preferred_language=st.session_state.reply_lang)
        st.session_state.inbox_card_ids = card_ids
        st.session_state.inbox_texts = texts

    for c in cards:
        phrased = st.session_state.get("inbox_texts", {}).get(c["id"], c["computed_reason"])
        st.markdown(
            f'<div class="kgc-advisor-card"><div class="kgc-advisor-title">{c["title"]}</div>'
            f'{phrased}<br><small>Estimated impact: Rs.{c["estimated_impact"]:.0f} (estimated)</small></div>',
            unsafe_allow_html=True,
        )
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Approve", key=f"approve_{c['id']}", type="primary", width="stretch"):
                actions_log.log_action(c["kind"], c["title"], c["estimated_impact"], "approved")
                if c["kind"] in ("udhaar", "repeat_customer", "dead_stock"):
                    link = whatsapp.build_wa_link("", phrased)
                    st.markdown(f"[Open WhatsApp]({link})")
                st.success("Approved and logged.")
        with col2:
            if st.button("Later", key=f"later_{c['id']}", width="stretch"):
                actions_log.log_action(c["kind"], c["title"], c["estimated_impact"], "later")
                st.info("Saved for later.")
        with col3:
            if st.button("Reject", key=f"reject_{c['id']}", width="stretch"):
                actions_log.log_action(c["kind"], c["title"], c["estimated_impact"], "rejected")
                st.info("Rejected and logged.")

# ---------------------------------------------------------------- Missed-Sales Ledger
elif st.session_state.nav == "ledger":
    st.subheader("Missed-Sales Ledger (estimated)")
    st.caption("Replays the last 30 days: stock-outs avoided and rupees recovered IF the reorder advice had been followed. All figures are estimated.")
    ledger = munshi.missed_sales_ledger(stockouts)
    st.metric("Stock-outs in the last 30 days", ledger["stockouts_avoided"])
    st.metric("Estimated rupees recoverable", f"Rs.{ledger['est_total_recovered']:.0f}")
    if ledger["entries"]:
        st.dataframe(ledger["entries"], width="stretch", hide_index=True)
    else:
        st.caption("No recorded stock-out windows in the last 30 days.")

# ---------------------------------------------------------------- Concept Cards (Tier 3, mock UI only)
elif st.session_state.nav == "concepts":
    st.subheader("Concept Cards")
    st.caption("These are mock/concept UI only -- not real financial products or integrations.")

    emi_amount = cash_data.get("emi_due_amount", 0)
    emi_date_str = cash_data.get("emi_due_date", "")
    st.markdown(
        f'<div class="kgc-advisor-card"><div class="kgc-advisor-title">EMI-safe planning <span class="kgc-sidebar-new-badge">Concept</span></div>'
        f"Shukravar ko EMI Rs.{emi_amount:.0f} hai ({emi_date_str}), pehle alag rakh diya. "
        f"Reorder budget ab Rs.{usable_cash:.0f} hai, Rs.{cash_data.get('available_cash', 0):.0f} mein se.</div>",
        unsafe_allow_html=True,
    )

    if usable_cash < 500:
        st.markdown(
            '<div class="kgc-advisor-card"><div class="kgc-advisor-title">Cash-short? <span class="kgc-sidebar-new-badge">Concept</span></div>'
            "Short-term credit Paytm ke lending partners se mil sakta hai (concept). "
            "No rates or eligibility shown here -- concept only.</div>",
            unsafe_allow_html=True,
        )

    st.markdown('<div class="kgc-advisor-card"><div class="kgc-advisor-title">Pay supplier by UPI <span class="kgc-sidebar-new-badge">Concept</span></div>'
                "Approve and pay a supplier directly -- mock confirmation only, no real payment is sent.</div>", unsafe_allow_html=True)
    if plan["reorder_list"]:
        top = plan["reorder_list"][0]
        if st.button(f"Approve and pay {top['supplier']} Rs.{top['cost']:.0f} (mock)", type="primary"):
            st.success(f"Mock confirmation: Rs.{top['cost']:.0f} 'paid' to {top['supplier']} via UPI. (Concept -- no real payment was sent.)")
    else:
        st.caption("No reorder item to demo this concept card against right now.")
