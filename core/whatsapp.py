"""Builds a wa.me click-to-send link. The app never sends anything itself --
this only opens WhatsApp with the message pre-filled for the merchant to
review and hit send themselves."""
import urllib.parse

WA_BASE = "https://wa.me/"


def build_wa_link(phone, message):
    """phone: digits only, country code included (e.g. "919876543210").
    If phone is blank, returns a wa.me link with no number -- WhatsApp
    will prompt the user to pick a contact, message still pre-filled."""
    text = urllib.parse.quote(message or "")
    phone = "".join(ch for ch in (phone or "") if ch.isdigit())
    if phone:
        return f"{WA_BASE}{phone}?text={text}"
    return f"https://api.whatsapp.com/send?text={text}"
