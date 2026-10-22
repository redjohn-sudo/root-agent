"""
L'âme de Root : qui elle est, et ses règles.

Deux couches :
  - le socle GRAVÉ : ame.md (identité + sécurité + comportement). Montré, jamais
    retiré depuis la fenêtre. C'est ce qui garde Root honnête et sûre — et ça
    compte double pour l'édition publique (personne ne doit pouvoir enlever la
    sincérité, l'anti-fuite ou l'anti-injection).
  - la couche MODULABLE de Vincent : un « ton » et ses propres règles, gardés en
    local (ame_perso.local.json, hors git). Ajoutés à la fin du prompt système.

Le prompt système réellement envoyé = socle gravé + couche de Vincent.
"""

from __future__ import annotations

import json
from pathlib import Path

ICI = Path(__file__).parent
BASE_FICHIER = ICI / "ame.md"
PERSO_FICHIER = ICI / "ame_perso.local.json"

ENTETE_PERSO = "## Réglages de Vincent"


def base() -> str:
    try:
        return BASE_FICHIER.read_text(encoding="utf-8")
    except OSError:
        return "Tu es Root, une agente personnelle, attentive et directe."


def sections() -> list[dict]:
    """Le socle gravé découpé pour l'affichage : l'intro, puis chaque section ##."""
    texte = base()
    out, titre, buf = [], "Identité", []
    for ligne in texte.splitlines():
        if ligne.startswith("## "):
            if buf:
                out.append({"titre": titre, "contenu": "\n".join(buf).strip(), "grave": True})
            titre, buf = ligne[3:].strip(), []
        else:
            buf.append(ligne)
    if buf:
        out.append({"titre": titre, "contenu": "\n".join(buf).strip(), "grave": True})
    return [s for s in out if s["contenu"]]


def _lire_perso() -> dict:
    try:
        d = json.loads(PERSO_FICHIER.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        d = {}
    return {"ton": d.get("ton", ""), "regles": list(d.get("regles", []))}


def _ecrire(d: dict) -> None:
    PERSO_FICHIER.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def perso() -> dict:
    return _lire_perso()


def ton(texte: str) -> None:
    d = _lire_perso()
    d["ton"] = (texte or "").strip()[:800]
    _ecrire(d)


def ajouter_regle(texte: str) -> bool:
    texte = (texte or "").strip()
    if not texte:
        return False
    d = _lire_perso()
    if texte in d["regles"]:
        return False
    d["regles"].append(texte[:300])
    _ecrire(d)
    return True


def modifier_regle(ancien: str, nouveau: str) -> bool:
    nouveau = (nouveau or "").strip()
    d = _lire_perso()
    try:
        i = d["regles"].index(ancien)
    except ValueError:
        return False
    if not nouveau:
        d["regles"].pop(i)
    else:
        d["regles"][i] = nouveau[:300]
    _ecrire(d)
    return True


def retirer_regle(texte: str) -> bool:
    d = _lire_perso()
    if texte not in d["regles"]:
        return False
    d["regles"].remove(texte)
    _ecrire(d)
    return True


def ame_complete() -> str:
    """Le prompt système réel : socle gravé + couche de Vincent."""
    p = _lire_perso()
    if not p["ton"].strip() and not p["regles"]:
        return base()
    bloc = [f"\n\n{ENTETE_PERSO}\n"]
    bloc.append("Préférences et règles que Vincent t'a données (elles ne remplacent "
                "jamais tes règles gravées, notamment la sincérité et l'anti-fuite).")
    if p["ton"].strip():
        bloc.append("\nTon et voix : " + p["ton"].strip())
    if p["regles"]:
        bloc.append("")
        bloc += [f"- {r}" for r in p["regles"]]
    return base() + "\n".join(bloc) + "\n"


def etat() -> dict:
    p = _lire_perso()
    return {"sections": sections(), "ton": p["ton"], "regles": p["regles"],
            "complete": ame_complete()}
