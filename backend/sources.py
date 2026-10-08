"""Sources d'offres. Chaque fonction renvoie une liste d'offres brutes :
{source, ext_id, company, title, place, url, description, published, geo_ok}
geo_ok=True quand la source a déjà filtré sur l'Île-de-France.
Uniquement des API officielles ou des flux publics prévus pour être lus par des programmes.
"""
import asyncio
import json
import os
import pathlib
import re
import time
from urllib.parse import parse_qs, urlparse
import xml.etree.ElementTree as ET

import httpx

import domains as dom
from scoring import is_internship, strip_html

UA = {"User-Agent": "veille-stages/1.0 (veille d'offres de stage)"}
HERE = pathlib.Path(__file__).parent
ADZUNA_PAUSE = float(os.getenv("ADZUNA_PAUSE_SEC", "2.5"))


def companies() -> dict:
    try:
        return json.loads((HERE / "companies.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _offer(source, ext_id, company, title, place, url, description="", published="", geo_ok=False):
    return {"source": source, "ext_id": str(ext_id), "company": (company or "").strip()[:200],
            "title": (title or "").strip()[:300], "place": (place or "").strip()[:200], "url": url or "",
            "description": strip_html(description)[:6000], "published": (published or "")[:40], "geo_ok": geo_ok}


# ---------- France Travail (API officielle, gratuite) ----------
_tok = {"v": None, "exp": 0}


def ft_enabled() -> bool:
    return bool(os.getenv("FT_CLIENT_ID") and os.getenv("FT_CLIENT_SECRET"))


async def ft_token(h: httpx.AsyncClient) -> str:
    if _tok["v"] and time.time() < _tok["exp"]:
        return _tok["v"]
    r = await h.post(
        "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire",
        data={"grant_type": "client_credentials", "client_id": os.getenv("FT_CLIENT_ID"),
              "client_secret": os.getenv("FT_CLIENT_SECRET"), "scope": "api_offresdemploiv2 o2dsoffre"})
    if r.status_code != 200:
        raise RuntimeError(f"authentification France Travail refusée ({r.status_code}) : {r.text[:150]}")
    j = r.json()
    _tok.update(v=j["access_token"], exp=time.time() + j.get("expires_in", 1200) - 60)
    return _tok["v"]


def _ft_map(o: dict) -> dict:
    origine = o.get("origineOffre") or {}
    url = origine.get("urlOrigine") or f"https://candidat.francetravail.fr/offres/recherche/detail/{o.get('id')}"
    return _offer("France Travail", o.get("id"), (o.get("entreprise") or {}).get("nom") or "Entreprise non précisée",
                  o.get("intitule"), (o.get("lieuTravail") or {}).get("libelle", ""), url,
                  o.get("description", ""), o.get("dateCreation", ""), geo_ok=True)


async def ft_search(h: httpx.AsyncClient, mots: str, region: str = "", departement: str = "",
                    days: int | None = 3, limit: int = 50) -> list[dict]:
    params = {"motsCles": mots, "range": f"0-{limit - 1}", "sort": "1"}
    if days:
        params["publieeDepuis"] = str(days)
    if departement:
        params["departement"] = departement
    elif region:
        params["region"] = region
    r = await h.get("https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search",
                    params=params, headers={"Authorization": f"Bearer {await ft_token(h)}"})
    if r.status_code == 204:
        return []
    if r.status_code not in (200, 206):
        raise RuntimeError(f"France Travail {r.status_code} : {r.text[:150]}")
    return [_ft_map(o) for o in r.json().get("resultats", [])]


async def france_travail(h: httpx.AsyncClient, crit: dict) -> list[dict]:
    out, errors = [], []
    for q in crit["ft_queries"]:
        try:
            out += await ft_search(h, q)
        except Exception as e:  # une requête en échec ne bloque pas les autres
            errors.append(str(e))
    if errors and not out:
        raise RuntimeError(errors[0])
    return out


# ---------- Adzuna (API officielle, gratuite, quota limité) ----------
def adzuna_enabled() -> bool:
    return bool(os.getenv("ADZUNA_APP_ID") and os.getenv("ADZUNA_APP_KEY"))


async def adzuna(h: httpx.AsyncClient, queries: list[str]) -> list[dict]:
    # Une requête par couple de mots, tous obligatoires (ex. "stage cybersécurité"), sur toute la France.
    results, errors = [], []
    for i, q in enumerate(queries):
        if i:
            await asyncio.sleep(ADZUNA_PAUSE)   # Adzuna limite le nombre de demandes par minute
        r = await h.get("https://api.adzuna.com/v1/api/jobs/fr/search/1", params={
            "app_id": os.getenv("ADZUNA_APP_ID"), "app_key": os.getenv("ADZUNA_APP_KEY"),
            "what_and": q, "what_exclude": "alternance apprentissage",
            "sort_by": "date", "max_days_old": 10, "results_per_page": 50, "content-type": "application/json"})
        if r.status_code != 200:
            errors.append(f"Adzuna {r.status_code} : {r.text[:150]}")
            continue
        results += r.json().get("results", [])
    if errors and not results:
        raise RuntimeError(errors[0])
    return [_offer("Adzuna", o.get("id"), (o.get("company") or {}).get("display_name") or "Entreprise non précisée",
                   o.get("title"), (o.get("location") or {}).get("display_name", ""), o.get("redirect_url"),
                   o.get("description", ""), o.get("created", ""), geo_ok=True)
            for o in results]


# ---------- Pages carrières (API publiques des outils de recrutement) ----------
_gh_done: set[tuple[str, str]] = set()   # annonces dont le détail a déjà été lu depuis le démarrage
GH_DETAILS_PER_RUN = 25


async def greenhouse(h: httpx.AsyncClient, c: dict) -> list[dict]:
    """Deux temps, pour la mémoire (512 Mo sur Render gratuit) : la liste SANS le texte des annonces (légère),
    puis le texte des seuls stages en France pas encore lus. Avant, on téléchargeait le texte de toutes les
    annonces de l'entreprise (plusieurs Mo par page carrières) : c'est ce qui saturait la mémoire."""
    base = f"https://boards-api.greenhouse.io/v1/boards/{c['token']}/jobs"
    r = await h.get(base)
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        place = (j.get("location") or {}).get("name", "")
        ref = (c["token"], str(j.get("id")))
        if ref in _gh_done or not is_internship(j.get("title") or "", "") or not dom.in_france(place):
            continue
        if len(out) >= GH_DETAILS_PER_RUN:
            break   # la suite au prochain passage
        d = await h.get(f"{base}/{j.get('id')}")
        if d.status_code != 200:
            continue
        full = d.json()
        _gh_done.add(ref)
        if len(_gh_done) > 50000:
            _gh_done.clear()
        out.append(_offer(c["name"], j.get("id"), c["name"], j.get("title"), place, j.get("absolute_url"),
                          full.get("content", ""), j.get("first_published") or j.get("updated_at", "")))
    return out


async def lever(h: httpx.AsyncClient, c: dict) -> list[dict]:
    r = await h.get(f"https://api.lever.co/v0/postings/{c['token']}", params={"mode": "json"})
    r.raise_for_status()
    out = []
    for j in r.json():
        cat = j.get("categories") or {}
        place = ", ".join(cat.get("allLocations") or [cat.get("location") or ""])
        when = time.strftime("%Y-%m-%d", time.gmtime(j["createdAt"] / 1000)) if j.get("createdAt") else ""
        title = j.get("text", "")
        if "intern" in (cat.get("commitment") or "").lower() or "stage" in (cat.get("commitment") or "").lower():
            title += " (stage)"
        out.append(_offer(c["name"], j.get("id"), c["name"], title, place, j.get("hostedUrl"),
                          j.get("descriptionPlain", ""), when))
    return out


async def ashby(h: httpx.AsyncClient, c: dict) -> list[dict]:
    r = await h.get(f"https://api.ashbyhq.com/posting-api/job-board/{c['token']}")
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        title = j.get("title", "")
        if (j.get("employmentType") or "").lower() == "intern":
            title += " (stage)"
        out.append(_offer(c["name"], j.get("id"), c["name"], title, j.get("location", ""), j.get("jobUrl"),
                          j.get("descriptionPlain", ""), j.get("publishedAt", "")))
    return out


async def smartrecruiters(h: httpx.AsyncClient, c: dict) -> list[dict]:
    out = []
    for q in ("stage", "intern"):
        for page in range(3):  # 100 résultats par page
            r = await h.get(f"https://api.smartrecruiters.com/v1/companies/{c['token']}/postings",
                            params={"country": "fr", "q": q, "limit": 100, "offset": page * 100})
            r.raise_for_status()
            posts = r.json().get("content", [])
            for j in posts:
                loc = j.get("location") or {}
                place = ", ".join(x for x in (loc.get("city"), loc.get("region")) if x)
                out.append(_offer(c["name"], j.get("id"), (j.get("company") or {}).get("name") or c["name"],
                                  j.get("name"), place,
                                  f"https://jobs.smartrecruiters.com/{c['token']}/{j.get('id')}", "",
                                  j.get("releasedDate", "")))
            if len(posts) < 100:
                break
    return out


async def workday(h: httpx.AsyncClient, c: dict) -> list[dict]:
    """Même point d'accès que le site carrières public de l'entreprise (non documenté)."""
    base = f"https://{c['host']}"
    out = []
    for q in ("stage", "internship"):
        for page in range(5):  # 20 résultats par page
            r = await h.post(f"{base}/wday/cxs/{c['tenant']}/{c['site']}/jobs",
                             json={"appliedFacets": {}, "limit": 20, "offset": page * 20, "searchText": q},
                             headers={"Accept": "application/json"})
            r.raise_for_status()
            posts = r.json().get("jobPostings", [])
            for j in posts:
                path = j.get("externalPath", "")
                out.append(_offer(c["name"], path.rsplit("/", 1)[-1] or j.get("title"), c["name"], j.get("title"),
                                  j.get("locationsText", ""), f"{base}/{c['site']}{path}", "", j.get("postedOn", "")))
            if len(posts) < 20:
                break
    return out


_wk_done: set[tuple[str, str]] = set()   # annonces Workable déjà lues depuis le démarrage


async def workable(h: httpx.AsyncClient, c: dict) -> list[dict]:
    """Page carrières apply.workable.com/XXX (point d'accès public du module à intégrer de Workable).
    Même principe que Greenhouse, pour la mémoire : la liste SANS les textes d'abord ; les textes ne sont
    demandés que s'il y a un stage en France pas encore lu."""
    base = f"https://apply.workable.com/api/v1/widget/accounts/{c['token']}"
    r = await h.get(base)
    r.raise_for_status()

    def wanted(j) -> bool:
        place = ", ".join(x for x in (j.get("city"), j.get("country")) if x)
        intern = "intern" in (j.get("employment_type") or "").lower()
        return (intern or is_internship(j.get("title") or "", "")) and dom.in_france(place)

    todo = {j.get("shortcode") for j in r.json().get("jobs", [])
            if j.get("shortcode") and wanted(j) and (c["token"], j["shortcode"]) not in _wk_done}
    if not todo:
        return []
    r = await h.get(base, params={"details": "true"})
    r.raise_for_status()
    if len(r.content) > 5_000_000:
        raise RuntimeError("réponse trop volumineuse (plus de 5 Mo), ignorée")

    def parse():
        out = []
        for j in r.json().get("jobs", []):
            code = j.get("shortcode")
            if code not in todo:
                continue
            place = ", ".join(dict.fromkeys(x for x in (j.get("city"), j.get("state"), j.get("country")) if x))
            title = j.get("title", "")
            if "intern" in (j.get("employment_type") or "").lower():
                title += " (stage)"
            url = j.get("url") or j.get("shortlink") or f"https://apply.workable.com/j/{code}"
            out.append(_offer(c["name"], code, c["name"], title, place, url, j.get("description", ""),
                              j.get("published_on") or j.get("created_at", "")))
        return out
    out = await asyncio.to_thread(parse)
    _wk_done.update((c["token"], o["ext_id"]) for o in out)
    if len(_wk_done) > 50000:
        _wk_done.clear()
    return out


def _tt_place(item) -> str:
    """Lieux d'une offre Teamtailor : <tt:locations><tt:location><tt:city/><tt:country/>… (plusieurs possibles)."""
    places = []
    for loc in item.iter():
        if loc.tag.split("}")[-1] != "location":
            continue
        city, country = _txt(loc, "city") or _txt(loc, "name"), _txt(loc, "country")
        label = ", ".join(x for x in (city, country) if x)
        if label and label not in places:
            places.append(label)
    return " / ".join(places[:4])


async def teamtailor(h: httpx.AsyncClient, c: dict) -> list[dict]:
    """Flux RSS public d'un site carrières Teamtailor (XXX.teamtailor.com/jobs.rss). « url » remplace l'adresse
    quand l'entreprise utilise son propre nom de domaine. Flux léger (quelques dizaines d'annonces), plafonné à 5 Mo."""
    r = await h.get(c.get("url") or f"https://{c['token']}.teamtailor.com/jobs.rss")
    r.raise_for_status()
    if len(r.content) > 5_000_000:
        raise RuntimeError("flux trop volumineux (plus de 5 Mo), ignoré")

    def parse():
        out = []
        for it in (n for n in ET.fromstring(r.content).iter() if n.tag.split("}")[-1] == "item"):
            link = _txt(it, "link")
            place = _tt_place(it)
            if not place and _txt(it, "remoteStatus") == "fully":
                place = "Remote"
            out.append(_offer(c["name"], _txt(it, "guid") or link, c["name"], strip_html(_txt(it, "title")), place,
                              link, _txt(it, "description"), _txt(it, "pubDate")))
        return out
    return await asyncio.to_thread(parse)


ATS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby,
       "smartrecruiters": smartrecruiters, "workday": workday,
       "workable": workable, "teamtailor": teamtailor}


# ---------- Flux RSS / Atom (ex. alerte Google transformée en flux) ----------
def _txt(node, *names):
    for n in names:
        for child in node:
            if child.tag.split("}")[-1] == n:
                if n == "link" and child.get("href"):
                    return child.get("href")
                if child.text:
                    return child.text.strip()
    return ""


def _real_link(link: str) -> str:
    """Les alertes Google enveloppent le vrai lien : https://www.google.com/url?...&url=LE_VRAI_LIEN&..."""
    if "google." in link and "/url?" in link:
        target = parse_qs(urlparse(link).query).get("url") or parse_qs(urlparse(link).query).get("q")
        if target:
            return target[0]
    return link


async def rss(h: httpx.AsyncClient, url: str, company: str = "", label: str = "") -> list[dict]:
    """company = entreprise du flux (site carrières) ; vide pour un flux multi-entreprises (alerte Google)."""
    r = await h.get(url)
    r.raise_for_status()
    if len(r.content) > 5_000_000:
        raise RuntimeError("flux trop volumineux (plus de 5 Mo), ignoré")
    root = ET.fromstring(r.content)
    items = [n for n in root.iter() if n.tag.split("}")[-1] in ("item", "entry")]
    out = []
    for it in items[:100]:
        link = _real_link(_txt(it, "link"))
        title = strip_html(_txt(it, "title"))
        title = re.sub(r"\s*[|\-–]\s*(LinkedIn|Indeed(\.com)?|Welcome to the Jungle|HelloWork|Glassdoor)\s*$", "", title)
        out.append(_offer(label or company or "RSS", _txt(it, "guid", "id") or link, company, title, "", link,
                          _txt(it, "description", "summary", "content"), _txt(it, "pubDate", "published", "updated")))
    return out
