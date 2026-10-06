"""Comptes utilisateurs : création, lecture, réglages, secrets chiffrés, suppression."""
import json
import re
import time

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError

import db
import security

EMAIL = re.compile(r"^[^@\s]{1,80}@[^@\s]{1,100}\.[a-z]{2,24}$")


def _json(text, default):
    try:
        v = json.loads(text or "")
        return v if isinstance(v, type(default)) else default
    except (TypeError, ValueError):
        return default


def _load(row) -> dict:
    u = dict(row._mapping)
    u["settings"] = _json(u.get("settings"), {})
    u["profile"] = _json(u.get("profile"), {})
    u["secrets"] = _json(security.decrypt(u.get("secrets") or ""), {})
    return u


def clean_email(email: str) -> str:
    return (email or "").strip().lower()


def count() -> int:
    with db.engine.connect() as c:
        return c.execute(select(func.count()).select_from(db.users)).scalar() or 0


def create(email: str, name: str, password: str, is_admin: bool = False) -> dict | None:
    """Crée le compte. Renvoie None si l'adresse est déjà utilisée."""
    now = time.time()
    try:
        with db.engine.begin() as c:
            r = c.execute(insert(db.users).values(
                email=clean_email(email), name=name.strip()[:80], pw_hash=security.hash_password(password),
                created=now, last_seen=now, is_admin=int(is_admin), disabled=0, token_version=0,
                secrets="", settings="{}", profile="{}", cursor=0, bootstrapped=0, last_eval=0,
                ai_error="", alert_error=""))
            uid = r.inserted_primary_key[0]
    except IntegrityError:
        return None
    return by_id(uid)


def by_id(uid: int) -> dict | None:
    with db.engine.connect() as c:
        row = c.execute(select(db.users).where(db.users.c.id == uid)).first()
    return _load(row) if row else None


def by_email(email: str) -> dict | None:
    with db.engine.connect() as c:
        row = c.execute(select(db.users).where(db.users.c.email == clean_email(email))).first()
    return _load(row) if row else None


def everyone() -> list[dict]:
    with db.engine.connect() as c:
        return [_load(r) for r in c.execute(select(db.users).order_by(db.users.c.id))]


def active(inactive_days: int) -> list[dict]:
    """Comptes à traiter par la veille, ceux qui attendent depuis le plus longtemps en premier."""
    limit = time.time() - inactive_days * 86400
    with db.engine.connect() as c:
        return [_load(r) for r in c.execute(
            select(db.users).where(db.users.c.disabled == 0, db.users.c.last_seen >= limit)
            .order_by(db.users.c.last_eval))]


def set_fields(uid: int, **fields) -> None:
    with db.engine.begin() as c:
        c.execute(update(db.users).where(db.users.c.id == uid).values(**fields))


def save_settings(u: dict) -> None:
    set_fields(u["id"], settings=json.dumps(u["settings"], ensure_ascii=False))


def save_profile(u: dict) -> None:
    set_fields(u["id"], profile=json.dumps(u["profile"], ensure_ascii=False))


def save_secrets(u: dict) -> None:
    clean = {k: v for k, v in u["secrets"].items() if v}
    set_fields(u["id"], secrets=security.encrypt(json.dumps(clean)) if clean else "")


def remove(uid: int) -> None:
    """Supprime le compte et toutes ses données (CV, notes, candidatures, consommation)."""
    with db.engine.begin() as c:
        c.execute(delete(db.user_offers).where(db.user_offers.c.user_id == uid))
        c.execute(delete(db.applications).where(db.applications.c.user_id == uid))
        c.execute(delete(db.usage).where(db.usage.c.user_id == uid))
        c.execute(delete(db.users).where(db.users.c.id == uid))


def own_key(u: dict) -> str:
    return u["secrets"].get("gemini", "")


def channels(u: dict) -> dict:
    """Canaux d'alerte de l'utilisateur. Vide s'il a coupé ses alertes."""
    if not u["settings"].get("alerts_on", True):
        return {}
    s = u["secrets"]
    return {k: s[k] for k in ("discord", "ntfy", "telegram") if s.get(k)}
