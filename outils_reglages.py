"""
Réglages des outils de Root, pilotés depuis la fenêtre.

root.py garde la table OUTILS et la politique d'autorisation. Ici on ajoute une
couche que Vincent contrôle : couper un outil (il n'est plus proposé au cerveau),
le rendre plus strict (toujours demander), et choisir le mode d'autonomie. Les
choix vivent dans reglages.local.json (hors du dépôt) ; aucune règle de sécurité
du moteur n'est affaiblie, on ne fait que RETIRER ou AJOUTER des demandes.
"""

from __future__ import annotations

import root

FAMILLES = [
    ("Fichiers et terminal", ["lire_fichier", "lister", "ecrire_fichier", "terminal"]),
    ("Navigateur", ["web_naviguer", "web_voir", "web_cliquer", "web_ecrire", "web_entree",
                    "web_defiler", "web_onglets", "web_nouvel_onglet", "web_basculer", "web_fermer_onglet"]),
    ("Écran du Mac", ["capture_ecran", "ecran_position", "ecran_cliquer", "ecran_double_cliquer",
                      "ecran_taper", "ecran_touche"]),
    ("Entendre", ["entendre_etat", "entendre"]),
    ("Mémoire et immunité", ["memoire_noter", "memoire_oublier", "immunite_verifier",
                             "immunite_apprendre", "immunite_actifs", "immunite_oublier"]),
    ("Recherche web", ["recherche_web", "recherche_lire", "recherche_conclure"]),
    ("Actes irréversibles", ["consentement_verifier", "consentement_demander",
                             "consentement_marquer_fait", "consentement_oublier", "verifier_citation"]),
]

RISQUES = {
    "sûr": ("Sûr", "ne demande jamais"),
    "web": ("Web", "agit dans Brave"),
    "modifie": ("Modifie", "change un fichier ou un état"),
    "systeme": ("Système", "clavier/souris ou micro du Mac"),
    "variable": ("Variable", "selon la commande"),
}

PREREGLAGES = {
    "lecture": ("Lecture seule", "Root observe, n'agit pas",
                lambda n, o: o["risque"] in ("sûr", "web") and n not in ECRITURE_WEB),
    "navigateur": ("Navigateur", "lire, chercher et piloter Brave",
                   lambda n, o: o["risque"] in ("sûr", "web") or n == "capture_ecran"),
    "tout": ("Tout", "tous les outils actifs", lambda n, o: True),
}
ECRITURE_WEB = {"web_cliquer", "web_ecrire", "web_entree", "web_nouvel_onglet", "web_fermer_onglet"}


def _reglages_lire():
    from fenetre import lire_reglages
    return lire_reglages()


def _outils_reglages():
    return _reglages_lire().get("outils", {})


def actifs() -> set:
    """Les outils actuellement proposés au cerveau (tous sauf ceux coupés)."""
    coupes = {n for n, r in _outils_reglages().items() if r.get("coupe")}
    return {n for n in root.OUTILS if n not in coupes}


def strict(nom: str) -> bool:
    return bool(_outils_reglages().get(nom, {}).get("strict"))


def etat() -> dict:
    """Tout ce que le panneau affiche : familles, outils, autonomie, préréglages."""
    reg = _outils_reglages()
    familles = []
    for titre, noms in FAMILLES:
        outils = []
        for nom in noms:
            o = root.OUTILS.get(nom)
            if o is None:
                continue
            r = reg.get(nom, {})
            libelle, aide = RISQUES.get(o["risque"], (o["risque"], ""))
            outils.append({
                "id": nom, "risque": o["risque"], "risque_nom": libelle, "risque_aide": aide,
                "description": o["schema"]["description"],
                "coupe": bool(r.get("coupe")), "strict": bool(r.get("strict")),
                "verrouille_demande": o["risque"] in ("systeme", "modifie", "variable"),
            })
        if outils:
            familles.append({"titre": titre, "outils": outils})
    return {"familles": familles, "autonomie": root.AUTONOMIE,
            "prereglages": [{"id": k, "nom": v[0], "aide": v[1]} for k, v in PREREGLAGES.items()],
            "actif": _prereglage_actif(), "terminal_auto": terminal_auto(),
            "verbes_dangereux": list(root.VERBES_DANGEREUX)}


def _prereglage_actif() -> str | None:
    a = actifs()
    for k, (_nom, _aide, regle) in PREREGLAGES.items():
        if a == {n for n, o in root.OUTILS.items() if regle(n, o)}:
            return k
    return None


def basculer(nom: str, coupe: bool) -> bool:
    if nom not in root.OUTILS:
        return False
    _ecrire(nom, coupe=bool(coupe))
    appliquer_au_moteur()
    return True


def rendre_strict(nom: str, strict: bool) -> bool:
    """Ajoute une demande d'autorisation sur un outil « sûr » ou « web ».
    On ne peut que RENDRE PLUS STRICT : un outil qui demande déjà n'est pas allégé ici."""
    if nom not in root.OUTILS:
        return False
    _ecrire(nom, strict=bool(strict))
    appliquer_au_moteur()
    return True


def appliquer_prereglage(ident: str) -> bool:
    regle = PREREGLAGES.get(ident)
    if regle is None:
        return False
    garder = regle[2]
    reg = _outils_reglages()
    for nom, o in root.OUTILS.items():
        reg.setdefault(nom, {})["coupe"] = not garder(nom, o)
    _sauver(reg)
    appliquer_au_moteur()
    return True


def choisir_autonomie(mode: str) -> bool:
    if mode not in ("prudente", "large"):
        return False
    root.AUTONOMIE = mode
    from fenetre import ecrire_reglages
    ecrire_reglages(autonomie=mode)
    return True


# ── Auto-exécution du terminal : éteinte par défaut, pilotée par Vincent ─────
def terminal_auto() -> dict:
    reg = _reglages_lire()
    return {"actif": bool(reg.get("terminal_auto_actif")),
            "prefixes": list(reg.get("terminal_auto", []))}


def terminal_auto_activer(actif: bool) -> bool:
    from fenetre import ecrire_reglages
    ecrire_reglages(terminal_auto_actif=bool(actif))
    appliquer_au_moteur()
    return True


def terminal_auto_prefixes(prefixes: list) -> bool:
    """Remplace la liste des préfixes autorisés (nettoyés, sans vides ni doublons)."""
    propres, vus = [], set()
    for p in prefixes or []:
        p = str(p).strip()
        if p and p not in vus:
            vus.add(p)
            propres.append(p)
    from fenetre import ecrire_reglages
    ecrire_reglages(terminal_auto=propres)
    appliquer_au_moteur()
    return True


def appliquer_au_moteur() -> None:
    """Pousse les choix de Vincent dans les variables du moteur (root.py).
    Appelé au démarrage de la fenêtre et après chaque changement."""
    reg = _reglages_lire()
    outils = reg.get("outils", {})
    root.OUTILS_COUPES = {n for n, r in outils.items() if r.get("coupe")}
    root.OUTILS_STRICTS = {n for n, r in outils.items() if r.get("strict")}
    root.TERMINAL_AUTO_ACTIF = bool(reg.get("terminal_auto_actif"))
    root.TERMINAL_AUTO = list(reg.get("terminal_auto", []))
    mode = reg.get("autonomie")
    if mode in ("prudente", "large"):
        root.AUTONOMIE = mode


def _ecrire(nom: str, **valeurs) -> None:
    reg = _outils_reglages()
    reg.setdefault(nom, {}).update(valeurs)
    _sauver(reg)


def _sauver(reg: dict) -> None:
    from fenetre import ecrire_reglages
    ecrire_reglages(outils=reg)
