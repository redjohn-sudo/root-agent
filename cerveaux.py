"""
Les cerveaux de Root : plusieurs LLM interchangeables derrière la même âme.

Changer de cerveau ne change pas Root : même âme, mêmes outils, même mémoire.
Seul le modèle qui pense change. La liste vit dans cerveaux.json (sans aucune
clé : seulement le NOM de la variable d'environnement qui la contient).

Trois précautions quand l'historique passe d'un cerveau à l'autre :
  - la réflexion (`reasoning_content`) n'est renvoyée qu'au fournisseur qui l'a
    produite (son format n'est pas portable, et certains la refusent) ;
  - les champs privés du harness (`_par`, `_cerveau`) ne partent jamais ;
  - un cerveau qui ne voit pas reçoit un texte à la place de l'image, au lieu
    d'une erreur 400.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

ICI = Path(__file__).parent
FICHIER = ICI / "cerveaux.json"
ENVS = [Path.home() / ".hermes" / "profiles" / "racine" / ".env",
        Path.home() / ".hermes" / ".env"]
IMAGE_ABSENTE = "[image non transmise : ce cerveau ne voit pas les images]"


def charger() -> dict:
    return json.loads(FICHIER.read_text(encoding="utf-8"))


def liste() -> list[dict]:
    return charger()["cerveaux"]


def par_id(ident: str) -> dict | None:
    return next((c for c in liste() if c["id"] == ident), None)


def defaut() -> dict:
    d = charger()
    return par_id(d.get("defaut", "")) or d["cerveaux"][0]


def cle(cerveau: dict) -> str:
    """La clé, lue dans l'environnement ou les fichiers .env. Jamais affichée."""
    nom = cerveau["cle"]
    if os.environ.get(nom):
        return os.environ[nom]
    for f in ENVS:
        try:
            for ligne in f.read_text(encoding="utf-8").splitlines():
                ligne = ligne.strip()
                if ligne.startswith(nom + "="):
                    return ligne.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            continue
    return ""


def preparer(messages: list[dict], cerveau: dict) -> list[dict]:
    """Copie de l'historique adaptée à ce cerveau (voir les trois précautions)."""
    sortie = []
    for m in messages:
        m2 = {k: v for k, v in m.items() if not k.startswith("_")}
        if m.get("role") == "assistant" and m.get("_par") != cerveau["fournisseur"]:
            m2.pop("reasoning_content", None)
        contenu = m2.get("content")
        if not cerveau.get("vision") and isinstance(contenu, list):
            m2["content"] = [{"type": "text", "text": IMAGE_ABSENTE}
                             if isinstance(p, dict) and p.get("type") == "image_url" else p
                             for p in contenu]
        sortie.append(m2)
    return sortie


def corps_requete(cerveau: dict, messages: list[dict], outils=None, max_tokens=None) -> dict:
    corps = {"model": cerveau["modele"], "messages": preparer(messages, cerveau),
             "max_tokens": max_tokens or cerveau.get("max_tokens", 4000)}
    if outils:
        corps["tools"] = outils
        corps["tool_choice"] = "auto"
    if cerveau.get("effort"):
        corps["reasoning_effort"] = cerveau["effort"]   # sinon Kimi/GLM brûlent tout en réflexion
    return corps


def appeler(cerveau: dict, messages: list[dict], outils=None, max_tokens=None) -> dict:
    """Un appel /chat/completions. La réponse garde la trace de son auteur
    (`_par`, `_cerveau`) pour l'affichage et pour `preparer`."""
    req = urllib.request.Request(
        cerveau["url"].rstrip("/") + "/chat/completions",
        data=json.dumps(corps_requete(cerveau, messages, outils, max_tokens)).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + cle(cerveau)})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.load(r)
    msg = data["choices"][0]["message"]
    msg["_par"] = cerveau["fournisseur"]
    msg["_cerveau"] = cerveau["id"]
    return data


def cout(cerveau: dict, entree: int, sortie: int) -> float | None:
    """Coût en dollars, ou None si le prix n'est pas confirmé (jamais inventé)."""
    prix = cerveau.get("prix")
    if not prix:
        return None
    return (entree * prix[0] + sortie * prix[1]) / 1_000_000


def sonder(cerveau: dict) -> dict:
    """Le cerveau répond-il ? (liste des modèles : gratuit) et en combien de temps."""
    if not cle(cerveau):
        return {"ok": False, "ms": None, "raison": "clé absente"}
    t = time.time()
    try:
        req = urllib.request.Request(cerveau["url"].rstrip("/") + "/models",
                                     headers={"Authorization": "Bearer " + cle(cerveau)})
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read(256)
        return {"ok": True, "ms": round((time.time() - t) * 1000)}
    except Exception as e:
        return {"ok": False, "ms": None, "raison": type(e).__name__}
