"""Alertes. Chaque utilisateur branche SON canal depuis l'onglet Réglages :
- Discord : l'adresse d'un webhook de son propre serveur (le plus fiable) ;
- ntfy : un sujet secret auquel son téléphone est abonné ;
- Telegram : seulement si le site possède un bot (TELEGRAM_TOKEN), liaison par un code.
Les fonctions reçoivent les canaux en paramètre : {"discord": adresse, "ntfy": sujet, "telegram": discussion}.
"""
import asyncio
import html
import os
import re

import httpx

API = "https://api.telegram.org/bot{}/{}"
DISCORD = re.compile(r"^https://(?:(?:canary|ptb)\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]+$")
NTFY = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def token() -> str:
    return os.getenv("TELEGRAM_TOKEN", "").strip()


def bot_name() -> str:
    return os.getenv("TELEGRAM_BOT", "").strip().lstrip("@")


async def _post(url: str, **kw) -> httpx.Response:
    """Envoi avec 3 essais : les services gratuits coupent parfois la connexion."""
    last = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=15) as h:
                r = await h.post(url, **kw)
            if r.status_code not in (429, 500, 502, 503, 504):
                return r
            last = RuntimeError(f"réponse {r.status_code} : {r.text[:150]}")
        except httpx.HTTPError as e:
            last = RuntimeError(f"connexion impossible ({type(e).__name__})")
        await asyncio.sleep(2 + 3 * attempt)
    raise last


async def _ntfy(topic: str, text: str, button_url: str, button_text: str) -> None:
    """Application ntfy sur le téléphone, abonnée à un sujet secret."""
    plain = html.unescape(re.sub(r"<[^>]+>", "", text))
    title, _, rest = plain.partition("\n")
    body = {"topic": topic, "title": title[:200], "message": (rest or title)[:3500]}
    if button_url.startswith("http"):
        body["click"] = button_url
        body["actions"] = [{"action": "view", "label": button_text, "url": button_url}]
    r = await _post("https://ntfy.sh", json=body)
    if r.status_code != 200:
        raise RuntimeError(f"réponse {r.status_code} : {r.text[:200]}")


async def _discord(url: str, text: str, button_url: str) -> None:
    """Salon Discord privé : notification instantanée sur le téléphone via l'application Discord."""
    md = re.sub(r"</?b>", "**", text)
    md = re.sub(r"</?i>", "*", md)
    md = re.sub(r'<a href="([^"]+)">([^<]*)</a>', r"[\2](\1)", md)
    md = html.unescape(re.sub(r"<[^>]+>", "", md))
    if button_url.startswith("http"):
        md += f"\n{button_url}"
    r = await _post(url, json={"content": md[:1990], "allowed_mentions": {"parse": []}})
    if r.status_code in (401, 403, 404):
        raise RuntimeError("webhook Discord refusé (supprimé ou adresse incomplète)")
    if r.status_code not in (200, 204):
        raise RuntimeError(f"réponse {r.status_code} : {r.text[:200]}")


async def _telegram(chat: str, text: str, button_url: str, button_text: str) -> None:
    body = {"chat_id": chat, "text": text[:4000], "parse_mode": "HTML", "disable_web_page_preview": True}
    if button_url.startswith("http"):
        body["reply_markup"] = {"inline_keyboard": [[{"text": button_text, "url": button_url}]]}
    r = await _post(API.format(token(), "sendMessage"), json=body)
    if r.status_code != 200:
        raise RuntimeError(f"réponse {r.status_code} : {r.text[:200]}")


async def send(ch: dict, text: str, button_url: str = "", button_text: str = "Voir l'offre") -> bool:
    """Envoie sur tous les canaux de l'utilisateur. Réussi si au moins un canal a fonctionné.
    Renvoie False s'il n'a aucun canal ; lève RuntimeError si tous ont échoué."""
    jobs = []
    if DISCORD.match(ch.get("discord", "")):
        jobs.append(("Discord", _discord(ch["discord"], text, button_url)))
    if NTFY.match(ch.get("ntfy", "")):
        jobs.append(("ntfy", _ntfy(ch["ntfy"], text, button_url, button_text)))
    if ch.get("telegram") and token():
        jobs.append(("Telegram", _telegram(ch["telegram"], text, button_url, button_text)))
    if not jobs:
        return False
    errors = []
    for name, coro in jobs:
        try:
            await coro
        except Exception as e:
            errors.append(f"{name} : {e or type(e).__name__}")
    if len(errors) == len(jobs):
        raise RuntimeError(" ; ".join(errors))
    return True


async def find_chat(code: str) -> dict | None:
    """Cherche, dans les derniers messages reçus par le bot du site, celui qui contient le code de l'utilisateur."""
    if not token():
        raise RuntimeError("Telegram n'est pas activé sur ce site")
    async with httpx.AsyncClient(timeout=20) as h:
        r = await h.get(API.format(token(), "getUpdates"))
        if r.status_code == 409:  # bot réutilisé : un ancien webhook bloque la lecture des messages
            await h.post(API.format(token(), "deleteWebhook"))
            r = await h.get(API.format(token(), "getUpdates"))
    if r.status_code != 200:
        raise RuntimeError(f"Telegram {r.status_code} : {r.text[:200]}")
    for u in reversed(r.json().get("result", [])):
        msg = u.get("message") or {}
        if code.lower() in (msg.get("text") or "").lower() and msg.get("chat"):
            return {"chat_id": str(msg["chat"]["id"]), "name": msg["chat"].get("first_name") or ""}
    return None


def offer_message(o: dict, cv_labels: dict[str, str]) -> str:
    from scoring import published_date
    e = html.escape
    score = o.get("ai_score")
    if score is not None:
        line = f"⭐ <b>{score}/100</b> — {e(o.get('ai_reason') or '')}"
    else:
        line = f"⭐ {o.get('kw_score', 0)}/100 (mots-clés, sans analyse du CV)"
    pub = published_date(o.get("published", ""), o.get("first_seen"))
    warn = f"\n⚠️ {e(o['dup_note'])}" if o.get("dup_note") else ""
    when = f"\n📅 Mise en ligne le {pub[8:10]}/{pub[5:7]}/{pub[:4]}" if pub else ""
    cv = f"\n📄 CV à envoyer : <b>{e(cv_labels[o['cv']])}</b>" if o.get("cv") in cv_labels else ""
    return (f"🆕 <b>{e(o['title'])}</b>\n🏢 {e(o['company'] or '?')}  ·  📍 {e(o['place'] or '?')}\n"
            f"{line}{cv}{when}{warn}\n<i>Source : {e(o['source'])}</i>")
