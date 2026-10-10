"""Combien d'IA chacun peut utiliser, et avec quelle clé.

Les limites par jour dépendent de la FORMULE du compte (gratuite ou Premium), jamais de la clé utilisée.
Avant le 10/10/2026, enregistrer sa propre clé Gemini gratuite supprimait toute limite : personne n'avait
alors de raison de payer. Une clé personnelle reste possible, mais elle ne fait que deux choses : les appels
passent par le quota Google de la personne (rien ne coûte au site), et elle ne dépend plus du plafond commun.

Un plafond global protège la clé commune ; quand il existe des comptes Premium, une part leur est réservée.
Les limites se règlent depuis l'onglet Administration (enregistrées dans kv, clé « limits »).
"""
import datetime as dt
import os
import re
import time

from sqlalchemy import func, select

import accounts
import db
import mailer

DEFAULT_LIMITS = {
    "assist": 5,            # lettres, analyses, messages… par jour et par personne
    "score": 40,            # offres notées d'après le CV, par jour et par personne
    "cv": 6,                # analyses de CV par jour et par personne
    "p_assist": 40,         # les mêmes limites pour un compte Premium
    "p_score": 200,
    "p_cv": 20,
    "shared_requests": 800,  # appels par jour sur la clé commune, tous utilisateurs confondus
    "p_reserve": 150,       # derniers appels du jour gardés pour les Premium (seulement s'il y en a)
    "max_users": 300,       # au-delà, les inscriptions se ferment toutes seules
}
LABELS = {"assist": "générations de l'assistant", "score": "offres notées par l'IA", "cv": "analyses de CV"}

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Europe/Paris")
except Exception:  # pas de base de fuseaux sur la machine : on compte en heure universelle
    _TZ = dt.timezone.utc


class QuotaError(Exception):
    pass


def today() -> str:
    return dt.datetime.now(_TZ).strftime("%Y-%m-%d")


def limits() -> dict:
    out = dict(DEFAULT_LIMITS)
    saved = db.kv_get("limits", {}) or {}
    out.update({k: int(v) for k, v in saved.items() if k in DEFAULT_LIMITS and isinstance(v, (int, float))})
    return out


def limit_for(u: dict, kind: str, lim: dict | None = None) -> int:
    lim = lim or limits()
    return lim["p_" + kind] if accounts.is_premium(u) else lim[kind]


def shared_key() -> str:
    return os.getenv("GEMINI_API_KEY", "").strip()


def ai_available(u: dict) -> bool:
    return bool(accounts.own_key(u) or shared_key())


def needs_verification(u: dict) -> bool:
    """Vrai si ce compte doit d'abord confirmer son adresse pour utiliser la clé commune."""
    return mailer.enabled() and not accounts.is_verified(u) and not accounts.own_key(u)


def shared_left() -> int:
    return max(0, limits()["shared_requests"] - db.usage_get(0, today()).get("req", 0))


def premium_url() -> str:
    """Lien de paiement du Premium, s'il est réglé (variable PREMIUM_URL). Vide = rien à vendre."""
    url = os.getenv("PREMIUM_URL", "").strip()
    return url if re.match(r"https://", url) else ""


def can_upgrade(u: dict) -> bool:
    return bool(premium_url()) and not accounts.is_premium(u)


_premium = {"at": 0.0, "n": 0}


def premium_count() -> int:
    """Nombre de comptes Premium en cours (recompté au plus toutes les 5 minutes)."""
    now = time.time()
    if now - _premium["at"] > 300:
        with db.engine.connect() as c:
            n = c.execute(select(func.count()).select_from(db.users).where(db.users.c.plan_until > now)).scalar() or 0
        _premium.update(at=now, n=n)
    return _premium["n"]


def reset_cache() -> None:
    _premium["at"] = 0.0


def reserve(lim: dict | None = None) -> int:
    """Appels de la clé commune gardés pour les Premium : ceux qui paient ne doivent pas être bloqués parce que
    les comptes gratuits ont tout consommé. Rien n'est réservé tant qu'aucun compte n'est Premium."""
    lim = lim or limits()
    return min(lim["p_reserve"], lim["shared_requests"] // 2) if premium_count() else 0


def grant(u: dict, kind: str, units: int = 1) -> tuple[str, bool, int]:
    """Renvoie (clé à utiliser, clé personnelle ?, unités accordées). Lève QuotaError si rien n'est possible.
    La limite du jour est celle de la formule, avec ou sans clé personnelle."""
    own = accounts.own_key(u)
    if not own and not shared_key():
        raise QuotaError("L'IA n'est pas disponible sur ce site pour l'instant. Ajoute ta propre clé Gemini "
                         "gratuite dans l'onglet Réglages.")
    if not own and needs_verification(u):
        raise QuotaError("Confirme d'abord ton adresse e-mail (lien reçu à l'inscription) pour utiliser l'IA incluse.")
    lim = limits()
    mine = limit_for(u, kind, lim)
    left = mine - db.usage_get(u["id"], today()).get(kind, 0)
    if left <= 0:
        more = (f" La formule Premium en donne {lim['p_' + kind]} par jour : onglet Réglages." if can_upgrade(u) else "")
        raise QuotaError(f"Limite du jour atteinte ({mine} {LABELS[kind]}). Elle repart à zéro à minuit." + more)
    if own:
        return own, True, min(units, left)
    remaining = shared_left()
    if remaining <= 0:
        raise QuotaError("Le quota commun du site est épuisé pour aujourd'hui. Il repart à zéro à minuit.")
    if not accounts.is_premium(u) and remaining <= reserve(lim):
        raise QuotaError("Le quota d'IA des comptes gratuits est épuisé pour aujourd'hui. Il repart à zéro à minuit."
                         + (" Les comptes Premium gardent une part réservée : onglet Réglages." if can_upgrade(u) else ""))
    return shared_key(), False, min(units, left)


def record(u: dict, kind: str, units: int, own: bool) -> None:
    db.usage_add(u["id"], today(), kind, units)
    if not own:
        db.usage_add(0, today(), "req", 1)


def view(u: dict) -> dict:
    """Ce que le site affiche : consommation du jour et limites."""
    lim, used = limits(), db.usage_get(u["id"], today())
    own = bool(accounts.own_key(u))
    return {"own_key": own, "shared_available": bool(shared_key()), "premium": accounts.is_premium(u), "needs_verification": needs_verification(u),
            "premium_until": u.get("plan_until") or 0, "can_upgrade": can_upgrade(u),
            "kinds": {k: {"used": used.get(k, 0), "limit": limit_for(u, k, lim)} for k in LABELS}}
