import asyncio
import hmac
import io
import os
import pathlib
import secrets
import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import delete, func, insert, or_, select, update

load_dotenv()

import accounts  # noqa: E402
import ai  # noqa: E402
import collector  # noqa: E402
import cvstore  # noqa: E402
import db  # noqa: E402
import notify  # noqa: E402
import quota  # noqa: E402
import scoring  # noqa: E402
import security  # noqa: E402
import sources  # noqa: E402

COLLECT_EVERY = int(os.getenv("COLLECT_EVERY_SEC", "180"))  # 0 = pas de collecte automatique
APP_NAME = os.getenv("APP_NAME", "Veille Stages")


async def _loop():
    await asyncio.sleep(10)
    while True:
        try:
            await collector.run_once()
        except Exception as e:  # la boucle ne doit jamais s'arrêter
            print("collecte en erreur :", e)
        await asyncio.sleep(COLLECT_EVERY)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.kv_set("lock", 0)
    task = asyncio.create_task(_loop()) if COLLECT_EVERY > 0 else None
    yield
    if task:
        task.cancel()


app = FastAPI(title=APP_NAME, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"],
                   allow_methods=["*"], allow_headers=["*"])


# ---------- garde-fous contre les essais en rafale (mémoire du serveur, suffisant pour un seul service) ----------
_hits: dict[str, list[float]] = {}


def throttle(key: str, limit: int, seconds: int, message: str = "Trop d'essais. Réessaie dans quelques minutes.") -> None:
    now = time.time()
    recent = [t for t in _hits.get(key, []) if now - t < seconds]
    if len(recent) >= limit:
        _hits[key] = recent
        raise HTTPException(429, message)
    recent.append(now)
    _hits[key] = recent
    if len(_hits) > 5000:  # ménage
        for k in [k for k, v in _hits.items() if not v or now - v[-1] > 3600]:
            _hits.pop(k, None)


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "?")


# ---------- réglages du site ----------
def site_settings() -> dict:
    s = {"signup": os.getenv("SIGNUP_MODE", "open"), "invite_code": os.getenv("INVITE_CODE", "")}
    saved = db.kv_get("site", {}) or {}
    s.update({k: v for k, v in saved.items() if k in s and isinstance(v, str)})
    if s["signup"] not in ("open", "invite", "closed"):
        s["signup"] = "open"
    return s


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/public")
def public():
    """Ce que la page d'accueil a besoin de savoir avant la connexion."""
    s, lim = site_settings(), quota.limits()
    full = accounts.count() >= lim["max_users"]
    return {"name": APP_NAME, "signup": "closed" if full else s["signup"], "donate": os.getenv("DONATE_URL", ""),
            "contact": os.getenv("CONTACT_EMAIL", ""), "limits": {k: lim[k] for k in quota.LABELS},
            "shared_ai": bool(quota.shared_key())}


# ---------- comptes ----------
def current(authorization: str = Header(default="")) -> dict:
    """Utilisateur connecté, d'après son jeton. Refuse un compte supprimé, désactivé ou un ancien jeton."""
    got = security.read_token(authorization.removeprefix("Bearer ").strip())
    u = accounts.by_id(got[0]) if got else None
    if not u or u["disabled"] or u["token_version"] != got[1]:
        raise HTTPException(401, "Connexion requise")
    if time.time() - (u["last_seen"] or 0) > 600:
        accounts.set_fields(u["id"], last_seen=time.time())
    return u


def admin(u: dict = Depends(current)) -> dict:
    if not u["is_admin"]:
        raise HTTPException(403, "Réservé à l'administrateur")
    return u


def me_view(u: dict) -> dict:
    s = u["secrets"]
    return {
        "id": u["id"], "email": u["email"], "name": u["name"], "is_admin": bool(u["is_admin"]),
        "settings": scoring.user_criteria(u),
        "alerts": {"on": u["settings"].get("alerts_on", True), "discord": bool(s.get("discord")),
                   "ntfy": s.get("ntfy", ""), "telegram": bool(s.get("telegram")),
                   "telegram_available": bool(notify.token()), "telegram_bot": notify.bot_name(),
                   "telegram_code": security.short_code(u["id"], "tg"), "error": u["alert_error"] or ""},
        "ai": {**quota.view(u), "error": u["ai_error"] or ""},
        "cv": len(cvstore.cvs(u)), "cv_labels": cvstore.labels(u), "cv_slots": sorted(cvstore.cvs(u)),
        "bootstrapped": bool(u["bootstrapped"]),
    }


class Signup(BaseModel):
    email: str
    password: str
    name: str = ""
    invite: str = ""
    consent: bool = False


class Login(BaseModel):
    email: str
    password: str


@app.post("/api/signup")
async def signup(body: Signup, request: Request, bg: BackgroundTasks):
    throttle("signup-try:" + client_ip(request), 30, 3600)
    mode = public()["signup"]
    site = site_settings()
    if mode == "closed":
        raise HTTPException(403, "Les inscriptions sont fermées pour le moment.")
    if mode == "invite" and not (site["invite_code"] and hmac.compare_digest(
            body.invite.strip().lower().encode(), site["invite_code"].strip().lower().encode())):
        raise HTTPException(403, "Code d'invitation incorrect.")
    email = accounts.clean_email(body.email)
    if not accounts.EMAIL.match(email):
        raise HTTPException(400, "Adresse e-mail invalide.")
    if not 8 <= len(body.password) <= 200:
        raise HTTPException(400, "Le mot de passe doit faire au moins 8 caractères.")
    if not body.consent:
        raise HTTPException(400, "Il faut accepter les conditions d'utilisation des données pour créer un compte.")
    throttle("signup:" + client_ip(request), 5, 3600, "Trop d'inscriptions depuis cette connexion. Réessaie plus tard.")
    owner = accounts.clean_email(os.getenv("ADMIN_EMAIL", ""))
    is_admin = email == owner if owner else accounts.count() == 0
    u = await asyncio.to_thread(accounts.create, email, body.name, body.password, is_admin)
    if not u:
        raise HTTPException(409, "Un compte existe déjà avec cette adresse. Connecte-toi.")
    bg.add_task(collector.process_one, u["id"])   # prépare tout de suite son flux d'offres
    return {"token": security.make_token(u["id"], 0), "me": me_view(u)}


@app.post("/api/login")
async def login(body: Login, request: Request):
    email = accounts.clean_email(body.email)
    throttle(f"login:{client_ip(request)}", 20, 900)
    throttle(f"login:{email}", 8, 900)
    u = accounts.by_email(email)
    ok = await asyncio.to_thread(security.check_password, body.password, u["pw_hash"] if u else "scrypt$00$00")
    if not u or not ok:
        raise HTTPException(401, "Adresse ou mot de passe incorrect.")
    if u["disabled"]:
        raise HTTPException(403, "Ce compte a été désactivé.")
    accounts.set_fields(u["id"], last_seen=time.time())
    return {"token": security.make_token(u["id"], u["token_version"]), "me": me_view(u)}


@app.get("/api/me")
def get_me(u: dict = Depends(current)):
    return me_view(u)


class Name(BaseModel):
    name: str


@app.put("/api/me")
def put_me(body: Name, u: dict = Depends(current)):
    accounts.set_fields(u["id"], name=body.name.strip()[:80])
    return me_view(accounts.by_id(u["id"]))


class PasswordChange(BaseModel):
    old: str
    new: str


@app.post("/api/me/password")
def change_password(body: PasswordChange, u: dict = Depends(current)):
    throttle(f"pw:{u['id']}", 8, 900)
    if not security.check_password(body.old, u["pw_hash"]):
        raise HTTPException(400, "Mot de passe actuel incorrect.")
    if not 8 <= len(body.new) <= 200:
        raise HTTPException(400, "Le nouveau mot de passe doit faire au moins 8 caractères.")
    version = u["token_version"] + 1   # déconnecte les autres appareils
    accounts.set_fields(u["id"], pw_hash=security.hash_password(body.new), token_version=version)
    return {"token": security.make_token(u["id"], version)}


class Confirm(BaseModel):
    password: str


@app.post("/api/me/delete")
def delete_me(body: Confirm, u: dict = Depends(current)):
    throttle(f"pw:{u['id']}", 8, 900)
    if not security.check_password(body.password, u["pw_hash"]):
        raise HTTPException(400, "Mot de passe incorrect.")
    accounts.remove(u["id"])
    return {"ok": True}


@app.get("/api/me/export")
def export_me(u: dict = Depends(current)):
    """Toutes les données personnelles du compte, dans un fichier lisible (droit d'accès)."""
    o, uo, a = db.offers, db.user_offers, db.applications
    with db.engine.connect() as c:
        apps = [dict(r._mapping) for r in c.execute(select(a).where(a.c.user_id == u["id"]))]
        marks = [dict(r._mapping) for r in c.execute(
            select(o.c.title, o.c.company, o.c.url, uo.c.state, uo.c.ai_score, uo.c.ai_reason, uo.c.cv)
            .join(uo, uo.c.offer_id == o.c.id).where(uo.c.user_id == u["id"], uo.c.state != "new"))]
    return {"compte": {"email": u["email"], "nom": u["name"], "cree_le": u["created"]},
            "reglages": u["settings"], "profil": u["profile"], "candidatures": apps, "offres_triees": marks,
            "alertes": {k: bool(v) for k, v in u["secrets"].items()}}


# ---------- clé Gemini personnelle ----------
class Key(BaseModel):
    key: str = ""


@app.put("/api/me/gemini")
async def put_gemini(body: Key, bg: BackgroundTasks, u: dict = Depends(current)):
    key = body.key.strip()
    if key:
        throttle(f"key:{u['id']}", 10, 3600)
        if not 20 <= len(key) <= 200 or " " in key:
            raise HTTPException(400, "Cette clé n'a pas le bon format. Copie-la en entier depuis Google AI Studio.")
        try:
            await ai.check_key(key)
        except Exception as e:
            raise HTTPException(400, f"Clé non acceptée : {e}")
    u["secrets"]["gemini"] = key
    accounts.save_secrets(u)
    accounts.set_fields(u["id"], ai_error="")
    bg.add_task(collector.process_one, u["id"])
    return me_view(accounts.by_id(u["id"]))


# ---------- alertes personnelles ----------
class Alerts(BaseModel):
    discord: str | None = None     # None = inchangé, "" = supprimer
    ntfy: str | None = None
    telegram: bool | None = None   # False = délier
    on: bool | None = None


@app.put("/api/me/alerts")
def put_alerts(body: Alerts, u: dict = Depends(current)):
    s = u["secrets"]
    if body.discord is not None:
        url = body.discord.strip()
        if url and not notify.DISCORD.match(url):
            raise HTTPException(400, "Ce n'est pas une adresse de webhook Discord. Elle commence par "
                                     "https://discord.com/api/webhooks/")
        s["discord"] = url
    if body.ntfy is not None:
        topic = body.ntfy.strip()
        if topic and not notify.NTFY.match(topic):
            raise HTTPException(400, "Sujet ntfy invalide : 8 à 64 lettres, chiffres, tirets, sans espace ni accent.")
        s["ntfy"] = topic
    if body.telegram is False:
        s["telegram"] = ""
    accounts.save_secrets(u)
    if body.on is not None:
        u["settings"]["alerts_on"] = bool(body.on)
        accounts.save_settings(u)
    accounts.set_fields(u["id"], alert_error="")
    return me_view(accounts.by_id(u["id"]))


@app.post("/api/me/alerts/test")
async def test_alerts(u: dict = Depends(current)):
    throttle(f"test:{u['id']}", 6, 600, "Trop de tests d'affilée. Réessaie dans quelques minutes.")
    ch = {k: v for k, v in u["secrets"].items() if k in ("discord", "ntfy", "telegram") and v}
    try:
        if not await notify.send(ch, f"🔔 <b>{APP_NAME}</b>\nMessage de test : tes alertes fonctionnent.",
                                 os.getenv("APP_URL", ""), "Ouvrir le site"):
            raise RuntimeError("Aucun canal d'alerte enregistré.")
    except Exception as e:
        raise HTTPException(400, str(e) or type(e).__name__)
    accounts.set_fields(u["id"], alert_error="")
    return {"ok": True}


@app.post("/api/me/telegram/link")
async def telegram_link(u: dict = Depends(current)):
    throttle(f"tg:{u['id']}", 10, 600)
    try:
        found = await notify.find_chat(security.short_code(u["id"], "tg"))
    except Exception as e:
        raise HTTPException(400, str(e))
    if not found:
        raise HTTPException(400, "Je ne trouve pas ton message. Envoie ton code au bot dans Telegram, puis réessaie.")
    u["secrets"]["telegram"] = found["chat_id"]
    accounts.save_secrets(u)
    await notify.send({"telegram": found["chat_id"]}, "✅ <b>Connexion réussie.</b> Tu recevras ici tes alertes.")
    return me_view(accounts.by_id(u["id"]))


# ---------- réglages personnels de la veille ----------
def _clean_list(v, each: int = 60, most: int = 150) -> list[str]:
    return [str(x).strip()[:each] for x in v if str(x).strip()][:most]


@app.get("/api/criteria")
def get_criteria(u: dict = Depends(current)):
    return scoring.user_criteria(u)


@app.put("/api/criteria")
def put_criteria(body: dict, bg: BackgroundTasks, u: dict = Depends(current)):
    s = u["settings"]
    if isinstance(body.get("goal"), str) and body["goal"].strip():
        s["goal"] = " ".join(body["goal"].split())[:300]
    for k in ("min_kw", "notify_ai", "notify_kw", "ai_min_kw"):
        if isinstance(body.get(k), (int, float)):
            s[k] = max(0, min(100, int(body[k])))
    if isinstance(body.get("profile_keywords"), list):
        s["profile_keywords"] = _clean_list(body["profile_keywords"], 40, 40)
    for k in scoring.USER_LISTS:
        if isinstance(body.get(k), list):
            mine = _clean_list(body[k])
            if mine == scoring.criteria()[k]:
                s.pop(k, None)      # identique à la liste du site : il continue de suivre ses mises à jour
            else:
                s[k] = mine
    if body.get("reset_lists"):
        for k in scoring.USER_LISTS:
            s.pop(k, None)
    accounts.save_settings(u)
    bg.add_task(_resync, u["id"])
    return scoring.user_criteria(u)


async def _resync(uid: int) -> None:
    await collector.resync_one(uid)


# ---------- profil / CV ----------
class CvText(BaseModel):
    slot: str
    text: str


class CvLabel(BaseModel):
    slot: str
    label: str


def _profile_view(u: dict) -> dict:
    p = cvstore.get(u)
    return {"slots": cvstore.labels(u), "cvs": p["cvs"], "analysis": p.get("analysis")}


async def _analyse(u: dict) -> str:
    """Analyse l'ensemble des CV avec Gemini et ajoute leurs mots-clés aux réglages. Renvoie un message d'erreur ou ''."""
    try:
        key, own, _ = quota.grant(u, "cv")
        analysis = await ai.analyse_cv(cvstore.block(u, each=4000), scoring.user_criteria(u)["goal"], key)
    except Exception as e:
        return str(e)
    quota.record(u, "cv", 1, own)
    cvstore.get(u)["analysis"] = analysis
    accounts.save_profile(u)
    u["settings"]["profile_keywords"] = _clean_list([str(k).lower() for k in analysis.get("mots_cles", [])], 40, 30)
    accounts.save_settings(u)
    return ""


async def _store_cv(u: dict, bg: BackgroundTasks, slot: str, text: str, filename: str = "") -> dict:
    if slot not in cvstore.SLOTS:
        raise HTTPException(400, "Emplacement de CV inconnu")
    p = cvstore.get(u)
    old = p["cvs"].get(slot, {})
    if text.strip():
        p["cvs"][slot] = {"text": text.strip()[:20000], "file": (filename or old.get("file", ""))[:120],
                          "label": old.get("label", "")}
    else:
        p["cvs"].pop(slot, None)
    accounts.save_profile(u)
    error = await _analyse(u) if cvstore.cvs(u) else ""
    bg.add_task(_resync, u["id"])
    return {**_profile_view(u), "error": error}


@app.get("/api/profile")
def get_profile(u: dict = Depends(current)):
    return _profile_view(u)


@app.put("/api/profile")
async def put_profile(body: CvText, bg: BackgroundTasks, u: dict = Depends(current)):
    return await _store_cv(u, bg, body.slot, body.text)


@app.put("/api/profile/label")
def put_label(body: CvLabel, u: dict = Depends(current)):
    p = cvstore.get(u)
    if body.slot not in cvstore.SLOTS:
        raise HTTPException(400, "Emplacement de CV inconnu")
    p["cvs"].setdefault(body.slot, {"text": "", "file": ""})["label"] = " ".join(body.label.split())[:40]
    accounts.save_profile(u)
    return _profile_view(u)


@app.post("/api/profile/cv")
async def upload_cv(bg: BackgroundTasks, slot: str = "cv1", file: UploadFile = File(...), u: dict = Depends(current)):
    throttle(f"cv:{u['id']}", 20, 3600)
    data = await file.read()
    if len(data) > 8_000_000:
        raise HTTPException(400, "Fichier trop lourd (8 Mo maximum)")
    name = (file.filename or "").lower()
    if name.endswith(".pdf") or data[:4] == b"%PDF":
        try:
            from pypdf import PdfReader
            text = await asyncio.to_thread(
                lambda: "\n".join((pg.extract_text() or "") for pg in PdfReader(io.BytesIO(data)).pages[:12]))
        except Exception as e:
            raise HTTPException(400, f"PDF illisible : {e}")
    elif name.endswith((".txt", ".md")):
        text = data.decode("utf-8", errors="ignore")
    else:
        raise HTTPException(400, "Envoie ton CV en PDF (ou en .txt)")
    if len(text.strip()) < 200:
        raise HTTPException(400, "Je n'arrive pas à lire le texte de ce PDF (CV scanné ou en image ?). "
                                 "Exporte-le en PDF texte ou colle son contenu dans la zone de texte.")
    return await _store_cv(u, bg, slot, text.replace("\x00", ""), file.filename or "")


# ---------- flux d'offres (le stock commun, vu à travers le tri de l'utilisateur) ----------
@app.get("/api/offers")
def list_offers(state: str = "new", min_score: int = 0, q: str = "", hours: int = 0, limit: int = 200,
                u: dict = Depends(current)):
    o, uo = db.offers, db.user_offers
    best = func.coalesce(uo.c.ai_score, uo.c.kw_score)
    stmt = (select(o.c.id, o.c.source, o.c.company, o.c.title, o.c.place, o.c.url, o.c.published, o.c.first_seen,
                   uo.c.kw_score, uo.c.ai_score, uo.c.ai_reason, uo.c.cv, uo.c.state, uo.c.dup_note,
                   func.substr(o.c.description, 1, 400).label("excerpt"))
            .join(uo, uo.c.offer_id == o.c.id).where(uo.c.user_id == u["id"]))
    if state != "all":
        stmt = stmt.where(uo.c.state == state)
    if min_score:
        stmt = stmt.where(best >= min_score)
    if hours:
        stmt = stmt.where(o.c.first_seen >= time.time() - hours * 3600)
    if q.strip():
        like = f"%{q.strip().lower()[:80]}%"
        stmt = stmt.where(or_(func.lower(o.c.title).like(like), func.lower(o.c.company).like(like),
                              func.lower(o.c.description).like(like)))
    stmt = stmt.order_by(o.c.first_seen.desc()).limit(max(1, min(limit, 500)))
    with db.engine.connect() as c:
        rows = [dict(r._mapping) for r in c.execute(stmt)]
    for r in rows:   # date de mise en ligne au format AAAA-MM-JJ, '' si la source ne la donne pas
        r["published"] = scoring.published_date(r["published"], r["first_seen"])
    return rows


@app.get("/api/offers/{oid}")
def get_offer(oid: str, u: dict = Depends(current)):
    o, uo = db.offers, db.user_offers
    with db.engine.connect() as c:
        r = c.execute(select(o, uo.c.cv, uo.c.ai_score, uo.c.ai_reason, uo.c.state)
                      .join(uo, uo.c.offer_id == o.c.id).where(o.c.id == oid, uo.c.user_id == u["id"])).first()
    if not r:
        raise HTTPException(404, "Offre introuvable")
    return dict(r._mapping)


class OfferState(BaseModel):
    state: str


@app.patch("/api/offers/{oid}")
def set_offer_state(oid: str, body: OfferState, u: dict = Depends(current)):
    if body.state not in ("new", "saved", "hidden", "applied"):
        raise HTTPException(400, "État inconnu")
    uo = db.user_offers
    with db.engine.begin() as c:
        c.execute(update(uo).where(uo.c.user_id == u["id"], uo.c.offer_id == oid).values(state=body.state))
    return {"ok": True}


# "/api/collect" est bloqué par les bloqueurs de publicité (même adresse qu'un outil de pistage connu).
@app.post("/api/refresh")
async def refresh(u: dict = Depends(current)):
    """Met à jour le flux de l'utilisateur tout de suite (tri, notes, alertes) sans attendre le prochain passage."""
    throttle(f"refresh:{u['id']}", 3, 120, "Tu viens déjà d'actualiser. Réessaie dans deux minutes.")
    return await collector.process_one(u["id"])


@app.get("/api/status")
def status(u: dict = Depends(current)):
    o, uo = db.offers, db.user_offers
    mine = select(func.count()).select_from(uo.join(o, uo.c.offer_id == o.c.id)).where(uo.c.user_id == u["id"])
    with db.engine.connect() as c:
        total = c.execute(mine.where(uo.c.state != "hidden")).scalar()
        day = c.execute(mine.where(o.c.first_seen >= time.time() - 86400)).scalar()
        pool = c.execute(select(func.count()).select_from(o)).scalar()
    return {"total": total, "last_24h": day, "pool": pool, "last_run": db.kv_get("last_run", None),
            "every": COLLECT_EVERY}


# ---------- suivi des candidatures ----------
class Application(BaseModel):
    company: str
    job: str = ""
    url: str = ""
    contact: str = ""
    note: str = ""
    status: int = 1


@app.get("/api/applications")
def list_apps(u: dict = Depends(current)):
    a = db.applications
    with db.engine.connect() as c:
        return [dict(r._mapping) for r in c.execute(select(a).where(a.c.user_id == u["id"]).order_by(a.c.updated.desc()))]


@app.post("/api/applications")
def add_app(body: Application, u: dict = Depends(current)):
    a = db.applications
    with db.engine.begin() as c:
        if (c.execute(select(func.count()).select_from(a).where(a.c.user_id == u["id"])).scalar() or 0) >= 1000:
            raise HTTPException(400, "Limite de 1000 candidatures atteinte.")
        r = c.execute(insert(a).values(user_id=u["id"], company=body.company[:200], job=body.job[:300],
                                       url=body.url[:1000], contact=body.contact[:200], note=body.note[:2000],
                                       status=max(0, min(5, body.status)), updated=time.time()))
        return {"id": r.inserted_primary_key[0]}


@app.patch("/api/applications/{id}")
def set_status(id: int, status: int, u: dict = Depends(current)):
    a = db.applications
    with db.engine.begin() as c:
        c.execute(update(a).where(a.c.id == id, a.c.user_id == u["id"])
                  .values(status=max(0, min(5, status)), updated=time.time()))
    return {"ok": True}


@app.delete("/api/applications/{id}")
def del_app(id: int, u: dict = Depends(current)):
    a = db.applications
    with db.engine.begin() as c:
        c.execute(delete(a).where(a.c.id == id, a.c.user_id == u["id"]))
    return {"ok": True}


# ---------- assistant Gemini ----------
TASKS = {
    "fit": "Analyse cette offre par rapport à mon profil : score d'adéquation sur 10, points forts, lacunes, mots-clés à reprendre, verdict (postuler ou non).",
    "letter": "Rédige une lettre de motivation courte (250 mots max), concrète et sur mesure, sans formules creuses.",
    "cv": "Propose les modifications précises de mon CV pour cette offre : accroche, compétences à mettre en avant, puces avec résultats chiffrés.",
    "interview": "Pose-moi 8 questions d'entretien adaptées à cette offre et donne les points clés d'une bonne réponse pour chacune.",
    "targets": "Propose 15 entreprises (avec ville) pouvant proposer des offres correspondant à ma recherche et à mon profil, avec l'équipe à viser. Je dois vérifier les offres actuelles.",
    "message": "Rédige un message LinkedIn de 500 caractères maximum au recruteur ou au manager de cette offre, direct et personnalisé, pour appuyer ma candidature.",
}


class AIReq(BaseModel):
    task: str
    offer: str = ""
    cv: str = ""


@app.post("/api/ai")
async def assistant(req: AIReq, u: dict = Depends(current)):
    if req.task not in TASKS:
        raise HTTPException(400, "Tâche inconnue")
    profile = cvstore.text_for(u, req.cv)
    if not profile:
        raise HTTPException(400, "Ajoute d'abord ton CV dans l'onglet Profil")
    throttle(f"ai:{u['id']}", 6, 60, "Doucement : attends une minute entre plusieurs demandes.")
    try:
        key, own, _ = quota.grant(u, "assist")
    except quota.QuotaError as e:
        raise HTTPException(429, str(e))
    prompt = ("Tu es un coach expert du recrutement en France. "
              "Réponds en français, de façon concrète, sans inventer de faits sur moi ni sur l'entreprise.\n\n"
              f"Ce que je cherche : {scoring.user_criteria(u)['goal']}\n\n"
              f"Mon CV :\n{profile[:8000]}\n\nOffre :\n{req.offer[:6000] or '(aucune)'}\n\nTâche : {TASKS[req.task]}")
    try:
        text = await ai.generate(prompt, key)
    except ai.AIError as e:
        raise HTTPException(502, str(e))
    quota.record(u, "assist", 1, own)
    return {"text": text, "ai": quota.view(u)}


# ---------- réveil / déclenchement externe (cron-job.org) ----------
@app.get("/api/cron")
async def cron(key: str = "", wait: int = 0, bg: BackgroundTasks = None):
    if not os.getenv("CRON_KEY") or not hmac.compare_digest(key.encode(), os.getenv("CRON_KEY").encode()):
        raise HTTPException(403, "Clé invalide")
    if wait:
        return await collector.run_once()
    bg.add_task(collector.run_once)
    return {"started": True}


# ---------- administration ----------
@app.get("/api/admin/overview")
def admin_overview(_: dict = Depends(admin)):
    day = quota.today()
    with db.engine.connect() as c:
        pool = c.execute(select(func.count()).select_from(db.offers)).scalar()
        used = {}
        for r in c.execute(select(db.usage).where(db.usage.c.day == day)):
            used.setdefault(r.user_id, {})[r.kind] = r.n
    people = [{"id": u["id"], "email": u["email"], "name": u["name"], "created": u["created"],
               "last_seen": u["last_seen"], "is_admin": bool(u["is_admin"]), "disabled": bool(u["disabled"]),
               "own_key": bool(accounts.own_key(u)), "cv": len(cvstore.cvs(u)),
               "channels": sorted(k for k in ("discord", "ntfy", "telegram") if u["secrets"].get(k)),
               "paused": time.time() - (u["last_seen"] or 0) > collector.INACTIVE_DAYS * 86400,
               "usage": used.get(u["id"], {}), "ai_error": u["ai_error"] or "", "alert_error": u["alert_error"] or ""}
              for u in accounts.everyone()]
    names = {c["name"]: True for k, v in sources.companies().items() if isinstance(v, list) for c in v}
    return {"users": people, "pool": pool, "last_run": db.kv_get("last_run", None), "sources": db.kv_prefix("src:"),
            "companies": names, "shared": {"used": used.get(0, {}).get("req", 0), "limit": quota.limits()["shared_requests"]},
            "config": {"gemini": bool(quota.shared_key()), "adzuna": sources.adzuna_enabled(),
                       "france_travail": sources.ft_enabled(), "telegram": bool(notify.token()),
                       "database": "postgres" if db.IS_PG else "sqlite", "secret": bool(os.getenv("SECRET_KEY")),
                       "cron": bool(os.getenv("CRON_KEY")), "app_url": bool(os.getenv("APP_URL"))}}


@app.get("/api/admin/settings")
def admin_get_settings(_: dict = Depends(admin)):
    crit = scoring.criteria()
    crit.pop("profile_keywords", None)
    return {"limits": quota.limits(), "site": site_settings(), "criteria": crit}


@app.put("/api/admin/settings")
def admin_put_settings(body: dict, _: dict = Depends(admin)):
    if isinstance(body.get("limits"), dict):
        lim = {k: max(0, min(100000, int(v))) for k, v in body["limits"].items()
               if k in quota.DEFAULT_LIMITS and isinstance(v, (int, float))}
        db.kv_set("limits", {**(db.kv_get("limits", {}) or {}), **lim})
    if isinstance(body.get("site"), dict):
        site = site_settings()
        if body["site"].get("signup") in ("open", "invite", "closed"):
            site["signup"] = body["site"]["signup"]
        if isinstance(body["site"].get("invite_code"), str):
            site["invite_code"] = body["site"]["invite_code"].strip()[:60]
        db.kv_set("site", site)
    if isinstance(body.get("criteria"), dict):
        saved = db.kv_get("criteria", {}) or {}
        for k, default in scoring.DEFAULT_CRITERIA.items():
            v = body["criteria"].get(k)
            if isinstance(default, list) and isinstance(v, list):
                saved[k] = _clean_list(v, 300, 200)
            elif isinstance(default, int) and isinstance(v, (int, float)):
                saved[k] = max(0, min(100, int(v)))
        db.kv_set("criteria", saved)
    return admin_get_settings(_)


class UserPatch(BaseModel):
    disabled: bool | None = None
    is_admin: bool | None = None


def _target(uid: int, me: dict) -> dict:
    u = accounts.by_id(uid)
    if not u:
        raise HTTPException(404, "Compte introuvable")
    if u["id"] == me["id"]:
        raise HTTPException(400, "Impossible sur ton propre compte.")
    return u


@app.patch("/api/admin/users/{uid}")
def admin_patch_user(uid: int, body: UserPatch, me: dict = Depends(admin)):
    _target(uid, me)
    fields = {k: int(v) for k, v in body.model_dump().items() if v is not None}
    if fields:
        accounts.set_fields(uid, **fields)
    return {"ok": True}


@app.post("/api/admin/users/{uid}/reset")
def admin_reset_password(uid: int, me: dict = Depends(admin)):
    """Mot de passe oublié : l'administrateur en crée un provisoire et le transmet à la personne."""
    u = _target(uid, me)
    temp = secrets.token_urlsafe(9)
    accounts.set_fields(uid, pw_hash=security.hash_password(temp), token_version=u["token_version"] + 1)
    return {"password": temp}


@app.delete("/api/admin/users/{uid}")
def admin_delete_user(uid: int, me: dict = Depends(admin)):
    _target(uid, me)
    accounts.remove(uid)
    return {"ok": True}


@app.post("/api/admin/collect")
async def admin_collect(_: dict = Depends(admin)):
    return await collector.run_once(force=True)


# ---------- site (frontend compilé), servi par le même service ----------
DIST = pathlib.Path(__file__).parent.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="site")
