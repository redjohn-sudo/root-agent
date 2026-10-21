"""Preuves locales de Root, sans réseau ni import du harness.

Portage des repères vérifiés et empreintes de Contingency, complété par les
observations figées et critères de fin d'Oblivion. Sources et limites dans
CONCEPTION-AUTONOMIE.md, section « Premier portage réalisé ».

Le harness déclare les critères et actualise les versions depuis ses propres
lectures. Lui seul enregistre les observations et fournit les contrôles Python.
Le modèle peut proposer des références, jamais ajouter un contrôle ou une preuve.
Ce module ne lit pas les fichiers cibles et ne détecte pas leurs changements seul.
Les observations restent en mémoire locale ; aucune méthode ne les exporte.
Ce registre ne constitue ni un filtre de secrets ni une sandbox Python.
"""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable
from uuid import uuid4


VERSION = "preuves-locales-1"
_CLES_PREUVE = {"observation", "ligne", "citation"}


def empreinte_texte(texte: str) -> str:
    """Même principe SHA-256 que les versions de documents de Contingency."""
    if type(texte) is not str:
        raise ValueError("Le texte doit être une chaîne.")
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def empreinte_configuration(configuration: dict) -> str:
    """Inclure modèle, prompt, schéma et versions de contrôles dans la clé locale."""
    if type(configuration) is not dict:
        raise ValueError("La configuration doit être un objet.")
    return empreinte_texte(json.dumps(
        configuration, ensure_ascii=False, sort_keys=True, allow_nan=False,
        separators=(",", ":"),
    ))


def _texte_requis(valeur: object) -> bool:
    return type(valeur) is str and bool(valeur.strip())


@dataclass(frozen=True)
class Observation:
    """Un résultat réellement reçu par le harness, pas une déclaration du modèle."""

    identifiant: str
    outil: str = field(repr=False)
    cible: str = field(repr=False)
    version: str | None = field(repr=False)
    generation_cible: int
    configuration: str = field(repr=False)
    generation_configuration: int
    sequence: int
    texte: str = field(repr=False)
    empreinte: str = field(repr=False)
    etat_execution: str
    tronquee: bool
    code_sortie: int | None


@dataclass(frozen=True)
class ResultatVerification:
    """Verdict limité au critère, avec motifs fermés et sans extrait de source."""

    statut: str
    motif: str
    critere: str = field(repr=False)
    observations: tuple[str, ...] = ()


@dataclass(frozen=True)
class BilanVerification:
    statut: str
    motif: str
    resultats: tuple[ResultatVerification, ...] = ()

    @property
    def reussi(self) -> bool:
        return self.statut == "verifie" and bool(self.resultats)


@dataclass(frozen=True)
class _Critere:
    cible: str
    version_controle: str
    verifier: Callable[[Observation], bool]
    apres_sequence: int


class RegistrePreuves:
    """Un registre par tâche. Appels locaux de confiance, pas des outils du modèle.

    `verifier` et `conclure` acceptent seulement les propositions de références du
    modèle. Les autres méthodes sont réservées au harness. Toute validation est
    recalculée : un ancien BilanVerification n'est pas un certificat réutilisable.
    L'appelant doit sérialiser les événements d'une tâche et mettre les versions
    à jour avant `conclure`, sans mutation concurrente des cibles.
    """

    def __init__(self, configuration: str, *, limite_observations: int = 256):
        if not _texte_requis(configuration):
            raise ValueError("Une version de configuration est nécessaire.")
        if type(limite_observations) is not int or limite_observations < 1:
            raise ValueError("La limite doit être un entier strictement positif.")
        self._configuration = configuration
        self._generation_configuration = 0
        self._limite = limite_observations
        self._sequence = 0
        self._versions: dict[str, tuple[str | None, int]] = {}
        self._observations: OrderedDict[str, Observation] = OrderedDict()
        self._dernieres: dict[str, str] = {}
        self._criteres: dict[str, _Critere] = {}

    def actualiser_cible(self, cible: str, version: str | None) -> None:
        """Version du contenu/état lu localement, jamais le seul hash d'une URL.

        None signifie état inconnu. Revenir à une ancienne version ne réactive
        pas ses preuves : chaque changement incrémente la génération.
        """
        if not _texte_requis(cible) or (version is not None and not _texte_requis(version)):
            raise ValueError("Cible ou version invalide.")
        if cible not in self._versions:
            self._versions[cible] = (version, 1)
        elif self._versions[cible][0] != version:
            self._versions[cible] = (version, self._versions[cible][1] + 1)

    def actualiser_configuration(self, configuration: str) -> None:
        if not _texte_requis(configuration):
            raise ValueError("Une version de configuration est nécessaire.")
        if configuration != self._configuration:
            self._configuration = configuration
            self._generation_configuration += 1

    def observation_locale(self, identifiant: str) -> Observation | None:
        """Lecture locale de la capture enregistrée, jamais un outil d'export cloud."""
        return self._observations.get(identifiant) if type(identifiant) is str else None

    def ajouter_critere(self, identifiant: str, cible: str, *,
                        version_controle: str,
                        verifier: Callable[[Observation], bool]) -> None:
        """Contrôle déterministe écrit localement avant l'observation à prouver.

        Le contrôle doit être pur, sans effet ni réseau, et rendre exactement un
        booléen. Une recherche de mot ne démontre que sa présence. Pour un bug,
        fournir un contrôle métier ou de test, pas seulement chercher « OK ».
        """
        if not all(_texte_requis(v) for v in (identifiant, cible, version_controle)):
            raise ValueError("Identifiant, cible et version du contrôle nécessaires.")
        if identifiant in self._criteres:
            raise ValueError("Un critère existant ne peut pas être remplacé.")
        if not callable(verifier):
            raise ValueError("Le contrôle doit être une fonction locale.")
        self._criteres[identifiant] = _Critere(
            cible, version_controle, verifier, self._sequence,
        )

    def enregistrer(self, *, outil: str, cible: str, version: str | None,
                    texte: str, etat_execution: str = "reussi",
                    tronquee: bool = False, code_sortie: int | None = None) -> Observation:
        """Appeler seulement après le retour d'un outil ; ne jamais exposer au modèle."""
        if not _texte_requis(outil) or not _texte_requis(cible) or type(texte) is not str:
            raise ValueError("Outil, cible ou texte invalide.")
        if cible not in self._versions or self._versions[cible][0] != version:
            raise ValueError("Actualiser la cible depuis l'état local avant l'observation.")
        if etat_execution not in ("reussi", "echec", "inconnu"):
            raise ValueError("État d'exécution invalide.")
        if type(tronquee) is not bool or (code_sortie is not None and type(code_sortie) is not int):
            raise ValueError("Troncature ou code de sortie invalide.")
        self._sequence += 1
        observation = Observation(
            "obs-" + uuid4().hex, outil, cible, version, self._versions[cible][1],
            self._configuration, self._generation_configuration, self._sequence,
            texte, empreinte_texte(texte), etat_execution, tronquee, code_sortie,
        )
        self._observations[observation.identifiant] = observation
        self._dernieres[cible] = observation.identifiant
        while len(self._observations) > self._limite:
            self._observations.popitem(last=False)
        return observation

    def verifier(self, identifiant: str, preuves: object) -> ResultatVerification:
        """Valide chaque référence puis applique le contrôle local du critère.

        Une preuve est {observation: identifiant, ligne: entier, citation: ligne
        entière exacte}. Toutes les preuves doivent décrire la même observation
        finale. Aucun mélange de captures ni de vraie et fausse référence.
        """
        def resultat(statut: str, motif: str, observations=()) -> ResultatVerification:
            return ResultatVerification(statut, motif, identifiant, tuple(observations))

        if not _texte_requis(identifiant) or identifiant not in self._criteres:
            return resultat("invalide", "critere_inconnu")
        if type(preuves) is not list or not preuves or len(preuves) > 128:
            return resultat("invalide", "preuves_absentes_ou_mal_formees")
        for preuve in preuves:
            if (type(preuve) is not dict or set(preuve) != _CLES_PREUVE
                    or not _texte_requis(preuve["observation"])
                    or type(preuve["ligne"]) is not int or preuve["ligne"] < 1
                    or not _texte_requis(preuve["citation"])):
                return resultat("invalide", "preuve_mal_formee")
        references = tuple(dict.fromkeys(p["observation"] for p in preuves))
        if any(ref not in self._observations for ref in references):
            return resultat("inconnu", "observation_absente", references)
        if len(references) != 1:
            return resultat("invalide", "observations_melangees", references)
        observation = self._observations[references[0]]
        critere = self._criteres[identifiant]
        if observation.cible != critere.cible:
            return resultat("invalide", "cible_incorrecte", references)
        if empreinte_texte(observation.texte) != observation.empreinte:
            return resultat("invalide", "observation_alteree", references)
        lignes = observation.texte.splitlines()
        for preuve in preuves:
            numero = preuve["ligne"]
            if numero > len(lignes) or lignes[numero - 1] != preuve["citation"]:
                return resultat("invalide", "citation_inexacte", references)
        version, generation = self._versions[critere.cible]
        if version is None:
            return resultat("inconnu", "version_cible_inconnue", references)
        if observation.version != version or observation.generation_cible != generation:
            return resultat("non_verifie", "version_cible_perimee", references)
        if (observation.configuration != self._configuration
                or observation.generation_configuration != self._generation_configuration):
            return resultat("non_verifie", "configuration_perimee", references)
        if observation.sequence <= critere.apres_sequence:
            return resultat("non_verifie", "observation_anterieure_au_critere", references)
        if self._dernieres.get(critere.cible) != observation.identifiant:
            return resultat("non_verifie", "observation_remplacee", references)
        if observation.tronquee:
            return resultat("inconnu", "observation_tronquee", references)
        if observation.etat_execution == "inconnu":
            return resultat("inconnu", "execution_inconnue", references)
        if observation.etat_execution == "echec" or observation.code_sortie not in (None, 0):
            return resultat("non_verifie", "execution_en_echec", references)
        try:
            satisfait = critere.verifier(observation)
        except Exception:
            # L'exception peut contenir un secret : aucun détail n'est recopié.
            return resultat("inconnu", "erreur_controle_local", references)
        if type(satisfait) is not bool:
            return resultat("inconnu", "reponse_controle_invalide", references)
        return resultat(
            "verifie" if satisfait else "non_verifie",
            "critere_satisfait" if satisfait else "critere_non_satisfait", references,
        )

    def conclure(self, propositions: object) -> BilanVerification:
        """Recontrôle tous les critères ; aucun sous-ensemble ne peut clore la tâche.

        Le bilan est local et n'active aucune action ou transmission. Sa validité
        cesse dès que l'état des cibles, de la configuration ou du registre change.
        """
        if not self._criteres:
            return BilanVerification("invalide", "aucun_critere")
        if type(propositions) is not dict or set(propositions) != set(self._criteres):
            return BilanVerification("invalide", "criteres_absents_ou_inconnus")
        resultats = tuple(self.verifier(c, propositions[c]) for c in self._criteres)
        for statut in ("invalide", "inconnu", "non_verifie"):
            if any(r.statut == statut for r in resultats):
                return BilanVerification(statut, "criteres_non_valides", resultats)
        return BilanVerification("verifie", "tous_criteres_satisfaits", resultats)


@dataclass(frozen=True)
class RegleImmunitaire:
    """Détecteur écrit et autorisé localement, pas une regex libre du modèle."""
    nom: str
    libelle: str = field(repr=False)
    detecteur: str = field(repr=False)
    version: str


@dataclass(frozen=True)
class CandidatImmunite:
    regle: str
    cible: str = field(repr=False)
    version: str = field(repr=False)
    debut: int
    fin: int


@dataclass(frozen=True)
class BilanImmunite:
    statut: str
    motif: str
    candidats: tuple[CandidatImmunite, ...] = ()


def _travail_immunite(connexion, detecteurs, textes, presence, limite):
    """Travail local isolé pour pouvoir arrêter une expression trop coûteuse."""
    import re
    try:
        motifs = [re.compile(motif) for motif in detecteurs]
        if presence:
            trouves = [motifs[0].search(texte) for texte in textes]
            retour = {"presences": [m is not None for m in trouves],
                      "premiere_non_vide": bool(trouves[0] and trouves[0].end() > trouves[0].start())}
        else:
            positions = []
            partiel = False
            for numero, motif in enumerate(motifs):
                for correspondance in motif.finditer(textes[0]):
                    if len(positions) >= limite:
                        partiel = True
                        break
                    debut, fin = correspondance.span()
                    if debut != fin:
                        positions.append((numero, debut, fin))
                if partiel:
                    break
            retour = {"positions": positions, "partiel": partiel}
        connexion.send(retour)
    except Exception:
        try:
            connexion.send({"erreur": "detecteur_invalide_ou_indisponible"})
        except Exception:
            pass
    finally:
        connexion.close()


def _calculer_immunite(detecteurs, textes, *, presence=False, limite=32, delai=2.0):
    lecture = ecriture = processus = None
    demarre = False
    try:
        import multiprocessing
        contexte = multiprocessing.get_context("spawn")
        lecture, ecriture = contexte.Pipe(duplex=False)
        processus = contexte.Process(target=_travail_immunite,
                                      args=(ecriture, detecteurs, textes, presence, limite), daemon=True)
        processus.start()
        demarre = True
        ecriture.close()
        if not lecture.poll(delai):
            return {"erreur": "delai_immunite"}
        return lecture.recv()
    except Exception:
        return {"erreur": "calcul_immunite_indisponible"}
    finally:
        if lecture is not None:
            lecture.close()
        if ecriture is not None:
            ecriture.close()
        if demarre:
            processus.join(0.1)
            if processus.is_alive():
                processus.terminate()
                processus.join(0.2)
            if processus.is_alive():
                processus.kill()
                processus.join(0.2)
            if not processus.is_alive():
                processus.close()
        elif processus is not None:
            processus.close()


class ImmuniteControlee:
    """Adaptateur du magasin Immunite de Claude, sans second stockage.

    Apprendre exige une capture avant enregistrée et une correction actuelle
    validée par tous les critères du registre après. Une règle doit reconnaître
    l'avant, épargner l'après et ne pas reconnaître le texte vide. Les exemples
    restent en mémoire. La base conserve des empreintes, jamais les extraits.
    Une règle importée ou retrouvée après redémarrage nécessite cette validation
    de nouveau : aucune approbation n'est déduite d'un simple hash en base.
    """

    def __init__(self, magasin, regles: tuple[RegleImmunitaire, ...], *,
                 delai: float = 2.0, caracteres_maximum: int = 100_000,
                 correspondances_maximum: int = 32):
        from immunite import Immunite
        import math
        if (not isinstance(magasin, Immunite) or type(regles) is not tuple
                or not 1 <= len(regles) <= 16
                or type(delai) not in (int, float) or not math.isfinite(delai) or not 0 < delai <= 5
                or type(caracteres_maximum) is not int or not 1 <= caracteres_maximum <= 100_000
                or type(correspondances_maximum) is not int or not 1 <= correspondances_maximum <= 128):
            raise ValueError("Magasin, règles locales et limites valides nécessaires.")
        self._magasin = magasin
        self._regles = {}
        detecteurs = set()
        for regle in regles:
            if (type(regle) is not RegleImmunitaire
                    or not all(_texte_requis(v) for v in (regle.nom, regle.libelle, regle.detecteur, regle.version))
                    or len(regle.detecteur) > 512 or len(regle.libelle) > 300
                    or regle.nom in self._regles or regle.detecteur in detecteurs):
                raise ValueError("Règle locale invalide ou dupliquée.")
            self._regles[regle.nom] = regle
            detecteurs.add(regle.detecteur)
        self._delai = delai
        self._maximum = caracteres_maximum
        self._limite = correspondances_maximum
        self._validees: dict[str, str] = {}

    def _capture_valide(self, observation) -> bool:
        return (type(observation) is Observation and not observation.tronquee
                and observation.etat_execution == "reussi" and observation.code_sortie in (None, 0)
                and observation.version is not None and len(observation.texte) <= self._maximum
                and empreinte_texte(observation.texte) == observation.empreinte)

    @staticmethod
    def _version_regle(regle):
        return empreinte_configuration({"detecteur": regle.detecteur, "version": regle.version,
                                         "nom": regle.nom, "libelle": regle.libelle})

    def apprendre(self, nom: str, *, avant: Observation, apres: Observation,
                  registre_avant: RegistrePreuves, registre_apres: RegistrePreuves,
                  preuves_apres: object) -> BilanImmunite:
        if type(nom) is not str or nom not in self._regles:
            return BilanImmunite("refuse", "regle_locale_inconnue")
        if (not isinstance(registre_avant, RegistrePreuves)
                or not isinstance(registre_apres, RegistrePreuves)
                or not self._capture_valide(avant) or not self._capture_valide(apres)
                or registre_avant.observation_locale(avant.identifiant) != avant
                or registre_apres.observation_locale(apres.identifiant) != apres
                or avant.cible != apres.cible or avant.version == apres.version):
            return BilanImmunite("refuse", "captures_correction_invalides")
        bilan = registre_apres.conclure(preuves_apres)
        if not bilan.reussi or not any(apres.identifiant in r.observations for r in bilan.resultats):
            return BilanImmunite("refuse", "correction_non_prouvee")
        regle = self._regles[nom]
        retour = _calculer_immunite([regle.detecteur], [avant.texte, apres.texte, ""],
                                     presence=True, delai=self._delai)
        if "erreur" in retour:
            return BilanImmunite("inconnu", retour["erreur"])
        if (retour.get("presences") != [True, False, False]
                or retour.get("premiere_non_vide") is not True):
            return BilanImmunite("refuse", "detecteur_rate_erreur_ou_touche_corrige")
        if not registre_apres.conclure(preuves_apres).reussi:
            return BilanImmunite("refuse", "correction_devenue_non_prouvee")
        origine = {"format": "root-correction-v1", "avant": avant.empreinte,
                   "apres": apres.empreinte, "regle": self._version_regle(regle)}
        try:
            identifiant = self._magasin.apprendre(regle.libelle, regle.detecteur, origine)
            if not any(a["id"] == identifiant for a in self._magasin.actifs()):
                return BilanImmunite("refuse", "regle_oubliee")
        except Exception:
            return BilanImmunite("inconnu", "stockage_immunite_indisponible")
        self._validees[identifiant] = self._version_regle(regle)
        return BilanImmunite("apprise", "exemples_et_correction_verifies")

    def reperer(self, observation: Observation) -> BilanImmunite:
        if not self._capture_valide(observation):
            return BilanImmunite("inconnu", "observation_incomplete_ou_invalide")
        try:
            actifs = {a["id"] for a in self._magasin.actifs()}
        except Exception:
            return BilanImmunite("inconnu", "stockage_immunite_indisponible")
        regles = [regle for regle in self._regles.values()
                  if (identifiant := self._magasin.empreinte(regle.detecteur)) in actifs
                  and self._validees.get(identifiant) == self._version_regle(regle)]
        if not regles:
            return BilanImmunite("non_verifie", "aucune_regle_validee_dans_cette_session")
        retour = _calculer_immunite([r.detecteur for r in regles], [observation.texte],
                                     limite=self._limite, delai=self._delai)
        if "erreur" in retour:
            return BilanImmunite("inconnu", retour["erreur"])
        candidats = tuple(CandidatImmunite(regles[n].nom, observation.cible, observation.version, debut, fin)
                          for n, debut, fin in retour["positions"])
        return BilanImmunite("partiel" if retour["partiel"] else "recherchee",
                            "correspondances_candidates_uniquement", candidats)

    def oublier(self, nom: str) -> bool:
        if type(nom) is not str or nom not in self._regles:
            return False
        identifiant = self._magasin.empreinte(self._regles[nom].detecteur)
        self._validees.pop(identifiant, None)
        try:
            return self._magasin.oublier(identifiant)
        except Exception:
            return False
