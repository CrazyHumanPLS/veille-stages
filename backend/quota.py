"""Qui paie l'IA ? Deux cas :

1. L'utilisateur a enregistré SA clé Gemini (gratuite, créée en 2 minutes) : il utilise son propre quota
   Google, sans limite côté site.
2. Sinon il utilise la clé commune du site, avec une petite limite par jour pour que tout le monde
   puisse essayer sans épuiser le quota gratuit. Un plafond global protège la clé commune.

Les limites se règlent depuis l'onglet Administration (enregistrées dans kv, clé « limits »).
"""
import datetime as dt
import os

import accounts
import db

DEFAULT_LIMITS = {
    "assist": 5,            # lettres, analyses, messages… par jour et par personne
    "score": 40,            # offres notées d'après le CV, par jour et par personne
    "cv": 6,                # analyses de CV par jour et par personne
    "p_assist": 40,         # les mêmes limites pour un compte Premium
    "p_score": 200,
    "p_cv": 20,
    "shared_requests": 800,  # appels par jour sur la clé commune, tous utilisateurs confondus
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


def shared_left() -> int:
    return max(0, limits()["shared_requests"] - db.usage_get(0, today()).get("req", 0))


def grant(u: dict, kind: str, units: int = 1) -> tuple[str, bool, int]:
    """Renvoie (clé à utiliser, clé personnelle ?, unités accordées). Lève QuotaError si rien n'est possible."""
    own = accounts.own_key(u)
    if own:
        return own, True, units
    key = shared_key()
    if not key:
        raise QuotaError("L'IA n'est pas disponible sur ce site pour l'instant. Ajoute ta propre clé Gemini "
                         "gratuite dans l'onglet Réglages.")
    mine = limit_for(u, kind)
    left = mine - db.usage_get(u["id"], today()).get(kind, 0)
    if left <= 0:
        raise QuotaError(f"Limite du jour atteinte ({mine} {LABELS[kind]}). Elle repart à zéro à minuit. "
                         "Pour ne plus avoir de limite, ajoute ta propre clé Gemini gratuite dans l'onglet Réglages.")
    if shared_left() <= 0:
        raise QuotaError("Le quota commun du site est épuisé pour aujourd'hui. Il repart à zéro à minuit. "
                         "Avec ta propre clé Gemini gratuite (onglet Réglages), tu n'en dépends plus.")
    return key, False, min(units, left)


def record(u: dict, kind: str, units: int, own: bool) -> None:
    db.usage_add(u["id"], today(), kind, units)
    if not own:
        db.usage_add(0, today(), "req", 1)


def view(u: dict) -> dict:
    """Ce que le site affiche : consommation du jour et limites."""
    lim, used = limits(), db.usage_get(u["id"], today())
    own = bool(accounts.own_key(u))
    return {"own_key": own, "shared_available": bool(shared_key()), "premium": accounts.is_premium(u),
            "premium_until": u.get("plan_until") or 0,
            "kinds": {k: {"used": used.get(k, 0), "limit": None if own else limit_for(u, k, lim)} for k in LABELS}}
