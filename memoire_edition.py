"""
Édition de la mémoire durable de Root (memoire.md) depuis la fenêtre.

memoire.py (Kimi) garde les règles : plafond, refus des données sensibles,
quasi-doublons, pierres tombales. Ce module n'en contourne aucune ; il ajoute
seulement ce qu'il faut pour que Vincent voie et retouche ses faits :
lire en catégories, modifier un fait sur place, retirer sans tombe (le bouton
Annuler), lever une tombe quand il remet lui-même un fait oublié.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime

import memoire

DATE = re.compile(r"\s+_\(noté le ([^)]+)\)_\s*$")
CATEGORIES_PROPOSEES = ["Profil", "Certifs et diplômes", "Cadre de travail", "Projets", "Préférences"]


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", (s or "").strip())


def _lignes() -> list[str]:
    return memoire._lire_texte_tolerant(memoire.MEMOIRE_FICHIER).splitlines()


def _ecrire(lignes: list[str]) -> None:
    memoire._ecrire_texte_atomique(memoire.MEMOIRE_FICHIER, "\n".join(lignes).rstrip("\n") + "\n")


def _texte_de(ligne: str) -> str:
    return DATE.sub("", ligne[2:]).strip()


def lire() -> dict:
    """Les faits par catégorie, dans l'ordre du fichier, et la jauge du plafond."""
    categories, courante = [], None
    for ligne in _lignes():
        if ligne.startswith("## "):
            courante = {"nom": ligne[3:].strip(), "faits": []}
            categories.append(courante)
        elif ligne.startswith("- "):
            if courante is None:
                courante = {"nom": "Divers", "faits": []}
                categories.append(courante)
            m = DATE.search(ligne)
            courante["faits"].append({"texte": _texte_de(ligne), "date": m.group(1) if m else ""})
    taille = len(memoire._lire_texte_tolerant(memoire.MEMOIRE_FICHIER))
    return {"categories": [c for c in categories if c["faits"]], "taille": taille,
            "plafond": memoire.MEMOIRE_PLAFOND, "proposees": CATEGORIES_PROPOSEES}


def ajouter(categorie: str, fait: str) -> dict:
    statut = memoire.memoire_noter(_nfc(categorie) or "Divers", fait)
    return {"ok": statut.startswith("Noté"), "message": statut,
            "tombe": "pierre tombale" in statut}


def _trouver(lignes: list[str], fait: str) -> int:
    cible = _nfc(fait)
    return next((i for i, l in enumerate(lignes) if l.startswith("- ") and _texte_de(l) == cible), -1)


def retirer(fait: str) -> bool:
    """Retire un fait SANS pierre tombale : Root pourra le réapprendre."""
    lignes = _lignes()
    i = _trouver(lignes, fait)
    if i < 0:
        return False
    del lignes[i]
    _ecrire(_sans_categories_vides(lignes))
    return True


def oublier(fait: str) -> bool:
    """Oublie un fait : retiré, et sa tombe empêche Root de le réapprendre."""
    if not retirer(fait):
        return False
    memoire._tombes_deposer([_nfc(fait)])
    return True


def modifier(ancien: str, nouveau: str) -> dict:
    """Réécrit un fait sur place (même catégorie, date du jour), sous les mêmes règles."""
    nouveau = _nfc(nouveau)
    if not nouveau:
        return {"ok": False, "message": "Refusé : fait vide."}
    if memoire._fait_sensible(nouveau):
        return {"ok": False, "message": "Refusé : le fait ressemble à une donnée sensible, on ne le stocke pas."}
    lignes = _lignes()
    i = _trouver(lignes, ancien)
    if i < 0:
        return {"ok": False, "message": "Fait introuvable (modifié ailleurs ?)."}
    lignes[i] = f"- {nouveau}  _(noté le {datetime.now():%Y-%m-%d})_"
    if len("\n".join(lignes)) + 1 > memoire.MEMOIRE_PLAFOND:
        return {"ok": False, "message": f"Refusé : la mémoire dépasserait le plafond ({memoire.MEMOIRE_PLAFOND} caractères)."}
    _ecrire(lignes)
    return {"ok": True, "message": "Modifié."}


def renommer_categorie(ancien: str, nouveau: str) -> bool:
    nouveau = _nfc(nouveau)
    lignes = _lignes()
    if not nouveau or f"## {nouveau}" in lignes:
        return False
    for i, l in enumerate(lignes):
        if l == f"## {ancien}":
            lignes[i] = f"## {nouveau}"
            _ecrire(lignes)
            return True
    return False


def lever_tombe(fait: str) -> bool:
    """Vincent remet lui-même un fait oublié : la tombe de ce fait seul est levée."""
    empreinte = memoire._empreinte_chaine(_nfc(fait))
    tombes = memoire._tombes_charger()
    if empreinte not in tombes:
        return False
    tombes.remove(empreinte)
    memoire._ecrire_texte_atomique(memoire.TOMBES_FICHIER, json.dumps(tombes))
    return True


def _sans_categories_vides(lignes: list[str]) -> list[str]:
    """Retire un titre de catégorie qui n'a plus aucun fait."""
    garde = []
    for i, l in enumerate(lignes):
        if l.startswith("## "):
            suite = next((x for x in lignes[i + 1:] if x.startswith(("## ", "- "))), "")
            if not suite.startswith("- "):
                continue
        garde.append(l)
    while garde and not garde[-1].strip():
        garde.pop()
    return garde


VIDES = set("""les des une est sont pour dans avec sur qui que quoi pas son ses mon mes ton tes notre vous nous
elle ils elles fait faire plus tout tous bien comme mais quel quelle quels cette ces aux par peux peut moi toi lui
leur leurs ici alors donc car avoir etre suis été the and for you are""".split())


def lies(demande: str, n: int = 3) -> list[str]:
    """Les souvenirs liés à une demande (rappel de Kimi), sans ceux qui ne
    partagent qu'un mot vide (« est », « pour »…) : sinon tout serait « lié »."""
    utiles = {w for w in memoire._mots(demande) if len(w) >= 3 and w not in VIDES}
    return [f for f in memoire.rappel_pertinent(demande, n)
            if utiles & set(memoire._mots(f))]
