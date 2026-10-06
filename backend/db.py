"""Base de données : Postgres en ligne (DATABASE_URL) ou SQLite en local.

Les offres sont communes à tout le monde (table offers). Tout le reste est rangé par utilisateur :
son compte (users), sa note et son tri pour chaque offre (user_offers), ses candidatures (applications),
sa consommation d'IA du jour (usage).
"""
import json
import os
import time
from urllib.parse import unquote

from dotenv import load_dotenv
from sqlalchemy import func  # noqa: F401
from sqlalchemy import (Column, Float, Index, Integer, MetaData, String, Table, Text,
                        create_engine, delete, insert, select, update)
from sqlalchemy.engine import url as sa_url
from sqlalchemy.exc import IntegrityError

load_dotenv()


def _url():
    u = os.getenv("DATABASE_URL", "").strip().strip('"').strip("'")
    if not u:
        return "sqlite:///veille.db"
    if not u.startswith("postgres"):
        return u
    # Découpage manuel : le mot de passe peut contenir @ # / ? : sans casser l'adresse.
    rest = u.split("://", 1)[1]
    creds, _, hostpart = rest.rpartition("@")
    user, _, password = creds.partition(":")
    hostport, _, tail = hostpart.partition("/")
    dbname, _, query = tail.partition("?")
    host, _, port = hostport.partition(":")
    if password.startswith("[") and password.endswith("]"):
        password = password[1:-1]  # crochets du modèle Supabase laissés par erreur
    return sa_url.URL.create("postgresql+psycopg", username=unquote(user), password=unquote(password),
                             host=host, port=int(port) if port.isdigit() else None, database=dbname or "postgres",
                             query=dict(p.split("=", 1) for p in query.split("&") if "=" in p))


URL = _url()
IS_PG = str(URL).startswith("postgresql")
# prepare_threshold=None : compatible avec les "poolers" (Supabase, Neon)
engine = create_engine(
    URL, pool_pre_ping=True, pool_recycle=280,
    connect_args={"prepare_threshold": None} if IS_PG else {"check_same_thread": False},
)
meta = MetaData()

users = Table(
    "users", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("email", String(200), unique=True, nullable=False),
    Column("name", String(80), default=""),
    Column("pw_hash", String(300), nullable=False),
    Column("created", Float, default=0),
    Column("last_seen", Float, default=0),             # dernière visite du site (sert à mettre en veille les comptes inactifs)
    Column("is_admin", Integer, default=0),
    Column("disabled", Integer, default=0),
    Column("token_version", Integer, default=0),       # augmente au changement de mot de passe : déconnecte partout
    Column("secrets", Text, default=""),               # chiffré : clé Gemini personnelle, adresses d'alerte
    Column("settings", Text, default="{}"),            # JSON : objectif, mots-clés, seuils
    Column("profile", Text, default="{}"),             # JSON : CV et analyse
    Column("cursor", Float, default=0),                # jusqu'où les offres communes ont été triées pour lui
    Column("bootstrapped", Integer, default=0),        # 1 quand le stock de départ a été noté
    Column("last_eval", Float, default=0),
    Column("ai_error", String(300), default=""),
    Column("alert_error", String(300), default=""),
)

offers = Table(
    "offers", meta,
    Column("id", String(40), primary_key=True),      # empreinte anti-doublon
    Column("source", String(60)),
    Column("company", String(200)),
    Column("title", String(300)),
    Column("place", String(200)),
    Column("url", Text),
    Column("description", Text),
    Column("published", String(40)),
    Column("first_seen", Float, index=True),
    Column("kw_score", Integer, default=0),           # score général (mots-clés par défaut)
    Column("ext_id", String(200), default=""),         # référence de l'offre chez la source
)

user_offers = Table(
    "user_offers", meta,
    Column("user_id", Integer, primary_key=True),
    Column("offer_id", String(40), primary_key=True),
    Column("kw_score", Integer, default=0),           # score d'après SES mots-clés
    Column("ai_score", Integer, nullable=True),
    Column("ai_reason", Text, default=""),
    Column("cv", String(20), default=""),              # CV conseillé : cv1 / cv2 / cv3
    Column("notified", Integer, default=0),           # 0 à traiter, 1 alerte envoyée, 2 traitée sans alerte
    Column("state", String(12), default="new"),       # new / saved / hidden / applied
    Column("dup_note", Text, default=""),              # avertissement « déjà postulé à une offre proche »
    Index("ix_user_offers_todo", "user_id", "notified"),
)

applications = Table(
    "applications", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, index=True, nullable=False),
    Column("company", String(200)), Column("job", String(300)), Column("url", Text),
    Column("contact", String(200)), Column("note", Text),
    Column("status", Integer, default=1), Column("updated", Float),
)

usage = Table(
    "usage", meta,
    Column("user_id", Integer, primary_key=True),      # 0 = total de la clé commune
    Column("day", String(10), primary_key=True),
    Column("kind", String(12), primary_key=True),      # assist / score / cv / req
    Column("n", Integer, default=0),
)

kv = Table("kv", meta, Column("key", String(80), primary_key=True), Column("value", Text))

meta.create_all(engine)

# Colonnes ajoutées après la première mise en ligne : create_all ne modifie pas une table existante.
# Pour ajouter une colonne plus tard, l'inscrire ici : ("table", "colonne", "TYPE SQL DEFAULT …").
for _table, _col, _type in ():
    try:
        with engine.begin() as _c:
            _c.exec_driver_sql(f"ALTER TABLE {_table} ADD COLUMN {_col} {_type}")
    except Exception:
        pass  # la colonne existe déjà


# ---------- petit magasin clé / valeur (réglages du site, état des sources) ----------
def kv_get(key: str, default=None):
    with engine.connect() as c:
        row = c.execute(select(kv.c.value).where(kv.c.key == key)).first()
    if row is None:
        return default
    try:
        return json.loads(row[0])
    except (TypeError, ValueError):
        return default


def kv_set(key: str, value) -> None:
    data = json.dumps(value, ensure_ascii=False)
    with engine.begin() as c:
        if c.execute(update(kv).where(kv.c.key == key).values(value=data)).rowcount == 0:
            try:
                c.execute(insert(kv).values(key=key, value=data))
            except IntegrityError:
                pass


def kv_prefix(prefix: str) -> dict:
    with engine.connect() as c:
        rows = c.execute(select(kv).where(kv.c.key.like(prefix + "%"))).all()
    out = {}
    for k, v in rows:
        try:
            out[k[len(prefix):]] = json.loads(v)
        except (TypeError, ValueError):
            pass
    return out


# ---------- offres communes ----------
def insert_offer(row: dict) -> bool:
    """Insère une offre. Renvoie False si elle existait déjà."""
    try:
        with engine.begin() as c:
            c.execute(insert(offers).values(**row))
        return True
    except IntegrityError:
        return False


def known_refs(ids: list[str]) -> dict[str, tuple[str, str]]:
    """Pour chaque identifiant déjà en base : (source, référence chez la source)."""
    found = {}
    with engine.connect() as c:
        for i in range(0, len(ids), 400):
            for r in c.execute(select(offers.c.id, offers.c.source, offers.c.ext_id).where(offers.c.id.in_(ids[i:i + 400]))):
                found[r.id] = (r.source or "", r.ext_id or "")
    return found


def prune(days: int = 60) -> None:
    """Garde la base légère : supprime les vieilles offres que personne n'a gardées ni suivies."""
    limit = time.time() - days * 86400
    kept = select(user_offers.c.offer_id).where(user_offers.c.state.in_(["saved", "applied"]))
    with engine.begin() as c:
        c.execute(delete(offers).where(offers.c.first_seen < limit, offers.c.id.not_in(kept)))
        c.execute(delete(user_offers).where(user_offers.c.offer_id.not_in(select(offers.c.id))))
        c.execute(delete(usage).where(usage.c.day < time.strftime("%Y-%m-%d", time.gmtime(time.time() - 40 * 86400))))


# ---------- consommation d'IA ----------
def usage_get(user_id: int, day: str) -> dict[str, int]:
    with engine.connect() as c:
        return {r.kind: r.n for r in c.execute(
            select(usage.c.kind, usage.c.n).where(usage.c.user_id == user_id, usage.c.day == day))}


def usage_add(user_id: int, day: str, kind: str, n: int = 1) -> None:
    where = (usage.c.user_id == user_id) & (usage.c.day == day) & (usage.c.kind == kind)
    with engine.begin() as c:
        if c.execute(update(usage).where(where).values(n=usage.c.n + n)).rowcount == 0:
            try:
                c.execute(insert(usage).values(user_id=user_id, day=day, kind=kind, n=n))
            except IntegrityError:
                pass
