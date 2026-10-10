"""Vitrine publique : les meilleures offres récentes de chaque domaine, visibles sans compte, et les textes de
publications (X, LinkedIn, courte vidéo) fabriqués à partir de ces mêmes offres. Aucun appel à l'IA : gratuit.

Le calcul parcourt le stock commun ; il est fait au plus une fois toutes les 10 minutes et gardé en mémoire.
"""
import threading
import time

from sqlalchemy import func, select

import db
import domains as dom
import scoring

TTL = 600            # secondes pendant lesquelles le résultat est réutilisé
DAYS = 7             # la vitrine couvre les offres entrées dans le stock depuis une semaine
FRESH_HOURS = 48     # « nouveautés » mises en avant
MIN_SCORE = 40       # en dessous, l'offre est trop loin du domaine pour être montrée
KEPT = 60            # offres gardées en mémoire par domaine
SHOWN = 8            # offres montrées à un visiteur sans compte
MAX_ROWS = 2500      # garde-fou mémoire

# Formulation courte de chaque domaine, pour les titres et les publications.
SHORT = {"reseaux": "réseaux, cybersécurité et cloud", "embarque": "embarqué et électronique",
         "logiciel": "développement logiciel", "data": "data et IA",
         "industrie": "mécanique, industrie et énergie", "gestion": "commerce, marketing, finance et RH"}
TAGS = {"reseaux": "#cybersécurité #réseaux #cloud", "embarque": "#embarqué #électronique", "logiciel": "#développement #dev",
        "data": "#data #IA", "industrie": "#industrie #mécanique", "gestion": "#marketing #finance #RH"}

_cache = {"at": 0.0, "data": None}
_lock = threading.Lock()


def short(key: str) -> str:
    return SHORT.get(key) or dom.DOMAINS[key]["label"].lower()


def _scan(now: float) -> dict[str, list[dict]]:
    site = scoring.criteria()
    crits = {k: {**site, **scoring.lists_for([k], site), "profile_keywords": []} for k in dom.DOMAINS}
    o = db.offers
    stmt = (select(o.c.id, o.c.source, o.c.company, o.c.title, o.c.place, o.c.url, o.c.published, o.c.first_seen,
                   func.substr(o.c.description, 1, 1500).label("text"))
            .where(o.c.first_seen > now - DAYS * 86400).order_by(o.c.first_seen.desc()).limit(MAX_ROWS))
    with db.engine.connect() as c:
        rows = c.execute(stmt).all()
    out: dict[str, list[dict]] = {k: [] for k in dom.DOMAINS}
    for r in rows:
        if not (r.url or "").lower().startswith(("https://", "http://")):
            continue
        published = scoring.published_date(r.published, r.first_seen)
        if scoring.too_old(published, DAYS * 3, now):
            continue
        item = None
        for k, crit in crits.items():
            score = scoring.kw_score(r.title, r.text or "", crit)
            if score < MIN_SCORE:
                continue
            if item is None:
                item = {"id": r.id, "title": r.title, "company": r.company or "", "place": r.place or "", "url": r.url,
                        "source": r.source or "", "published": published, "first_seen": r.first_seen,
                        "regions": dom.regions_of(r.place or ""), "anywhere": dom.place_ok(r.place or "", ["__"])}
            text = scoring.norm(f"{r.title} {r.text or ''}")   # compétences citées : sert aux pages publiques (seo.py)
            out[k].append({**item, "score": score, "tech": [w for w in crit["tech"] if scoring._has(w, text)]})
    for k, items in out.items():
        # les nouveautés d'abord, puis les plus proches du domaine
        items.sort(key=lambda x: (x["first_seen"] > now - FRESH_HOURS * 3600, x["score"], x["first_seen"]), reverse=True)
    return out


def _data(now: float | None = None) -> dict[str, list[dict]]:
    now = now or time.time()
    with _lock:
        if _cache["data"] is None or now - _cache["at"] > TTL:
            _cache.update(at=now, data=_scan(now))
        return _cache["data"]


def reset() -> None:
    _cache.update(at=0.0, data=None)


def _filter(items: list[dict], region: str) -> list[dict]:
    if not region:
        return items
    return [x for x in items if region in x["regions"] or x["anywhere"]]


def _public(x: dict) -> dict:
    return {k: x[k] for k in ("id", "title", "company", "place", "url", "source", "published", "score")}


def view(domain: str = "", region: str = "", now: float | None = None) -> dict:
    """Ce que voit un visiteur sans compte : quelques offres par domaine, et le nombre total disponible."""
    now = now or time.time()
    data = _data(now)
    region = region if region in dom.REGIONS else ""
    counts = {k: len(_filter(v, region)) for k, v in data.items()}
    if domain not in dom.DOMAINS:
        domain = max(counts, key=counts.get) if any(counts.values()) else dom.DEFAULT_DOMAINS[0]
    items = _filter(data[domain], region)
    return {"domain": domain, "region": region, "label": dom.DOMAINS[domain]["label"], "short": short(domain),
            "total": len(items), "fresh": sum(x["first_seen"] > now - FRESH_HOURS * 3600 for x in items),
            "counts": counts, "updated": _cache["at"], "offers": [_public(x) for x in items[:SHOWN]]}


# ---------- publications prêtes à copier ----------
def _city(place: str) -> str:
    """« 92 - Châtillon » → « Châtillon » ; « Paris, Île-de-France, France » → « Paris »."""
    p = (place or "").split("/")[0].split(",")[0].strip()
    if " - " in p and p.split(" - ")[0].strip().isdigit():
        p = p.split(" - ", 1)[1].strip()
    return "" if dom._norm(p) in ("france", "remote", "teletravail", "full remote") else p[:30]


def _line(x: dict, width: int = 70) -> str:
    where = _city(x["place"])
    title = x["title"] if len(x["title"]) <= width else x["title"][:width - 1].rstrip() + "…"
    who = x["company"] if x["company"] and "non précisée" not in x["company"].lower() else ""
    tail = ", ".join(v for v in (who[:30], where) if v)
    return f"• {title}" + (f" ({tail})" if tail else "")


def _distinct(items: list[dict], n: int) -> list[dict]:
    """Au plus une offre par entreprise, pour qu'une publication ne ressemble pas à une publicité."""
    seen, out = set(), []
    for x in items:
        key = scoring.company_key(x["company"]) or x["id"]
        if key in seen:
            continue
        seen.add(key)
        out.append(x)
        if len(out) == n:
            break
    return out


def posts(base_url: str, region: str = "", now: float | None = None) -> list[dict]:
    """Une série de textes par domaine qui a assez d'offres. Les chiffres et les offres sont réels."""
    now = now or time.time()
    data = _data(now)
    region = region if region in dom.REGIONS else ""
    place = f" en {dom.REGIONS[region][0]}" if region else " en France"
    out = []
    for k in dom.DOMAINS:
        items = _filter(data[k], region)
        picks = _distinct(items, 5)
        if len(picks) < 3:
            continue
        n, name = len(items), short(k)
        link = f"{base_url.rstrip('/')}/#offres/{k}" if base_url else f"/#offres/{k}"
        head = f"{n} stages en {name} repérés cette semaine{place}."
        end = f"La liste à jour, gratuite : {link}"
        lines = [_line(x, 60) for x in picks[:3]]
        tweet = "\n".join([head, "", *lines, "", end])
        while len(tweet) > 280 and len(lines) > 1:   # un message sur X ne dépasse pas 280 caractères
            lines.pop()
            tweet = "\n".join([head, "", *lines, "", end])
        linkedin = "\n".join([
            f"{n} offres de stage en {name} repérées cette semaine{place}.", "",
            "Quelques-unes des plus récentes :", *[_line(x, 90) for x in picks], "",
            "Je les suis avec un outil que j'ai construit pendant mon M2 : il surveille les sites carrières en continu, "
            "note chaque offre d'après ton CV et t'envoie une alerte quand une offre te correspond.", "",
            f"La liste du jour est en accès libre : {link}", "",
            f"#stage #stagedefindetudes {TAGS.get(k, '')}".strip()])
        video = "\n".join([
            f"[Accroche, 3 s] Tu cherches un stage en {name} ? {n} offres repérées cette semaine.",
            "[Écran : la page des offres, on fait défiler]",
            *[f"[Offre {i + 1}] {x['title'][:80]}" + (f", chez {x['company'][:30]}" if x["company"] else "")
              + (f", à {_city(x['place'])}" if _city(x["place"]) else "") + "." for i, x in enumerate(picks[:3])],
            "[Fin, 4 s] Le site les récupère toutes seul et te prévient quand une offre correspond à ton CV. "
            "C'est gratuit, le lien est dans la bio."])
        out.append({"domain": k, "label": dom.DOMAINS[k]["label"], "count": n, "link": link,
                    "x": tweet, "linkedin": linkedin, "video": video})
    return out
