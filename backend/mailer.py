"""Envoi des e-mails du site (confirmation d'adresse, mot de passe oublié) par l'API de Brevo.

Pourquoi une API et pas un serveur d'e-mail classique : l'offre gratuite de Render bloque les ports d'envoi.
Sans BREVO_API_KEY et MAIL_FROM, rien n'est envoyé et le site fonctionne comme avant (pas de confirmation
d'adresse, mot de passe oublié géré par l'administrateur).
"""
import asyncio
import html
import os
import re
import time

import httpx

API = "https://api.brevo.com/v3/smtp/email"
MAX_PER_DAY = int(os.getenv("MAIL_MAX_PER_DAY", "250"))   # l'offre gratuite de Brevo s'arrête à 300 par jour
_sent: list[float] = []


def sender() -> str:
    s = os.getenv("MAIL_FROM", "").strip()
    return s if re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,24}", s, re.I) else ""


def enabled() -> bool:
    return bool(os.getenv("BREVO_API_KEY", "").strip() and sender())


def site() -> str:
    return os.getenv("APP_NAME", "Veille Stages")


async def send(to: str, subject: str, lines: list[str], button: tuple[str, str] | None = None) -> None:
    """Envoie un e-mail simple : quelques lignes de texte et, au besoin, un bouton. Lève RuntimeError si l'envoi échoue."""
    if not enabled():
        raise RuntimeError("l'envoi d'e-mails n'est pas configuré")
    now = time.time()
    _sent[:] = [t for t in _sent if now - t < 86400]
    if len(_sent) >= MAX_PER_DAY:
        raise RuntimeError("trop d'e-mails envoyés aujourd'hui, réessaie demain")
    text = "\n\n".join(lines) + (f"\n\n{button[0]} : {button[1]}" if button else "")
    body = "".join(f"<p>{html.escape(l)}</p>" for l in lines)
    if button:
        url = html.escape(button[1], quote=True)
        body += (f'<p><a href="{url}" style="display:inline-block;background:#2f4cff;color:#fff;padding:12px 18px;'
                 f'border-radius:10px;text-decoration:none;font-weight:600">{html.escape(button[0])}</a></p>'
                 f'<p style="color:#5c6385;font-size:13px">Si le bouton ne fonctionne pas, copie cette adresse dans ton '
                 f'navigateur :<br>{url}</p>')
    page = (f'<div style="font-family:system-ui,Arial,sans-serif;font-size:16px;line-height:1.5;color:#141a3c;max-width:520px">'
            f'<p style="font-size:20px;font-weight:700">{html.escape(site())}</p>{body}</div>')
    payload = {"sender": {"name": site(), "email": sender()}, "to": [{"email": to}], "subject": subject,
               "htmlContent": page, "textContent": text}
    last = "envoi impossible"
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=15) as h:
                r = await h.post(API, json=payload, headers={"api-key": os.getenv("BREVO_API_KEY", "").strip()})
        except httpx.HTTPError as e:
            last = f"connexion au service d'e-mails impossible ({type(e).__name__})"
        else:
            if r.status_code in (200, 201, 202):
                _sent.append(now)
                return
            try:
                why = str(r.json().get("message") or "")[:200]
            except ValueError:
                why = r.text[:200]
            last = f"Brevo a refusé l'envoi (réponse {r.status_code}) : {why or 'sans explication'}"
            if r.status_code not in (429, 500, 502, 503, 504):
                print("e-mail refusé :", r.status_code, why)   # ni l'adresse du destinataire ni le contenu
                break
        await asyncio.sleep(1 + 2 * attempt if os.getenv("AI_BACKOFF_SEC", "1") != "0" else 0)
    raise RuntimeError(last)


def explain(error: str) -> str:
    """Traduit les refus les plus fréquents de Brevo en une consigne claire pour l'administrateur."""
    e = error.lower()
    if "unrecognised ip" in e or "unrecognized ip" in e or "authorised ip" in e or "authorized ip" in e:
        return ("Brevo bloque les adresses de connexion inconnues. Dans Brevo : menu du compte → Sécurité → "
                "IP autorisées, puis désactive le blocage des adresses IP inconnues.")
    if "key not found" in e or "unauthorized" in e or "(réponse 401)" in e:
        return ("La clé n'est pas reconnue. Dans Brevo : SMTP et API → Clés API. Il faut la clé qui commence par "
                "« xkeysib- » (pas « xsmtpsib- »), copiée en entier dans BREVO_API_KEY, sans espace.")
    if "sender" in e and ("not valid" in e or "invalid" in e or "not found" in e or "validate" in e):
        return "L'adresse MAIL_FROM n'est pas un expéditeur validé dans Brevo (Expéditeurs, domaines et IP dédiées → Expéditeurs)."
    if "not yet activated" in e or "not enabled" in e or "activate" in e or "suspended" in e or "(réponse 403)" in e:
        return ("Ton compte Brevo n'est pas encore autorisé à envoyer des e-mails transactionnels. Ouvre Brevo : "
                "un bandeau ou la page Transactionnel indique quoi compléter, ou écris à leur support.")
    if "connexion" in e:
        return "Le site n'arrive pas à joindre Brevo. Réessaie dans quelques minutes."
    return ""
