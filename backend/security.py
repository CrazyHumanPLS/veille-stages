"""Mots de passe, jetons de connexion et chiffrement des secrets des utilisateurs.

Tout repose sur SECRET_KEY (variable d'environnement, créée automatiquement par Render).
Si elle change, tout le monde est déconnecté et les clés Gemini / adresses d'alerte enregistrées
deviennent illisibles : il ne faut donc jamais la modifier une fois le site en service.
"""
import base64
import hashlib
import hmac
import os
import secrets
import time

from cryptography.fernet import Fernet, InvalidToken

import db

TOKEN_DAYS = 30


def _secret() -> bytes:
    s = os.getenv("SECRET_KEY", "").strip()
    if not s:  # en local seulement : secret créé une fois et gardé dans la base
        s = db.kv_get("local_secret")
        if not s:
            s = secrets.token_hex(32)
            db.kv_set("local_secret", s)
    return s.encode()


# ---------- mots de passe (scrypt, bibliothèque standard) ----------
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, salt, h = stored.split("$")
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(got.hex(), h)
    except (ValueError, TypeError):
        return False


# ---------- jeton de connexion : « identifiant.expiration.version.signature » ----------
def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()


def make_token(user_id: int, version: int) -> str:
    payload = f"{user_id}.{int(time.time()) + TOKEN_DAYS * 86400}.{version}"
    return f"{payload}.{_sign(payload)}"


def read_token(token: str) -> tuple[int, int] | None:
    """Renvoie (identifiant, version) si le jeton est authentique et encore valable."""
    payload, _, sig = token.rpartition(".")
    if not payload or not hmac.compare_digest(sig, _sign(payload)):
        return None
    try:
        uid, exp, ver = (int(x) for x in payload.split("."))
    except ValueError:
        return None
    return (uid, ver) if exp > time.time() else None


def make_link_token(purpose: str, user_id: int, version: int, hours: float) -> str:
    """Jeton glissé dans un lien envoyé par e-mail. « purpose » empêche d'utiliser un lien pour autre chose
    que ce pour quoi il a été créé ; « version » le rend inutilisable après un changement de mot de passe."""
    payload = f"{purpose}.{user_id}.{int(time.time() + hours * 3600)}.{version}"
    return f"{payload}.{_sign('lien:' + payload)}"


def read_link_token(purpose: str, token: str) -> tuple[int, int] | None:
    """Renvoie (identifiant, version) si le lien est authentique, du bon type et encore valable."""
    payload, _, sig = (token or "").rpartition(".")
    if not payload or not hmac.compare_digest(sig, _sign("lien:" + payload)):
        return None
    try:
        kind, uid, exp, ver = payload.split(".")
        uid, exp, ver = int(uid), int(exp), int(ver)
    except ValueError:
        return None
    return (uid, ver) if kind == purpose and exp > time.time() else None


def short_code(user_id: int, purpose: str) -> str:
    """Petit code stable et impossible à deviner (liaison Telegram)."""
    return hmac.new(_secret(), f"{purpose}:{user_id}".encode(), hashlib.sha256).hexdigest()[:8].upper()


# ---------- chiffrement des secrets enregistrés en base ----------
def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"secrets:" + _secret()).digest()))


def encrypt(text: str) -> str:
    return _fernet().encrypt(text.encode()).decode()


def decrypt(blob: str) -> str:
    if not blob:
        return ""
    try:
        return _fernet().decrypt(blob.encode()).decode()
    except (InvalidToken, ValueError):
        return ""
