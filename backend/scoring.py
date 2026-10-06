"""Filtres (stage ? Île-de-France ?), score par mots-clés et empreinte anti-doublon."""
import datetime as dt
import difflib
import hashlib
import html
import re
import unicodedata
from email.utils import parsedate_to_datetime

import db

# ---------- réglages communs du site (modifiables depuis l'onglet Administration) ----------
# Ils décident de ce qui entre dans le stock commun d'offres, et servent de mots-clés par défaut à chacun.
DEFAULT_CRITERIA = {
    # Requêtes France Travail : mots séparés par des virgules = tous obligatoires
    "ft_queries": ["stage,réseau", "stage,réseaux", "stage,télécom", "stage,cybersécurité",
                   "stage,sécurité,informatique", "stage,cloud", "stage,devops",
                   "stage,infrastructure", "stage,systèmes"],
    # Requêtes Adzuna : tous les mots d'une ligne sont obligatoires
    "adzuna_queries": ["stage réseaux", "stage télécom", "stage cybersécurité", "stage sécurité informatique",
                       "stage cloud", "stage devops", "stage infrastructure", "stage systèmes linux"],
    # Mots très importants : fort bonus s'ils sont dans le titre
    "strong": ["réseau", "réseaux", "network", "networking", "télécom", "télécoms", "telecom",
               "télécommunications", "cybersécurité", "cybersecurity", "cyber", "sécurité",
               "security", "ssi", "soc", "pentest", "cloud", "devops",
               "devsecops", "netdevops", "sre", "reliability", "platform", "plateforme", "infrastructure", "infrastructures", "infra",
               "système", "systèmes", "sysadmin", "5g", "4g", "lte", "réseaux mobiles", "ingénieur radio", "ran", "voip", "toip",
               "sd-wan", "datacenter", "virtualisation", "kubernetes", "finops", "grc", "red team",
               "blue team", "analyste soc", "active directory", "iam"],
    # Technologies : petit bonus à chaque présence
    "tech": ["cisco", "juniper", "fortinet", "palo alto", "arista", "nokia", "ericsson", "bgp", "ospf",
             "mpls", "vpn", "vlan", "firewall", "pare-feu", "tcp/ip", "ipv6", "sdn", "nfv", "wifi",
             "routage", "commutation", "linux", "ansible", "terraform", "kubernetes",
             "docker", "openstack", "vmware", "aws", "azure", "gcp", "python", "bash", "wireshark",
             "siem", "splunk", "active directory", "ci/cd", "gitlab", "supervision", "zabbix",
             "prometheus", "grafana", "pki", "edr", "iso 27001", "ebios", "nis 2", "dora", "splunk",
             "elk", "elastic", "qradar", "sentinel", "wazuh", "crowdstrike", "sigma", "yara", "mitre",
             "bloodhound", "burp", "nmap", "metasploit", "sonarqube", "semgrep", "snyk", "trivy",
             "helm", "argocd", "gitops", "github actions", "eks", "aks", "lambda", "serverless",
             "opentofu", "opentelemetry", "sip", "asterisk", "pfsense", "ipsec", "openvpn", "ims",
             "volte", "umts", "gsm", "check point", "f5", "aruba", "dns", "gpo", "kibana"],
    # Titre contenant un de ces mots = pénalité
    "negative": ["commercial", "commerciale", "vente", "marketing", "ressources humaines", "rh",
                 "comptable", "comptabilité", "juridique", "communication", "achats", "logistique",
                 "immobilier", "assurance", "recrutement", "business developer", "hse", "qse",
                 "incendie", "agent de sécurité", "sécurité au travail", "sécurité alimentaire"],
    "rss_feeds": [],          # ex. flux RSS d'une alerte Google
    "min_kw": 10,             # en dessous : l'offre n'entre pas dans le stock commun
}

# ---------- réglages propres à chaque utilisateur (onglet Réglages) ----------
USER_DEFAULTS = {
    "goal": "Stage de fin d'études (bac+5, environ 6 mois) en Île-de-France",
    "profile_keywords": [],   # mots tirés automatiquement de son CV (remplis par l'analyse Gemini)
    "min_kw": 25,             # en dessous : l'offre ne lui est pas proposée
    "notify_ai": 60,          # alerte si le score Gemini atteint ce seuil
    "notify_kw": 45,          # seuil utilisé quand l'IA n'est pas disponible
    "alerts_on": True,
}
USER_LISTS = ("strong", "tech", "negative")   # par défaut ceux du site ; chacun peut avoir les siens


def criteria() -> dict:
    c = dict(DEFAULT_CRITERIA)
    saved = db.kv_get("criteria", {}) or {}
    c.update({k: v for k, v in saved.items() if k in DEFAULT_CRITERIA})
    c["profile_keywords"] = []
    return c


def user_criteria(u: dict, site: dict | None = None) -> dict:
    """Réglages effectifs d'un utilisateur : les siens, complétés par ceux du site."""
    site = site or criteria()
    s = u.get("settings") or {}
    c = {k: s.get(k, v) for k, v in USER_DEFAULTS.items()}
    for k in USER_LISTS:
        c[k] = s[k] if isinstance(s.get(k), list) else site[k]
    c["custom_lists"] = [k for k in USER_LISTS if isinstance(s.get(k), list)]
    return c


# ---------- outils texte ----------
def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip()


def strip_html(s: str) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"<(br|/p|/li|/h\d|/div)[^>]*>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", s)).strip()


def _has(term: str, text: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(norm(term)) + r"(?![a-z0-9])", text) is not None


def fingerprint(source: str, ext_id: str, company: str, title: str, place: str) -> str:
    """Même offre vue sur deux sites = même empreinte (entreprise + titre + ville)."""
    comp = norm(company)
    if not comp or "non precise" in comp or comp in ("confidentiel", "anonyme"):
        base = f"{source}|{ext_id}"
    else:
        city = re.sub(r"[^a-z ]", " ", norm(place)).split()
        base = f"{comp}|{re.sub(r'[^a-z0-9]+', ' ', norm(title)).strip()}|{city[0] if city else ''}"
    return hashlib.sha1(base.encode()).hexdigest()


# ---------- est-ce un stage ? ----------
_STAGE_TITLE = re.compile(r"(?<![a-z])(stage|stagiaire|intern|internship|interns|pfe|fin d'etudes|fin d etudes)(?![a-z])")
_STAGE_BODY = re.compile(r"(stage de fin d'etudes|stage de \d+ ?(a \d+ ?)?mois|convention de stage|"
                         r"stage \(?\d+ mois|stage ingenieur|stagiaire|gratification|end[- ]of[- ]studies internship|"
                         r"\d[- ]month internship)")
_ALTERNANCE = re.compile(r"(?<![a-z])(alternance|alternant|alternante|apprenti|apprentie|apprentissage|"
                         r"contrat pro|professionnalisation|cdi|cdd|freelance)(?![a-z])")


def is_internship(title: str, description: str) -> bool:
    t, d = norm(title), norm(description)[:3000]
    if _STAGE_TITLE.search(t):
        return True
    if _ALTERNANCE.search(t):
        return False
    return bool(_STAGE_BODY.search(d))


# ---------- est-ce en Île-de-France ? ----------
_IDF_WORDS = ["ile-de-france", "ile de france", "idf", "paris", "la defense", "courbevoie", "nanterre",
              "puteaux", "issy", "boulogne", "massy", "palaiseau", "saclay", "velizy", "guyancourt",
              "saint-denis", "cergy", "montrouge", "levallois", "rueil", "gennevilliers", "elancourt",
              "chatillon", "meudon", "saint-ouen", "montreuil", "vincennes", "noisy", "creteil", "evry",
              "les ulis", "roissy", "arcueil", "bagneux", "malakoff", "clichy", "neuilly", "colombes",
              "antony", "orsay", "gif-sur-yvette", "versailles", "saint-quentin-en-yvelines", "pontoise",
              "argenteuil", "bezons", "suresnes", "sevres", "saint-cloud", "ivry", "villejuif", "rungis",
              "nozay", "limours", "trappes", "poissy", "les mureaux", "magny", "bois-colombes", "asnieres",
              "aubervilliers", "pantin", "bobigny", "villepinte", "marne-la-vallee", "champs-sur-marne",
              "fontenay", "charenton", "saint-mande", "kremlin", "cachan", "chatenay", "plessis",
              "hauts-de-seine", "yvelines", "essonne", "val-d'oise", "val d'oise", "val-de-marne",
              "seine-saint-denis", "seine-et-marne", "sartrouville", "osny", "eragny", "taverny",
              "franconville", "sarcelles", "gonesse", "garges", "ermont", "herblay", "cormeilles"]
_IDF_CP = re.compile(r"(?<!\d)(75|77|78|91|92|93|94|95)(\d{3})?(?!\d)")


def is_idf(place: str, unknown_ok: bool = True) -> bool:
    p = norm(place)
    if not p:
        return unknown_ok
    if any(w in p for w in _IDF_WORDS):
        return True
    return bool(_IDF_CP.search(p))


# ---------- score par mots-clés (0 à 100) ----------
def kw_score(title: str, description: str, crit: dict | None = None) -> int:
    crit = crit or criteria()
    t, d = norm(title), norm(description)
    score = 0
    for w in crit["strong"]:
        if _has(w, t):
            score += 30
        elif _has(w, d):
            score += 8
    for w in crit["tech"]:
        if _has(w, t):
            score += 10
        elif _has(w, d):
            score += 4
    for w in crit.get("profile_keywords", []):
        if _has(w, t) or _has(w, d):
            score += 5
    if re.search(r"bac ?\+ ?5|master 2|(?<![a-z])m2(?![a-z])|fin d'etudes|ecole d'ingenieur|ingenieur", t + " " + d):
        score += 10
    if any(_has(w, t) for w in crit["negative"]):
        score -= 40
    return max(0, min(100, score))


# ---------- date de mise en ligne ----------
def published_date(raw: str, ref_ts: float | None = None) -> str:
    """Ramène les formats des différentes sources à AAAA-MM-JJ. Renvoie '' si la source ne donne pas de date."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        return m.group(0)
    ref = dt.datetime.fromtimestamp(ref_ts, dt.timezone.utc) if ref_ts else dt.datetime.now(dt.timezone.utc)
    low = raw.lower()
    if "today" in low or "aujourd" in low:          # Workday : « Posted Today »
        return ref.strftime("%Y-%m-%d")
    if "yesterday" in low or "hier" in low:
        return (ref - dt.timedelta(days=1)).strftime("%Y-%m-%d")
    m = re.search(r"(\d+)\+?\s*(day|jour)", low)   # « Posted 3 Days Ago », « Posted 30+ Days Ago »
    if m:
        return (ref - dt.timedelta(days=int(m.group(1)))).strftime("%Y-%m-%d")
    try:                                             # flux RSS : « Mon, 05 Oct 2026 12:58:22 Z »
        return parsedate_to_datetime(re.sub(r"\s+Z$", " +0000", raw)).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return ""


# ---------- même offre publiée ailleurs, ou déjà dans mes candidatures ? ----------
def company_key(company: str) -> str:
    n = re.sub(r"\b(sas|sa|se|group|groupe|france|technologies|technology)\b", " ", norm(company))
    return re.sub(r"[^a-z0-9]", "", n)


def title_key(title: str) -> str:
    n = norm(title)
    n = re.sub(r"\(?\b[hfmx]\s*/\s*[hfmx](\s*/\s*[hfmx])?\b\)?", " ", n)          # H/F, F/H, x/f/m
    n = re.sub(r"\b(stage|stagiaire|internship|intern|pfe|alternance|de fin d'etudes|fin d'etudes|"
               r"\d+ mois|\d{4,}[-\d]*)\b", " ", n)
    return " ".join(re.findall(r"[a-z0-9+#]+", n))


def same_job(title_a: str, title_b: str) -> bool:
    a, b = title_key(title_a), title_key(title_b)
    if not a or not b:
        return False
    return a == b or set(a.split()) == set(b.split()) or difflib.SequenceMatcher(None, a, b).ratio() >= 0.9
