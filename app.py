import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st

try:
    for _k in ("ANTHROPIC_API_KEY", "SARVAM_API_KEY", "GEMINI_API_KEY", "CLAUDE_MODEL",
               "GEMINI_MODEL", "SARVAM_STT_MODEL", "SARVAM_TTS_MODEL"):
        if _k in st.secrets and not os.environ.get(_k):
            os.environ[_k] = st.secrets[_k]
except (FileNotFoundError, st.errors.StreamlitAPIException):
    pass  # no secrets.toml present locally -- fine, falls back to plain env vars

from core import advisors
from core import data as data_mod
from core import i18n
from core import logs
from core import reasoning
from core import voice
from core import whatsapp

st.set_page_config(page_title="Kirana Growth Copilot", layout="wide")

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


st.markdown(
    """
    <style>
    html, body, [class*="css"] { font-size: 17px; }
    .block-container { padding-top: 1.2rem; }
    .kgc-header { display:flex; align-items:center; justify-content:space-between; margin-bottom: 0.5rem; }
    .kgc-brand { font-size: 1.6rem; font-weight: 800; color: #0B5FFF; }
    .kgc-tagline { color: #667; font-size: 0.95rem; margin-top: -4px; }
    .kgc-card { border-radius: 14px; padding: 1.1rem 1.3rem; }
    .kgc-card-cash { background: linear-gradient(135deg,#E8F4FD,#D7ECFC); }
    .kgc-card-reorder { background: linear-gradient(135deg,#E8F8EE,#D8F3E2); }
    .kgc-card-alert { background: linear-gradient(135deg,#FDEAEA,#FBDCDC); }
    .kgc-card-label { font-size: 0.95rem; color: #445; margin-bottom: 0.3rem; }
    .kgc-card-value { font-size: 2.0rem; font-weight: 800; color: #11182a; }
    .kgc-card-sub { color: #667; font-size: 0.85rem; margin-top: 0.3rem; }
    .kgc-advisor-card { border: 1px solid #e4e7ee; border-radius: 14px; padding: 1.1rem 1.3rem; margin-bottom: 1rem; background: #fff; }
    .kgc-advisor-title { font-weight: 700; font-size: 1.05rem; color: #0B5FFF; margin-bottom: 0.5rem; }
    .urgency-high { color: #b00020; font-weight: 700; }
    .urgency-medium { color: #b36b00; font-weight: 600; }
    .urgency-low { color: #2e7d32; font-weight: 500; }
    .cash-bar-bg { background:#eee; border-radius:8px; height:22px; width:100%; overflow:hidden; margin-top:4px; }
    .cash-bar-fill { background:#2e7d32; height:22px; }
    </style>
    """,
    unsafe_allow_html=True,
)

col_h1, col_h2, col_h3 = st.columns([3, 1, 1])
with col_h1:
    st.markdown(f'<div class="kgc-brand">{t("app_title")}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="kgc-tagline">{t("tagline")}</div>', unsafe_allow_html=True)
with col_h2:
    ui_lang_labels = {code: label for code, label in i18n.UI_LANGUAGES}
    chosen_ui = st.selectbox(t("ui_language"), options=list(ui_lang_labels.keys()),
                              format_func=lambda c: ui_lang_labels[c],
                              index=list(ui_lang_labels.keys()).index(st.session_state.ui_lang))
    st.session_state.ui_lang = chosen_ui
with col_h3:
    reply_lang_labels = {code: label for code, label in i18n.REPLY_LANGUAGES}
    chosen_reply = st.selectbox(t("reply_language"), options=list(reply_lang_labels.keys()),
                                 format_func=lambda c: reply_lang_labels[c],
                                 index=list(reply_lang_labels.keys()).index(st.session_state.reply_lang))
    st.session_state.reply_lang = chosen_reply

st.caption(
    f"{t('status_line')}: {t('ready') + ' (' + reasoning_provider + ')' if reasoning_ok else t('not_ready')}  |  "
    f"Sarvam voice: {'ready' if sarvam_ok else 'not set (type instead)'}"
)

with st.sidebar:
    st.markdown(f"**{t('app_title')}**")
    nav_options = {
        "home": t("nav_home"), "order": t("nav_order"), "stock": t("nav_stock"),
        "advisors": t("nav_advisors"), "log": t("nav_log"),
    }
    chosen_nav = st.radio("Navigation", options=list(nav_options.keys()), format_func=lambda k: nav_options[k],
                           index=list(nav_options.keys()).index(st.session_state.nav), label_visibility="collapsed")
    st.session_state.nav = chosen_nav

sales = data_mod.load_sales()
stock = data_mod.load_stock()
suppliers = data_mod.load_suppliers()
cash = data_mod.load_cash()
plan = data_mod.build_reorder_plan(sales, stock, suppliers, cash)
log_rows = logs.read_log(100)

# ---------------------------------------------------------------- Dashboard
if st.session_state.nav == "home":
    st.subheader(t("business_overview"))
    n_alerts = sum(1 for c in plan["reorder_list"] + plan["deferred_items"] if c["urgency"] == "high")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            f"""<div class="kgc-card kgc-card-cash">
            <div class="kgc-card-label">{t('card_cash')}</div>
            <div class="kgc-card-value">Rs.{cash:.0f}</div>
            <div class="kgc-card-sub">{t('items')}: {len(stock)}</div>
            </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(
            f"""<div class="kgc-card kgc-card-reorder">
            <div class="kgc-card-label">{t('card_reorder')}</div>
            <div class="kgc-card-value">Rs.{plan['cash_summary']['planned_spend']:.0f}</div>
            <div class="kgc-card-sub">{len(plan['reorder_list'])} {t('items')}</div>
            </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(
            f"""<div class="kgc-card kgc-card-alert">
            <div class="kgc-card-label">{t('card_alerts')}</div>
            <div class="kgc-card-value">{n_alerts}</div>
            <div class="kgc-card-sub">{t('items')}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("")
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
