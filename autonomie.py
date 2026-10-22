"""Suivi local d'une tâche : plan, limites et fin vérifiée, sans réseau ni disque.

Les méthodes sont appelées par le harness de confiance. Le modèle ne décide pas
des permissions, du progrès réel, des contrôles ni des compteurs. Les signatures
gardées ici sont des empreintes ; aucun argument brut d'outil n'est mémorisé.
L'intégration à la boucle, l'annulation des processus et la persistance relèvent
des adaptateurs locaux. Ce module n'exécute aucun outil ni code produit par l'IA.
"""

from __future__ import annotations

import math
import json
import re
import time
from collections import Counter, deque
from dataclasses import dataclass, field, replace
from typing import Callable

from verification import (
    BilanImmunite, BilanVerification, ImmuniteControlee, Observation, RegistrePreuves, empreinte_configuration,
)


VERSION = "autonomie-locale-1"


@dataclass(frozen=True)
class Budgets:
    outils: int = 80
    requetes: int = 100
    secondes: float = 2400.0
    sans_progres: int = 5
    approches: int = 3
    revisions_plan: int = 20

    def __post_init__(self):
        for nom in ("outils", "requetes", "sans_progres", "approches", "revisions_plan"):
            valeur = getattr(self, nom)
            if type(valeur) is not int or valeur < 1:
                raise ValueError("Budget entier strictement positif requis.")
        if (type(self.secondes) not in (int, float)
                or not math.isfinite(self.secondes) or self.secondes <= 0):
            raise ValueError("Durée finie et strictement positive requise.")


@dataclass(frozen=True)
class Etape:
    identifiant: str
    action: str = field(repr=False)
    condition_fin: str = field(repr=False)
    statut: str = "a_faire"


@dataclass(frozen=True)
class Decision:
    autorisee: bool
    motif: str


@dataclass(frozen=True)
class _Appel:
    signature: str
    outil: str = field(repr=False)
    cible: str = field(repr=False)
    lecture_seule: bool


@dataclass(frozen=True)
class ControleLocal:
    """Critère et fonction déclarés par le moteur, jamais fournis par le modèle."""

    identifiant: str
    cible: str = field(repr=False)
    version: str
    verifier: Callable[[Observation], bool] = field(repr=False)


@dataclass(frozen=True)
class PhaseLocale:
    etape: Etape
    controles: tuple[ControleLocal, ...] = field(repr=False)


def _valider_plan(etapes: list[Etape]) -> None:
    if type(etapes) is not list or not 1 <= len(etapes) <= 32:
        raise ValueError("Plan de une à trente-deux étapes requis.")
    identifiants = set()
    for etape in etapes:
        if (type(etape) is not Etape or etape.statut != "a_faire"
                or any(type(v) is not str or not v.strip()
                       for v in (etape.identifiant, etape.action, etape.condition_fin))
                or etape.identifiant in identifiants):
            raise ValueError("Étape mal formée, dupliquée ou statut proposé interdit.")
        identifiants.add(etape.identifiant)


class Tache:
    """Une instance par tâche, utilisée séquentiellement par le harness.

    Les étapes intermédiaires ont leurs propres registres : constater le bug
    initial n'est pas le même critère que vérifier sa correction à la fin.
    Le registre final est fixé à la création et recontrôlé avant de conclure.
    Les autorisations de sécurité sont toujours décidées séparément par Claude.
    """

    def __init__(self, objectif: str, etapes: list[Etape], registre_fin: RegistrePreuves,
                 *, budgets: Budgets | None = None,
                 horloge: Callable[[], float] = time.monotonic,
                 annuler_processus: Callable[[], None] | None = None):
        _valider_plan(etapes)
        if type(objectif) is not str or not objectif.strip():
            raise ValueError("Objectif nécessaire.")
        if not isinstance(registre_fin, RegistrePreuves):
            raise ValueError("Registre final local nécessaire.")
        self._objectif = objectif
        self._etapes = {e.identifiant: e for e in etapes}
        self._registres: dict[str, RegistrePreuves] = {}
        self._registre_fin = registre_fin
        self._budgets = budgets if budgets is not None else Budgets()
        if type(self._budgets) is not Budgets:
            raise ValueError("Budgets invalides.")
        self._horloge = horloge
        self._debut = horloge()
        self._annuler_processus = annuler_processus
        self._active: str | None = None
        self._appel: _Appel | None = None
        self._statut = "active"
        self._motif = "travail_en_cours"
        self._outils = self._requetes = self._revisions = self._sans_progres = 0
        self._approches: Counter[str] = Counter()
        self._erreurs: Counter[str] = Counter()
        self._reprises: set[str] = set()
        self._mutations: set[str] = set()
        self._recentes: deque[str] = deque(maxlen=6)
        self._faits: set[str] = set()
        self._observations_consommees: set[str] = set()
        self._mutation_incertaine = False
        self._cible_incertaine: str | None = None

    @property
    def statut(self) -> str:
        return self._statut

    @property
    def motif(self) -> str:
        return self._motif

    @property
    def etapes(self) -> tuple[Etape, ...]:
        return tuple(self._etapes.values())

    def _arreter(self, statut: str, motif: str) -> None:
        if self._statut != "active":
            return
        self._statut, self._motif = statut, motif
        if self._active is not None:
            self._etapes[self._active] = replace(self._etapes[self._active], statut="bloquee")
        if self._appel is not None:
            if not self._appel.lecture_seule:
                self._mutation_incertaine = True
                self._cible_incertaine = self._appel.cible
            if self._annuler_processus is None:
                self._motif = "annulation_processus_non_confirmee"
            else:
                try:
                    self._annuler_processus()
                except Exception:
                    self._motif = "annulation_processus_non_confirmee"
            self._appel = None

    def continuer(self) -> Decision:
        """À consulter avant chaque requête, outil ou transition, et pendant l'attente."""
        if self._statut == "active" and self._horloge() - self._debut >= self._budgets.secondes:
            self._arreter("incomplete", "budget_duree")
        return Decision(self._statut == "active", self._motif)

    def lier_verification(self, identifiant: str, registre: RegistrePreuves) -> None:
        """Liaison locale avant le démarrage ; jamais un choix fourni par le modèle."""
        if (identifiant not in self._etapes or identifiant in self._registres
                or self._etapes[identifiant].statut != "a_faire"
                or not isinstance(registre, RegistrePreuves) or not self.continuer().autorisee):
            raise ValueError("Liaison de vérification interdite.")
        self._registres[identifiant] = registre

    def commencer_etape(self, identifiant: str) -> Decision:
        if not self.continuer().autorisee:
            return self.continuer()
        if self._active is not None or identifiant not in self._etapes:
            return Decision(False, "etape_active_ou_inconnue")
        if self._etapes[identifiant].statut != "a_faire" or identifiant not in self._registres:
            return Decision(False, "etape_non_prete")
        self._etapes[identifiant] = replace(self._etapes[identifiant], statut="en_cours")
        self._active = identifiant
        return Decision(True, "etape_commencee")

    def reviser_plan(self, propositions: list[Etape]) -> Decision:
        """Conserve les identifiants et conditions existants, ainsi que tous les compteurs."""
        if not self.continuer().autorisee:
            return self.continuer()
        _valider_plan(propositions)
        nouveau = {e.identifiant: e for e in propositions}
        if not self._etapes.keys() <= nouveau.keys():
            return Decision(False, "suppression_etape_interdite")
        for identifiant, ancienne in self._etapes.items():
            proposition = nouveau[identifiant]
            if proposition.condition_fin != ancienne.condition_fin:
                return Decision(False, "condition_fin_non_modifiable")
            if ancienne.statut != "a_faire" and proposition.action != ancienne.action:
                return Decision(False, "etape_commencee_non_modifiable")
            nouveau[identifiant] = replace(proposition, statut=ancienne.statut)
        if self._revisions >= self._budgets.revisions_plan:
            self._arreter("incomplete", "budget_revisions_plan")
            return self.continuer()
        self._revisions += 1
        self._etapes = nouveau
        # Changer le plan ne constitue pas un progrès.
        return Decision(True, "plan_revise")

    def avant_requete(self) -> Decision:
        """Compter chaque tentative, y compris les reprises réseau de la boucle."""
        if not self.continuer().autorisee:
            return self.continuer()
        if self._appel is not None:
            return Decision(False, "resultat_outil_attendu")
        if self._requetes >= self._budgets.requetes:
            self._arreter("incomplete", "budget_requetes")
            return self.continuer()
        self._requetes += 1
        return Decision(True, "requete_permise")

    def avant_outil(self, nom: str, arguments: dict, *, cible: str, lecture_seule: bool,
                    version_etat: str | None, reprise_transitoire: bool = False) -> Decision:
        """Autorisation de poursuite seulement, jamais une permission de sécurité.

        Classification et version viennent du harness, pas d'un argument du modèle.
        Une reprise identique nécessite une lecture et une panne transitoire
        reconnue localement ; elle n'est permise qu'une fois.
        """
        if not self.continuer().autorisee:
            return self.continuer()
        if self._appel is not None:
            return Decision(False, "resultat_outil_attendu")
        if self._active is None or self._etapes[self._active].statut != "en_cours":
            return Decision(False, "aucune_etape_en_cours")
        if (type(nom) is not str or not nom.strip() or type(arguments) is not dict
                or type(cible) is not str or not cible.strip()
                or type(lecture_seule) is not bool or type(reprise_transitoire) is not bool
                or (version_etat is not None and (type(version_etat) is not str or not version_etat))):
            raise ValueError("Appel local mal formé.")
        if not lecture_seule and (self._mutation_incertaine or version_etat is None):
            return Decision(False, "observer_avant_mutation")
        signature = empreinte_configuration({
            "outil": nom, "arguments": arguments, "cible": cible, "etat": version_etat,
        })
        erreurs = self._erreurs[signature]
        reprise = (lecture_seule and reprise_transitoire and erreurs == 1
                   and signature not in self._reprises)
        if erreurs and not reprise:
            return Decision(False, "echec_identique_non_rejouable")
        if self._recentes.count(signature) >= 2 and not reprise:
            self._arreter("incomplete", "cycle_actions")
            return self.continuer()
        if not lecture_seule and signature in self._mutations:
            return Decision(False, "mutation_identique_non_rejouable")
        if self._outils >= self._budgets.outils:
            self._arreter("incomplete", "budget_outils")
            return self.continuer()
        self._outils += 1
        if reprise:
            self._reprises.add(signature)
        if not lecture_seule:
            self._mutations.add(signature)
        self._recentes.append(signature)
        self._appel = _Appel(signature, nom, cible, lecture_seule)
        return Decision(True, "outil_permis")

    def recevoir_resultat(self, etat: str, *, observation: Observation | None = None,
                          progres_pertinent: bool = False) -> None:
        """Observation et pertinence décidées localement, pas par une phrase du modèle."""
        if self._statut != "active" or self._appel is None:
            raise ValueError("Aucun résultat d'outil attendu.")
        if (etat not in ("reussi", "echec", "incertain", "refuse")
                or type(progres_pertinent) is not bool
                or (observation is not None and not isinstance(observation, Observation))):
            raise ValueError("Résultat local mal formé.")
        appel, self._appel = self._appel, None
        if etat == "refuse":
            self._arreter("attente_utilisateur", "action_refusee")
            return
        if etat in ("echec", "incertain"):
            self._erreurs[appel.signature] += 1
            if not appel.lecture_seule:
                self._mutation_incertaine = True
                self._cible_incertaine = appel.cible
        observation_complete = (
            observation is not None and not observation.tronquee
            and observation.cible == appel.cible and observation.outil == appel.outil
            and observation.identifiant not in self._observations_consommees
            and observation.etat_execution == "reussi" and observation.version is not None
            and observation.code_sortie in (None, 0)
        )
        if observation is not None:
            self._observations_consommees.add(observation.identifiant)
        if (etat == "reussi" and appel.lecture_seule and observation_complete
                and observation.cible == self._cible_incertaine):
            self._mutation_incertaine = False
            self._cible_incertaine = None
        progres = False
        if etat == "reussi" and progres_pertinent and observation_complete:
            fait = empreinte_configuration({
                "cible": observation.cible, "version": observation.version,
                "contenu": observation.empreinte,
            })
            progres = fait not in self._faits
            self._faits.add(fait)
        self._sans_progres = 0 if progres else self._sans_progres + 1
        if self._sans_progres >= self._budgets.sans_progres:
            self._arreter("incomplete", "absence_progres")
        self.continuer()

    def approche_echouee(self, obstacle: str) -> Decision:
        """Identité stable d'obstacle choisie localement, indépendante du texte du plan."""
        if not self.continuer().autorisee:
            return self.continuer()
        if type(obstacle) is not str or not obstacle.strip():
            raise ValueError("Obstacle local nécessaire.")
        self._approches[obstacle] += 1
        if self._approches[obstacle] >= self._budgets.approches:
            self._arreter("incomplete", "approches_epuisees")
        return self.continuer()

    def verifier_etape(self, identifiant: str, propositions: object) -> BilanVerification:
        if (not self.continuer().autorisee or self._active != identifiant
                or self._appel is not None or self._mutation_incertaine):
            return BilanVerification("invalide", "verification_etape_interdite")
        self._etapes[identifiant] = replace(self._etapes[identifiant], statut="a_verifier")
        bilan = self._registres[identifiant].conclure(propositions)
        if not self.continuer().autorisee:
            return BilanVerification("inconnu", self._motif)
        if bilan.reussi:
            self._etapes[identifiant] = replace(self._etapes[identifiant], statut="verifiee")
            self._active = None
        else:
            # Autorise une correction ciblée, sans prétendre que l'étape est finie.
            self._etapes[identifiant] = replace(self._etapes[identifiant], statut="en_cours")
        return bilan

    def terminer(self, propositions: object) -> BilanVerification:
        """Recontrôler le registre final actuel, jamais un ancien bilan transmis par l'IA."""
        if (not self.continuer().autorisee or self._appel is not None or self._active is not None
                or any(e.statut != "verifiee" for e in self._etapes.values())
                or self._mutation_incertaine):
            return BilanVerification("invalide", "tache_non_prete")
        bilan = self._registre_fin.conclure(propositions)
        if not self.continuer().autorisee:
            return BilanVerification("inconnu", self._motif)
        if bilan.reussi:
            self._statut, self._motif = "terminee", "criteres_finaux_verifies"
        return bilan

    def reprendre_derniere_etape(self) -> Decision:
        """Rendre possible un nouveau contrôle final sans remettre les budgets à zéro."""
        if not self.continuer().autorisee:
            return self.continuer()
        if (self._active is not None or self._appel is not None
                or any(e.statut != "verifiee" for e in self._etapes.values())):
            return Decision(False, "reprise_finale_interdite")
        if self._revisions >= self._budgets.revisions_plan:
            self._arreter("incomplete", "budget_revisions_plan")
            return self.continuer()
        self._revisions += 1
        self._active = next(reversed(self._etapes))
        self._etapes[self._active] = replace(self._etapes[self._active], statut="en_cours")
        return Decision(True, "verification_finale_reprise")

    def annuler(self) -> None:
        """Stop immédiat des nouvelles actions ; l'adaptateur arrête ses processus."""
        self._arreter("annulee", "demande_arret")

    def vue_locale(self) -> dict:
        """État de travail local, pas une projection autorisée pour le cloud.

        Pas de restauration dans cette version. La persistance de Kimi devra
        conserver les compteurs et traiter les actions interrompues comme inconnues.
        """
        return {
            "objectif": self._objectif, "statut": self._statut, "motif": self._motif,
            "etapes": self.etapes, "outils": self._outils, "requetes": self._requetes,
            "revisions_plan": self._revisions, "sans_progres": self._sans_progres,
            "secondes": max(0.0, self._horloge() - self._debut),
            "mutation_incertaine": self._mutation_incertaine,
        }


class PiloteAutonomie:
    """Adaptateur local des transitions, versions et références de preuves.

    Ne fait aucun appel modèle ni outil. Le moteur conserve son dispatch et ses
    permissions, et doit respecter chaque Decision avant d'agir. Les phases,
    contrôles, versions et classifications sont issus du moteur de confiance.
    Tous les appels d'une instance sont séquentiels. Aucun retour n'est une
    projection autorisée vers le cloud : filtrage et minimisation restent requis.
    """

    def __init__(self, objectif: str, phases: list[PhaseLocale],
                 controles_fin: tuple[ControleLocal, ...], *, configuration: str,
                 lire_version: Callable[[str], str | None],
                 budgets: Budgets | None = None,
                 horloge: Callable[[], float] = time.monotonic,
                 annuler_processus: Callable[[], None] | None = None,
                 immunite: ImmuniteControlee | None = None):
        if (type(phases) is not list or not phases
                or any(type(p) is not PhaseLocale for p in phases)
                or not callable(lire_version)):
            raise ValueError("Phases locales et lecteur de version nécessaires.")
        self._lire_version = lire_version
        if immunite is not None and type(immunite) is not ImmuniteControlee:
            raise ValueError("Adaptateur local d'immunité requis.")
        self._immunite = immunite
        self._bilans_immunite: dict[str, BilanImmunite] = {}
        self._versions_immunite: dict[str, str | None] = {}
        self._phases = tuple(phases)
        self._position = 0
        self._attendu: tuple[str, str, bool] | None = None
        self._registres: dict[str, RegistrePreuves] = {}
        self._controles: dict[str, tuple[ControleLocal, ...]] = {}
        self._preuves: dict[str, dict] = {}
        # Le registre final n'utilise pas l'identifiant d'une étape.
        self._final = ""
        for identifiant, controles in [
                (p.etape.identifiant, p.controles) for p in phases] + [(self._final, controles_fin)]:
            if (type(controles) is not tuple or not controles
                    or any(type(c) is not ControleLocal for c in controles)
                    or identifiant in self._registres):
                raise ValueError("Contrôles locaux nécessaires et phases uniques.")
            registre = RegistrePreuves(configuration)
            for controle in controles:
                registre.ajouter_critere(
                    controle.identifiant, controle.cible, version_controle=controle.version,
                    verifier=controle.verifier,
                )
                registre.actualiser_cible(controle.cible, None)
            self._registres[identifiant] = registre
            self._controles[identifiant] = controles
            self._preuves[identifiant] = {}
        self.tache = Tache(objectif, [p.etape for p in phases], self._registres[self._final],
                           budgets=budgets, horloge=horloge, annuler_processus=annuler_processus)
        for phase in phases:
            self.tache.lier_verification(phase.etape.identifiant,
                                        self._registres[phase.etape.identifiant])
        decision = self.tache.commencer_etape(phases[0].etape.identifiant)
        if not decision.autorisee:
            raise ValueError("Démarrage du suivi impossible.")

    @property
    def etape_active(self) -> str | None:
        if self._position >= len(self._phases):
            return None
        return self._phases[self._position].etape.identifiant

    def _actualiser(self) -> dict[str, str | None] | None:
        cibles = {c.cible for controles in self._controles.values() for c in controles}
        try:
            versions = {cible: self._lire_version(cible) for cible in sorted(cibles)}
            if any(v is not None and (type(v) is not str or not v.strip())
                   for v in versions.values()):
                raise ValueError("Version locale invalide.")
        except Exception:
            # Invalider toutes les anciennes preuves si la lecture échoue.
            self._bilans_immunite.clear()
            self._versions_immunite.clear()
            for registre, controles in ((self._registres[i], cs)
                                        for i, cs in self._controles.items()):
                for controle in controles:
                    registre.actualiser_cible(controle.cible, None)
            return None
        for cible in tuple(self._bilans_immunite):
            if self._versions_immunite[cible] != versions.get(cible):
                del self._bilans_immunite[cible]
                del self._versions_immunite[cible]
        for identifiant, controles in self._controles.items():
            for controle in controles:
                self._registres[identifiant].actualiser_cible(
                    controle.cible, versions[controle.cible])
        return versions

    @property
    def candidats_immunite_locaux(self) -> tuple:
        """Positions locales candidates ; ni preuve de bug ni projection cloud."""
        return tuple(c for bilan in self._bilans_immunite.values() for c in bilan.candidats)

    def etat_immunite(self) -> dict:
        """Compteurs de la dernière observation, sans cible ni extrait ni règle."""
        return {"active": self._immunite is not None,
                "candidats": len(self.candidats_immunite_locaux),
                "observations": len(self._bilans_immunite),
                "incompletes": sum(b.statut in ("inconnu", "partiel", "non_verifie")
                                   for b in self._bilans_immunite.values())}

    def avant_requete(self) -> Decision:
        return self.tache.avant_requete()

    def actualiser_configuration(self, configuration: str) -> None:
        """Le moteur appelle ceci si le prompt, modèle ou contrôle configuré change."""
        for registre in self._registres.values():
            registre.actualiser_configuration(configuration)

    def avant_outil(self, nom: str, arguments: dict, *, cible: str,
                    lecture_seule: bool, permission: Decision,
                    reprise_transitoire: bool = False) -> Decision:
        """Permission du moteur requise, avant de compter et réserver l'action."""
        if type(permission) is not Decision:
            raise ValueError("Décision locale de permission nécessaire.")
        decision = self.tache.continuer()
        if not decision.autorisee:
            return decision
        if not permission.autorisee:
            self.tache._arreter("attente_utilisateur", "action_refusee")
            return Decision(False, "action_refusee")
        if self._attendu is not None:
            return Decision(False, "resultat_outil_attendu")
        versions = self._actualiser()
        if versions is None:
            return Decision(False, "versions_indisponibles")
        if cible not in versions:
            return Decision(False, "cible_hors_plan")
        decision = self.tache.avant_outil(
            nom, arguments, cible=cible, lecture_seule=lecture_seule,
            version_etat=versions[cible], reprise_transitoire=reprise_transitoire,
        )
        if decision.autorisee:
            self._attendu = (nom, cible, lecture_seule)
        return decision

    def recevoir_resultat(self, etat: str, *, texte: str, tronquee: bool = False,
                          code_sortie: int | None = None,
                          progres_pertinent: bool = False) -> None:
        """Enregistrer le retour réel avant toute troncature ou résumé pour le modèle."""
        if self._attendu is None or not self.tache.continuer().autorisee:
            raise ValueError("Aucun résultat actif attendu.")
        if (etat not in ("reussi", "echec", "incertain", "refuse")
                or type(texte) is not str or type(tronquee) is not bool
                or type(progres_pertinent) is not bool
                or (code_sortie is not None and type(code_sortie) is not int)):
            raise ValueError("Retour local invalide.")
        nom, cible, lecture = self._attendu
        if etat == "reussi" and code_sortie not in (None, 0):
            etat = "echec"
        versions = self._actualiser()
        version = versions[cible] if versions is not None else None
        observation_active = None
        # Une écriture n'est pas une preuve de son effet : seule sa relecture
        # ou un test indépendant peut alimenter les critères de réussite.
        for identifiant in (self.etape_active, self._final):
            controles = self._controles[identifiant]
            if identifiant != self.etape_active and not any(c.cible == cible for c in controles):
                continue
            registre = self._registres[identifiant]
            registre.actualiser_cible(cible, version)
            observation = registre.enregistrer(
                outil=nom, cible=cible, version=version, texte=texte,
                etat_execution={"reussi": "reussi", "echec": "echec"}.get(etat, "inconnu"),
                tronquee=tronquee, code_sortie=code_sortie,
            )
            if identifiant == self.etape_active:
                observation_active = observation
            lignes = [(n, ligne) for n, ligne in enumerate(texte.splitlines(), 1) if ligne.strip()]
            for controle in controles:
                if controle.cible != cible:
                    continue
                self._preuves[identifiant].pop(controle.identifiant, None)
                if lecture and lignes:
                    numero, ligne = lignes[0]
                    self._preuves[identifiant][controle.identifiant] = [{
                        "observation": observation.identifiant, "ligne": numero, "citation": ligne,
                    }]
        if self._immunite is not None and lecture and etat == "reussi":
            self._bilans_immunite[cible] = self._immunite.reperer(observation_active)
            self._versions_immunite[cible] = version
        self.tache.recevoir_resultat(
            etat, observation=observation_active,
            progres_pertinent=progres_pertinent and lecture,
        )
        self._attendu = None

    def verifier_etape(self) -> BilanVerification:
        if not self.tache.continuer().autorisee:
            return BilanVerification("inconnu", self.tache.motif)
        identifiant = self.etape_active
        if identifiant is None or self._actualiser() is None:
            return BilanVerification("inconnu", "etape_absente_ou_versions_indisponibles")
        bilan = self.tache.verifier_etape(identifiant, self._preuves[identifiant])
        if bilan.reussi:
            self._position += 1
            if self.etape_active is not None:
                self.tache.commencer_etape(self.etape_active)
        return bilan

    def terminer(self) -> BilanVerification:
        if not self.tache.continuer().autorisee:
            return BilanVerification("inconnu", self.tache.motif)
        if self._actualiser() is None:
            return BilanVerification("inconnu", "versions_indisponibles")
        return self.tache.terminer(self._preuves[self._final])

    def reprendre_verification_finale(self) -> Decision:
        decision = self.tache.reprendre_derniere_etape()
        if decision.autorisee:
            self._position = len(self._phases) - 1
        return decision

    def annuler(self) -> None:
        self.tache.annuler()
        self._attendu = None


class CapaciteAutonomie:
    """Outils optionnels pour la table OUTILS du moteur.

    Une instance par demande utilisateur ; profils publics fournis localement.
    Une fabrique prépare un pilote pour cette demande, sans exécuter d'action.
    Le moteur ne doit exposer ces outils qu'une fois les hooks du pilote branchés
    aux véritables appels. Aucun contrôle, cible ou droit n'est choisi par l'IA.
    Ne jamais retirer un pilote arrêté pour continuer en boucle libre sur la même
    demande : un refus ou un budget atteint reste applicable jusqu'à l'utilisateur.
    """

    def __init__(self, profils: dict[str, Callable[[], PiloteAutonomie]]):
        if (type(profils) is not dict or len(profils) > 32
                or any(type(nom) is not str or re.fullmatch(r"[a-z][a-z0-9_]{0,47}", nom) is None
                       or not callable(fabrique) for nom, fabrique in profils.items())):
            raise ValueError("Profils locaux publics invalides.")
        self._profils = dict(profils)
        self._pilote: PiloteAutonomie | None = None
        self._demarrage_tente = False

    @property
    def pilote_local(self) -> PiloteAutonomie | None:
        """Accès réservé au moteur pour ses hooks, jamais un outil du modèle."""
        return self._pilote

    def etat(self) -> str:
        """État sans objectif, action, cible, citation ou contenu d'observation."""
        if self._pilote is None:
            return json.dumps({"statut": "indisponible" if self._demarrage_tente else "inactif"})
        tache = self._pilote.tache
        tache.continuer()
        vue = tache.vue_locale()
        return json.dumps({
            "statut": tache.statut, "motif": tache.motif,
            "etapes": [{"numero": n, "statut": e.statut}
                       for n, e in enumerate(tache.etapes, 1)],
            "outils": vue["outils"], "requetes": vue["requetes"],
            "mutation_incertaine": vue["mutation_incertaine"],
            "immunite": self._pilote.etat_immunite(),
        }, ensure_ascii=False)

    def demarrer(self, profil: str) -> str:
        if self._demarrage_tente:
            return json.dumps({"erreur": "demarrage_deja_tente", "etat": json.loads(self.etat())},
                              ensure_ascii=False)
        if type(profil) is not str or profil not in self._profils:
            return json.dumps({"erreur": "profil_inconnu"})
        # Une fabrique en erreur ne doit pas être appelée en boucle par le modèle.
        self._demarrage_tente = True
        try:
            pilote = self._profils[profil]()
            if type(pilote) is not PiloteAutonomie:
                raise ValueError("Pilote local attendu.")
        except Exception:
            return json.dumps({"erreur": "preparation_indisponible"})
        self._pilote = pilote
        return self.etat()

    def _verifier(self, operation: str) -> str:
        if self._pilote is None:
            return json.dumps({"erreur": "aucun_suivi"})
        try:
            bilan = (self._pilote.verifier_etape() if operation == "etape"
                     else self._pilote.terminer())
        except Exception:
            # Ne jamais exporter une exception pouvant nommer une cible privée.
            return json.dumps({"erreur": "verification_indisponible"})
        return json.dumps({"verification": bilan.statut, "motif": bilan.motif,
                           "reussi": bilan.reussi, "etat": json.loads(self.etat())},
                          ensure_ascii=False)

    def verifier_etape(self) -> str:
        return self._verifier("etape")

    def terminer(self) -> str:
        return self._verifier("fin")

    def reprendre_verification(self) -> str:
        if self._pilote is None:
            return json.dumps({"erreur": "aucun_suivi"})
        decision = self._pilote.reprendre_verification_finale()
        return json.dumps({"autorisee": decision.autorisee, "motif": decision.motif,
                           "etat": json.loads(self.etat())}, ensure_ascii=False)

    def arreter(self) -> str:
        if self._pilote is None:
            return json.dumps({"erreur": "aucun_suivi"})
        self._pilote.annuler()
        return self.etat()

    def outils(self) -> dict:
        """Schémas compatibles avec OUTILS ; aucun outil si aucun profil local."""
        if not self._profils:
            return {}
        descriptions = {
            "autonomie_demarrer": (self.demarrer,
                "Activer un profil local de suivi pour la demande en cours. Optionnel pour une grosse tâche. "
                "Les contrôles et permissions sont définis par le moteur. Aucun redémarrage du budget."),
            "autonomie_etat": (self.etat, "Consulter étapes numérotées, compteurs et incertitudes du suivi optionnel."),
            "autonomie_verifier_etape": (self.verifier_etape,
                "Demander le contrôle local de l'étape courante et avancer seulement si elle est vérifiée."),
            "autonomie_terminer": (self.terminer,
                "Recontrôler tous les critères finaux. Seul reussi=true autorise une conclusion vérifiée."),
            "autonomie_reprendre_verification": (self.reprendre_verification,
                "Rouvrir le dernier contrôle après une preuve périmée, sans réinitialiser les budgets."),
            "autonomie_arreter": (self.arreter,
                "Arrêter le suivi et ses actions. Aucun retour à la boucle libre sur la même demande sans l'utilisateur."),
        }
        outils = {}
        for nom, (fonction, description) in descriptions.items():
            parametres = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
            if nom == "autonomie_demarrer":
                parametres["properties"]["profil"] = {"type": "string", "enum": sorted(self._profils)}
                parametres["required"] = ["profil"]
            outils[nom] = {"fn": fonction, "risque": "sûr", "schema": {
                "description": description, "parameters": parametres,
            }}
        return outils


class ProfilTestsPython:
    """Premier profil optionnel : valider une suite unittest connue du moteur.

    Les modules, le contexte d'exécution et leurs versions sont locaux et de
    confiance. Aucun argument du modèle ne choisit le programme ou le dossier.
    Cette classe ne lance aucun processus ; elle entoure le dispatch terminal.
    """

    CIBLE = "suite_python"

    def __init__(self, modules: tuple[str, ...], *, nombre_minimum: int,
                 lire_version: Callable[[str], str | None],
                 contexte_valide: Callable[[], bool], configuration: str,
                 budgets: Budgets | None = None,
                 horloge: Callable[[], float] = time.monotonic,
                 annuler_processus: Callable[[], None] | None = None,
                 immunite: ImmuniteControlee | None = None):
        if (type(modules) is not tuple or not 1 <= len(modules) <= 32
                or any(type(m) is not str or re.fullmatch(r"test_[a-z0-9_]+", m) is None for m in modules)
                or len(set(modules)) != len(modules)
                or type(nombre_minimum) is not int or nombre_minimum < 1
                or not callable(lire_version) or not callable(contexte_valide)):
            raise ValueError("Suite locale et contexte de confiance nécessaires.")
        self.commande = "python3 -B -m unittest " + " ".join(modules)
        self._minimum = nombre_minimum
        self._lire_version = lire_version
        self._contexte_valide = contexte_valide
        self._configuration = configuration
        self._budgets = budgets
        self._horloge = horloge
        self._annuler_processus = annuler_processus
        self._immunite = immunite
        self._pilote: PiloteAutonomie | None = None
        self._version_execution: str | None = None
        self._attendu = False
        self._capacite: CapaciteAutonomie | None = None

    def creer_capacite(self) -> tuple[CapaciteAutonomie, dict]:
        """Capacité stable et schémas indiquant la seule commande publique permise."""
        if self._capacite is None:
            self._capacite = CapaciteAutonomie({"tests_python": self.preparer})
        outils = self._capacite.outils()
        outils["autonomie_demarrer"]["schema"]["description"] += (
            " Le profil tests_python accepte uniquement l'outil terminal avec commande="
            + json.dumps(self.commande) + ".")
        return self._capacite, outils


    def _controle(self, observation: Observation) -> bool:
        if (observation.outil != "terminal" or observation.code_sortie != 0
                or observation.version != self._version_execution):
            return False
        # Rapport final exact de unittest, pas un mot OK rencontré dans une page.
        resultat = re.search(r"\nRan ([0-9]+) tests? in [0-9.]+s\n\nOK\s*\Z", observation.texte)
        return resultat is not None and int(resultat.group(1)) >= self._minimum

    def preparer(self) -> PiloteAutonomie:
        if self._pilote is not None:
            raise ValueError("Profil déjà préparé pour cette demande.")
        controle = ControleLocal("suite_reussie", self.CIBLE, "unittest-v1", self._controle)
        self._pilote = PiloteAutonomie(
            "Valider la suite Python locale", [PhaseLocale(
                Etape("valider", "Exécuter les tests prévus", "Rapport complet, assez de tests, code zéro"),
                (controle,))], (controle,), configuration=self._configuration,
            lire_version=self._lire_version, budgets=self._budgets, horloge=self._horloge,
            annuler_processus=self._annuler_processus, immunite=self._immunite,
        )
        return self._pilote

    def avant_outil(self, nom: str, arguments: dict, *, permission: Decision) -> Decision:
        if self._pilote is None:
            return Decision(False, "profil_non_prepare")
        if type(nom) is not str or nom != "terminal" or arguments != {"commande": self.commande}:
            return Decision(False, "commande_hors_profil")
        if self._attendu:
            return Decision(False, "resultat_outil_attendu")
        poursuite = self._pilote.tache.continuer()
        if not poursuite.autorisee:
            return poursuite
        if type(permission) is not Decision:
            raise ValueError("Permission locale nécessaire.")
        if not permission.autorisee:
            return self._pilote.avant_outil(nom, arguments, cible=self.CIBLE,
                                            lecture_seule=True, permission=permission)
        try:
            if self._contexte_valide() is not True:
                return Decision(False, "contexte_execution_incorrect")
            version = self._lire_version(self.CIBLE)
            if type(version) is not str or not version.strip():
                return Decision(False, "versions_indisponibles")
        except Exception:
            return Decision(False, "contexte_execution_indisponible")
        decision = self._pilote.avant_outil(nom, arguments, cible=self.CIBLE,
                                           lecture_seule=True, permission=permission)
        if decision.autorisee:
            self._version_execution = version
            self._attendu = True
        return decision

    def recevoir_resultat(self, texte: str, *, tronquee: bool = False) -> None:
        """Retour terminal réel du moteur au format `[code N]`, jamais un argument IA."""
        if not self._attendu or self._pilote is None:
            raise ValueError("Aucun résultat de suite attendu.")
        if not self._pilote.tache.continuer().autorisee:
            raise ValueError("Résultat après arrêt du suivi.")
        if type(texte) is not str or type(tronquee) is not bool:
            raise ValueError("Résultat de suite invalide.")
        correspondance = re.match(r"\A\[code (-?[0-9]+)\]\n", texte)
        code = int(correspondance.group(1)) if correspondance else None
        etat = "reussi" if code == 0 else "echec"
        if code is None:
            etat = "incertain"
        try:
            if (self._contexte_valide() is not True
                    or self._lire_version(self.CIBLE) != self._version_execution):
                etat = "incertain"
        except Exception:
            etat = "incertain"
        self._pilote.recevoir_resultat(etat, texte=texte, tronquee=tronquee,
                                       code_sortie=code, progres_pertinent=etat == "reussi")
        self._attendu = False


def empreinte_suite_python(dossier) -> str | None:
    """Empreinte locale explicite des fichiers Python directs d'un projet.

    Aucun contenu, chemin ou détail d'erreur n'est exporté. Le moteur doit fournir
    le dossier de confiance et inclure les dépendances/configurations externes
    dans sa propre version. Ne pas modifier les fichiers pendant la capture.
    """
    from pathlib import Path
    import hashlib
    import stat

    def identite(fichier):
        etat = fichier.lstat()
        if not stat.S_ISREG(etat.st_mode) or etat.st_size > 2_000_000:
            raise ValueError("Fichier Python non admissible.")
        return (etat.st_dev, etat.st_ino, etat.st_mode, etat.st_size,
                etat.st_mtime_ns, etat.st_ctime_ns)

    try:
        chemin = Path(dossier)
        fichiers = sorted(chemin.glob("*.py"))
        if not chemin.is_dir() or not 1 <= len(fichiers) <= 128:
            return None
        identites = {fichier: identite(fichier) for fichier in fichiers}
        empreintes = {}
        for fichier in fichiers:
            avant = identites[fichier]
            contenu = fichier.read_bytes()
            if avant != identite(fichier) or len(contenu) != avant[3]:
                return None
            empreintes[fichier.name] = [
                hashlib.sha256(contenu).hexdigest(), avant[3], avant[4],
            ]
        # Recontrôler aussi les fichiers déjà lus et la liste entière : un
        # contrôle fichier par fichier peut produire une vue qui n'a jamais existé.
        if (sorted(chemin.glob("*.py")) != fichiers
                or any(identite(fichier) != identites[fichier] for fichier in fichiers)):
            return None
        return empreinte_configuration(empreintes)
    except (OSError, ValueError, TypeError):
        return None
