import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st

from core import data as data_mod
from core import logs
from core import reasoning
from core import voice
from core import whatsapp

st.set_page_config(page_title="Kirana Reorder Copilot", layout="centered")

claude_ok = bool(os.environ.get("ANTHROPIC_API_KEY"))
sarvam_ok = voice.has_key()

query_params = st.query_params
if query_params.get("health") is not None:
    st.json({
        "status": "ok",
        "claude_api_key_set": claude_ok,
        "sarvam_api_key_set": sarvam_ok,
    })
    st.stop()

st.markdown(
    """
    <style>
    html, body, [class*="css"] { font-size: 18px; }
    .urgency-high { color: #b00020; font-weight: 700; }
    .urgency-medium { color: #b36b00; font-weight: 600; }
    .urgency-low { color: #2e7d32; font-weight: 500; }
    .cash-bar-bg { background:#eee; border-radius:8px; height:22px; width:100%; overflow:hidden; margin-top:4px; }
    .cash-bar-fill { background:#2e7d32; height:22px; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Kirana Reorder Copilot")
st.caption("Dukaan ke liye awaaz se order planning — Hindi/Hinglish mein bolo ya likho.")
st.caption(
    f"Claude: {'ready' if claude_ok else 'not set (fallback mode)'}  |  "
    f"Sarvam voice: {'ready' if sarvam_ok else 'not set (type instead)'}"
)

for key, default in [("last_result", None), ("last_plan", None), ("last_message", ""),
                      ("used_fallback", False), ("tts_audio", None)]:
    if key not in st.session_state:
        st.session_state[key] = default

tab_order, tab_stock, tab_log = st.tabs(["Order", "Stock", "Log"])

with tab_order:
    st.subheader("Bolo ya likho")
    transcript_from_voice = None
    if sarvam_ok:
        audio_value = st.audio_input("Mic se bolo")
        if audio_value is not None:
            with st.spinner("Sun raha hoon..."):
                stt_result = voice.speech_to_text(audio_value.getvalue())
            if stt_result and stt_result.get("transcript"):
                transcript_from_voice = stt_result["transcript"]
                st.success(f"Suna: {transcript_from_voice}")
            else:
                st.warning("Voice samajh nahi aaya, neeche type kar do.")
    else:
        st.info("Voice abhi off hai (Sarvam key nahi hai) — neeche type karo.")

    merchant_message = st.text_area(
        "Ya yahan likho",
        value=transcript_from_voice or "",
        placeholder="Kal kya order karna chahiye? / Aaj 20 atta aaya, 5 chini bik gayi",
        height=80,
    )

    col_a, col_b = st.columns([1, 1])
    with col_a:
        ask_clicked = st.button("Poochho / Ask", type="primary", width="stretch")
    with col_b:
        example_clicked = st.button("Example: Kal kya order karu?", width="stretch")

    if example_clicked:
        merchant_message = "Kal kya order karna chahiye?"
        ask_clicked = True

    if ask_clicked and merchant_message.strip():
        with st.spinner("Soch raha hoon..."):
            out = reasoning.process_message(merchant_message.strip())
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
            st.caption("Offline mode: Claude key nahi mila, seedha data se jawaab.")
        if result.get("needs_human"):
            st.warning("Data adhoora ya ulajhan mein hai — kripya khud check karein.")

        st.markdown(f"**{result.get('spoken_summary', '')}**")
        if st.session_state.tts_audio:
            st.audio(st.session_state.tts_audio, format="audio/wav")

        intent = result.get("intent")

        if intent == "stock_update" and result.get("stock_changes"):
            st.subheader("Stock Update")
            for ch in result["stock_changes"]:
                sign = "+" if ch["change"] >= 0 else ""
                st.write(f"- {ch['item']}: {sign}{ch['change']} -> ab {ch['new_stock']}")

        if result.get("reorder_list"):
            st.subheader("Reorder List")
            cash = result.get("cash_summary", {})
            available = cash.get("available") or 0
            spend = cash.get("planned_spend") or 0
            pct = min(100, int(100 * spend / available)) if available else 0
            st.markdown(
                f"""<div class="cash-bar-bg"><div class="cash-bar-fill" style="width:{pct}%;"></div></div>
                <p>Available Rs.{available:.0f} | Planned Rs.{spend:.0f} | Baaki Rs.{cash.get('remaining', 0):.0f}</p>""",
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
                st.caption("Abhi nahi: " + ", ".join(result["deferred_items"]))
            if result.get("missed_opportunities"):
                st.caption("Dhyan dein (paisa kam pada): " + ", ".join(result["missed_opportunities"]))

            sm = result.get("supplier_message") or {}
            if sm.get("text"):
                st.subheader(f"Supplier Message — {sm.get('supplier', '')}")
                st.text_area("WhatsApp message", value=sm["text"], height=100, key="wa_text", disabled=True)
                phone = st.text_input("Supplier WhatsApp number (optional, with country code)", value="", key="wa_phone")

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Approve -> Open WhatsApp", type="primary", width="stretch"):
                        link = whatsapp.build_wa_link(phone, sm["text"])
                        logs.log_event(
                            "accepted", intent, st.session_state.last_message,
                            [i["item"] for i in result["reorder_list"]],
                            result.get("cash_summary", {}).get("planned_spend"),
                            result.get("needs_human"), st.session_state.used_fallback,
                        )
                        st.markdown(f"[Click here to open WhatsApp]({link})")
                        st.success("WhatsApp khul gaya (naya tab) — vahin se bhejo. App ne kuch bheja nahi.")
                with col2:
                    if st.button("Reject", width="stretch"):
                        logs.log_event(
                            "rejected", intent, st.session_state.last_message,
                            [i["item"] for i in result["reorder_list"]],
                            result.get("cash_summary", {}).get("planned_spend"),
                            result.get("needs_human"), st.session_state.used_fallback,
                        )
                        st.info("Theek hai, order reject kar diya (sirf log mein).")

with tab_stock:
    st.subheader("Current Stock")
    stock = data_mod.load_stock()
    st.dataframe(
        [{"Item": k, "Unit": v["unit"], "Stock": v["current_stock"]} for k, v in stock.items()],
        width="stretch", hide_index=True,
    )

with tab_log:
    st.subheader("Recommendation Log")
    rows = logs.read_log(50)
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.caption("Abhi tak koi log nahi hai.")
