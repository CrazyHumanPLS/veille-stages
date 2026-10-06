"""Appels Gemini : texte libre, analyse du CV, score des offres.
La clé est toujours passée par l'appelant : celle de l'utilisateur, ou la clé commune du site (voir quota.py)."""
import asyncio
import json
import os
import random
import re
import time

import httpx

# Essayés dans l'ordre si le modèle demandé n'existe plus (Google en retire régulièrement).
FALLBACK_MODELS = ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.1-flash-lite"]
_working = {"model": None}


class AIError(Exception):
    pass


def _models() -> list[str]:
    wanted = [_working["model"], os.getenv("GEMINI_MODEL"), *FALLBACK_MODELS]
    seen, out = set(), []
    for m in wanted:
        if m and m not in seen:
            seen.add(m)
            out.append(m)
    return out


RETRYABLE = {429, 500, 502, 503, 504, 529}   # passager : on réessaie. 400, 401, 403 : inutile d'insister
TRIES_PER_MODEL = 3
BACKOFF = float(os.getenv("AI_BACKOFF_SEC", "1"))   # attente de base entre deux essais (doublée à chaque fois)
MAX_WAIT = 8.0                                      # on n'attend jamais plus longtemps entre deux essais
_sleep = asyncio.sleep


def _pause(attempt: int, retry_after: str | None) -> float:
    """Attente avant le prochain essai : celle demandée par Google si elle est raisonnable, sinon une attente
    qui double à chaque fois, avec une part de hasard pour que tous les comptes ne réessaient pas ensemble."""
    try:
        asked = float(retry_after) if retry_after else 0.0
    except ValueError:
        asked = 0.0
    wait = asked if 0 < asked <= MAX_WAIT else BACKOFF * (2 ** attempt)
    return min(MAX_WAIT, wait) * (0.6 + 0.8 * random.random())


async def generate(prompt: str, key: str, as_json: bool = False, timeout: float = 45, budget: float = 100) -> str:
    """Demande un texte à Gemini. timeout : durée maximale d'un appel ; budget : durée maximale de l'ensemble.
    Erreur passagère (surcharge, trop de demandes, coupure) : nouveaux essais espacés, puis modèle suivant.
    Erreur définitive (clé refusée, demande invalide) : arrêt immédiat."""
    if not key:
        raise AIError("clé Gemini manquante")
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.2}}
    if as_json:
        body["generationConfig"]["responseMimeType"] = "application/json"
    last, deadline = "aucun modèle disponible", time.monotonic() + budget
    async with httpx.AsyncClient(timeout=timeout) as h:
        for model in _models():
            for attempt in range(TRIES_PER_MODEL):
                if time.monotonic() >= deadline:
                    raise AIError(f"l'IA met trop de temps à répondre ({last}), réessaie plus tard")
                retry_after = None
                try:
                    r = await h.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                                     headers={"x-goog-api-key": key}, json=body)
                except httpx.HTTPError as e:      # coupure réseau ou délai dépassé
                    last = f"connexion à Gemini impossible ({type(e).__name__})"
                else:
                    if r.status_code in (400, 401, 403) and "api key" in r.text.lower().replace("_", " "):
                        raise AIError("clé Gemini refusée par Google (clé invalide, supprimée ou restreinte)")
                    if r.status_code in (400, 404) and "model" in r.text.lower():
                        last = f"modèle {model} indisponible"
                        break                      # modèle retiré : on passe au suivant sans insister
                    if r.status_code == 200:
                        try:
                            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                        except (KeyError, IndexError, TypeError, ValueError):
                            raise AIError("réponse Gemini vide ou bloquée")
                        if model != _working["model"]:
                            print(f"IA : réponse du modèle {model}" + (f" (après : {last})" if attempt or last != "aucun modèle disponible" else ""))
                        _working["model"] = model
                        return text
                    if r.status_code not in RETRYABLE:
                        raise AIError(f"Gemini {r.status_code} : {r.text[:200]}")
                    last = ("quota Gemini atteint pour cette clé (trop de demandes)" if r.status_code == 429
                            else f"Gemini surchargé ({r.status_code})")
                    retry_after = r.headers.get("retry-after")
                if attempt < TRIES_PER_MODEL - 1:
                    await _sleep(min(_pause(attempt, retry_after), max(0.0, deadline - time.monotonic())))
    raise AIError(f"{last}, réessaie plus tard")


def _loads(text: str):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("\n") + 1:] if "\n" in text else text
    try:
        return json.loads(text)
    except ValueError as e:
        raise AIError(f"JSON Gemini illisible : {e}")


async def check_key(key: str) -> None:
    """Vérifie qu'une clé fonctionne (une toute petite demande). Lève AIError sinon."""
    await generate("Réponds uniquement : OK", key, timeout=30)


async def analyse_cv(cv_text: str, goal: str, key: str) -> dict:
    prompt = (
        "Voici le ou les CV d'une même personne (une version par domaine visé). "
        f"Ce qu'elle cherche : {goal}\n"
        "N'invente rien : appuie-toi uniquement sur ces CV.\n"
        "Renvoie un objet JSON avec exactement ces clés :\n"
        '- "resume" : 3 phrases sur le profil\n'
        '- "points_forts" : liste de 5 éléments maximum\n'
        '- "points_faibles" : liste de 4 éléments maximum (manques par rapport au marché visé)\n'
        '- "mots_cles" : 15 à 25 mots-clés courts présents dans le CV (technologies, outils, méthodes, domaines), en minuscules\n'
        '- "postes_cibles" : 6 intitulés de poste réalistes pour ce profil\n'
        '- "conseils_cv" : 5 améliorations concrètes du CV\n\n'
        f"CV :\n{cv_text[:12000]}")
    data = _loads(await generate(prompt, key, as_json=True))
    if not isinstance(data, dict):
        raise AIError("format inattendu")
    return data


def _cv_key(value, slots: list[str]) -> str:
    """Ramène la réponse de Gemini (« cv2 », « [CV cv2] », « CV 2 »…) à une clé de CV existante."""
    m = re.search(r"cv\s*([1-9])", str(value).lower())
    key = f"cv{m.group(1)}" if m else ""
    if key in slots:
        return key
    return slots[0] if len(slots) == 1 else ""


async def score_offers(profile: str, batch: list[dict], goal: str, slots: list[str], key: str) -> dict[str, dict]:
    """Note un lot d'offres par rapport aux CV. Renvoie {id: {score, raison, cv}}."""
    lines = []
    for o in batch:
        lines.append(f"### id={o['id']}\nTitre : {o['title']}\nEntreprise : {o['company']}\nLieu : {o['place']}\n"
                     f"Description : {(o.get('description') or '(non fournie)')[:1500]}")
    prompt = (
        f"Tu évalues des offres pour un candidat. Ce qu'il cherche : {goal}\n"
        "Il possède une ou plusieurs versions de son CV, identifiées par une clé entre crochets.\n"
        "Pour chaque offre, donne un score de 0 à 100 d'adéquation avec SON profil et SA recherche :\n"
        "- 80-100 : correspond à sa recherche, dans son domaine, compétences largement couvertes\n"
        "- 60-79 : bonne offre du domaine avec quelques manques\n"
        "- 30-59 : domaine voisin ou niveau inadapté\n"
        "- 0-29 : autre type de contrat que celui recherché, autre métier, niveau très éloigné, ou hors sujet\n"
        f"Indique aussi dans \"cv\" la clé du CV le plus adapté à envoyer pour cette offre : {', '.join(slots) or 'cv1'}.\n"
        'Renvoie uniquement un tableau JSON : '
        '[{"id": "...", "score": 0, "cv": "clé", "raison": "une phrase courte et concrète"}]\n\n'
        f"SES CV :\n{profile[:12000]}\n\nOFFRES :\n" + "\n\n".join(lines))
    data = _loads(await generate(prompt, key, as_json=True, budget=45))   # tâche de fond : on n'insiste pas longtemps
    if isinstance(data, dict):
        data = data.get("offres") or data.get("results") or list(data.values())[0]
    out = {}
    for item in data if isinstance(data, list) else []:
        try:
            out[str(item["id"])] = {"score": max(0, min(100, int(item["score"]))),
                                    "raison": str(item.get("raison", ""))[:300],
                                    "cv": _cv_key(item.get("cv", ""), slots)}
        except (KeyError, TypeError, ValueError):
            continue
    return out
