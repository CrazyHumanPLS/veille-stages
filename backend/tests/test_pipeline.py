"""Test de bout en bout avec de fausses réponses réseau :  cd backend && python -m pytest -q"""
import asyncio
import json
import re
import os
import sys
import tempfile

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.update(DATABASE_URL="sqlite:///" + tempfile.mkdtemp() + "/t.db", COLLECT_EVERY_SEC="0",
                  FT_CLIENT_ID="x", FT_CLIENT_SECRET="x", GEMINI_API_KEY="cle-commune", TELEGRAM_TOKEN="bot",
                  SECRET_KEY="secret-de-test", CRON_KEY="k", ADZUNA_APP_ID="", ADZUNA_APP_KEY="",
                  AI_BACKOFF_SEC="0", ADZUNA_PAUSE_SEC="0", ADMIN_EMAIL="chef@ex.fr", SIGNUP_MODE="open", APP_URL="https://site.test")

import accounts, collector, db, quota, scoring, security  # noqa: E402

# Dates des fausses annonces : calculées d'après le jour du test, sinon elles finiraient par dépasser
# l'ancienneté maximale (20 jours) et les tests échoueraient sans raison.
import datetime as _dt  # noqa: E402
from email.utils import format_datetime as _rfc  # noqa: E402
_NOW = _dt.datetime.now(_dt.timezone.utc)
RECENT = (_NOW - _dt.timedelta(days=2)).strftime("%Y-%m-%d")
RECENT_RSS, OLD_RSS = _rfc(_NOW - _dt.timedelta(days=2)), _rfc(_NOW - _dt.timedelta(days=36))

FT = [{"id": "A1", "intitule": "Stage ingénieur réseaux et sécurité H/F", "entreprise": {"nom": "Orange"},
       "lieuTravail": {"libelle": "92 - Châtillon"}, "dateCreation": RECENT + "T10:00:00Z",
       "description": "Stage de fin d'études bac+5. BGP, OSPF, Cisco, firewall Fortinet.",
       "origineOffre": {"urlOrigine": "https://ex.fr/a1"}},
      {"id": "A2", "intitule": "Commercial sédentaire réseau d'agences", "entreprise": {"nom": "Immo"},
       "lieuTravail": {"libelle": "75 - Paris"}, "description": "CDI. Un stage d'intégration est prévu.",
       "origineOffre": {"urlOrigine": "https://ex.fr/a2"}},
      {"id": "A3", "intitule": "Alternance administrateur systèmes et réseaux", "entreprise": {"nom": "Alt"},
       "lieuTravail": {"libelle": "75 - Paris"}, "description": "Contrat d'apprentissage.",
       "origineOffre": {"urlOrigine": "https://ex.fr/a3"}}]
GH = {"jobs": [
    {"id": 1, "title": "Site Reliability Engineer Intern", "location": {"name": "Paris, France"},
     "absolute_url": "https://dd/1", "content": "&lt;p&gt;Kubernetes, AWS, Linux, Terraform&lt;/p&gt;"},
    {"id": 2, "title": "Network Engineering Intern", "location": {"name": "New York, USA"},
     "absolute_url": "https://dd/2", "content": "BGP"},
    {"id": 3, "title": "Senior Network Engineer", "location": {"name": "Paris, France"},
     "absolute_url": "https://dd/3", "content": "BGP"}]}
HOOK_A = "https://discord.com/api/webhooks/111/aaa"
HOOK_B = "https://discord.com/api/webhooks/222/bbb"
discord: dict[str, list[str]] = {}   # adresse du webhook -> messages reçus
ntfy, telegram, gemini_keys, extra_ft = [], [], [], []
tg_updates = []
gemini_fail = {"on": False}
mails, mail_fail = [], {"on": False}
adzuna_calls = []
ADZUNA = {"stage embarqué": [
    {"id": "E1", "title": "Stage ingénieur logiciel embarqué C / STM32 (H/F)", "company": {"display_name": "Aero Systèmes"},
     "location": {"display_name": "Toulouse, Haute-Garonne"}, "redirect_url": "https://adz/e1", "created": RECENT + "T08:00:00Z",
     "description": "Stage de fin d'études. Développement C embarqué sur microcontrôleur STM32, RTOS, tests et validation."},
    {"id": "E2", "title": "Stage FPGA VHDL - électronique numérique", "company": {"display_name": "Onde Défense"},
     "location": {"display_name": "Élancourt, Yvelines"}, "redirect_url": "https://adz/e2", "created": RECENT + "T08:00:00Z",
     "description": "Stage ingénieur. Conception FPGA en VHDL, Vivado, bancs de test, CEM."}]}


WORKABLE = {"name": "Withings", "description": "", "jobs": [
    {"title": "Stage - Android Engineer (H/F)", "shortcode": "AB12CD34EF", "employment_type": "Full-time",
     "country": "France", "city": "Issy-les-Moulineaux", "state": "Île-de-France", "published_on": RECENT,
     "url": "https://apply.workable.com/j/AB12CD34EF", "shortlink": "https://apply.workable.com/j/AB12CD34EF",
     "description": "<p>Stage de fin d'études. Développement Android en Kotlin, API REST, tests unitaires, Git.</p>"},
    {"title": "Embedded Software Engineer", "shortcode": "ZZ00000001", "employment_type": "Internship",
     "country": "France", "city": "Paris", "state": "Île-de-France", "published_on": RECENT,
     "shortlink": "https://apply.workable.com/j/ZZ00000001",
     "description": "<p>Firmware C embarqué sur microcontrôleur STM32, RTOS, Bluetooth Low Energy.</p>"},
    {"title": "Internship - Software Engineering", "shortcode": "US00000001", "employment_type": "Full-time",
     "country": "United States", "city": "Boston", "state": "Massachusetts", "published_on": RECENT,
     "url": "https://apply.workable.com/j/US00000001", "description": "Python, Kubernetes"},
    {"title": "Senior Android Engineer (H/F)", "shortcode": "SR00000001", "employment_type": "Full-time",
     "country": "France", "city": "Paris", "published_on": RECENT,
     "url": "https://apply.workable.com/j/SR00000001", "description": "Kotlin. CDI."}]}
TEAMTAILOR = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:tt="https://teamtailor.com/locations"><channel><title>Skello</title>
<item><title>Data Analyst Intern - stage</title>
 <description>&lt;p&gt;Stage de 6 mois. SQL, Python, dbt, tableaux de bord Looker.&lt;/p&gt;</description>
 <pubDate>{RECENT_RSS}</pubDate><link>https://skello.teamtailor.com/jobs/1-data-analyst-intern</link>
 <remoteStatus>hybrid</remoteStatus><guid>guid-1</guid>
 <tt:locations><tt:location><tt:name>Siège</tt:name><tt:city>Paris</tt:city><tt:country>France</tt:country></tt:location>
 <tt:location><tt:name>Lille</tt:name><tt:city>Lille</tt:city><tt:country>France</tt:country></tt:location></tt:locations>
 <tt:department>Data</tt:department></item>
<item><title>Software Engineer Intern</title><description>Python, SQL</description>
 <pubDate>{RECENT_RSS}</pubDate><link>https://skello.teamtailor.com/jobs/2-software-engineer-intern</link>
 <guid>guid-2</guid>
 <tt:locations><tt:location><tt:name>London</tt:name><tt:city>London</tt:city><tt:country>United Kingdom</tt:country></tt:location></tt:locations></item>
<item><title>Stage - Développeur Python (H/F)</title><description>Stage. Python, Django, PostgreSQL.</description>
 <pubDate>{OLD_RSS}</pubDate><link>https://skello.teamtailor.com/jobs/3-stage-dev</link><guid>guid-3</guid>
 <tt:locations><tt:location><tt:city>Paris</tt:city><tt:country>France</tt:country></tt:location></tt:locations></item>
</channel></rss>"""
wk_calls = []
ats_extra = {"on": False}   # les sources Workable et Teamtailor ne répondent que dans leur propre test


def handler(req: httpx.Request) -> httpx.Response:
    u = str(req.url)
    if "access_token" in u:
        return httpx.Response(200, json={"access_token": "t", "expires_in": 1000})
    if "francetravail.io" in u:
        return httpx.Response(200, json={"resultats": FT + extra_ft})
    if "greenhouse" in u and "/datadog/" in u:
        one = re.search(r"/jobs/(\d+)", u)      # détail d'une annonce : seul endroit où le texte est fourni
        if one:
            return httpx.Response(200, json=next(j for j in GH["jobs"] if j["id"] == int(one.group(1))))
        return httpx.Response(200, json={"jobs": [{k: v for k, v in j.items() if k != "content"} for j in GH["jobs"]]})
    if ats_extra["on"] and "apply.workable.com/api/v1/widget/accounts/withings" in u:
        wk_calls.append(req.url.params.get("details"))
        return httpx.Response(200, json=WORKABLE)
    if ats_extra["on"] and u.startswith("https://skello.teamtailor.com/jobs.rss"):
        return httpx.Response(200, content=TEAMTAILOR.encode(), headers={"content-type": "application/rss+xml"})
    if "generativelanguage" in u:
        key = req.headers["x-goog-api-key"]
        if key.startswith("cle-invalide"):
            return httpx.Response(400, json={"error": {"message": "API key not valid. Please pass a valid API key."}})
        if gemini_fail["on"]:
            return httpx.Response(503, text="surcharge")
        gemini_keys.append(key)
        prompt = json.loads(req.content)["contents"][0]["parts"][0]["text"]
        ids = [l.split("=")[1] for l in prompt.splitlines() if l.startswith("### id=")]
        if not ids:
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(
                {"resume": "Profil test", "mots_cles": ["bgp", "cisco"],
                 **({"domaines": ["embarque", "inconnu"], "objectif": "Je cherche un stage en logiciel embarqué (C, STM32, FPGA)."}
                    if "VHDL" in prompt else {})}) if "JSON" in prompt else "Texte généré"}]}}]})
        cv = "cv2" if "[CV cv2" in prompt else "cv1"
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(
            [{"id": i, "score": 85, "cv": cv, "raison": "Très proche du profil"} for i in ids])}]}}]})
    if "api.adzuna.com" in u:
        q = req.url.params.get("what_and")
        adzuna_calls.append({"q": q, "where": req.url.params.get("where")})
        return httpx.Response(200, json={"results": ADZUNA.get(q, [])})
    if "api.brevo.com" in u:
        if mail_fail["on"]:
            return httpx.Response(401, json={"message": "Key not found"})
        mails.append({**json.loads(req.content), "_key": req.headers.get("api-key")})
        return httpx.Response(201, json={"messageId": "<1@relay>"})
    if "discord.com" in u:
        if u.endswith("/casse"):
            return httpx.Response(404, text="Unknown Webhook")
        discord.setdefault(u, []).append(json.loads(req.content)["content"])
        return httpx.Response(204)
    if "ntfy" in u:
        ntfy.append(json.loads(req.content))
        return httpx.Response(200, json={})
    if "telegram" in u and "getUpdates" in u:
        return httpx.Response(200, json={"result": tg_updates})
    if "telegram" in u:
        telegram.append(json.loads(req.content))
        return httpx.Response(200, json={"ok": True})
    return httpx.Response(404, text="inconnu")


@pytest.fixture(autouse=True)
def fake_network(monkeypatch):
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


def run(coro):
    return asyncio.run(coro)


def rows(uid):
    o, uo = db.offers, db.user_offers
    with db.engine.connect() as c:
        return {r.title: r for r in c.execute(
            db.select(o.c.title, o.c.place, uo.c.ai_score, uo.c.kw_score, uo.c.cv, uo.c.state, uo.c.notified, uo.c.dup_note)
            .join(uo, uo.c.offer_id == o.c.id).where(uo.c.user_id == uid))}


def test_filters():
    crit = scoring.criteria()
    assert scoring.is_internship("Stage ingénieur réseaux", "")
    assert scoring.is_internship("Ingénieur réseau", "Nous proposons un stage de fin d'études de 6 mois")
    assert not scoring.is_internship("Alternance admin réseaux", "stage de fin d'études possible")
    assert not scoring.is_internship("Commercial", "Un stage d'intégration est prévu")
    assert scoring.is_idf("92 - Châtillon") and scoring.is_idf("Massy, France") and scoring.is_idf("Paris 15e")
    assert not scoring.is_idf("Lyon, France") and not scoring.is_idf("Toulouse (31)")
    assert scoring.kw_score("Stage réseaux et sécurité", "BGP OSPF Cisco", crit) >= 45
    assert scoring.kw_score("Stage commercial réseau d'agences", "", crit) < 25
    for raw, want in [("2026-10-05T10:00:00Z", "2026-10-05"), ("Mon, 05 Oct 2026 12:58:22 Z", "2026-10-05"),
                      ("Posted Today", "2026-10-06"), ("Posted Yesterday", "2026-10-05"),
                      ("Posted 3 Days Ago", "2026-10-03"), ("Posted 30+ Days Ago", "2026-09-06"), ("", ""), ("bientôt", "")]:
        assert scoring.published_date(raw, 1791280800) == want, (raw, scoring.published_date(raw, 1791280800))
    assert scoring.same_job("STAGE - Ingénieur Réseaux - F/H", "Stage Ingénieur réseaux (H/F) - 6 mois")
    assert scoring.same_job("Cloud Engineer GCP - Stage de fin d'études H/F", "Stage de fin d'études - Cloud Engineer GCP")
    assert not scoring.same_job("Stage ingénieur réseaux", "Stage ingénieur cybersécurité")
    assert scoring.company_key("THALES Group") == scoring.company_key("Thales") == "thales"
    assert scoring.fingerprint("a", "1", "Orange", "Stage Réseaux H/F", "92 - Châtillon") == \
        scoring.fingerprint("b", "9", "ORANGE", "stage réseaux h/f", "Châtillon (92)")


def test_security():
    h = security.hash_password("motdepasse")
    assert security.check_password("motdepasse", h) and not security.check_password("autre", h) and "motdepasse" not in h
    tok = security.make_token(7, 2)
    assert security.read_token(tok) == (7, 2)
    assert security.read_token(tok[:-1] + ("0" if tok[-1] != "0" else "1")) is None      # signature falsifiée
    assert security.read_token("8" + tok[1:]) is None                                    # identifiant falsifié
    blob = security.encrypt("cle-perso")
    assert "cle-perso" not in blob and security.decrypt(blob) == "cle-perso" and security.decrypt("abîmé") == ""


def test_pipeline():
    a = accounts.create("alice@ex.fr", "Alice", "motdepasse1")
    b = accounts.create("bob@ex.fr", "Bob", "motdepasse2")
    assert accounts.create("ALICE@ex.fr ", "x", "motdepasse3") is None                    # adresse déjà prise
    a["profile"] = {"cvs": {"cv1": {"text": "M2 réseaux. Cisco, BGP, Linux.", "label": "Réseaux"},
                            "cv2": {"text": "M2. SOC, SIEM Splunk.", "label": "Cybersécurité"}}}
    accounts.save_profile(a)
    a["secrets"] = {"discord": HOOK_A}
    accounts.save_secrets(a)
    b["secrets"] = {"discord": HOOK_B}
    accounts.save_secrets(b)
    with db.engine.connect() as c:   # les secrets ne sont jamais en clair dans la base
        assert "discord.com" not in c.execute(db.select(db.users.c.secrets).where(db.users.c.id == a["id"])).scalar()

    first = run(collector.run_once(force=True))
    with db.engine.connect() as c:
        titles = sorted(r.title for r in c.execute(db.offers.select()))
    # stock commun : le stage Orange et le stage SRE à Paris. Écartées : CDI, alternance, New York, poste senior.
    assert titles == ["Site Reliability Engineer Intern", "Stage ingénieur réseaux et sécurité H/F"], titles
    assert first["new"] == 2 and first["scored"] == 2 and first["users"] == 2
    # Alice (CV + Discord) : notes de l'IA et un seul récapitulatif de bienvenue
    assert len(discord[HOOK_A]) == 1 and "Veille activée" in discord[HOOK_A][0] and "85/100" in discord[HOOK_A][0]
    assert all(r.ai_score == 85 and r.cv == "cv2" for r in rows(a["id"]).values())
    # Bob (pas encore de CV) : il voit les offres avec leur score par mots-clés, sans note d'IA ni alerte
    assert HOOK_B not in discord and len(rows(b["id"])) == 2 and all(r.ai_score is None for r in rows(b["id"]).values())
    assert gemini_keys == ["cle-commune"]

    again = run(collector.run_once(force=True))
    assert again["new"] == 0 and len(discord[HOOK_A]) == 1                               # aucun doublon, aucune alerte

    # Bob importe son CV et met SA clé Gemini : son stock est noté avec sa clé, sans toucher au quota commun
    b = accounts.by_id(b["id"])
    b["profile"] = {"cvs": {"cv1": {"text": "M2 cloud. AWS, Terraform, Kubernetes."}}}
    accounts.save_profile(b)
    b["secrets"]["gemini"] = "cle-de-bob"
    accounts.save_secrets(b)
    shared_before = db.usage_get(0, quota.today()).get("req", 0)
    assert run(collector.process_one(b["id"]))["scored"] == 2
    assert gemini_keys[-1] == "cle-de-bob" and db.usage_get(0, quota.today()).get("req", 0) == shared_before
    assert len(discord[HOOK_B]) == 1 and "Veille activée" in discord[HOOK_B][0]
    assert all(r.cv == "cv1" for r in rows(b["id"]).values())

    # nouvelle offre : chacun reçoit SON alerte, avec le nom de SON CV
    extra_ft.append({"id": "B7", "intitule": "Stagiaire analyste SOC cybersécurité", "entreprise": {"nom": "Thales"},
                     "lieuTravail": {"libelle": "78 - Élancourt"}, "description": "SIEM Splunk, EDR. Bac+5.",
                     "origineOffre": {"urlOrigine": "https://ex.fr/b7"}})
    third = run(collector.run_once(force=True))
    assert third["new"] == 1 and third["alerts"] == 2
    assert "Stagiaire analyste SOC" in discord[HOOK_A][1] and "CV à envoyer : **Cybersécurité**" in discord[HOOK_A][1]
    assert "Stagiaire analyste SOC" in discord[HOOK_B][1] and "CV à envoyer : **CV principal**" in discord[HOOK_B][1]

    # le tri de l'un ne change rien pour l'autre
    oid = db.known_refs([scoring.fingerprint("France Travail", "B7", "Thales", "Stagiaire analyste SOC cybersécurité", "78 - Élancourt")])
    with db.engine.begin() as c:
        c.execute(db.user_offers.update().where(db.user_offers.c.user_id == a["id"],
                                                db.user_offers.c.offer_id == list(oid)[0]).values(state="hidden"))
    assert rows(a["id"])["Stagiaire analyste SOC cybersécurité"].state == "hidden"
    assert rows(b["id"])["Stagiaire analyste SOC cybersécurité"].state == "new"

    # dédoublonnage du stock commun, et avertissement « déjà postulé » propre à Alice
    with db.engine.begin() as c:
        c.execute(db.applications.insert().values(user_id=a["id"], company="Airbus", job="Stage ingénieur cybersécurité SOC", status=1, updated=0))
        c.execute(db.offers.update().where(db.offers.c.title.like("Stagiaire analyste SOC%")).values(source="Thales"))
    ft = lambda i, title, comp, place: {"id": i, "intitule": title, "entreprise": {"nom": comp},
                                        "lieuTravail": {"libelle": place}, "description": "SIEM, SOC, EDR. Bac+5.",
                                        "origineOffre": {"urlOrigine": f"https://ex.fr/{i}"}}
    extra_ft.append(ft("C1", "Stage - Analyste SOC Cybersécurité (H/F)", "THALES", "78 - Élancourt"))   # republiée ailleurs : ignorée
    extra_ft.append(ft("C2", "Stage - Analyste SOC Cybersécurité (H/F)", "THALES", "92 - Gennevilliers"))  # autre ville : gardée
    extra_ft.append(ft("C3", "Stage Ingénieur Cybersécurité SOC H/F", "Airbus", "78 - Élancourt"))      # proche d'une candidature d'Alice
    assert run(collector.run_once(force=True))["new"] == 2
    ra, rb = rows(a["id"]), rows(b["id"])
    assert ra["Stage - Analyste SOC Cybersécurité (H/F)"].place == "92 - Gennevilliers"
    assert "déjà postulé" in ra["Stage Ingénieur Cybersécurité SOC H/F"].dup_note
    assert rb["Stage Ingénieur Cybersécurité SOC H/F"].dup_note == ""
    two = [{"source": "Thales", "ext_id": x, "company": "Thales", "title": "Stage - Ingénieur Réseaux - F/H",
            "place": "Vélizy-Villacoublay", "url": f"https://t/{x}", "description": "", "published": "", "geo_ok": False}
           for x in ("R1", "R2")]
    collector.load_seen()
    assert collector.store("Thales", two, scoring.criteria(), distinct=True) == 2
    assert collector.store("Thales", two, scoring.criteria(), distinct=True) == 0
    assert collector.store("Adzuna", [dict(two[0], source="Adzuna", ext_id="Z9")], scoring.criteria()) == 0
    assert db.kv_get("src:Datadog")["ok"] and not db.kv_get("src:Qonto")["ok"]  # source en panne signalée, pas bloquante
    run(collector.run_once())   # distribue les deux offres Thales à chacun

    # limite du jour de la formule gratuite : au-delà, Alice garde le score par mots-clés ; Bob, en Premium, continue
    db.kv_set("limits", {"score": db.usage_get(a["id"], quota.today())["score"] + 1, "p_score": 999})
    accounts.set_fields(b["id"], plan_until=__import__("time").time() + 86400)
    for i in range(3):
        extra_ft.append(ft(f"Q{i}", f"Stage ingénieur réseaux équipe {i}", f"Societe{i}", "75 - Paris"))
    run(collector.run_once(force=True))
    ra, rb = rows(a["id"]), rows(b["id"])
    scored_a = [ra[f"Stage ingénieur réseaux équipe {i}"].ai_score for i in range(3)]
    assert sorted(x is None for x in scored_a) == [False, True, True], scored_a
    assert all(ra[f"Stage ingénieur réseaux équipe {i}"].notified for i in range(3))     # triées quand même
    assert all(rb[f"Stage ingénieur réseaux équipe {i}"].ai_score == 85 for i in range(3))
    db.kv_set("limits", {})
    accounts.set_fields(b["id"], plan_until=0)

    # panne passagère de Gemini : on attend le passage suivant au lieu de se rabattre tout de suite sur les mots-clés
    gemini_fail["on"] = True
    extra_ft.append(ft("P1", "Stage ingénieur réseaux datacenter", "Equinix", "93 - Saint-Denis"))
    run(collector.run_once(force=True))
    assert rows(a["id"])["Stage ingénieur réseaux datacenter"].notified == 0 and accounts.by_id(a["id"])["ai_error"]
    gemini_fail["on"] = False
    run(collector.run_once(force=True))
    assert rows(a["id"])["Stage ingénieur réseaux datacenter"].ai_score == 85 and not accounts.by_id(a["id"])["ai_error"]

    # webhook supprimé : l'erreur est notée sur le compte, les autres utilisateurs ne sont pas touchés
    b = accounts.by_id(b["id"])
    pass
    a = accounts.by_id(a["id"])
    a["secrets"]["discord"] = "https://discord.com/api/webhooks/999/casse"
    accounts.save_secrets(a)
    extra_ft.append(ft("P2", "Stage ingénieur sécurité réseaux", "Stormshield", "92 - Issy"))
    before_b = len(discord[HOOK_B])
    run(collector.run_once(force=True))
    assert "Discord" in accounts.by_id(a["id"])["alert_error"] and len(discord[HOOK_B]) == before_b + 1
    assert rows(a["id"])["Stage ingénieur sécurité réseaux"].notified == 0               # sera renvoyée

    # changement de mots-clés : le stock est retrié pour cette personne seulement
    b = accounts.by_id(b["id"])
    b["settings"]["strong"] = ["kubernetes"]
    b["settings"]["tech"] = []
    b["settings"]["min_kw"] = 5
    accounts.save_settings(b)
    n_before = len(rows(a["id"]))
    run(collector.resync_one(b["id"]))
    assert rows(b["id"])["Site Reliability Engineer Intern"].kw_score >= 5 and len(rows(a["id"])) == n_before

    # compte inactif depuis longtemps : sa veille se met en pause
    accounts.set_fields(b["id"], last_seen=1.0)
    assert [u["id"] for u in accounts.active(collector.INACTIVE_DAYS)] == [a["id"]]
    accounts.set_fields(b["id"], last_seen=9e12)

    # suppression d'un compte : toutes ses données partent, pas celles des autres
    accounts.remove(b["id"])
    assert not rows(b["id"]) and rows(a["id"]) and accounts.by_id(b["id"]) is None


def test_api():
    from fastapi.testclient import TestClient
    import main
    main._hits.clear()
    with TestClient(main.app) as c:
        assert c.get("/api/offers").status_code == 401 and c.get("/api/admin/overview").status_code == 401
        pub = c.get("/api/public").json()
        assert pub["signup"] == "open" and pub["limits"]["assist"] == 5
        bad = lambda **kw: c.post("/api/signup", json={"email": "z@ex.fr", "password": "motdepasse", "consent": True, **kw})
        assert bad(email="pas-une-adresse").status_code == 400 and bad(password="court").status_code == 400
        assert bad(consent=False).status_code == 400
        assert bad(email="alice@ex.fr").status_code == 409                               # déjà inscrite (test précédent)

        chef = c.post("/api/signup", json={"email": "Chef@ex.fr", "password": "motdepasse", "name": "Chef", "consent": True}).json()
        zoe = c.post("/api/signup", json={"email": "zoe@ex.fr", "password": "motdepasse", "consent": True}).json()
        assert chef["me"]["is_admin"] and not zoe["me"]["is_admin"]
        hc, hz = ({"Authorization": f"Bearer {x['token']}"} for x in (chef, zoe))
        assert c.post("/api/login", json={"email": "zoe@ex.fr", "password": "faux-mot"}).status_code == 401
        assert c.post("/api/login", json={"email": "inconnu@ex.fr", "password": "motdepasse"}).status_code == 401
        assert c.post("/api/login", json={"email": "ZOE@ex.fr", "password": "motdepasse"}).json()["me"]["email"] == "zoe@ex.fr"
        assert c.get("/api/admin/overview", headers=hz).status_code == 403               # Zoé n'est pas administratrice
        assert c.put("/api/admin/settings", json={"limits": {"assist": 999}}, headers=hz).status_code == 403

        # profil : import du CV, analyse, mots-clés tirés du CV
        up = c.post("/api/profile/cv?slot=cv1", files={"file": ("cv.txt", ("Réseaux Cisco BGP OSPF Linux " * 20).encode())}, headers=hz).json()
        assert set(up["cvs"]) == {"cv1"} and up["error"] == "" and up["analysis"]["resume"] == "Profil test"
        assert c.get("/api/criteria", headers=hz).json()["profile_keywords"] == ["bgp", "cisco"]
        assert c.put("/api/profile/label", json={"slot": "cv1", "label": "Réseaux"}, headers=hz).json()["slots"]["cv1"] == "Réseaux"
        assert c.get("/api/profile", headers=hc).json()["cvs"] == {}                     # le CV de Zoé n'est pas visible par un autre
        assert c.post("/api/profile/cv?slot=cv9", files={"file": ("cv.txt", b"x" * 300)}, headers=hz).status_code == 400

        # flux : uniquement le sien
        offers = c.get("/api/offers?state=all", headers=hz).json()
        assert len(offers) >= 3 and any(o["ai_score"] == 85 and o["cv"] == "cv1" for o in offers)
        first = next(o for o in offers if o["state"] == "new")
        assert c.patch(f"/api/offers/{first['id']}", json={"state": "saved"}, headers=hz).json()["ok"]
        assert first["id"] in {o["id"] for o in c.get("/api/offers?state=saved", headers=hz).json()}
        assert c.get("/api/offers?state=saved", headers=hc).json() == []
        assert c.get(f"/api/offers/{first['id']}", headers=hz).json()["description"]
        st = c.get("/api/status", headers=hz).json()
        assert st["total"] >= 3 and st["pool"] >= st["total"]
        assert "new" in c.post("/api/refresh", headers=hz).json()

        # candidatures : chacun les siennes, impossible de toucher à celles d'un autre
        aid = c.post("/api/applications", json={"company": "Orange", "job": "Stage"}, headers=hz).json()["id"]
        assert c.patch(f"/api/applications/{aid}?status=3", headers=hz).json()["ok"]
        assert c.get("/api/applications", headers=hz).json()[0]["status"] == 3
        assert c.get("/api/applications", headers=hc).json() == []
        c.patch(f"/api/applications/{aid}?status=5", headers=hc)
        c.delete(f"/api/applications/{aid}", headers=hc)
        assert c.get("/api/applications", headers=hz).json()[0]["status"] == 3

        # assistant : limite du jour de la formule ; une clé personnelle ne la lève pas, elle change seulement qui paie
        assert c.put("/api/admin/settings", json={"limits": {"assist": 2}}, headers=hc).json()["limits"]["assist"] == 2
        ask = lambda: c.post("/api/ai", json={"task": "letter", "offer": "Stage réseaux"}, headers=hz)
        r1, r2, r3 = ask(), ask(), ask()
        assert r1.json()["text"] == "Texte généré" and r2.json()["ai"]["kinds"]["assist"] == {"used": 2, "limit": 2}
        assert r3.status_code == 429 and "Limite du jour atteinte" in r3.json()["detail"] and "propre clé" not in r3.json()["detail"]
        assert c.put("/api/me/gemini", json={"key": "cle-invalide-cle-invalide"}, headers=hz).status_code == 400
        assert c.put("/api/me/gemini", json={"key": "court"}, headers=hz).status_code == 400
        me = c.put("/api/me/gemini", json={"key": "cle-de-zoe-" + "x" * 20}, headers=hz).json()
        assert me["ai"]["own_key"] and me["ai"]["kinds"]["assist"]["limit"] == 2                # la limite reste celle de la formule
        assert ask().status_code == 429                                                          # la clé ne débloque rien
        c.put("/api/admin/settings", json={"limits": {"assist": 3}}, headers=hc)
        assert ask().status_code == 200 and gemini_keys[-1].startswith("cle-de-zoe-")           # sous la limite : c'est sa clé qui sert
        assert ask().status_code == 429
        assert "cle-de-zoe" not in json.dumps(c.get("/api/me", headers=hz).json())      # la clé n'est jamais renvoyée
        assert not c.put("/api/me/gemini", json={"key": ""}, headers=hz).json()["ai"]["own_key"]

        # alertes : seules de vraies adresses Discord sont acceptées (le serveur n'appelle jamais une adresse quelconque)
        for url in ("http://169.254.169.254/latest", "https://exemple.fr/api/webhooks/1/x", "https://discord.com.evil.fr/api/webhooks/1/x"):
            assert c.put("/api/me/alerts", json={"discord": url}, headers=hz).status_code == 400, url
        assert c.put("/api/me/alerts", json={"ntfy": "a b"}, headers=hz).status_code == 400
        assert c.post("/api/me/alerts/test", headers=hz).status_code == 400              # aucun canal
        me = c.put("/api/me/alerts", json={"discord": "https://discord.com/api/webhooks/333/zzz", "ntfy": "sujet-secret-zoe"}, headers=hz).json()
        assert me["alerts"]["discord"] is True and me["alerts"]["ntfy"] == "sujet-secret-zoe"
        assert c.post("/api/me/alerts/test", headers=hz).json()["ok"]
        assert "Message de test" in discord["https://discord.com/api/webhooks/333/zzz"][-1]
        assert ntfy[-1]["topic"] == "sujet-secret-zoe" and ntfy[-1]["click"] == "https://site.test"
        assert c.post("/api/me/telegram/link", headers=hz).status_code == 400            # code pas encore envoyé au bot
        tg_updates.append({"message": {"text": "/start " + me["alerts"]["telegram_code"], "chat": {"id": 4242, "first_name": "Zoé"}}})
        assert c.post("/api/me/telegram/link", headers=hz).json()["alerts"]["telegram"] and telegram[-1]["chat_id"] == "4242"
        assert not c.put("/api/me/alerts", json={"on": False}, headers=hz).json()["alerts"]["on"]
        assert accounts.channels(accounts.by_email("zoe@ex.fr")) == {}                   # alertes coupées

        # réglages personnels
        crit = c.put("/api/criteria", json={"notify_ai": 70, "goal": "Alternance cloud à Lyon", "strong": ["cloud"], "evil": 1}, headers=hz).json()
        assert crit["notify_ai"] == 70 and crit["goal"] == "Alternance cloud à Lyon" and crit["strong"] == ["cloud"] and "evil" not in crit
        assert c.get("/api/criteria", headers=hc).json()["notify_ai"] == 60
        assert c.put("/api/criteria", json={"reset_lists": True}, headers=hz).json()["custom_lists"] == []

        # administration
        ov = c.get("/api/admin/overview", headers=hc).json()
        zid = next(u["id"] for u in ov["users"] if u["email"] == "zoe@ex.fr")
        assert ov["sources"]["France Travail"]["ok"] and ov["config"]["gemini"] and ov["shared"]["used"] >= 1
        assert "pw_hash" not in json.dumps(ov) and "secrets" not in ov["users"][0]
        s = c.put("/api/admin/settings", json={"site": {"signup": "invite", "invite_code": "Promo2027"}, "criteria": {"min_kw": 12, "rss_feeds": ["Nom | https://x/feed"]}}, headers=hc).json()
        assert s["site"]["signup"] == "invite" and s["criteria"]["min_kw"] == 12 and s["criteria"]["rss_feeds"] == ["Nom | https://x/feed"]
        assert c.post("/api/signup", json={"email": "yan@ex.fr", "password": "motdepasse", "consent": True}).status_code == 403
        assert c.post("/api/signup", json={"email": "yan@ex.fr", "password": "motdepasse", "consent": True, "invite": "promo2027"}).status_code == 200
        c.put("/api/admin/settings", json={"limits": {"max_users": 1}}, headers=hc)
        assert c.get("/api/public").json()["signup"] == "closed"
        c.put("/api/admin/settings", json={"limits": {"max_users": 300}, "site": {"signup": "open"}}, headers=hc)
        assert c.patch(f"/api/admin/users/{chef['me']['id']}", json={"is_admin": False}, headers=hc).status_code == 400
        temp = c.post(f"/api/admin/users/{zid}/reset", headers=hc).json()["password"]
        assert c.get("/api/me", headers=hz).status_code == 401                           # anciens jetons de Zoé refusés
        hz = {"Authorization": "Bearer " + c.post("/api/login", json={"email": "zoe@ex.fr", "password": temp}).json()["token"]}
        assert c.post("/api/me/password", json={"old": "faux", "new": "nouveau-mot"}, headers=hz).status_code == 400
        tok = c.post("/api/me/password", json={"old": temp, "new": "nouveau-mot"}, headers=hz).json()["token"]
        assert c.get("/api/me", headers=hz).status_code == 401
        hz = {"Authorization": f"Bearer {tok}"}
        assert c.patch(f"/api/admin/users/{zid}", json={"disabled": True}, headers=hc).json()["ok"]
        assert c.get("/api/me", headers=hz).status_code == 401
        assert c.post("/api/login", json={"email": "zoe@ex.fr", "password": "nouveau-mot"}).status_code == 403
        c.patch(f"/api/admin/users/{zid}", json={"disabled": False}, headers=hc)

        # export puis suppression du compte par l'utilisatrice
        exp = c.get("/api/me/export", headers=hz).json()
        assert exp["compte"]["email"] == "zoe@ex.fr" and exp["candidatures"][0]["company"] == "Orange" and "pw_hash" not in json.dumps(exp)
        assert c.post("/api/me/delete", json={"password": "faux"}, headers=hz).status_code == 400
        assert c.post("/api/me/delete", json={"password": "nouveau-mot"}, headers=hz).json()["ok"]
        assert c.get("/api/me", headers=hz).status_code == 401 and accounts.by_email("zoe@ex.fr") is None
        with db.engine.connect() as k:
            assert k.execute(db.select(db.func.count()).select_from(db.applications).where(db.applications.c.user_id == zid)).scalar() == 0

        assert c.get("/api/cron?key=bad").status_code == 403
        assert "new" in c.get("/api/cron?key=k&wait=1").json()
        assert "new" in c.post("/api/admin/collect", headers=hc).json()


def test_ai_threshold():
    """L'IA ne note que les offres dont le score par mots-clés atteint le seuil de l'utilisateur."""
    u = accounts.create("seuil@ex.fr", "Seuil", "motdepasse9")
    u["profile"] = {"cvs": {"cv1": {"text": "M2 réseaux. Cisco, BGP, Linux."}}}
    accounts.save_profile(u)
    u["settings"] = {"min_kw": 0}
    accounts.save_settings(u)
    collector.sync_user(u)
    scores = sorted({r.kw_score for r in rows(u["id"]).values()})
    assert len(scores) >= 2, scores
    u["settings"]["ai_min_kw"] = scores[-1]          # seule la mieux placée passe le seuil
    accounts.save_settings(u)
    res = run(collector.process_one(u["id"]))
    mine = rows(u["id"]).values()
    assert res["scored"] == sum(r.kw_score >= scores[-1] for r in mine) >= 1
    assert all((r.ai_score == 85) == (r.kw_score >= scores[-1]) for r in mine)
    assert all(r.notified for r in mine)             # les autres sont traitées sans IA, pas laissées en attente
    assert quota.view(accounts.by_id(u["id"]))["kinds"]["score"]["used"] == res["scored"]
    assert scoring.user_criteria({"settings": {}})["ai_min_kw"] == 40


def test_guards(monkeypatch):
    """Inscriptions en rafale, blocage de connexion par un tiers, liens d'offres piégés."""
    from fastapi.testclient import TestClient
    import main
    main._hits.clear()
    monkeypatch.setattr(main, "SIGNUPS_PER_HOUR", 3)
    body = lambda i: {"email": f"rafale{i}@ex.fr", "password": "motdepasse1", "consent": True}
    with TestClient(main.app) as c:
        # 1) changer d'adresse de connexion à chaque essai ne contourne plus le plafond du site
        codes = [c.post("/api/signup", json=body(i), headers={"X-Forwarded-For": f"9.9.9.{i}"}).status_code for i in range(5)]
        assert codes == [200, 200, 200, 429, 429], codes
        # l'en-tête écrit par Cloudflare passe avant celui que le visiteur peut modifier
        main._hits.clear()
        monkeypatch.setattr(main, "SIGNUPS_PER_HOUR", 100)
        codes = [c.post("/api/signup", json=body(10 + i), headers={"CF-Connecting-IP": "5.5.5.5", "X-Forwarded-For": f"8.8.8.{i}"}).status_code
                 for i in range(7)]
        assert codes == [200] * 5 + [429] * 2, codes
        # 2) un tiers qui se trompe exprès ne bloque pas le vrai propriétaire
        bad = [c.post("/api/login", json={"email": "rafale0@ex.fr", "password": "faux"}, headers={"X-Forwarded-For": "6.6.6.6"}).status_code
               for _ in range(10)]
        assert bad[:8] == [401] * 8 and bad[8:] == [429, 429], bad
        good = {"email": "rafale0@ex.fr", "password": "motdepasse1"}
        assert c.post("/api/login", json=good, headers={"X-Forwarded-For": "7.7.7.7"}).status_code == 200
        assert c.post("/api/login", json=good, headers={"X-Forwarded-For": "6.6.6.6"}).status_code == 429
        # ... mais le nombre total d'essais sur un même compte reste plafonné
        main._hits.clear()
        many = [c.post("/api/login", json={"email": "rafale1@ex.fr", "password": "faux"}, headers={"X-Forwarded-For": f"4.4.{i // 250}.{i % 250}"}).status_code
                for i in range(62)]
        assert many[:60] == [401] * 60 and many[60:] == [429, 429], many[55:]
    # 3) un lien qui n'est pas une adresse web n'entre jamais dans le stock
    raw = {"source": "RSS", "ext_id": "1", "company": "X", "title": "Stage ingénieur réseaux", "place": "Paris",
           "url": "javascript:alert(1)", "description": "BGP Cisco", "published": "", "geo_ok": False}
    assert collector.keep(raw, scoring.criteria()) is None
    assert collector.keep({**raw, "url": "https://ex.fr/1"}, scoring.criteria()) is not None
    main._hits.clear()


def test_ai_retries(monkeypatch):
    """Appels à l'IA : nouveaux essais sur erreur passagère, modèle de secours, arrêt net sur erreur définitive."""
    import ai
    calls, script = [], []

    def fake(req: httpx.Request) -> httpx.Response:
        model = str(req.url).split("/models/")[1].split(":")[0]
        calls.append(model)
        step = script.pop(0) if script else 200
        if step == "coupure":
            raise httpx.ConnectError("coupé")
        if step == 200:
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "ok " + model}]}}]})
        return httpx.Response(step, text="API key not valid" if step == 403 else "surcharge", headers={"retry-after": "0"})

    real = httpx._client.AsyncClient   # la vraie classe (la version simulée par défaut est remplacée ici)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(fake), **kw))
    monkeypatch.setitem(ai._working, "model", None)
    monkeypatch.setenv("GEMINI_MODEL", "modele-a")
    monkeypatch.setattr(ai, "FALLBACK_MODELS", ["modele-b"])
    # 1) deux erreurs passagères puis succès : même modèle, 3 appels
    script[:] = [503, "coupure", 200]
    assert run(ai.generate("x", "k")) == "ok modele-a" and calls == ["modele-a"] * 3
    # 2) le premier modèle reste saturé : 3 essais, puis le modèle de secours répond
    calls.clear(); script[:] = [429, 429, 429, 200]; ai._working["model"] = None
    assert run(ai.generate("x", "k")) == "ok modele-b" and calls == ["modele-a"] * 3 + ["modele-b"]
    # 3) clé refusée : un seul appel, aucun nouvel essai
    calls.clear(); script[:] = [403]; ai._working["model"] = None
    with pytest.raises(ai.AIError, match="refusée"):
        run(ai.generate("x", "k"))
    assert calls == ["modele-a"]
    # 4) tout est en panne : on s'arrête après 3 essais par modèle, avec un message clair
    calls.clear(); script[:] = [503] * 6; ai._working["model"] = None
    with pytest.raises(ai.AIError, match="surchargé"):
        run(ai.generate("x", "k"))
    assert calls == ["modele-a"] * 3 + ["modele-b"] * 3
    # 5) durée totale plafonnée : avec un budget nul, aucun appel n'est fait
    calls.clear(); ai._working["model"] = None
    with pytest.raises(ai.AIError, match="trop de temps"):
        run(ai.generate("x", "k", budget=0))
    assert calls == []


def test_premium():
    """Formule Premium : limites plus hautes, activée et retirée par l'administrateur, prolongeable."""
    import time as _t
    from fastapi.testclient import TestClient
    import main
    main._hits.clear()
    with TestClient(main.app) as c:
        boss = accounts.by_email("chef@ex.fr") or accounts.create("chef@ex.fr", "Chef", "motdepasse1", True)
        accounts.set_fields(boss["id"], is_admin=1)
        h = {"Authorization": "Bearer " + security.make_token(boss["id"], accounts.by_id(boss["id"])["token_version"])}
        tok = c.post("/api/signup", json={"email": "client@ex.fr", "password": "motdepasse1", "consent": True}).json()
        hu, uid = {"Authorization": "Bearer " + tok["token"]}, tok["me"]["id"]
        lim = quota.limits()
        assert tok["me"]["ai"]["premium"] is False and tok["me"]["ai"]["kinds"]["assist"]["limit"] == lim["assist"]
        assert c.patch(f"/api/admin/users/{uid}", json={"premium_days": 30}, headers=hu).status_code == 403   # réservé à l'admin
        assert c.patch(f"/api/admin/users/{uid}", json={"premium_days": 30}, headers=h).json()["ok"]
        me = c.get("/api/me", headers=hu).json()
        assert me["ai"]["premium"] and me["ai"]["kinds"]["assist"]["limit"] == lim["p_assist"] > lim["assist"]
        until = me["ai"]["premium_until"]
        assert 29.9 * 86400 < until - _t.time() < 30.1 * 86400
        c.patch(f"/api/admin/users/{uid}", json={"premium_days": 30}, headers=h)                                # prolonge
        assert abs(c.get("/api/me", headers=hu).json()["ai"]["premium_until"] - until - 30 * 86400) < 5
        ov = c.get("/api/admin/overview", headers=h).json()
        assert ov["stats"]["premium"] == 1 and ov["stats"]["total"] == len(ov["users"]) and ov["stats"]["new_7d"] >= 1
        c.patch(f"/api/admin/users/{uid}", json={"premium_days": 0}, headers=h)                                 # retour au gratuit
        me = c.get("/api/me", headers=hu).json()
        assert not me["ai"]["premium"] and me["ai"]["kinds"]["assist"]["limit"] == lim["assist"]
        assert c.patch(f"/api/admin/users/{boss['id']}", json={"disabled": True}, headers=h).status_code == 400  # pas sur soi-même
        pub = c.get("/api/public").json()
        assert pub["premium_limits"]["score"] == lim["p_score"] and "url" in pub["premium"]
    main._hits.clear()


def test_plan_limits(monkeypatch):
    """Les limites suivent la formule, pas la clé ; ceux qui paient gardent une part réservée du quota commun."""
    import time as _t
    free = accounts.create("gratuit@ex.fr", "G", "motdepasse1")
    keyed = accounts.create("cle@ex.fr", "C", "motdepasse1")
    paid = accounts.create("payant@ex.fr", "P", "motdepasse1")
    keyed["secrets"]["gemini"] = "cle-perso-" + "y" * 20
    accounts.save_secrets(keyed)
    free, keyed = accounts.by_id(free["id"]), accounts.by_id(keyed["id"])
    day, before = quota.today(), db.usage_get(0, quota.today()).get("req", 0)
    db.kv_set("limits", {"assist": 2, "p_assist": 9, "shared_requests": before + 10, "p_reserve": 4})
    monkeypatch.delenv("PREMIUM_URL", raising=False)
    quota.reset_cache()
    try:
        # clé personnelle en formule gratuite : c'est sa clé qui sert, mais avec la limite gratuite
        assert quota.grant(keyed, "assist", 5) == ("cle-perso-" + "y" * 20, True, 2)
        quota.record(keyed, "assist", 2, True)
        with pytest.raises(quota.QuotaError) as e:
            quota.grant(keyed, "assist")
        assert "Limite du jour atteinte (2" in str(e.value) and "Premium" not in str(e.value)    # rien à vendre : pas de réclame
        assert quota.view(keyed)["kinds"]["assist"] == {"used": 2, "limit": 2} and not quota.view(keyed)["can_upgrade"]
        assert db.usage_get(0, day).get("req", 0) == before                                      # sa clé ne coûte rien au site
        monkeypatch.setenv("PREMIUM_URL", "https://payer.test/premium")
        with pytest.raises(quota.QuotaError) as e:
            quota.grant(keyed, "assist")
        assert "La formule Premium en donne 9 par jour" in str(e.value) and quota.view(keyed)["can_upgrade"]
        monkeypatch.setenv("PREMIUM_URL", "javascript:alert(1)")                                 # lien refusé s'il n'est pas en https
        assert quota.premium_url() == "" and not quota.view(keyed)["can_upgrade"]
        monkeypatch.setenv("PREMIUM_URL", "https://payer.test/premium")
        # le même compte en Premium : limite relevée, toujours avec sa clé
        accounts.set_fields(keyed["id"], plan_until=_t.time() + 86400)
        assert quota.grant(accounts.by_id(keyed["id"]), "assist", 20)[1:] == (True, 7)
        accounts.set_fields(keyed["id"], plan_until=0)
        # part réservée : sans aucun Premium, les comptes gratuits vont jusqu'au bout du quota commun
        db.usage_add(0, day, "req", 7)                                                           # il reste 3 appels communs
        quota.reset_cache()
        assert quota.reserve() == 0 and quota.grant(free, "assist")[1] is False
        accounts.set_fields(paid["id"], plan_until=_t.time() + 86400)
        paid = accounts.by_id(paid["id"])
        quota.reset_cache()
        assert quota.reserve() == 4
        with pytest.raises(quota.QuotaError) as e:
            quota.grant(free, "assist")
        assert "comptes gratuits" in str(e.value) and "Premium" in str(e.value)
        assert quota.grant(paid, "assist", 3) == ("cle-commune", False, 3)                       # celui qui paie passe
        assert not quota.view(paid)["can_upgrade"]
        db.usage_add(0, day, "req", 3)                                                           # quota commun à zéro
        with pytest.raises(quota.QuotaError):
            quota.grant(paid, "assist")
    finally:
        db.usage_add(0, day, "req", before - db.usage_get(0, day).get("req", 0))
        db.kv_set("limits", {})
        for u in (free, keyed, paid):
            accounts.remove(u["id"])
        quota.reset_cache()


def test_emails(monkeypatch):
    """Confirmation de l'adresse et mot de passe oublié par e-mail."""
    import re as _re
    from fastapi.testclient import TestClient
    import main, mailer
    main._hits.clear(); mails.clear(); mailer._sent.clear()
    link = lambda m, kind: _re.search(rf"#{kind}=([\w.]+)", m["textContent"]).group(1)
    with TestClient(main.app) as c:
        # sans service d'e-mails : rien ne change, le compte est utilisable tout de suite
        r = c.post("/api/signup", json={"email": "sansmail@ex.fr", "password": "motdepasse1", "consent": True}).json()
        assert r["me"]["verified"] and not mails and c.get("/api/public").json()["mail"] is False
        assert c.post("/api/password/forgot", json={"email": "sansmail@ex.fr"}).status_code == 400

        monkeypatch.setenv("BREVO_API_KEY", "cle-brevo"); monkeypatch.setenv("MAIL_FROM", "bonjour@site.test")
        assert c.get("/api/public").json()["mail"] is True
        # 1) inscription : un e-mail part, le compte attend la confirmation pour utiliser l'IA commune
        r = c.post("/api/signup", json={"email": "nouvelle@ex.fr", "password": "motdepasse1", "name": "Lina", "consent": True}).json()
        h = {"Authorization": "Bearer " + r["token"]}
        assert r["me"]["verified"] is False and r["me"]["ai"]["needs_verification"] is True
        m = mails[-1]
        assert m["to"] == [{"email": "nouvelle@ex.fr"}] and m["sender"]["email"] == "bonjour@site.test" and m["_key"] == "cle-brevo"
        assert "https://site.test/#verify=" in m["textContent"] and "Confirmer mon adresse" in m["htmlContent"]
        u = accounts.by_email("nouvelle@ex.fr")
        u["profile"] = {"cvs": {"cv1": {"text": "M2 réseaux. Cisco, BGP, Linux."}}}; accounts.save_profile(u)
        assert run(collector.process_one(u["id"])).get("setup") == "email"          # pas de note par l'IA avant confirmation
        assert c.post("/api/ai", json={"task": "targets"}, headers=h).status_code == 429
        # un lien d'un autre type, ou trafiqué, est refusé
        assert c.post("/api/verify", json={"token": security.make_link_token("reset", u["id"], 0, 1)}).status_code == 400
        assert c.post("/api/verify", json={"token": link(m, "verify")[:-1] + ("1" if link(m, "verify").endswith("0") else "0")}).status_code == 400
        assert c.post("/api/verify", json={"token": link(m, "verify")}).json()["ok"]
        me = c.get("/api/me", headers=h).json()
        assert me["verified"] and me["ai"]["needs_verification"] is False and not me["is_admin"]
        assert c.post("/api/ai", json={"task": "targets"}, headers=h).status_code == 200
        # 2) renvoi : inutile une fois confirmé, donc aucun e-mail de plus
        n = len(mails); assert c.post("/api/me/verify/resend", headers=h).json()["ok"] and len(mails) == n
        # 3) mot de passe oublié : même réponse pour une adresse inconnue, mais aucun e-mail
        assert c.post("/api/password/forgot", json={"email": "inconnu@ex.fr"}).json() == {"ok": True} and len(mails) == n
        assert c.post("/api/password/forgot", json={"email": " Nouvelle@ex.fr "}).json() == {"ok": True}
        m = mails[-1]; tok = link(m, "reset")
        assert len(mails) == n + 1 and "Choisir un nouveau mot de passe" in m["htmlContent"]
        assert c.post("/api/password/reset", json={"token": tok, "new": "court"}).status_code == 400
        assert c.post("/api/password/reset", json={"token": link(mails[n - 1] if "#verify=" in mails[n - 1]["textContent"] else mails[0], "verify"), "new": "motdepasse2"}).status_code == 400
        r = c.post("/api/password/reset", json={"token": tok, "new": "motdepasse2"})
        assert r.status_code == 200 and r.json()["me"]["email"] == "nouvelle@ex.fr"
        assert c.get("/api/me", headers=h).status_code == 401                         # l'ancienne connexion est fermée
        assert c.post("/api/password/reset", json={"token": tok, "new": "motdepasse3"}).status_code == 400   # lien à usage unique
        h2 = {"Authorization": "Bearer " + c.post("/api/login", json={"email": "nouvelle@ex.fr", "password": "motdepasse2"}).json()["token"]}
        assert c.post("/api/login", json={"email": "nouvelle@ex.fr", "password": "motdepasse1"}).status_code == 401
        # pas plus de 3 demandes par heure pour une même adresse
        for _ in range(4):
            c.post("/api/password/forgot", json={"email": "nouvelle@ex.fr"})
        assert len(mails) == n + 3
        # 4) l'adresse de l'administrateur ne donne le rôle qu'après confirmation
        accounts.remove(accounts.by_email("chef@ex.fr")["id"]) if accounts.by_email("chef@ex.fr") else None
        main._hits.clear()
        r = c.post("/api/signup", json={"email": "chef@ex.fr", "password": "motdepasse1", "consent": True}).json()
        assert r["me"]["is_admin"] is False
        assert c.post("/api/verify", json={"token": link(mails[-1], "verify")}).json()["ok"]
        assert c.get("/api/me", headers={"Authorization": "Bearer " + r["token"]}).json()["is_admin"] is True
        # test d'envoi réservé à l'administrateur, avec la raison exacte en cas de refus
        boss = {"Authorization": "Bearer " + r["token"]}
        ok = c.post("/api/admin/mail/test", headers=boss).json()
        assert ok == {"to": "chef@ex.fr", "from": "bonjour@site.test"} and "Test d'envoi" in mails[-1]["subject"]
        assert c.post("/api/admin/mail/test", headers=h2).status_code == 403
        mail_fail["on"] = True
        bad = c.post("/api/admin/mail/test", headers=boss)
        assert bad.status_code == 502 and "Key not found" in bad.json()["detail"]["error"] and "xkeysib" in bad.json()["detail"]["help"]
        mail_fail["on"] = False
        # 5) service d'e-mails en panne : l'inscription marche quand même
        mail_fail["on"] = True
        assert c.post("/api/signup", json={"email": "panne@ex.fr", "password": "motdepasse1", "consent": True}).status_code == 200
        mail_fail["on"] = False
    main._hits.clear(); mails.clear()


def test_domains_and_regions(monkeypatch):
    """Autres domaines et autres régions : chacun ne voit que ce qui correspond à ses choix."""
    import domains, sources
    from fastapi.testclient import TestClient
    import main
    main._hits.clear()
    assert domains.regions_of("Toulouse, Haute-Garonne") == ["occ"] and domains.regions_of("92 - Châtillon") == ["idf"]
    assert domains.in_france("Lyon, France") and not domains.in_france("New York, USA") and domains.in_france("")
    assert domains.place_ok("Toulouse (31)", ["occ"]) and not domains.place_ok("Toulouse (31)", ["idf"])
    assert domains.place_ok("Toulouse (31)", []) and domains.place_ok("", ["idf"]) and domains.place_ok("France", ["bre"])
    site = scoring.criteria()
    emb = scoring.user_criteria({"settings": {"domains": ["embarque"], "regions": ["occ"]}}, site)
    assert "fpga" in emb["strong"] and "cisco" not in emb["tech"] and emb["search_set"] and "Occitanie" in emb["goal"]
    old = scoring.user_criteria({"settings": {}}, site)                      # compte d'avant : rien ne change pour lui
    assert old["domains"] == ["reseaux"] and old["regions"] == ["idf"] and old["strong"] == site["strong"] and not old["search_set"]
    mix = scoring.user_criteria({"settings": {"domains": ["reseaux", "gestion"]}}, site)
    assert "marketing" in mix["strong"] and "marketing" not in mix["negative"]   # recherché d'un côté : plus pénalisé de l'autre

    with TestClient(main.app) as c:
        mk = lambda mail: c.post("/api/signup", json={"email": mail, "password": "motdepasse1", "consent": True}).json()
        sarah, paul = mk("sarah@ex.fr"), mk("paul@ex.fr")
        hs = {"Authorization": "Bearer " + sarah["token"]}
        assert set(c.get("/api/public").json()["domains"]) == set(domains.DOMAINS) and "occ" in c.get("/api/public").json()["regions"]
        got = c.put("/api/criteria", json={**sarah["me"]["settings"], "domains": ["embarque"], "regions": ["occ", "idf"]}, headers=hs).json()
        assert got["domains"] == ["embarque"] and got["regions"] == ["idf", "occ"] and "fpga" in got["strong"] and not got["custom_lists"]
        assert got["goal_is_default"] and "embarqués" in got["goal"]             # la phrase suit ses nouveaux choix
        # Adzuna : interrogé sur toute la France, et seulement pour les domaines que quelqu'un a cochés
        monkeypatch.setenv("ADZUNA_APP_ID", "x"); monkeypatch.setenv("ADZUNA_APP_KEY", "y")
        assert set(collector.domains_in_use()) >= {"reseaux", "embarque"} and "gestion" not in collector.domains_in_use()
        adzuna_calls.clear()
        run(collector.run_once(force=True))
        asked = [x["q"] for x in adzuna_calls]
        assert "stage embarqué" in asked and "stage réseaux" in asked and "stage marketing" not in asked
        assert all(x["where"] is None for x in adzuna_calls)
        s_titles, p_titles = set(rows(sarah["me"]["id"])), set(rows(paul["me"]["id"]))
        assert {"Stage ingénieur logiciel embarqué C / STM32 (H/F)", "Stage FPGA VHDL - électronique numérique"} <= s_titles
        assert "Stage ingénieur réseaux et sécurité H/F" not in s_titles          # hors de son domaine
        assert not any("embarqué" in t or "FPGA" in t for t in p_titles)          # Paul (réseaux, Île-de-France) ne les voit pas
        # elle retire l'Île-de-France : l'offre d'Élancourt quitte sa liste, celle de Toulouse reste
        c.put("/api/criteria", json={"regions": ["occ"]}, headers=hs)
        run(collector.resync_one(sarah["me"]["id"]))
        s_titles = set(rows(sarah["me"]["id"]))
        assert "Stage ingénieur logiciel embarqué C / STM32 (H/F)" in s_titles and "Stage FPGA VHDL - électronique numérique" not in s_titles
        # toute la France : les deux reviennent
        c.put("/api/criteria", json={"regions": []}, headers=hs)
        run(collector.resync_one(sarah["me"]["id"]))
        assert "Stage FPGA VHDL - électronique numérique" in set(rows(sarah["me"]["id"]))
    main._hits.clear()


def test_old_offers_ignored():
    """Une annonce mise en ligne depuis plus de 20 jours n'entre pas dans le stock ; sans date, elle est gardée."""
    import datetime as dt
    crit = scoring.pool_criteria(scoring.criteria())
    day = lambda n: (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=n)).strftime("%Y-%m-%d")
    raw = lambda pub: {"source": "X", "ext_id": "1", "company": "X", "title": "Stage ingénieur cybersécurité réseau",
                       "place": "Paris", "url": "https://x.io/1", "description": "stage de fin d'études", "published": pub,
                       "geo_ok": False}
    assert collector.keep(raw(day(5)), crit)
    assert collector.keep(raw(""), crit)
    assert collector.keep(raw(day(21)), crit) is None
    assert collector.keep(raw("Posted 30+ Days Ago"), crit) is None


def test_domains_from_cv():
    """Un nouvel inscrit qui n'a rien réglé reçoit ses domaines et sa phrase d'après son CV ; ses choix priment ensuite."""
    from fastapi.testclient import TestClient
    import main
    main._hits.clear()
    with TestClient(main.app) as c:
        new = lambda mail: {"Authorization": "Bearer " + c.post("/api/signup", json={
            "email": mail, "password": "motdepasse", "consent": True}).json()["token"]}
        cv = lambda h, text: c.post("/api/profile/cv?slot=cv1", files={"file": ("cv.txt", (text * 20).encode())}, headers=h).json()
        h = new("emb@ex.fr")
        assert c.get("/api/criteria", headers=h).json()["domains"] == ["reseaux"]
        assert cv(h, "VHDL FPGA STM32 C embarqué ")["error"] == ""
        crit = c.get("/api/criteria", headers=h).json()
        assert crit["domains"] == ["embarque"] and crit["regions"] == ["idf"] and "embarqué" in crit["goal"]
        assert "fpga" in [w.lower() for w in crit["strong"] + crit["tech"]] or crit["strong"]
        # quelqu'un qui a déjà choisi ses domaines garde ses choix
        h2 = new("choix@ex.fr")
        c.put("/api/criteria", json={"domains": ["data"], "goal": "Je veux un stage en data science à Lyon"}, headers=h2)
        cv(h2, "VHDL FPGA STM32 C embarqué ")
        crit = c.get("/api/criteria", headers=h2).json()
        assert crit["domains"] == ["data"] and crit["goal"] == "Je veux un stage en data science à Lyon"


def test_own_key_scores_the_rest():
    """Passer en Premium remet en file les offres restées sans note (et seulement celles au-dessus du seuil)."""
    import time
    from sqlalchemy import insert, select
    u = accounts.create("reste@ex.fr", "Reste", "motdepasse")
    with db.engine.begin() as c:
        for i, (kw, ai_s, state) in enumerate([(80, None, "new"), (20, None, "new"), (90, 70, "new"), (85, None, "hidden")]):
            oid = f"rq{i}"
            c.execute(insert(db.offers).values(id=oid, source="X", company="X", title=f"Stage {i}", place="Paris",
                                               url="https://x.io", description="", published="", ext_id=oid,
                                               first_seen=time.time(), kw_score=kw))
            c.execute(insert(db.user_offers).values(user_id=u["id"], offer_id=oid, kw_score=kw, ai_score=ai_s,
                                                    state=state, notified=2))
    assert collector.requeue_unscored(u) == 1
    with db.engine.connect() as c:
        rows = dict(c.execute(select(db.user_offers.c.offer_id, db.user_offers.c.notified)
                              .where(db.user_offers.c.user_id == u["id"])).all())
    assert rows == {"rq0": 0, "rq1": 2, "rq2": 2, "rq3": 2}


def test_workable_and_teamtailor():
    """Connecteurs Workable et Teamtailor : lecture des réponses, puis filtres habituels du stock commun."""
    import sources
    assert {"workable", "teamtailor"} <= set(sources.ATS) and sources.companies()["workable"] and sources.companies()["teamtailor"]

    async def read():
        async with httpx.AsyncClient(headers=sources.UA) as h:
            return (await sources.workable(h, {"name": "Withings", "token": "withings"}),
                    await sources.teamtailor(h, {"name": "Skello", "token": "skello"}))
    ats_extra["on"] = True
    try:
        wk, tt = run(read())
        a = wk[0]
        assert (a["source"], a["company"], a["ext_id"]) == ("Withings", "Withings", "AB12CD34EF")
        assert a["place"] == "Issy-les-Moulineaux, Île-de-France, France" and a["published"] == RECENT
        assert a["url"] == "https://apply.workable.com/j/AB12CD34EF" and "<p>" not in a["description"] and "Kotlin" in a["description"]
        # contrat « Internship » : le titre est complété, et sans « url » on prend le lien court
        assert wk[1]["title"] == "Embedded Software Engineer (stage)" and wk[1]["url"].endswith("/ZZ00000001")
        b = tt[0]
        assert (b["source"], b["ext_id"], b["place"]) == ("Skello", "guid-1", "Paris, France / Lille, France")
        assert b["url"] == "https://skello.teamtailor.com/jobs/1-data-analyst-intern" and "SQL" in b["description"]
        assert tt[1]["place"] == "London, United Kingdom" and len(tt) == 3

        # mémoire : liste légère d'abord, textes demandés une seule fois, et seulement les stages en France
        assert len(wk) == 2 and wk_calls == [None, "true"]
        sources._wk_done.clear()
        new = run(collector.collect(force=True))
        with db.engine.connect() as c:
            got = {r.title: r for r in c.execute(db.offers.select().where(db.offers.c.source.in_(["Withings", "Skello"])))}
        # gardées : les stages en France. Écartées : Boston, Londres, le poste senior, l'annonce de plus de 20 jours.
        assert sorted(got) == ["Data Analyst Intern - stage", "Embedded Software Engineer (stage)",
                               "Stage - Android Engineer (H/F)"], sorted(got)
        assert new >= 3 and got["Data Analyst Intern - stage"].published == RECENT
        assert db.kv_get("src:Withings")["ok"] and db.kv_get("src:Skello")["found"] == 3
        wk_calls.clear()
        assert run(collector.collect(force=True)) == 0                                    # aucun doublon au passage suivant
        assert wk_calls == [None]                                                         # et plus aucun texte téléchargé
    finally:
        ats_extra["on"] = False
    # une page carrières en panne (404) est signalée dans Administration sans bloquer les autres
    run(collector.collect(force=True))
    assert db.kv_get("src:Withings")["ok"] is False and "404" in db.kv_get("src:Withings")["error"]


def test_public_board_and_posts(monkeypatch):
    """Vitrine sans compte et textes de publications : uniquement des offres réelles, récentes et du bon domaine."""
    import time
    from fastapi.testclient import TestClient
    from sqlalchemy import delete, insert
    import board, main
    monkeypatch.setenv("APP_URL", "https://site.test")
    now = time.time()
    with db.engine.begin() as c:
        c.execute(delete(db.offers))
        def add(i, title, company, place, text, hours=2, url=None, published=RECENT):
            c.execute(insert(db.offers).values(id=f"pb{i}", source=company, company=company, title=title, place=place,
                                               url=url or f"https://ex.fr/pb{i}", description=text, published=published,
                                               ext_id=f"pb{i}", first_seen=now - hours * 3600, kw_score=50))
        add(1, "Stage ingénieur cybersécurité SOC", "Orange", "92 - Châtillon", "SIEM Splunk, EDR, bac+5")
        add(2, "Stage ingénieur réseaux BGP", "Thales", "Toulouse, Haute-Garonne", "Cisco, MPLS, firewall")
        add(3, "Stage DevOps cloud Kubernetes", "Datadog", "Paris, France", "AWS, Terraform, Linux", hours=100)
        add(4, "Stage analyste SOC N2", "Orange", "Rennes", "SIEM, EDR")
        add(5, "Stage sécurité cloud", "Capgemini", "France", "Azure, IAM, Kubernetes")
        add(6, "Stage data scientist NLP", "Dataiku", "Paris", "Python, machine learning, deep learning, pandas")
        add(7, "Stage cybersécurité piégé", "Piège", "Paris", "SOC", url="javascript:alert(1)")
        add(8, "Stage assistant marketing digital", "Mode", "Lyon", "réseaux sociaux, community management")
        add(9, "Stage ingénieur réseaux ancien", "Vieux", "Paris", "BGP", hours=30 * 24)
    board.reset()
    with TestClient(main.app) as c:
        v = c.get("/api/public/offers", params={"domain": "reseaux"})
        assert v.status_code == 200 and "max-age" in v.headers["cache-control"]                # lisible sans compte
        v = v.json()
        titles = [o["title"] for o in v["offers"]]
        assert v["total"] == 5 and v["fresh"] == 4 and set(titles) == {
            "Stage ingénieur cybersécurité SOC", "Stage ingénieur réseaux BGP", "Stage DevOps cloud Kubernetes",
            "Stage analyste SOC N2", "Stage sécurité cloud"}, v
        assert titles[-1] == "Stage DevOps cloud Kubernetes"                                    # les nouveautés d'abord
        assert set(v["offers"][0]) == {"id", "title", "company", "place", "url", "source", "published", "score"}  # pas de texte complet
        assert v["counts"]["data"] >= 1 and v["counts"]["reseaux"] == 5
        # par région : Île-de-France garde Châtillon, Paris et l'offre « France » (valable partout), pas Toulouse ni Rennes
        idf = c.get("/api/public/offers", params={"domain": "reseaux", "region": "idf"}).json()
        assert {o["company"] for o in idf["offers"]} == {"Orange", "Datadog", "Capgemini"} and idf["total"] == 3
        # domaine inconnu : celui qui a le plus d'offres
        assert c.get("/api/public/offers", params={"domain": "<script>"}).json()["domain"] == "reseaux"
        # publications : réservées à l'administrateur
        assert c.get("/api/admin/posts").status_code == 401
        u = accounts.create("vitrine@ex.fr", "V", "motdepasse1")
        accounts.set_fields(u["id"], is_admin=1)
        tok = c.post("/api/login", json={"email": "vitrine@ex.fr", "password": "motdepasse1"}).json()["token"]
        posts = c.get("/api/admin/posts", headers={"Authorization": f"Bearer {tok}"}).json()["posts"]
        assert [p["domain"] for p in posts] == ["reseaux"]                                      # les autres ont moins de 3 offres
        p = posts[0]
        assert p["count"] == 5 and len(p["x"]) <= 280 and p["link"] == "https://site.test/#offres/reseaux"
        assert p["x"].startswith("5 stages en réseaux, cybersécurité et cloud repérés cette semaine en France.")
        assert "https://site.test/#offres/reseaux" in p["x"] and "Châtillon" in p["x"] and "92 -" not in p["x"]
        assert p["linkedin"].count("Orange") == 1 and "#stage" in p["linkedin"]                 # une offre par entreprise
        assert "[Accroche" in p["video"] and "piégé" not in p["x"] + p["linkedin"] + p["video"]
    with db.engine.begin() as c:
        c.execute(delete(db.offers))
    board.reset()


def test_seo_pages(monkeypatch):
    """Pages lisibles par Google : contenu réel écrit par le serveur, pages maigres non proposées, ouverture progressive."""
    import time
    from fastapi.testclient import TestClient
    from sqlalchemy import delete, insert
    import board, main, seo
    monkeypatch.setenv("APP_URL", "https://site.test/")
    monkeypatch.setattr(main, "GOOGLE_VERIFY", "abcDEF123_-xyz")
    now = time.time()
    with db.engine.begin() as c:
        c.execute(delete(db.offers))
        def add(i, title, company, place, text, url=None):
            c.execute(insert(db.offers).values(id=f"seo{i}", source=company, company=company, title=title, place=place,
                                               url=url or f"https://ex.fr/seo{i}", description=text, published=RECENT,
                                               ext_id=f"seo{i}", first_seen=now - 3600, kw_score=50))
        add(1, "Stage data scientist NLP", "Dataiku", "Paris", "Python, machine learning, pandas, SQL")
        add(2, "Stage data analyst", "Qonto", "Paris, France", "SQL, Python, Tableau, statistiques")
        add(3, "Stage data engineer", "Doctolib", "92 - Levallois", "Python, Spark, Airflow, SQL")
        add(4, "Stage machine learning <b>vision</b>", "Valeo & Co", "Lyon", "Python, PyTorch, deep learning")
        add(5, "Stage data scientist", "Thales", "France", "Python, statistiques, machine learning")
        add(6, "Stage data piégé", "Piège", "Paris", "machine learning", url="javascript:alert(1)")
        add(7, "Stage ingénieur cybersécurité SOC", "Orange", "Rennes", "SIEM Splunk, EDR, bac+5")
        add(8, "Stage ingénieur cybersécurité SOC", "Orange", "Lannion", "SIEM Splunk, EDR, bac+5")
        add(9, "Stage ingénieur cybersécurité SOC", "Orange", "Brest", "SIEM Splunk, EDR, bac+5")
    db.kv_set("seo_pages", None)
    board.reset()
    seo.reset()
    with TestClient(main.app) as c:
        r = c.get("/stages/data-ia")
        page = r.text
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/html") and "max-age" in r.headers["cache-control"]
        assert "frame-ancestors" in r.headers["content-security-policy"]                         # en-têtes de sécurité conservés
        assert "<h1>Stage data et IA en France</h1>" in page and "5 offres de stage en data et IA" in page
        assert '<meta name="robots" content="index,follow">' in page                             # assez d'offres : proposée à Google
        assert '<link rel="canonical" href="https://site.test/stages/data-ia">' in page
        assert 'content="abcDEF123_-xyz"' in page and "application/ld+json" in page
        for word in ("Dataiku", "Qonto", "Doctolib", "Thales", "Les entreprises qui recrutent", "Où sont les stages",
                     "Les compétences les plus demandées", "python <span>(dans 5 annonces)</span>"):
            assert word in page, word                                                           # chiffres propres à la page
        assert "&lt;b&gt;vision&lt;/b&gt;" in page and "<b>vision</b>" not in page and "Valeo &amp; Co" in page  # texte neutralisé
        assert "javascript:" not in page and "piégé" not in page                                # lien dangereux écarté
        assert 'href="/stages/data-ia/ile-de-france"' in page                                   # maillage vers la région fournie
        assert "/stages/data-ia/bretagne" not in page                                           # pas de lien vers une page vide
        # la même annonce dans trois villes : comptée trois fois, montrée une seule
        cyber = c.get("/stages/reseaux-cybersecurite-cloud").text
        assert "3 offres de stage" in cyber and cyber.count('<article class="offer">') == 1 and "et 2 autres lieux" in cyber
        # région : seulement les offres qui s'y trouvent (pas « France »), 3 offres donc lisible mais pas encore ouverte
        idf = c.get("/stages/data-ia/ile-de-france").text
        assert "<h1>Stage data et IA en Île-de-France</h1>" in idf and "3 offres de stage" in idf
        assert "Thales" not in idf and "Valeo" not in idf and "Stage data et IA Paris et La Défense (Île-de-France)" in idf
        assert '<meta name="robots" content="noindex,follow">' in idf                           # ouverture progressive
        # page maigre : visible, jamais proposée à Google
        thin = c.get("/stages/data-ia/auvergne-rhone-alpes").text
        assert "1 offre de stage" in thin and "noindex,follow" in thin
        empty = c.get("/stages/embarque-electronique/corse").text
        assert "Aucune offre" in empty and "noindex,follow" in empty
        assert c.get("/stages/inconnu").status_code == 404 and c.get("/stages/data-ia/atlantide").status_code == 404
        hub = c.get("/stages").text
        assert 'href="/stages/data-ia"' in hub and "5 offres cette semaine" in hub and "index,follow" in hub
        # plan du site : accueil, sommaire et le seul domaine assez fourni
        sm = c.get("/sitemap.xml")
        assert sm.headers["content-type"].startswith("application/xml")
        assert re.findall(r"<loc>(.*?)</loc>", sm.text) == ["https://site.test/", "https://site.test/stages",
                                                            "https://site.test/stages/reseaux-cybersecurite-cloud",
                                                            "https://site.test/stages/data-ia"]
        rb = c.get("/robots.txt").text
        assert "Sitemap: https://site.test/sitemap.xml" in rb and "Disallow: /api/" in rb
        # une semaine plus tard : la page de région la plus fournie est ouverte à son tour, et le reste
        assert db.kv_get("seo_pages")["pages"] == ["reseaux", "data"]
        later = now + 8 * 86400
        seo.reset()
        n = seo.counts(board._data(now))
        assert seo.published(n, later) == ["reseaux", "data", "reseaux/bre", "data/idf"]
        seo.reset()
        assert seo.published(n, later + 3600) == ["reseaux", "data", "reseaux/bre", "data/idf"]                          # pas deux fois dans la semaine
        assert "index,follow" in c.get("/stages/data-ia/ile-de-france").text
    # adresses stables, et celles de la page d'accueil sans JavaScript existent toutes
    assert seo.path("data", "paca") == "/stages/data-ia/provence-alpes-cote-d-azur"
    index = open(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "index.html"), encoding="utf-8").read()
    for d in seo.SLUGS:
        assert f'href="{seo.path(d)}"' in index, d
    home = main.home_html("<html><head><title>x</title></head><body></body></html>", "https://site.test")
    assert '<link rel="canonical" href="https://site.test/">' in home and "google-site-verification" in home
    with db.engine.begin() as c:
        c.execute(delete(db.offers))
    db.kv_set("seo_pages", None)
    board.reset()
    seo.reset()
