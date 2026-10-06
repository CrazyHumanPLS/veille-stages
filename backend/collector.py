"""Veille en deux temps.

1. collect() : interroge les sources et range les nouveautés dans le stock COMMUN d'offres (une seule fois
   pour tout le monde, quel que soit le nombre d'inscrits).
2. process_user() : pour chaque utilisateur, trie le stock avec SES mots-clés, note les nouveautés d'après
   SES CV (dans la limite de son quota) et envoie SES alertes.

Lancement manuel :  python collector.py
"""
import asyncio
import hashlib
import os
import re
import time

import httpx
from sqlalchemy import delete, insert, select, update

import accounts
import ai
import cvstore as prof
import db
import notify
import quota
import scoring
import sources

# Délai minimum entre deux interrogations d'une même source (minutes)
EVERY = {"ft": 3, "adzuna": 120, "ats": 15, "rss": 15}
MAX_ALERTS_PER_RUN = 10      # au-delà : un message récapitulatif
LOCK_SECONDS = 240
DIGEST_ABOVE = 5             # au-delà de 5 bonnes offres d'un coup : un récapitulatif au lieu d'une alerte chacune
HIDE_BELOW = 30              # score Gemini sous lequel une offre est masquée automatiquement
STOCK_DAYS = 45              # ancienneté maximale des offres proposées à un nouvel inscrit
FIRST_RUN_AI = 40            # offres du stock notées par l'IA à l'inscription (les mieux placées par mots-clés)
SHARED_BATCHES_PER_RUN = 6   # appels à la clé commune par passage (un appel = 8 offres) : respecte le débit gratuit
OWN_BATCHES_PER_RUN = 5      # appels par passage pour quelqu'un qui utilise sa propre clé
INACTIVE_DAYS = 21           # sans visite du site pendant ce délai, la veille du compte se met en pause
MAX_EVAL_SECONDS = 150       # durée maximale consacrée aux utilisateurs à chaque passage


def _due(name: str, minutes: float, force: bool) -> bool:
    st = db.kv_get(f"src:{name}", {}) or {}
    return force or time.time() - st.get("last", 0) >= minutes * 60 - 5


def _state(name: str, ok: bool, found: int = 0, new: int = 0, error: str = "") -> None:
    prev = db.kv_get(f"src:{name}", {}) or {}
    db.kv_set(f"src:{name}", {"last": time.time(), "ok": ok, "found": found, "new": new,
                              "error": error[:200], "last_ok": time.time() if ok else prev.get("last_ok", 0)})


def keep(raw: dict, crit: dict) -> dict | None:
    """Applique les filtres. Renvoie la ligne prête à enregistrer, ou None si l'offre est écartée."""
    if not raw["title"] or not raw["url"].lower().startswith(("https://", "http://")):
        return None   # pas de titre, ou lien qui n'est pas une adresse web (jamais de « javascript: »)
    if not scoring.is_internship(raw["title"], raw["description"]):
        return None
    if not raw["geo_ok"] and not scoring.is_idf(raw["place"]):
        return None
    score = scoring.kw_score(raw["title"], raw["description"], crit)
    if score < crit["min_kw"]:
        return None
    return {"id": scoring.fingerprint(raw["source"], raw["ext_id"], raw["company"], raw["title"], raw["place"]),
            "source": raw["source"], "company": raw["company"], "title": raw["title"], "place": raw["place"],
            "url": raw["url"], "description": raw["description"],
            "published": scoring.published_date(raw["published"]) or raw["published"],
            "ext_id": raw["ext_id"][:200], "first_seen": time.time(), "kw_score": score}


_seen: dict[str, list[dict]] = {}   # entreprise -> offres déjà dans le stock commun


def _city(place: str) -> str:
    words = re.sub(r"[^a-z ]", " ", scoring.norm(place)).split()
    return words[0] if words else ""


def load_seen() -> None:
    """Mémorise le stock commun : sert à reconnaître une offre republiée sur un autre site."""
    _seen.clear()
    o = db.offers
    with db.engine.connect() as c:
        for r in c.execute(select(o.c.company, o.c.title, o.c.place, o.c.source)):
            _remember(r.company, r.title, r.place, r.source)


def _remember(company, title, place, source) -> None:
    key = scoring.company_key(company or "")
    if key and title:
        _seen.setdefault(key, []).append({"title": title, "city": _city(place or ""), "source": source})


def check_seen(row: dict) -> bool:
    """Doublon à ignorer ? = même entreprise, même intitulé, même ville, vu sur UN AUTRE site.
    Deux annonces du même site (deux équipes, deux villes) sont toujours gardées."""
    city = _city(row["place"])
    for e in _seen.get(scoring.company_key(row["company"]), []):
        if (scoring.same_job(row["title"], e["title"]) and e["source"] != row["source"]
                and (not city or not e["city"] or city == e["city"])):
            return True
    return False


def store(name: str, raws: list[dict], crit: dict, distinct: bool = False) -> int:
    """distinct : vrai pour le site carrières d'une entreprise, où deux références différentes sont deux vraies
    offres même si le titre et la ville sont identiques. Sur un agrégateur, ce serait la même offre republiée."""
    rows = {}
    for raw in raws:
        row = keep(raw, crit)
        if not row:
            continue
        other = rows.get(row["id"])
        if other and distinct and other["ext_id"] != row["ext_id"]:
            row["id"] = hashlib.sha1(f"{row['source']}|{row['ext_id']}".encode()).hexdigest()
        rows.setdefault(row["id"], row)
    known = db.known_refs([r["id"] for r in rows.values()])
    new = 0
    for row in rows.values():
        if row["id"] in known:
            src, ext = known[row["id"]]
            if not (distinct and src == row["source"] and ext and ext != row["ext_id"]):
                continue
            row["id"] = hashlib.sha1(f"{row['source']}|{row['ext_id']}".encode()).hexdigest()
            if db.known_refs([row["id"]]):
                continue
        elif check_seen(row):
            continue
        if db.insert_offer(row):
            new += 1
            _remember(row["company"], row["title"], row["place"], row["source"])
    _state(name, True, found=len(raws), new=new)
    return new


async def _run_source(name: str, coro, crit: dict, distinct: bool = False) -> int:
    try:
        return store(name, await coro, crit, distinct)
    except Exception as e:  # une source en panne ne doit jamais bloquer les autres
        _state(name, False, error=f"{type(e).__name__}: {e}")
        return 0


async def collect(force: bool = False) -> int:
    crit = scoring.criteria()
    load_seen()
    jobs = []
    async with httpx.AsyncClient(timeout=30, headers=sources.UA, follow_redirects=True) as h:
        if sources.ft_enabled() and _due("France Travail", EVERY["ft"], force):
            jobs.append(_run_source("France Travail", sources.france_travail(h, crit), crit))
        if sources.adzuna_enabled() and _due("Adzuna", EVERY["adzuna"], force):
            jobs.append(_run_source("Adzuna", sources.adzuna(h, crit), crit))
        for kind, fetch in sources.ATS.items():
            for c in sources.companies().get(kind, []):
                if _due(c["name"], EVERY["ats"], force):
                    jobs.append(_run_source(c["name"], fetch(h, c), crit, distinct=True))
        for f in sources.companies().get("rss", []):
            if _due(f["name"], EVERY["rss"], force):
                jobs.append(_run_source(f["name"], sources.rss(h, f["url"], f["name"], f["name"]), crit, distinct=True))
        for i, line in enumerate(crit["rss_feeds"]):
            label, _, url = line.rpartition("|")          # format accepté : « Nom | https://… » ou l'adresse seule
            label = label.strip() or f"RSS {i + 1}"
            if url.strip().startswith("http") and _due(label, EVERY["rss"], force):
                jobs.append(_run_source(label, sources.rss(h, url.strip(), "", label), crit))
        results = await asyncio.gather(*jobs) if jobs else []
    return sum(results)


# =====================================================================================================
# Partie personnelle : tri, notation et alertes pour un utilisateur
# =====================================================================================================
_locks: dict[int, asyncio.Lock] = {}


def _applied(uid: int) -> list[tuple[str, str]]:
    """(entreprise, intitulé) de tout ce à quoi l'utilisateur a déjà postulé."""
    a, uo, o = db.applications, db.user_offers, db.offers
    with db.engine.connect() as c:
        out = [(scoring.company_key(r.company or ""), r.job or "")
               for r in c.execute(select(a.c.company, a.c.job).where(a.c.user_id == uid))]
        out += [(scoring.company_key(r.company or ""), r.title or "") for r in c.execute(
            select(o.c.company, o.c.title).join(uo, uo.c.offer_id == o.c.id)
            .where(uo.c.user_id == uid, uo.c.state == "applied"))]
    return [x for x in out if x[0] and x[1]]


def sync_user(u: dict, full: bool = False, site: dict | None = None) -> int:
    """Propose à l'utilisateur les offres du stock commun qui passent SES mots-clés.
    full=True : après un changement de mots-clés, recalcule aussi le score des offres déjà proposées."""
    uid, now = u["id"], time.time()
    crit = scoring.user_criteria(u, site)
    oldest = now - STOCK_DAYS * 86400
    since = oldest if full or not u["cursor"] else max(oldest, u["cursor"] - 600)
    o, uo = db.offers, db.user_offers
    with db.engine.connect() as c:
        pool = c.execute(select(o.c.id, o.c.company, o.c.title, o.c.description, o.c.first_seen)
                         .where(o.c.first_seen > since)).all()
        mine = {r.offer_id: r for r in c.execute(
            select(uo.c.offer_id, uo.c.state, uo.c.ai_score, uo.c.kw_score).where(uo.c.user_id == uid))}
    applied = _applied(uid)
    add, change, drop, newest = [], [], [], u["cursor"] or 0
    for r in pool:
        newest = max(newest, r.first_seen)
        have = mine.get(r.id)
        if have and not full:
            continue
        score = scoring.kw_score(r.title, r.description, crit)
        if have:
            if score < crit["min_kw"] and have.state == "new" and have.ai_score is None:
                drop.append(r.id)
            elif score != have.kw_score:
                change.append((r.id, score))
            continue
        if score < crit["min_kw"]:
            continue
        note = ""
        key = scoring.company_key(r.company or "")
        for comp, title in applied:
            if comp == key and scoring.same_job(r.title, title):
                note = f"Tu as déjà postulé à une offre proche chez {r.company} : « {title[:80]} »"
                break
        add.append({"user_id": uid, "offer_id": r.id, "kw_score": score, "ai_score": None, "ai_reason": "",
                    "cv": "", "notified": 0, "state": "new", "dup_note": note})
    with db.engine.begin() as c:
        if add:
            c.execute(insert(uo), add)
        for oid, score in change:
            c.execute(update(uo).where(uo.c.user_id == uid, uo.c.offer_id == oid).values(kw_score=score))
        for i in range(0, len(drop), 400):
            c.execute(delete(uo).where(uo.c.user_id == uid, uo.c.offer_id.in_(drop[i:i + 400])))
        c.execute(update(db.users).where(db.users.c.id == uid).values(cursor=newest or now))
    u["cursor"] = newest or now
    return len(add)


def _pending(uid: int, first: bool) -> list[dict]:
    o, uo = db.offers, db.user_offers
    stmt = (select(o.c.id, o.c.source, o.c.company, o.c.title, o.c.place, o.c.url, o.c.description, o.c.published,
                   o.c.first_seen, uo.c.kw_score, uo.c.ai_score, uo.c.ai_reason, uo.c.cv, uo.c.state, uo.c.dup_note)
            .join(uo, uo.c.offer_id == o.c.id).where(uo.c.user_id == uid, uo.c.notified == 0)
            .order_by(uo.c.kw_score.desc() if first else o.c.first_seen.desc()))
    with db.engine.connect() as c:
        return [dict(r._mapping) for r in c.execute(stmt)]


def _best(o: dict) -> int:
    return o["ai_score"] if o["ai_score"] is not None else o["kw_score"]


def _lines(offers: list[dict]) -> str:
    return "\n".join(f"• {_best(o)}/100 — <a href=\"{notify.html.escape(o['url'], quote=True)}\">{notify.html.escape(o['title'][:70])}</a> "
                     f"({notify.html.escape((o['company'] or '?')[:30])})" for o in offers)


async def process_user(u: dict, budget: dict) -> dict:
    """Trie, note et alerte pour un utilisateur. budget["shared"] = appels restants sur la clé commune."""
    uid, now = u["id"], time.time()
    site = scoring.criteria()
    crit = scoring.user_criteria(u, site)
    created = sync_user(u, site=site)
    first = not u["bootstrapped"]
    profile = prof.block(u)
    slots = sorted(prof.cvs(u))
    result = {"new": created, "scored": 0, "alerts": 0}
    # Tant que le CV n'est pas importé, on ne note rien et on n'alerte pas : le récapitulatif de départ
    # partira une fois le CV en place. Les offres restent visibles sur le site avec leur score par mots-clés.
    if first and quota.ai_available(u) and not profile.strip():
        return {**result, "setup": "cv"}
    if first and quota.needs_verification(u) and quota.shared_key():
        return {**result, "setup": "email"}
    pending = _pending(uid, first)
    if not pending:
        if first:
            accounts.set_fields(uid, bootstrapped=1)
        return result

    # ---- notation par l'IA ----
    wait, error, own_left = False, "", OWN_BATCHES_PER_RUN
    if quota.ai_available(u) and profile.strip():
        # Économie de quota : sous le seuil, l'offre garde son score par mots-clés et n'est pas envoyée à l'IA.
        to_score = [o for o in pending if o["ai_score"] is None and o["kw_score"] >= crit["ai_min_kw"]]
        if first:
            to_score = to_score[:FIRST_RUN_AI]
        for i in range(0, len(to_score), 8):
            batch = to_score[i:i + 8]
            try:
                key, own, n = quota.grant(u, "score", len(batch))
            except quota.QuotaError:
                break  # limite du jour atteinte : les offres restantes gardent leur score par mots-clés
            if (own_left if own else budget["shared"]) <= 0:
                wait = True  # débit maximal du passage atteint : la suite au prochain passage, dans 3 minutes
                break
            if own:
                own_left -= 1
            else:
                budget["shared"] -= 1
            batch = batch[:n]
            try:
                res = await ai.score_offers(profile, batch, crit["goal"], slots, key)
            except Exception as e:
                error = (str(e) or type(e).__name__)[:300]
                if not own:
                    db.kv_set("src:Gemini (clé commune)", {"last": now, "ok": False, "error": error[:200]})
                # premier échec : on réessaie au prochain passage ; deuxième de suite : on se rabat sur les mots-clés
                wait = not u["ai_error"]
                break
            quota.record(u, "score", len(batch), own)
            if not own:
                db.kv_set("src:Gemini (clé commune)", {"last": now, "ok": True, "found": len(res), "last_ok": now})
            with db.engine.begin() as c:
                for o in batch:
                    if o["id"] in res:
                        o["ai_score"], o["ai_reason"], o["cv"] = (res[o["id"]]["score"], res[o["id"]]["raison"],
                                                                  res[o["id"]]["cv"])
                        result["scored"] += 1
                        c.execute(update(db.user_offers)
                                  .where(db.user_offers.c.user_id == uid, db.user_offers.c.offer_id == o["id"])
                                  .values(ai_score=o["ai_score"], ai_reason=o["ai_reason"], cv=o["cv"]))
        if error != (u["ai_error"] or ""):
            accounts.set_fields(uid, ai_error=error)
    if wait and first:
        return {**result, "waiting": len(pending)}   # le stock de départ n'est pas fini de noter
    handle = [o for o in pending if o["ai_score"] is not None] if wait else pending

    def wanted(o):
        if o["ai_score"] is not None:
            return o["ai_score"] >= crit["notify_ai"]
        return o["kw_score"] >= crit["notify_kw"]

    # ---- alertes ----
    good = sorted((o for o in handle if wanted(o)), key=_best, reverse=True)
    ch = accounts.channels(u)
    failed, alert_error, sent_ids = False, "", set()
    app_url = os.getenv("APP_URL", "").rstrip("/")
    if ch and (good or first):
        try:
            if first:
                # Tout le stock existant arrive d'un coup : un seul message de bienvenue, pas une rafale.
                top = f"\n\n{_lines(good[:8])}" if good else ""
                if await notify.send(ch, f"✅ <b>Veille activée</b>\n{len(handle)} offres déjà en ligne triées "
                                         f"pour toi, dont {len(good)} intéressantes.{top}\n\n"
                                         "À partir de maintenant, tu reçois chaque nouvelle offre dès sa détection.",
                                     app_url, "Ouvrir mon tableau de bord"):
                    result["alerts"] = 1
                    sent_ids = {o["id"] for o in good}
            elif len(good) > DIGEST_ABOVE:
                # Arrivée groupée (nouvelle source, reprise après coupure) : un seul message récapitulatif.
                more = f"\n… et {len(good) - 12} autres sur le site." if len(good) > 12 else ""
                if await notify.send(ch, f"🆕 <b>{len(good)} nouvelles offres intéressantes</b>\n\n"
                                         f"{_lines(good[:12])}{more}", app_url, "Ouvrir mon tableau de bord"):
                    result["alerts"] = 1
                    sent_ids = {o["id"] for o in good}
            else:
                labels = prof.labels(u)
                for o in good[:MAX_ALERTS_PER_RUN]:
                    if await notify.send(ch, notify.offer_message(o, labels), o["url"]):
                        result["alerts"] += 1
                        sent_ids.add(o["id"])
        except Exception as e:
            failed = True  # les alertes non parties restent en attente et seront renvoyées au prochain passage
            alert_error = (str(e) or type(e).__name__)[:300]
    if ch and alert_error != (u["alert_error"] or ""):
        accounts.set_fields(uid, alert_error=alert_error)

    good_ids = {o["id"] for o in good}
    with db.engine.begin() as c:
        for o in handle:
            if o["id"] in sent_ids:
                done = 1
            elif o["id"] in good_ids and failed and o["first_seen"] > now - 86400:
                done = 0   # à renvoyer (on n'insiste pas au-delà d'un jour)
            else:
                done = 2
            values = {"notified": done}
            # hors sujet d'après Gemini : rangée dans « Masquées » pour ne pas encombrer le flux
            if o["ai_score"] is not None and o["ai_score"] < HIDE_BELOW and o["state"] == "new":
                values["state"] = "hidden"
            c.execute(update(db.user_offers)
                      .where(db.user_offers.c.user_id == uid, db.user_offers.c.offer_id == o["id"]).values(**values))
    if first and not (failed and any(o["first_seen"] > now - 86400 for o in good)):
        accounts.set_fields(uid, bootstrapped=1)
    if wait:
        result["waiting"] = len(pending) - len(handle)
    return result


async def process_one(uid: int, budget: dict | None = None) -> dict:
    """Traite un utilisateur (jamais deux fois en même temps), en relisant son compte à jour."""
    async with _locks.setdefault(uid, asyncio.Lock()):
        u = accounts.by_id(uid)
        if not u or u["disabled"]:
            return {"skipped": True}
        try:
            return await process_user(u, budget if budget is not None else {"shared": 3})
        finally:
            accounts.set_fields(uid, last_eval=time.time())


async def resync_one(uid: int) -> dict:
    """Après un changement de CV ou de mots-clés : retrie tout le stock pour cet utilisateur, puis le traite."""
    async with _locks.setdefault(uid, asyncio.Lock()):
        u = accounts.by_id(uid)
        if u and not u["disabled"]:
            sync_user(u, full=True)
    return await process_one(uid)


async def evaluate_all() -> dict:
    """Passe sur tous les comptes actifs, ceux qui attendent depuis le plus longtemps en premier."""
    budget = {"shared": min(SHARED_BATCHES_PER_RUN, quota.shared_left())}
    total = {"users": 0, "scored": 0, "alerts": 0}
    start = time.time()
    for u in accounts.active(INACTIVE_DAYS):
        if time.time() - start > MAX_EVAL_SECONDS:
            break
        try:
            r = await process_one(u["id"], budget)
        except Exception as e:  # un compte en erreur ne doit jamais bloquer les autres
            print(f"utilisateur {u['id']} en erreur :", type(e).__name__, e)
            continue
        total["users"] += 1
        total["scored"] += r.get("scored", 0)
        total["alerts"] += r.get("alerts", 0)
    return total


async def run_once(force: bool = False) -> dict:
    lock = db.kv_get("lock", 0) or 0
    if time.time() - lock < LOCK_SECONDS:
        return {"skipped": "une collecte est déjà en cours"}
    db.kv_set("lock", time.time())
    try:
        new = await collect(force)
        result = await evaluate_all()
        result["new"] = new
        db.kv_set("last_run", {"at": time.time(), **result})
        if int(time.time()) % 50 == 0:
            db.prune()
        return result
    finally:
        db.kv_set("lock", 0)


if __name__ == "__main__":
    print(asyncio.run(run_once(force=True)))
