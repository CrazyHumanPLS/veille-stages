"""Les CV d'un utilisateur : jusqu'à trois versions (une par domaine visé), rangées dans son profil.
Gemini indique pour chaque offre laquelle envoyer."""

SLOTS = ["cv1", "cv2", "cv3"]
DEFAULT_LABELS = {"cv1": "CV principal", "cv2": "CV n° 2", "cv3": "CV n° 3"}


def get(u: dict) -> dict:
    p = u["profile"]
    if not isinstance(p.get("cvs"), dict):
        p["cvs"] = {}
    p.setdefault("analysis", None)
    return p


def label(u: dict, slot: str) -> str:
    return (get(u)["cvs"].get(slot, {}).get("label") or DEFAULT_LABELS.get(slot, slot))[:40]


def labels(u: dict) -> dict[str, str]:
    return {s: label(u, s) for s in SLOTS}


def cvs(u: dict) -> dict[str, str]:
    return {k: v["text"] for k, v in get(u)["cvs"].items() if k in SLOTS and (v.get("text") or "").strip()}


def text_for(u: dict, slot: str = "") -> str:
    """Texte d'un CV précis, sinon tous les CV à la suite."""
    all_cvs = cvs(u)
    if slot in all_cvs:
        return all_cvs[slot]
    return block(u, 8000)


def block(u: dict, each: int = 3500) -> str:
    return "\n\n".join(f"[CV {k} — {label(u, k)}]\n{t[:each]}" for k, t in sorted(cvs(u).items()))
