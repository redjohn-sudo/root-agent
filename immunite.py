"""Mémoire immunitaire de Root : d'une correction vérifiée on apprend un « anticorps ».

Un anticorps est un détecteur (une expression régulière généralisée, par exemple
``items.get(3).unwrap()`` donne ``\\w+\\.get\\(\\d+\\)\\.unwrap\\(\\)``) qui retrouve
les erreurs jumelles partout dans un texte, et qui se partage d'une machine à l'autre.

Ce module est autonome : il ne dépend que de la bibliothèque standard (sqlite3 inclus),
n'importe rien du reste du harness, et ne fait sortir aucune donnée. Tout vit dans une
base SQLite locale dont le chemin est configurable (voir ``CHEMIN_BASE``).
"""

import hashlib
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


# Chemin par défaut de la base. Modifiable au niveau du module (ou par argument du
# constructeur) pour pointer ailleurs, notamment vers un fichier temporaire en test.
CHEMIN_BASE = Path.home() / ".local" / "root-immunite.db"

# Étiquette du format d'échange partageable : un anticorps appris par l'un protège les autres.
FORMAT_ECHANGE = "antibodies-v1"


def maintenant():
    """Horodatage UTC en ISO 8601, pour dater les apprentissages et les rencontres."""
    return datetime.now(timezone.utc).isoformat()


class RegexInvalide(ValueError):
    """Un détecteur qui ne compile pas n'est jamais enregistré : on refuse proprement."""


class FormatInvalide(ValueError):
    """Un paquet d'import qui n'est pas un ``antibodies-v1`` cohérent est refusé."""


class Immunite:
    """Le magasin des anticorps : apprendre, chercher les jumeaux, oublier, exporter, importer.

    Chaque anticorps est identifié par l'empreinte sha256 de son détecteur, si bien que le
    même détecteur appris deux fois reste un seul anticorps (on garde la première origine).
    """

    def __init__(self, chemin=None):
        """Ouvre (ou crée) la base. Sans chemin, on prend la variable module ``CHEMIN_BASE``."""
        self.chemin = Path(chemin) if chemin is not None else Path(CHEMIN_BASE)
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        with self.base() as base:
            base.execute("""CREATE TABLE IF NOT EXISTS anticorps (
                id TEXT PRIMARY KEY,
                regle TEXT NOT NULL,
                detecteur TEXT NOT NULL,
                origine TEXT NOT NULL,
                actif INTEGER NOT NULL DEFAULT 1,
                cree_le TEXT NOT NULL)""")
            base.execute("""CREATE TABLE IF NOT EXISTS rencontres (
                anticorps_id TEXT NOT NULL REFERENCES anticorps(id),
                lieu TEXT NOT NULL,
                texte TEXT NOT NULL,
                vu_le TEXT NOT NULL,
                PRIMARY KEY (anticorps_id, lieu, texte))""")
        # La base peut contenir des traces d'erreurs : lisible et modifiable par le seul propriétaire.
        try:
            os.chmod(self.chemin, 0o600)
        except OSError:
            # Certains systèmes de fichiers refusent chmod ; ce n'est pas bloquant.
            pass

    @contextmanager
    def base(self):
        """Une connexion SQLite par opération, en transaction, toujours refermée."""
        connexion = sqlite3.connect(self.chemin, timeout=10)
        try:
            with connexion:
                yield connexion
        finally:
            connexion.close()

    @staticmethod
    def empreinte(detecteur):
        """Empreinte sha256 (hex) d'un détecteur : l'identité d'un anticorps tient à son détecteur seul."""
        return hashlib.sha256(detecteur.encode("utf-8")).hexdigest()

    @staticmethod
    def _compiler(detecteur):
        """Compile le détecteur ou lève ``RegexInvalide`` avec un message clair."""
        try:
            return re.compile(detecteur)
        except re.error as erreur:
            raise RegexInvalide(f"Détecteur regex invalide : {erreur}") from erreur

    def apprendre(self, regle, detecteur, origine=""):
        """Enregistre un anticorps et renvoie son identifiant.

        ``regle`` décrit l'erreur en une phrase, ``detecteur`` est la regex généralisée,
        ``origine`` dit d'où vient la leçon (une correction, un lieu, une date...).
        Si le même détecteur existe déjà, on ne le réapprend pas : on renvoie l'existant
        en gardant sa première origine. Un détecteur qui ne compile pas est refusé.
        """
        self._compiler(detecteur)
        identifiant = self.empreinte(detecteur)
        origine_json = origine if isinstance(origine, str) else json.dumps(origine, ensure_ascii=False)
        with self.base() as base:
            # INSERT OR IGNORE : la première origine l'emporte, le réapprentissage ne l'écrase pas.
            base.execute("INSERT OR IGNORE INTO anticorps VALUES (?, ?, ?, ?, 1, ?)",
                         (identifiant, regle, detecteur, origine_json, maintenant()))
        return identifiant

    def actifs(self):
        """Tous les anticorps encore actifs, du plus ancien au plus récent."""
        with self.base() as base:
            lignes = base.execute(
                "SELECT id, regle, detecteur, origine, cree_le FROM anticorps "
                "WHERE actif=1 ORDER BY cree_le, id").fetchall()
        return [{"id": i, "regle": r, "detecteur": d, "origine": o, "cree_le": c}
                for i, r, d, o, c in lignes]

    def chercher(self, texte, lieu=""):
        """Confronte un texte à tous les détecteurs actifs et renvoie les correspondances.

        Chaque correspondance est un dict ``{"anticorps", "regle", "detecteur", "extrait",
        "origine", "lieu"}`` où ``extrait`` est le fragment exact qui a déclenché l'alerte.
        Chaque trouvaille est journalisée dans ``rencontres`` (une par anticorps/lieu/extrait).
        """
        trouvailles = []
        for anticorps in self.actifs():
            # Un détecteur stocké compile toujours (vérifié à l'apprentissage), mais on reste prudent.
            try:
                motif = re.compile(anticorps["detecteur"])
            except re.error:
                continue
            for correspondance in motif.finditer(texte):
                extrait = correspondance.group(0)
                trouvailles.append({"anticorps": anticorps["id"], "regle": anticorps["regle"],
                                    "detecteur": anticorps["detecteur"], "extrait": extrait,
                                    "origine": anticorps["origine"], "lieu": lieu})
                self._journaliser(anticorps["id"], lieu, extrait)
        return trouvailles

    def _journaliser(self, anticorps_id, lieu, texte):
        """Note une rencontre ; la même (anticorps, lieu, extrait) n'est comptée qu'une fois."""
        with self.base() as base:
            base.execute("INSERT OR IGNORE INTO rencontres VALUES (?, ?, ?, ?)",
                         (anticorps_id, lieu, texte, maintenant()))

    def rencontres_de(self, anticorps_id):
        """L'historique des rencontres d'un anticorps, du plus ancien au plus récent."""
        with self.base() as base:
            lignes = base.execute(
                "SELECT lieu, texte, vu_le FROM rencontres WHERE anticorps_id=? ORDER BY vu_le, lieu",
                (anticorps_id,)).fetchall()
        return [{"lieu": l, "texte": t, "vu_le": v} for l, t, v in lignes]

    def oublier(self, anticorps_id):
        """Désactive un anticorps (actif=0) sans effacer son histoire. Renvoie True si trouvé."""
        with self.base() as base:
            return base.execute("UPDATE anticorps SET actif=0 WHERE id=?",
                                (anticorps_id,)).rowcount == 1

    def exporter(self):
        """Produit un paquet partageable ``antibodies-v1`` (dict JSON) des anticorps actifs."""
        return {"format": FORMAT_ECHANGE, "anticorps": self.actifs()}

    def importer(self, donnees):
        """Ajoute les anticorps d'un paquet ``antibodies-v1`` et renvoie le nombre réellement ajoutés.

        On vérifie pour chaque anticorps que son identifiant est bien l'empreinte sha256 de
        son détecteur : un paquet trafiqué (id qui ne colle pas au détecteur) est refusé. Un
        détecteur qui ne compile pas est également refusé. Les anticorps déjà connus sont ignorés.
        """
        if not isinstance(donnees, dict) or donnees.get("format") != FORMAT_ECHANGE:
            raise FormatInvalide(f"Ce n'est pas un paquet {FORMAT_ECHANGE}")
        liste = donnees.get("anticorps")
        if not isinstance(liste, list):
            raise FormatInvalide("Champ « anticorps » manquant ou mal formé")
        ajoutes = 0
        with self.base() as base:
            for a in liste:
                try:
                    identifiant = a["id"]
                    detecteur = a["detecteur"]
                    regle = a["regle"]
                except (TypeError, KeyError) as erreur:
                    raise FormatInvalide(f"Anticorps incomplet : {erreur}") from erreur
                if self.empreinte(detecteur) != identifiant:
                    raise FormatInvalide(f"L'anticorps {identifiant} ne correspond pas à son détecteur")
                self._compiler(detecteur)
                ajoutes += base.execute(
                    "INSERT OR IGNORE INTO anticorps VALUES (?, ?, ?, ?, 1, ?)",
                    (identifiant, regle, detecteur, a.get("origine", ""),
                     a.get("cree_le") or maintenant())).rowcount
        return ajoutes
