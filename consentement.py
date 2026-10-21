"""
Consentement lié à l'empreinte de la charge utile.

Un accord de l'utilisateur ne vaut que pour CE contenu et CETTE cible exacts : si
la charge change après l'accord (texte, destinataire, canal), l'accord est périmé
et il faut redemander. Idempotence : une action déjà effectuée ET confirmée n'est
pas refaite (filet contre un agent relancé qui rejouerait un envoi).

Pour les actes irréversibles de Root (envoi d'un message, publication, soumission
d'un formulaire). Inspiré de oblivion/entraide/consentement.py.

Persistance JSON locale, écriture atomique. L'accord vient toujours d'un humain :
ce module ne décide rien seul, il mémorise et vérifie. Aucune donnée ne sort.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

FICHIER = Path.home() / ".local" / "root-consentement.json"


def empreinte(description: str, cible: str, canal: str = "") -> str:
    """Empreinte stable de la charge exacte (espaces/casse normalisés)."""
    base = "\u0000".join(" ".join(x.lower().split()) for x in (description, cible, canal))
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]


def _charger() -> dict:
    try:
        return json.loads(FICHIER.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _sauver(d: dict) -> None:
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    tmp = FICHIER.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, FICHIER)          # remplacement atomique


def accorder(description: str, cible: str, canal: str = "", par: str = "utilisateur") -> str:
    """Enregistre l'accord d'un humain pour cette charge exacte. Renvoie l'empreinte."""
    d = _charger()
    e = empreinte(description, cible, canal)
    d[e] = {"etat": "accorde", "par": par,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "cible": cible[:80]}
    _sauver(d)
    return e


def marquer_fait(description: str, cible: str, canal: str = "") -> None:
    """À appeler APRÈS l'exécution réussie : l'action ne sera pas refaite."""
    d = _charger()
    e = empreinte(description, cible, canal)
    if e in d:
        d[e]["etat"] = "fait"
        d[e]["fait_ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        _sauver(d)


def peut_agir(description: str, cible: str, canal: str = "") -> tuple[bool, str]:
    """Décide si l'action peut être exécutée maintenant, selon l'accord existant
    pour CETTE charge exacte. Toute modification du texte/cible change l'empreinte
    et retombe donc sur « accord requis »."""
    info = _charger().get(empreinte(description, cible, canal))
    if info is None:
        return False, "aucun accord pour ce contenu exact : demander à l'utilisateur"
    if info["etat"] == "fait":
        return False, "déjà fait et confirmé : ne pas refaire (idempotence)"
    if info["etat"] == "accorde":
        return True, "accord valide pour ce contenu exact"
    return False, "état d'accord inconnu"


def oublier(description: str, cible: str, canal: str = "") -> None:
    _charger_et = _charger()
    _charger_et.pop(empreinte(description, cible, canal), None)
    _sauver(_charger_et)


if __name__ == "__main__":
    import tempfile
    FICHIER = Path(tempfile.mkdtemp()) / "c.json"
    ok, _ = peut_agir("Envoi: bonjour", "ami@example.org", "email")
    assert not ok, "sans accord, on n'agit pas"
    accorder("Envoi: bonjour", "ami@example.org", "email")
    ok, _ = peut_agir("Envoi: bonjour", "ami@example.org", "email")
    assert ok, "accord valide pour la charge exacte"
    # la charge change (texte) -> accord périmé
    ok, _ = peut_agir("Envoi: coucou", "ami@example.org", "email")
    assert not ok, "un texte différent n'est pas couvert"
    # le destinataire change -> accord périmé
    ok, _ = peut_agir("Envoi: bonjour", "autre@example.org", "email")
    assert not ok, "un destinataire différent n'est pas couvert"
    # idempotence
    marquer_fait("Envoi: bonjour", "ami@example.org", "email")
    ok, motif = peut_agir("Envoi: bonjour", "ami@example.org", "email")
    assert not ok and "refaire" in motif, "une action faite ne se refait pas"
    print("auto-tests consentement : OK")
