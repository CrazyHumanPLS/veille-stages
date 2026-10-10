"""Pages publiques lisibles par Google : /stages, /stages/<domaine>, /stages/<domaine>/<région>.

Le site lui-même est une application (React) : sans JavaScript, un moteur de recherche n'y lit presque rien.
Ces pages sont donc écrites en HTML par le serveur, à partir du même calcul que la vitrine (board.py) : aucune
requête de plus à la base, aucun appel à l'IA.

Trois règles, pour ne pas ressembler à un site qui fabrique des pages en série :
1. une page n'est proposée à Google que si elle contient au moins MIN_OFFERS offres réelles de la semaine ;
2. chaque page montre des chiffres qui lui sont propres (entreprises, villes, compétences demandées) ;
3. les pages sont ouvertes à Google petit à petit : les domaines d'abord, puis PER_WEEK pages de région par semaine.
"""
import datetime as dt
import html
import json
import os
import pathlib
import re
import time
from collections import Counter
from zoneinfo import ZoneInfo

import board
import db
import domains as dom
import scoring

MIN_OFFERS = 3                                      # en dessous, la page reste visible mais pas proposée à Google
SHOWN = 12                                          # offres affichées sur une page
PER_WEEK = int(os.getenv("SEO_PER_WEEK", "2"))      # pages de région ouvertes à Google chaque semaine
WEEK = 7 * 86400
PARIS = ZoneInfo("Europe/Paris")
DIST = pathlib.Path(__file__).parent.parent / "frontend" / "dist"

# Adresse et nom court de chaque domaine. Les adresses ne doivent plus changer une fois en ligne.
SLUGS = {"reseaux": "reseaux-cybersecurite-cloud", "embarque": "embarque-electronique",
         "logiciel": "developpement-logiciel", "data": "data-ia", "industrie": "mecanique-industrie-energie",
         "gestion": "commerce-marketing-finance-rh"}
TITLES = {"reseaux": "réseaux et cybersécurité", "embarque": "embarqué et électronique", "logiciel": "développeur",
          "data": "data et IA", "industrie": "mécanique et industrie", "gestion": "marketing, finance et RH"}
# Comment on écrit « dans telle région », et les villes que les étudiants tapent vraiment dans Google.
IN = {"idf": "en Île-de-France", "ara": "en Auvergne-Rhône-Alpes", "occ": "en Occitanie",
      "naq": "en Nouvelle-Aquitaine", "paca": "en Provence-Alpes-Côte d'Azur", "hdf": "dans les Hauts-de-France",
      "ges": "dans le Grand Est", "bre": "en Bretagne", "pdl": "dans les Pays de la Loire", "nor": "en Normandie",
      "bfc": "en Bourgogne-Franche-Comté", "cvl": "en Centre-Val de Loire", "cor": "en Corse"}
CITIES = {"idf": ["Paris", "La Défense"], "ara": ["Lyon", "Grenoble"], "occ": ["Toulouse", "Montpellier"],
          "naq": ["Bordeaux"], "paca": ["Marseille", "Nice", "Sophia Antipolis"], "hdf": ["Lille"],
          "ges": ["Strasbourg", "Nancy"], "bre": ["Rennes", "Brest"], "pdl": ["Nantes", "Angers"],
          "nor": ["Rouen", "Caen"], "bfc": ["Dijon", "Besançon"], "cvl": ["Orléans", "Tours"], "cor": ["Ajaccio"]}
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
          "novembre", "décembre"]


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", dom._norm(label)).strip("-")


REGION_SLUGS = {k: _slug(v[0]) for k, v in dom.REGIONS.items()}
_DOMAIN_OF = {v: k for k, v in SLUGS.items()}
_REGION_OF = {v: k for k, v in REGION_SLUGS.items()}


def path(domain: str = "", region: str = "") -> str:
    if not domain:
        return "/stages"
    return f"/stages/{SLUGS[domain]}" + (f"/{REGION_SLUGS[region]}" if region else "")


def _key(domain: str, region: str = "") -> str:
    return f"{domain}/{region}" if region else domain


def _items(data: dict, domain: str, region: str = "") -> list[dict]:
    """Offres d'une page. Pour une région, seulement celles qui s'y trouvent vraiment : une offre « France
    entière » répétée sur treize pages de région donnerait treize fois la même page."""
    items = data.get(domain, [])
    return [x for x in items if region in x["regions"]] if region else items


def counts(data: dict) -> dict[str, int]:
    out = {}
    for d in dom.DOMAINS:
        out[d] = len(_items(data, d))
        for r in dom.REGIONS:
            out[_key(d, r)] = len(_items(data, d, r))
    return out


# ---------- ouverture progressive à Google ----------
_checked = {"at": None}


def published(n: dict[str, int], now: float) -> list[str]:
    """Pages proposées à Google. Au départ : les domaines qui ont assez d'offres. Ensuite, PER_WEEK pages de
    région de plus chaque semaine, les plus fournies d'abord. Une page ouverte le reste (adresse stable)."""
    state = db.kv_get("seo_pages", None) or {}
    pages = [p for p in state.get("pages", []) if p in n]
    if _checked["at"] == board._cache["at"] and state:
        return pages
    _checked["at"] = board._cache["at"]
    changed = False
    for d in dom.DOMAINS:                           # un domaine entre dès qu'il a assez d'offres
        if d not in pages and n[d] >= MIN_OFFERS:
            pages.append(d)
            changed = True
    last = state.get("last", 0)
    if not state:
        last, changed = now, True
    elif now - last >= WEEK:
        waiting = sorted((k for k in n if "/" in k and k not in pages and n[k] >= MIN_OFFERS and k.split("/")[0] in pages),
                         key=lambda k: n[k], reverse=True)
        if waiting:
            pages += waiting[:max(0, PER_WEEK)]
            last, changed = now, True
    if changed:
        db.kv_set("seo_pages", {"pages": pages, "last": last})
    return pages


def reset() -> None:
    _checked["at"] = None


# ---------- petits outils d'écriture ----------
def e(s) -> str:
    return html.escape(str(s or ""), quote=True)


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n < 2 else (many or one + 's')}"


def _list(words: list[str]) -> str:
    """« A », « A et B », « A, B et C »."""
    words = [w for w in words if w]
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " et " + words[-1] if words else ""


def _when(published_day: str, now: float) -> str:
    try:
        day = dt.date.fromisoformat((published_day or "")[:10])
    except ValueError:
        return ""
    days = max(0, (dt.datetime.fromtimestamp(now, PARIS).date() - day).days)
    return "mise en ligne aujourd'hui" if days == 0 else "mise en ligne hier" if days == 1 else f"mise en ligne il y a {days} jours"


def _date(ts: float) -> str:
    d = dt.datetime.fromtimestamp(ts, PARIS)
    return f"{d.day}{'er' if d.day == 1 else ''} {MONTHS[d.month - 1]} {d.year} à {d.hour} h {d.minute:02d}"


def _company(x: dict) -> str:
    c = (x.get("company") or "").strip()
    return "" if not c or "non précisée" in c.lower() else c


def facts(items: list[dict]) -> dict:
    """Ce que cette page est seule à pouvoir dire : qui recrute, où, et quelles compétences reviennent."""
    firms = Counter(c for c in map(_company, items) if c)
    towns = Counter(c for c in (board._city(x["place"]) for x in items) if c)
    skills = Counter(t for x in items for t in x.get("tech", []))
    return {"firms": firms.most_common(8), "towns": towns.most_common(6),
            "skills": [(t, c) for t, c in skills.most_common(10) if c >= 2] if len(items) >= 5 else []}


def distinct(items: list[dict]) -> list[dict]:
    """Une même annonce publiée dans plusieurs villes (ou reprise par deux sources) n'est montrée qu'une fois ;
    « also » compte les autres lieux. L'ordre est conservé."""
    seen, out = {}, []
    for x in items:
        key = (scoring.company_key(x["company"]) or x["id"], scoring.title_key(x["title"]))
        if key in seen:
            seen[key]["also"] += 1
            continue
        seen[key] = {**x, "also": 0}
        out.append(seen[key])
    return out


_css = {"href": None, "at": 0.0}


def _stylesheet() -> str:
    """La feuille de style compilée du site (même apparence que l'application), si elle existe."""
    if time.time() - _css["at"] > 300:
        found = sorted((DIST / "assets").glob("*.css")) if (DIST / "assets").exists() else []
        _css.update(href=f"/assets/{found[0].name}" if found else "", at=time.time())
    return _css["href"]


# Quelques règles propres à ces pages. Sans feuille compilée (tests, poste de développement), elles suffisent
# à rendre la page lisible.
EXTRA_CSS = """
.crumbs{font-size:.9rem;color:var(--mute,#5c6385);margin:0 0 10px}
.crumbs a{color:inherit}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 6px;padding:0;list-style:none}
.chips a,.chips span{display:inline-block;padding:7px 13px;border-radius:999px;background:var(--p,#fff);border:1px solid var(--line,#dfe3f0);color:var(--ink,#141a3c);text-decoration:none;font-weight:600;font-size:.92rem}
.chips a:hover{border-color:var(--ink,#141a3c)}
.chips small{color:var(--mute,#5c6385);font-weight:400}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin:22px 0}
.facts .card{margin:0}
.facts h2{font-size:1.05rem;margin:0 0 8px}
.facts ol{margin:0;padding-left:20px}
.facts li span{color:var(--mute,#5c6385)}
.seo h2.sec{margin:34px 0 12px}
.seo .lead{max-width:68ch}
.seo .how p{max-width:70ch}
"""
BASE_CSS = """
body{margin:0;background:#f2f4fa;color:#141a3c;font:16px/1.55 system-ui,sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:22px 16px 40px}
.topbar{display:flex;justify-content:space-between;align-items:center;padding:14px 16px}
.btn{display:inline-block;background:#2f4cff;color:#fff;border-radius:10px;padding:9px 15px;font-weight:600;text-decoration:none}
.card,.sheet{background:#fff;border:1px solid #dfe3f0;border-radius:18px}.card{padding:18px}
.offer{display:flex;gap:18px;padding:18px;border-bottom:1px solid #dfe3f0}
.mute{color:#5c6385;font-size:.9rem}
"""


def _page(*, title: str, description: str, canonical: str, index: bool, body: str, ld: list[dict], name: str,
          verify: str = "") -> str:
    css = _stylesheet()
    head = [
        '<!DOCTYPE html>', '<html lang="fr"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">',
        f"<title>{e(title)}</title>", f'<meta name="description" content="{e(description)}">',
        f'<meta name="robots" content="{"index,follow" if index else "noindex,follow"}">',
        f'<link rel="canonical" href="{e(canonical)}">',
        '<meta name="theme-color" content="#f2f4fa">', '<link rel="icon" href="/icon.svg" type="image/svg+xml">',
        '<meta property="og:type" content="website">', f'<meta property="og:title" content="{e(title)}">',
        f'<meta property="og:description" content="{e(description)}">', f'<meta property="og:url" content="{e(canonical)}">',
        '<meta property="og:image" content="/icon-512.png">', f'<meta property="og:site_name" content="{e(name)}">',
    ]
    if verify:
        head.append(f'<meta name="google-site-verification" content="{e(verify)}">')
    head.append(f'<link rel="stylesheet" href="{e(css)}">' if css else f"<style>{BASE_CSS}</style>")
    head.append(f"<style>{EXTRA_CSS}</style>")
    for block in ld:   # données structurées : du JSON, jamais exécuté ; « < » est neutralisé par précaution
        head.append('<script type="application/ld+json">' + json.dumps(block, ensure_ascii=False).replace("<", "\\u003c") + "</script>")
    head.append("</head>")
    top = (f'<div class="topbar"><a class="brand" href="/"><span class="mark" aria-hidden="true"></span>{e(name)}</a>'
           '<a class="btn" href="/">Créer mon compte gratuit</a></div>')
    foot = ('<footer class="mute"><a href="/stages">Tous les stages par domaine et par région</a>'
            f'<a href="/">{e(name)}, la veille de stages notée d\'après ton CV</a></footer>')
    return "\n".join(head) + f'\n<body><div class="landing board seo">{top}<main class="wrap">{body}{foot}</main></div></body></html>\n'


def _offer(x: dict, now: float) -> str:
    tone = "hi" if x["score"] >= 75 else "mid" if x["score"] >= 55 else "lo"
    url = e(x["url"])
    when = _when(x["published"], now)
    also = f" et {_plural(x['also'], 'autre lieu', 'autres lieux')}" if x.get("also") else ""
    return (
        f'<article class="offer"><div class="score {tone}" title="Proximité avec le domaine, d\'après les mots-clés de '
        f'l\'annonce"><span>{x["score"]}</span><small>mots-clés</small></div><div class="body">'
        f'<h3 class="otitle"><a href="{url}" target="_blank" rel="noopener noreferrer nofollow">{e(x["title"])}</a></h3>'
        f'<p class="ometa"><b>{e(_company(x) or "Entreprise non précisée")}</b><span>{e(x["place"] or "lieu non précisé")}{also}</span>'
        f'<span>via {e(x["source"])}</span></p>' + (f'<p class="odate">{when}</p>' if when else "")
        + f'<div class="actions"><a class="btn ghost" href="{url}" target="_blank" rel="noopener noreferrer nofollow">'
          "Voir l'offre</a></div></div></article>")


def _chips(links: list[tuple[str, str, int]]) -> str:
    return '<ul class="chips">' + "".join(
        f'<li><a href="{e(href)}">{e(text)} <small>({n})</small></a></li>' for href, text, n in links) + "</ul>"


def _facts_html(f: dict) -> str:
    cards = []
    if f["firms"]:
        cards.append('<div class="card"><h2>Les entreprises qui recrutent</h2><ol>' + "".join(
            f"<li>{e(c)} <span>({_plural(n, 'offre')})</span></li>" for c, n in f["firms"]) + "</ol></div>")
    if f["towns"]:
        cards.append('<div class="card"><h2>Où sont les stages</h2><ol>' + "".join(
            f"<li>{e(c)} <span>({_plural(n, 'offre')})</span></li>" for c, n in f["towns"]) + "</ol></div>")
    if f["skills"]:
        cards.append('<div class="card"><h2>Les compétences les plus demandées</h2><ol>' + "".join(
            f"<li>{e(t)} <span>(dans {_plural(n, 'annonce')})</span></li>" for t, n in f["skills"]) + "</ol></div>")
    return f'<section class="facts">{"".join(cards)}</section>' if cards else ""


def _cta(more: int) -> str:
    head = (f"{_plural(more, 'autre offre', 'autres offres')} cette semaine sur cette page" if more > 0
            else "Ne rate pas les prochaines")
    return (f'<div class="card boardcta"><h2>{head}</h2><p>Avec un compte, chaque offre est notée de 0 à 100 d\'après '
            "ton CV, et les meilleures arrivent sur ton téléphone dès leur mise en ligne. Lettre de motivation et "
            'préparation d\'entretien incluses.</p><a class="btn big" href="/">Créer mon compte gratuit</a>'
            '<p class="mute">Gratuit, sans publicité.</p></div>')


HOW = ('<section class="how"><h2 class="sec">D\'où viennent ces offres</h2>'
       "<p>Le site relève en continu les pages carrières d'entreprises et plusieurs sites d'emploi, partout en "
       "France. Il ne garde que les stages (pas l'alternance ni les CDI), écarte les annonces de plus de 20 jours, "
       "et classe chaque offre d'après les mots-clés de son texte. Le chiffre affiché à gauche d'une offre mesure "
       "sa proximité avec le domaine de la page, de 0 à 100.</p>"
       "<p>Cette page est recalculée toute la journée : une offre retirée ou trop ancienne en disparaît, et les "
       "nouveautés des dernières 48 heures passent en tête.</p></section>")


def _crumbs(trail: list[tuple[str, str]], base: str) -> tuple[str, dict]:
    parts = [f'<a href="{e(href)}">{e(text)}</a>' if i < len(trail) - 1 else e(text) for i, (href, text) in enumerate(trail)]
    ld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": text, "item": base + href} for i, (href, text) in enumerate(trail)]}
    return f'<p class="crumbs">{" › ".join(parts)}</p>', ld


def render(domain: str, region: str, base: str, name: str, now: float | None = None, verify: str = "") -> str:
    """Une page : toute la France (region vide) ou une région, pour un domaine ; ou le sommaire (domain vide)."""
    now = now or time.time()
    data = board._data(now)
    n = counts(data)
    live = published(n, now)
    updated = _date(board._cache["at"] or now)
    if not domain:
        return _hub(n, live, base, name, updated, verify)
    items = _items(data, domain, region)
    total, fresh = len(items), sum(x["first_seen"] > now - board.FRESH_HOURS * 3600 for x in items)
    f = facts(items)
    long_name, short_name = board.short(domain), TITLES[domain]
    where = IN[region] if region else "en France"
    towns = CITIES.get(region, [])
    key = _key(domain, region)

    title = (f"Stage {short_name} {_list(towns[:2])} ({dom.REGIONS[region][0]}) | {name}" if region
             else f"Stage {short_name} : les offres de la semaine | {name}")
    h1 = f"Stage {long_name} {where}"
    if total:
        firms = [c for c, _ in f["firms"][:3]]
        lead = (f"{_plural(total, 'offre')} de stage en {long_name} {'repérée' if total < 2 else 'repérées'} {where} "
                f"ces 7 derniers jours" + (f", dont {fresh} depuis 48 heures" if fresh else "") + "."
                + (f" {_list(firms)} {'recrute' if len(firms) < 2 else 'recrutent'} en ce moment." if firms else ""))
        description = (f"{_plural(total, 'offre')} de stage en {long_name} {where} cette semaine"
                       + (f" ({_list(towns)})" if towns else "") + ". Liste gratuite, mise à jour en continu, "
                       "avec les entreprises qui recrutent et les compétences demandées.")
    else:
        lead = f"Aucune offre de stage en {long_name} repérée {where} ces 7 derniers jours."
        description = f"Les offres de stage en {long_name} {where}, relevées en continu sur les sites carrières."

    trail = [("/", name), ("/stages", "Stages"), (path(domain), f"Stage {short_name}")]
    if region:
        trail.append((path(domain, region), dom.REGIONS[region][0]))
    crumbs, ld_crumbs = _crumbs(trail, base)

    body = [crumbs, f"<h1>{e(h1)}</h1>", f'<p class="lead">{e(lead)}</p>',
            f'<p class="mute">Mis à jour le {updated}.</p>']
    if items:
        shown = distinct(items)[:SHOWN]
        body.append('<div class="sheet">' + "".join(_offer(x, now) for x in shown) + "</div>")
        body.append(_cta(total - sum(1 + x["also"] for x in shown)))
        body.append(_facts_html(f))
    else:
        body.append('<div class="empty"><b>Rien cette semaine dans cette sélection.</b>'
                    '<p class="mute">Regarde toute la France ou un domaine voisin, juste en dessous.</p></div>')

    # Maillage : la même recherche ailleurs, puis les autres domaines au même endroit. Uniquement des pages fournies.
    others = [(path(domain, r), f"Stage {short_name} {_list(CITIES[r][:1])} ({v[0]})", n[_key(domain, r)])
              for r, v in dom.REGIONS.items() if r != region and n[_key(domain, r)] >= MIN_OFFERS]
    if region:
        others.insert(0, (path(domain), f"Stage {short_name} dans toute la France", n[domain]))
    if others:
        body.append(f'<h2 class="sec">Stage {e(short_name)} : les autres régions</h2>' + _chips(others))
    same = [(path(d, region), f"Stage {TITLES[d]} {where}", n[_key(d, region)])
            for d in dom.DOMAINS if d != domain and n[_key(d, region)] >= (MIN_OFFERS if region else 1)]
    if same:
        body.append(f'<h2 class="sec">Les autres domaines {e(where)}</h2>' + _chips(same))
    body.append(HOW)

    ld_page = {"@context": "https://schema.org", "@type": "CollectionPage", "name": h1, "description": description,
               "url": base + path(domain, region), "inLanguage": "fr",
               "dateModified": dt.datetime.fromtimestamp(board._cache["at"] or now, PARIS).isoformat(timespec="seconds"),
               "isPartOf": {"@type": "WebSite", "name": name, "url": base + "/"}}
    return _page(title=title, description=description, canonical=base + path(domain, region),
                 index=key in live and total >= MIN_OFFERS, body="".join(body), ld=[ld_crumbs, ld_page], name=name,
                 verify=verify)


def _hub(n: dict, live: list[str], base: str, name: str, updated: str, verify: str) -> str:
    total = sum(n[d] for d in dom.DOMAINS)
    crumbs, ld_crumbs = _crumbs([("/", name), ("/stages", "Stages")], base)
    body = [crumbs, "<h1>Offres de stage en France, par domaine et par région</h1>",
            '<p class="lead">Les pages carrières des entreprises et plusieurs sites d\'emploi sont relevés en continu. '
            "Choisis ton domaine, puis ta région : chaque page liste les stages mis en ligne cette semaine, "
            "les entreprises qui recrutent et les compétences demandées.</p>",
            f'<p class="mute">Mis à jour le {updated}.</p>']
    for d in dom.DOMAINS:
        regions = [(path(d, r), f"{_list(CITIES[r][:1])} ({v[0]})", n[_key(d, r)])
                   for r, v in dom.REGIONS.items() if n[_key(d, r)] >= MIN_OFFERS]
        body.append(f'<h2 class="sec"><a href="{path(d)}">Stage {e(board.short(d))}</a></h2>'
                    f'<p class="mute">{_plural(n[d], "offre")} cette semaine dans toute la France.</p>'
                    + (_chips(regions) if regions else ""))
    body.append(_cta(0) + HOW)
    description = ("Les offres de stage de la semaine en France, classées par domaine (data, cybersécurité, "
                   "développement, embarqué, industrie, marketing, finance) et par région. Gratuit, mis à jour en continu.")
    return _page(title=f"Offres de stage par domaine et par région | {name}", description=description,
                 canonical=base + "/stages", index=total >= MIN_OFFERS, body="".join(body), ld=[ld_crumbs], name=name,
                 verify=verify)


def resolve(domain_slug: str, region_slug: str = "") -> tuple[str, str] | None:
    """Adresse → (domaine, région). None si l'adresse n'existe pas."""
    d = _DOMAIN_OF.get(domain_slug)
    if not d:
        return None
    if not region_slug:
        return d, ""
    r = _REGION_OF.get(region_slug)
    return (d, r) if r else None


def sitemap(base: str, now: float | None = None) -> str:
    """Plan du site pour Google : l'accueil, le sommaire, et les seules pages ouvertes qui ont assez d'offres."""
    now = now or time.time()
    data = board._data(now)
    n = counts(data)
    live = published(n, now)
    day = dt.datetime.fromtimestamp(board._cache["at"] or now, PARIS).date().isoformat()
    urls = [(base + "/", ""), (base + "/stages", day)]
    for key in live:
        if n.get(key, 0) < MIN_OFFERS:
            continue
        d, _, r = key.partition("/")
        urls.append((base + path(d, r), day))
    rows = "".join(f"<url><loc>{e(u)}</loc>{f'<lastmod>{m}</lastmod>' if m else ''}</url>" for u, m in urls)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{rows}</urlset>\n'


def robots(base: str) -> str:
    return f"User-agent: *\nAllow: /\nDisallow: /api/\n\nSitemap: {base}/sitemap.xml\n"
