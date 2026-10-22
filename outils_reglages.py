"""
Réglages des outils de Root, pilotés depuis la fenêtre.

root.py garde la table OUTILS et la politique d'autorisation. Ici on ajoute une
couche que Vincent contrôle : couper un outil (il n'est plus proposé au cerveau),
le rendre plus strict (toujours demander), et choisir le mode d'autonomie. Les
choix vivent dans reglages.local.json (hors du dépôt) ; aucune règle de sécurité
du moteur n'est affaiblie, on ne fait que RETIRER ou AJOUTER des demandes.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import root

CHEMINS_CMD = [Path.home() / "bin", Path.home() / ".local" / "bin", Path("/opt/homebrew/bin"), Path("/usr/bin")]

FAMILLES = [
    ("Fichiers et terminal", ["lire_fichier", "lister", "ecrire_fichier", "terminal", "executer_script"]),
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
    "sandbox": ("Bac à sable", "code isolé, avec timeout"),
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
    perso = outils_perso()
    if perso:
        outils = []
        for d in perso:
            outils.append({"id": d["id"], "risque": RISQUE_PERSO.get(d.get("risque"), "modifie"),
                           "risque_nom": "Mien", "risque_aide": "outil que tu as ajouté",
                           "description": d["description"], "coupe": bool(reg.get(d["id"], {}).get("coupe")),
                           "strict": bool(reg.get(d["id"], {}).get("strict")),
                           "verrouille_demande": d.get("risque") == "demande",
                           "perso": True, "source": d.get("source", ""), "commande": " ".join(d["commande"])})
        familles.append({"titre": "Mes outils", "perso": True, "outils": outils})
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




# ─────────────────────────────────────────────────────────────────────────────
# Mes outils : des outils que Vincent déclare lui-même (une commande locale, ou
# un dépôt GitHub qu'il a installé). Root les propose au cerveau comme les
# autres, et ils passent par les MÊMES autorisations. Rien ne s'installe ni ne
# s'exécute tout seul : Vincent écrit la commande et valide.
# ─────────────────────────────────────────────────────────────────────────────

RISQUE_PERSO = {"demande": "modifie", "libre": "variable"}   # « demande » = toujours demander


def outils_perso() -> list[dict]:
    return list(_reglages_lire().get("outils_perso", []))


def _slug(nom: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", nom.strip().lower()).strip("_") or "outil"
    return base[:40]


def ajouter_outil_perso(nom, description, commande, argument=False, quand="",
                        toujours_demander=True, source="") -> dict:
    """Déclare un outil. `commande` est une liste (pas de shell) ; si `argument`,
    le cerveau peut passer un texte ajouté à la fin. Refuse d'écraser un outil du
    moteur. Ne lance ni n'installe rien."""
    nom = (nom or "").strip()
    if not nom or not description.strip():
        return {"ok": False, "message": "Il faut au moins un nom et une description."}
    cmd = [str(x) for x in commande if str(x).strip()] if isinstance(commande, list) else           [m for m in re.split(r"\s+", str(commande).strip()) if m]
    if not cmd:
        return {"ok": False, "message": "Il faut une commande à lancer."}
    ident = _slug(nom)
    socle = {n for n in root.OUTILS if n not in root.OUTILS_PERSO}
    if ident in socle:
        ident += "_" + uuid.uuid4().hex[:3]
    perso = outils_perso()
    d = {"id": ident, "nom": nom, "description": description.strip(), "commande": cmd,
         "argument": bool(argument), "quand": quand.strip(),
         "risque": "demande" if toujours_demander else "libre", "source": source.strip()}
    perso = [o for o in perso if o["id"] != ident] + [d]
    _sauver_perso(perso)
    return {"ok": True, "message": f"« {nom} » ajouté.", "id": ident}


def retirer_outil_perso(ident: str) -> bool:
    perso = [o for o in outils_perso() if o["id"] != ident]
    _sauver_perso(perso)
    return True


def _sauver_perso(perso: list) -> None:
    from fenetre import ecrire_reglages
    ecrire_reglages(outils_perso=perso)
    appliquer_au_moteur()


def _fn_perso(d: dict):
    """Fabrique la fonction qu'appelle le cerveau : lance la commande (sans shell),
    rend sa sortie. L'argument éventuel est ajouté comme UN seul argument."""
    def faire(argument: str = "", **_ignore):
        cmd = list(d["commande"])
        if d.get("argument") and argument:
            cmd.append(str(argument))
        exe = shutil.which(cmd[0]) or next(
            (str(p / cmd[0]) for p in CHEMINS_CMD if (p / cmd[0]).exists()), None)
        if exe is None:
            return f"ERREUR : commande introuvable « {cmd[0]} ». Installe-la d'abord."
        try:
            r = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            return "ERREUR : la commande a dépassé 120 s."
        except OSError as e:
            return f"ERREUR au lancement : {e}"
        sortie = (r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")
        return sortie.strip() or f"(code {r.returncode}, aucune sortie)"
    return faire


def _appliquer_perso() -> None:
    for n in list(root.OUTILS_PERSO):
        root.OUTILS.pop(n, None)
    root.OUTILS_PERSO = set()
    for d in outils_perso():
        props = {"argument": {"type": "string", "description": d.get("quand") or "argument à passer"}} \
            if d.get("argument") else {}
        root.OUTILS[d["id"]] = {
            "fn": _fn_perso(d), "risque": RISQUE_PERSO.get(d.get("risque"), "modifie"), "perso": True,
            "schema": {"description": d["description"],
                       "parameters": {"type": "object", "properties": props, "required": []}}}
        root.OUTILS_PERSO.add(d["id"])


def lire_readme_github(url: str) -> dict:
    """Lit le README d'un dépôt GitHub pour PRÉPARER une fiche d'outil. N'installe
    rien, ne lance rien. Renvoie un brouillon que Vincent complète et valide."""
    m = re.search(r"github\.com/([^/\s]+)/([^/\s#?]+)", url or "")
    if not m:
        return {"ok": False, "message": "Donne un lien de dépôt GitHub (github.com/…)."}
    proprio, depot = m.group(1), m.group(2).removesuffix(".git")
    texte = None
    for branche in ("main", "master"):
        for nom in ("README.md", "readme.md", "README.rst", "README"):
            u = f"https://raw.githubusercontent.com/{proprio}/{depot}/{branche}/{nom}"
            try:
                req = urllib.request.Request(u, headers={"User-Agent": "root-terminal"})
                with urllib.request.urlopen(req, timeout=12) as r:
                    texte = r.read(60000).decode("utf-8", "replace")
                    break
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
                continue
        if texte:
            break
    return {"ok": True, "nom": depot, "source": f"https://github.com/{proprio}/{depot}",
            "readme": texte or "", "readme_manquant": texte is None}


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
    _appliquer_perso()


def _ecrire(nom: str, **valeurs) -> None:
    reg = _outils_reglages()
    reg.setdefault(nom, {}).update(valeurs)
    _sauver(reg)


def _sauver(reg: dict) -> None:
    from fenetre import ecrire_reglages
    ecrire_reglages(outils=reg)
