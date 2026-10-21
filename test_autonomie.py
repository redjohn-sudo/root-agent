"""Tâches simulées : aucun modèle, navigateur, processus ou service externe."""

import socket
import json
import subprocess
import sys
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from autonomie import Budgets, CapaciteAutonomie, ControleLocal, Decision, Etape, PhaseLocale, PiloteAutonomie, ProfilTestsPython, Tache, empreinte_suite_python
from verification import ImmuniteControlee, RegistrePreuves, RegleImmunitaire, empreinte_texte, _calculer_immunite


class AutonomieLocale(unittest.TestCase):
    def setUp(self):
        for objet, nom in [(socket, "getaddrinfo"), (socket, "create_connection"),
                           (socket.socket, "connect"), (socket.socket, "connect_ex")]:
            garde = patch.object(objet, nom, side_effect=AssertionError("Réseau interdit"))
            garde.start()
            self.addCleanup(garde.stop)
        self.temps = 0.0
        self.registre = RegistrePreuves("configuration-v1")
        self.registre.actualiser_cible("cible-synthetique", "v1")
        self.registre.ajouter_critere(
            "resultat", "cible-synthetique", version_controle="controle-v1",
            verifier=lambda observation: observation.texte == "résultat attendu",
        )
        self.tache = self.creer_tache()

    def creer_tache(self, budgets=None, annuler=None):
        tache = Tache("Objectif synthétique", [Etape("verification", "Vérifier", "Résultat attendu")],
                      self.registre, budgets=budgets, horloge=lambda: self.temps,
                      annuler_processus=annuler)
        tache.lier_verification("verification", self.registre)
        self.assertTrue(tache.commencer_etape("verification").autorisee)
        return tache

    def avant(self, *, tache=None, nom="lire", arguments=None, lecture=True,
              version="v1", reprise=False, cible="cible-synthetique"):
        return (tache or self.tache).avant_outil(
            nom, arguments if arguments is not None else {}, cible=cible,
            lecture_seule=lecture, version_etat=version, reprise_transitoire=reprise,
        )

    def observation(self, texte="résultat attendu", nom="lire", cible="cible-synthetique", **options):
        return self.registre.enregistrer(outil=nom, cible=cible, version="v1", texte=texte, **options)

    @staticmethod
    def preuves(observation):
        return {"resultat": [{"observation": observation.identifiant, "ligne": 1,
                              "citation": observation.texte}]}

    def test_parcours_complet_et_arret_des_actions_apres_succes(self):
        self.assertTrue(self.tache.avant_requete().autorisee)
        self.assertTrue(self.avant().autorisee)
        observation = self.observation()
        self.tache.recevoir_resultat("reussi", observation=observation, progres_pertinent=True)
        preuves = self.preuves(observation)
        self.assertTrue(self.tache.verifier_etape("verification", preuves).reussi)
        self.assertTrue(self.tache.terminer(preuves).reussi)
        self.assertEqual(self.tache.statut, "terminee")
        self.assertFalse(self.tache.avant_requete().autorisee)
        self.assertFalse(self.avant().autorisee)

    def test_texte_fini_ne_peut_pas_terminer(self):
        self.assertFalse(self.tache.terminer("fini").reussi)
        self.assertFalse(self.tache.verifier_etape("verification", {"statut": "verifie"}).reussi)
        self.assertEqual(self.tache.etapes[0].statut, "en_cours")

    def test_un_seul_outil_en_attente(self):
        self.assertTrue(self.avant().autorisee)
        self.assertEqual(self.avant(nom="autre").motif, "resultat_outil_attendu")
        self.assertFalse(self.tache.avant_requete().autorisee)

    def test_deux_etapes_ne_peuvent_pas_etre_actives(self):
        self.tache.reviser_plan([Etape("verification", "Vérifier", "Résultat attendu"),
                                 Etape("seconde", "Autre contrôle", "Autre résultat")])
        self.tache.lier_verification("seconde", self.registre)
        self.assertFalse(self.tache.commencer_etape("seconde").autorisee)

    def test_verification_obligatoire_avant_etape_suivante(self):
        self.assertFalse(self.tache.commencer_etape("verification").autorisee)
        self.assertTrue(self.avant().autorisee)
        observation = self.observation("mauvais résultat")
        self.tache.recevoir_resultat("reussi", observation=observation)
        self.assertFalse(self.tache.verifier_etape("verification", self.preuves(observation)).reussi)
        self.assertFalse(self.tache.terminer(self.preuves(observation)).reussi)

    def test_modification_apres_etape_verifiee_bloque_fin(self):
        observation = self.observation()
        preuves = self.preuves(observation)
        self.assertTrue(self.tache.verifier_etape("verification", preuves).reussi)
        self.registre.actualiser_cible("cible-synthetique", "v2")
        self.assertFalse(self.tache.terminer(preuves).reussi)

    def test_budget_requetes_inclut_toutes_les_tentatives(self):
        tache = self.creer_tache(Budgets(requetes=2))
        self.assertTrue(tache.avant_requete().autorisee)
        self.assertTrue(tache.avant_requete().autorisee)
        self.assertFalse(tache.avant_requete().autorisee)
        self.assertEqual(tache.motif, "budget_requetes")

    def test_derniere_action_autorisee_permet_encore_la_verification(self):
        tache = self.creer_tache(Budgets(outils=1, requetes=1))
        self.assertTrue(tache.avant_requete().autorisee)
        self.assertTrue(self.avant(tache=tache).autorisee)
        observation = self.observation()
        tache.recevoir_resultat("reussi", observation=observation, progres_pertinent=True)
        preuves = self.preuves(observation)
        self.assertTrue(tache.verifier_etape("verification", preuves).reussi)
        self.assertTrue(tache.terminer(preuves).reussi)

    def test_budget_outils_bloque_avant_execution_supplementaire(self):
        tache = self.creer_tache(Budgets(outils=1))
        self.avant(tache=tache)
        tache.recevoir_resultat("reussi")
        self.assertFalse(self.avant(tache=tache, nom="autre").autorisee)
        self.assertEqual(tache.vue_locale()["outils"], 1)
        self.assertEqual(tache.motif, "budget_outils")

    def test_budget_duree_inclut_attente_et_annule_processus(self):
        annulations = []
        tache = self.creer_tache(Budgets(secondes=5), annuler=lambda: annulations.append(True))
        self.avant(tache=tache, lecture=False)
        self.temps = 5.0
        self.assertFalse(tache.continuer().autorisee)
        self.assertEqual(tache.motif, "budget_duree")
        self.assertEqual(annulations, [True])
        self.assertTrue(tache.vue_locale()["mutation_incertaine"])
        tache.annuler()
        self.assertEqual(annulations, [True])

    def registre_lent(self):
        registre = RegistrePreuves("configuration-lente")
        registre.actualiser_cible("cible-synthetique", "v1")

        def controler(observation):
            # Simule le temps consommé par un contrôle, sans attente réelle.
            self.temps = 5.0
            return observation.texte == "résultat attendu"

        registre.ajouter_critere("resultat", "cible-synthetique", version_controle="v1", verifier=controler)
        return registre

    def test_budget_expire_pendant_verification_etape_ne_donne_pas_succes(self):
        registre = self.registre_lent()
        tache = Tache("Objectif", [Etape("etape", "Vérifier", "Résultat attendu")], registre,
                      budgets=Budgets(secondes=5), horloge=lambda: self.temps)
        tache.lier_verification("etape", registre)
        tache.commencer_etape("etape")
        observation = registre.enregistrer(outil="test", cible="cible-synthetique", version="v1",
                                           texte="résultat attendu")
        bilan = tache.verifier_etape("etape", self.preuves(observation))
        self.assertFalse(bilan.reussi)
        self.assertEqual((tache.statut, tache.motif), ("incomplete", "budget_duree"))
        self.assertEqual(tache.etapes[0].statut, "bloquee")

    def test_budget_expire_pendant_verification_finale_ne_termine_pas(self):
        registre_final = self.registre_lent()
        tache = Tache("Objectif", [Etape("etape", "Vérifier", "Résultat attendu")], registre_final,
                      budgets=Budgets(secondes=5), horloge=lambda: self.temps)
        tache.lier_verification("etape", self.registre)
        tache.commencer_etape("etape")
        observation = self.observation()
        self.assertTrue(tache.verifier_etape("etape", self.preuves(observation)).reussi)
        finale = registre_final.enregistrer(outil="test", cible="cible-synthetique", version="v1",
                                            texte="résultat attendu")
        bilan = tache.terminer(self.preuves(finale))
        self.assertFalse(bilan.reussi)
        self.assertEqual((tache.statut, tache.motif), ("incomplete", "budget_duree"))

    def test_stop_sans_annulation_confirmable_est_signale(self):
        self.avant(lecture=False)
        self.tache.annuler()
        self.assertEqual(self.tache.statut, "annulee")
        self.assertEqual(self.tache.motif, "annulation_processus_non_confirmee")
        self.assertFalse(self.avant().autorisee)

    def test_erreur_annulation_sans_fuite_de_message(self):
        def echouer():
            raise RuntimeError("MARQUEUR_PRIVE_FICTIF")
        tache = self.creer_tache(annuler=echouer)
        self.avant(tache=tache)
        tache.annuler()
        self.assertNotIn("MARQUEUR_PRIVE_FICTIF", repr(tache.vue_locale()))
        self.assertEqual(tache.motif, "annulation_processus_non_confirmee")

    def test_absence_progres_ne_devient_pas_un_succes(self):
        for numero in range(3):
            self.assertTrue(self.avant(arguments={"essai": numero}).autorisee)
            self.tache.recevoir_resultat("reussi")
        self.assertEqual(self.tache.statut, "incomplete")
        self.assertEqual(self.tache.motif, "absence_progres")

    def test_meme_fait_avec_nouvel_identifiant_ne_recompte_pas(self):
        for numero in range(3):
            self.avant(arguments={"essai": numero})
            observation = self.observation()
            self.tache.recevoir_resultat("reussi", observation=observation, progres_pertinent=True)
        self.assertEqual(self.tache.vue_locale()["sans_progres"], 2)

    def test_observation_tronquee_ne_compte_pas_comme_progres(self):
        self.avant()
        self.tache.recevoir_resultat("reussi", observation=self.observation(tronquee=True), progres_pertinent=True)
        self.assertEqual(self.tache.vue_locale()["sans_progres"], 1)

    def test_reprise_transitoire_lecture_permise_une_seule_fois(self):
        self.avant()
        self.tache.recevoir_resultat("echec")
        self.assertFalse(self.avant().autorisee)
        self.assertTrue(self.avant(reprise=True).autorisee)
        self.tache.recevoir_resultat("reussi", observation=self.observation(), progres_pertinent=True)
        self.assertFalse(self.avant(reprise=True).autorisee)

    def test_mutation_incertaine_exige_observation_meme_cible(self):
        self.avant(nom="ecrire", lecture=False)
        self.tache.recevoir_resultat("incertain")
        self.assertEqual(self.avant(nom="corriger", lecture=False).motif, "observer_avant_mutation")
        self.registre.actualiser_cible("autre-cible", "v1")
        self.avant(cible="autre-cible")
        observation = self.observation(cible="autre-cible")
        self.tache.recevoir_resultat("reussi", observation=observation, progres_pertinent=True)
        self.assertFalse(self.avant(nom="corriger", lecture=False).autorisee)
        self.avant()
        self.tache.recevoir_resultat("reussi", observation=self.observation(), progres_pertinent=True)
        self.assertTrue(self.avant(nom="corriger", lecture=False).autorisee)

    def test_mutation_sans_version_cible_refusee(self):
        self.assertEqual(self.avant(lecture=False, version=None).motif, "observer_avant_mutation")

    def test_mutation_incertaine_ne_clot_pas_etape_et_permet_relecture(self):
        self.assertTrue(self.avant().autorisee)
        ancienne = self.observation()
        self.tache.recevoir_resultat("reussi", observation=ancienne, progres_pertinent=True)
        self.assertTrue(self.avant(nom="ecrire", lecture=False).autorisee)
        self.tache.recevoir_resultat("incertain")
        bilan = self.tache.verifier_etape("verification", self.preuves(ancienne))
        self.assertFalse(bilan.reussi)
        self.assertEqual(self.tache.etapes[0].statut, "en_cours")
        # Garder l'étape active permet d'observer et de sortir de l'incertitude.
        self.assertTrue(self.avant(nom="relire").autorisee)
        actuelle = self.observation(nom="relire")
        self.tache.recevoir_resultat("reussi", observation=actuelle, progres_pertinent=True)
        self.assertFalse(self.tache.vue_locale()["mutation_incertaine"])
        preuves = self.preuves(actuelle)
        self.assertTrue(self.tache.verifier_etape("verification", preuves).reussi)
        self.assertTrue(self.tache.terminer(preuves).reussi)

    def test_ancienne_observation_ne_leve_pas_incertitude(self):
        self.avant()
        ancienne = self.observation()
        self.tache.recevoir_resultat("reussi", observation=ancienne, progres_pertinent=True)
        self.avant(nom="ecrire", lecture=False)
        self.tache.recevoir_resultat("incertain")
        self.avant()
        self.tache.recevoir_resultat("reussi", observation=ancienne, progres_pertinent=True)
        self.assertTrue(self.tache.vue_locale()["mutation_incertaine"])

    def test_observation_autre_outil_ne_prouve_pas_progres(self):
        self.avant(nom="lire")
        self.tache.recevoir_resultat("reussi", observation=self.observation(nom="autre"), progres_pertinent=True)
        self.assertEqual(self.tache.vue_locale()["sans_progres"], 1)

    def test_mutation_identique_non_rejouee(self):
        self.avant(nom="ecrire", lecture=False)
        self.tache.recevoir_resultat("reussi", observation=self.observation(nom="ecrire"), progres_pertinent=True)
        self.assertEqual(self.avant(nom="ecrire", lecture=False).motif, "mutation_identique_non_rejouable")

    def test_refus_ne_peut_pas_etre_contourne(self):
        self.avant(nom="ecrire", lecture=False)
        self.tache.recevoir_resultat("refuse")
        self.assertEqual(self.tache.statut, "attente_utilisateur")
        self.assertFalse(self.avant(nom="terminal").autorisee)

    def test_cycle_de_deux_outils_detecte(self):
        tache = self.creer_tache(Budgets(sans_progres=10))
        for nom in ["a", "b", "a", "b"]:
            self.assertTrue(self.avant(tache=tache, nom=nom).autorisee)
            tache.recevoir_resultat("reussi")
        self.assertFalse(self.avant(tache=tache, nom="a").autorisee)
        self.assertEqual(tache.motif, "cycle_actions")

    def test_deux_approches_echouees_arretent(self):
        self.assertTrue(self.tache.approche_echouee("obstacle-stable").autorisee)
        self.assertFalse(self.tache.approche_echouee("obstacle-stable").autorisee)
        self.assertEqual(self.tache.motif, "approches_epuisees")

    def test_reviser_plan_ne_reinitialise_pas_budget(self):
        self.tache.avant_requete()
        self.avant()
        self.tache.recevoir_resultat("reussi")
        decision = self.tache.reviser_plan([Etape("verification", "Vérifier", "Résultat attendu")])
        self.assertTrue(decision.autorisee)
        vue = self.tache.vue_locale()
        self.assertEqual((vue["outils"], vue["requetes"], vue["sans_progres"]), (1, 1, 1))

    def test_plan_ne_peut_pas_supprimer_etape_ni_affaiblir_condition(self):
        self.assertFalse(self.tache.reviser_plan([Etape("autre", "Autre", "Autre")]).autorisee)
        self.assertFalse(self.tache.reviser_plan([Etape("verification", "Vérifier", "OK suffit")]).autorisee)
        with self.assertRaises(ValueError):
            self.tache.reviser_plan([Etape("verification", "Vérifier", "Résultat attendu", "verifiee")])

    def test_revisions_plan_bornees(self):
        tache = self.creer_tache(Budgets(revisions_plan=1))
        plan = [Etape("verification", "Vérifier", "Résultat attendu")]
        self.assertTrue(tache.reviser_plan(plan).autorisee)
        self.assertFalse(tache.reviser_plan(plan).autorisee)
        self.assertEqual(tache.motif, "budget_revisions_plan")

    def test_plan_sans_controle_local_ne_demarre_pas(self):
        tache = Tache("Objectif", [Etape("a", "Action", "Condition")], self.registre)
        self.assertEqual(tache.commencer_etape("a").motif, "etape_non_prete")

    def test_budgets_mal_formes_refuses(self):
        for options in [{"outils": True}, {"requetes": 0}, {"secondes": float("nan")}, {"secondes": -1}]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                Budgets(**options)

    def test_resultat_tardif_apres_stop_refuse(self):
        self.avant()
        self.tache.annuler()
        with self.assertRaises(ValueError):
            self.tache.recevoir_resultat("reussi")

    def test_registres_intermediaires_distincts_du_resultat_final(self):
        initial = RegistrePreuves("configuration-v1")
        initial.actualiser_cible("cas-initial", "avant")
        initial.ajouter_critere("bug-reproduit", "cas-initial", version_controle="v1",
                               verifier=lambda o: o.texte == "bug reproduit")
        tache = Tache("Corriger", [Etape("reproduire", "Reproduire", "Symptôme observé"),
                                  Etape("corriger", "Corriger", "Résultat attendu")], self.registre)
        tache.lier_verification("reproduire", initial)
        tache.lier_verification("corriger", self.registre)
        tache.commencer_etape("reproduire")
        origine = initial.enregistrer(outil="test", cible="cas-initial", version="avant", texte="bug reproduit")
        preuves_initiales = {"bug-reproduit": [{"observation": origine.identifiant, "ligne": 1, "citation": origine.texte}]}
        self.assertTrue(tache.verifier_etape("reproduire", preuves_initiales).reussi)
        tache.commencer_etape("corriger")
        observation = self.observation()
        preuves = self.preuves(observation)
        self.assertTrue(tache.verifier_etape("corriger", preuves).reussi)
        initial.actualiser_cible("cas-initial", "apres")
        self.assertTrue(tache.terminer(preuves).reussi)

    def test_correction_reelle_et_relecture_finale_sur_fichier_temporaire(self):
        # Le programme est une fixture fixe, jamais du code fourni par un modèle.
        avant = "def additionner(a, b):\n    return a + b - 1\n"
        apres = "def additionner(a, b):\n    return a + b\n"
        for changement_final in (False, True):
            with self.subTest(changement_final=changement_final), tempfile.TemporaryDirectory() as dossier:
                fichier = Path(dossier) / "calcul.py"
                fichier.write_text(avant, encoding="utf-8")
                cible = "calcul-synthetique"

                def registre_attendu(texte):
                    registre = RegistrePreuves("scenario-local-v1")
                    registre.ajouter_critere(
                        "resultat", cible, version_controle="addition-v1",
                        verifier=lambda observation: observation.texte == texte,
                    )
                    return registre

                reproduction = registre_attendu("4")
                correction = registre_attendu(apres)
                final = registre_attendu("5")
                registres = (reproduction, correction, final)

                def actualiser():
                    version = empreinte_texte(fichier.read_text(encoding="utf-8"))
                    for registre in registres:
                        registre.actualiser_cible(cible, version)
                    return version

                def observer(tache, registre, outil, texte):
                    observation = registre.enregistrer(
                        outil=outil, cible=cible, version=actualiser(), texte=texte,
                        code_sortie=0,
                    )
                    tache.recevoir_resultat("reussi", observation=observation, progres_pertinent=True)
                    return {"resultat": [
                        {"observation": observation.identifiant, "ligne": numero, "citation": ligne}
                        for numero, ligne in enumerate(texte.splitlines(), start=1)
                    ]}

                def executer_calcul():
                    execution = subprocess.run(
                        [sys.executable, "-I", "-B", "-c",
                         "import runpy, sys; print(runpy.run_path(sys.argv[1])['additionner'](2, 3))",
                         str(fichier)], capture_output=True, text=True, timeout=5,
                    )
                    self.assertEqual(execution.returncode, 0, "Échec du programme synthétique")
                    return execution.stdout.strip()

                tache = Tache("Corriger une addition", [
                    Etape("reproduire", "Reproduire le défaut", "2 + 3 produit 4"),
                    Etape("corriger", "Corriger le fichier", "Source corrigée relue"),
                    Etape("tester", "Tester la correction", "2 + 3 produit 5"),
                ], final)
                for identifiant, registre in zip(("reproduire", "corriger", "tester"), registres):
                    tache.lier_verification(identifiant, registre)

                def lancer(identifiant, outil, lecture):
                    self.assertTrue(tache.commencer_etape(identifiant).autorisee)
                    self.assertTrue(tache.avant_requete().autorisee)
                    self.assertTrue(tache.avant_outil(
                        outil, {}, cible=cible, lecture_seule=lecture,
                        version_etat=actualiser(),
                    ).autorisee)

                lancer("reproduire", "calculer", True)
                preuves = observer(tache, reproduction, "calculer", executer_calcul())
                self.assertTrue(tache.verifier_etape("reproduire", preuves).reussi)

                lancer("corriger", "ecrire", False)
                fichier.write_text(apres, encoding="utf-8")
                tache.recevoir_resultat("reussi")
                self.assertTrue(tache.avant_outil(
                    "relire", {}, cible=cible, lecture_seule=True,
                    version_etat=actualiser(),
                ).autorisee)
                preuves = observer(tache, correction, "relire", fichier.read_text(encoding="utf-8"))
                self.assertTrue(tache.verifier_etape("corriger", preuves).reussi)

                lancer("tester", "calculer", True)
                preuves = observer(tache, final, "calculer", executer_calcul())
                self.assertTrue(tache.verifier_etape("tester", preuves).reussi)
                if changement_final:
                    fichier.write_text(avant, encoding="utf-8")
                # Le harness doit relire la version réelle avant la conclusion.
                actualiser()
                bilan = tache.terminer(preuves)
                self.assertEqual(bilan.reussi, not changement_final)
                self.assertEqual(tache.statut, "active" if changement_final else "terminee")
                self.assertEqual(tache.vue_locale()["outils"], 4)


class AdaptateurLocal(unittest.TestCase):
    def setUp(self):
        for objet, nom in [(socket, "getaddrinfo"), (socket, "create_connection"),
                           (socket.socket, "connect"), (socket.socket, "connect_ex")]:
            garde = patch.object(objet, nom, side_effect=AssertionError("Réseau interdit"))
            garde.start()
            self.addCleanup(garde.stop)
        self.temps = 0.0
        self.version = "v1"
        self.etat_fichier = "défaut"
        self.erreur_version = False
        self.permission = Decision(True, "permission_locale")
        self.pilote = self.creer_pilote()

    def creer_pilote(self, *, budgets=None, annuler=None):
        def lire_version(cible):
            if self.erreur_version:
                raise RuntimeError("DETAIL_LOCAL_CONFIDENTIEL")
            return self.version

        def controle(attendu):
            return ControleLocal("resultat", "fichier", "controle-v1", lambda o: o.texte == attendu)

        return PiloteAutonomie("Corriger", [
            PhaseLocale(Etape("reproduire", "Reproduire", "Défaut observé"), (controle("défaut"),)),
            PhaseLocale(Etape("corriger", "Corriger et tester", "Résultat corrigé"), (controle("corrigé"),)),
        ], (controle("corrigé"),), configuration="configuration-v1", lire_version=lire_version,
            horloge=lambda: self.temps, budgets=budgets, annuler_processus=annuler)

    def action(self, nom="lire", *, lecture=True, texte=None, etat="reussi", **options):
        decision = self.pilote.avant_outil(nom, {}, cible="fichier", lecture_seule=lecture,
                                          permission=self.permission)
        self.assertTrue(decision.autorisee, decision.motif)
        self.pilote.recevoir_resultat(etat, texte=texte if texte is not None else self.etat_fichier,
                                     progres_pertinent=True, **options)

    def reproduire(self):
        self.action()
        self.assertTrue(self.pilote.verifier_etape().reussi)
        self.assertEqual(self.pilote.etape_active, "corriger")

    def corriger(self):
        self.action("ecrire", lecture=False, texte="écriture effectuée")
        self.version, self.etat_fichier = "v2", "corrigé"
        self.action()
        self.assertTrue(self.pilote.verifier_etape().reussi)

    def test_adaptateur_parcours_deux_etapes(self):
        self.reproduire()
        self.corriger()
        self.assertIsNone(self.pilote.etape_active)
        self.assertTrue(self.pilote.terminer().reussi)
        self.assertEqual(self.pilote.tache.statut, "terminee")

    def test_adaptateur_ancienne_preuve_finale_invalidee(self):
        self.reproduire()
        self.corriger()
        self.version = "v3"
        self.assertFalse(self.pilote.terminer().reussi)

    def test_adaptateur_erreur_version_ne_fuit_pas_et_invalide_preuves(self):
        self.reproduire()
        self.corriger()
        self.erreur_version = True
        bilan = self.pilote.terminer()
        self.assertEqual(bilan.motif, "versions_indisponibles")
        self.assertNotIn("DETAIL_LOCAL_CONFIDENTIEL", repr(bilan))
        self.erreur_version = False
        self.assertFalse(self.pilote.terminer().reussi)

    def test_adaptateur_ecriture_ne_prouve_pas_correction(self):
        self.reproduire()
        self.action("ecrire", lecture=False, texte="corrigé")
        self.assertFalse(self.pilote.verifier_etape().reussi)
        self.assertEqual(self.pilote.etape_active, "corriger")

    def test_adaptateur_refus_ne_declenche_aucun_outil(self):
        decision = self.pilote.avant_outil("ecrire", {}, cible="fichier", lecture_seule=False,
                                          permission=Decision(False, "refus_utilisateur"))
        self.assertFalse(decision.autorisee)
        self.assertEqual(self.pilote.tache.vue_locale()["outils"], 0)
        self.assertEqual(self.pilote.tache.statut, "attente_utilisateur")

    def test_adaptateur_resultat_obligatoire_avant_action_suivante(self):
        decision = self.pilote.avant_outil("lire", {}, cible="fichier", lecture_seule=True,
                                          permission=self.permission)
        self.assertTrue(decision.autorisee)
        self.assertFalse(self.pilote.avant_requete().autorisee)
        self.assertFalse(self.pilote.avant_outil("lire", {}, cible="fichier", lecture_seule=True,
                                               permission=self.permission).autorisee)
        self.assertFalse(self.pilote.verifier_etape().reussi)

    def test_adaptateur_mutation_incertaine_et_relecture(self):
        self.reproduire()
        self.action("ecrire", lecture=False, etat="incertain")
        self.assertFalse(self.pilote.verifier_etape().reussi)
        self.version, self.etat_fichier = "v2", "corrigé"
        self.action()
        self.assertTrue(self.pilote.verifier_etape().reussi)
        self.assertTrue(self.pilote.terminer().reussi)

    def test_adaptateur_code_non_nul_marque_mutation_incertaine(self):
        self.reproduire()
        self.action("ecrire", lecture=False, code_sortie=1)
        self.assertTrue(self.pilote.tache.vue_locale()["mutation_incertaine"])

    def test_adaptateur_retour_tronque_ne_valide_pas_etape(self):
        self.action(tronquee=True)
        self.assertFalse(self.pilote.verifier_etape().reussi)

    def test_adaptateur_retour_mal_forme_conserve_action_en_attente(self):
        self.assertTrue(self.pilote.avant_outil("lire", {}, cible="fichier", lecture_seule=True,
                                              permission=self.permission).autorisee)
        with self.assertRaises(ValueError):
            self.pilote.recevoir_resultat("reussi", texte="défaut", tronquee="oui")
        self.pilote.recevoir_resultat("reussi", texte="défaut", progres_pertinent=True)
        self.assertTrue(self.pilote.verifier_etape().reussi)

    def test_adaptateur_cible_hors_plan_refusee(self):
        decision = self.pilote.avant_outil("lire", {}, cible="autre", lecture_seule=True,
                                          permission=self.permission)
        self.assertEqual(decision.motif, "cible_hors_plan")

    def test_adaptateur_arret_annule_processus(self):
        appels = []
        self.pilote = self.creer_pilote(annuler=lambda: appels.append("annulé"))
        self.assertTrue(self.pilote.avant_outil("lire", {}, cible="fichier", lecture_seule=True,
                                              permission=self.permission).autorisee)
        self.pilote.annuler()
        self.assertEqual(appels, ["annulé"])
        with self.assertRaises(ValueError):
            self.pilote.recevoir_resultat("reussi", texte="défaut")

    def test_adaptateur_budget_requetes(self):
        self.pilote = self.creer_pilote(budgets=Budgets(requetes=1))
        self.assertTrue(self.pilote.avant_requete().autorisee)
        self.assertFalse(self.pilote.avant_requete().autorisee)
        self.assertEqual(self.pilote.tache.motif, "budget_requetes")

    def test_adaptateur_texte_faux_ne_devient_pas_preuve(self):
        self.action(texte="tout est fini")
        self.assertFalse(self.pilote.verifier_etape().reussi)
        self.assertFalse(self.pilote.terminer().reussi)

    def test_adaptateur_recontrole_apres_preuve_finale_perimee(self):
        self.reproduire()
        self.corriger()
        self.version = "v3"
        self.assertFalse(self.pilote.terminer().reussi)
        outils_avant = self.pilote.tache.vue_locale()["outils"]
        self.assertTrue(self.pilote.reprendre_verification_finale().autorisee)
        self.assertEqual(self.pilote.tache.vue_locale()["outils"], outils_avant)
        self.action()
        self.assertTrue(self.pilote.verifier_etape().reussi)
        self.assertTrue(self.pilote.terminer().reussi)

    def test_adaptateur_reprises_finales_bornees(self):
        self.pilote = self.creer_pilote(budgets=Budgets(revisions_plan=1))
        self.reproduire()
        self.corriger()
        self.assertTrue(self.pilote.reprendre_verification_finale().autorisee)
        self.action(nom="tester")
        self.assertTrue(self.pilote.verifier_etape().reussi)
        self.assertFalse(self.pilote.reprendre_verification_finale().autorisee)
        self.assertEqual(self.pilote.tache.motif, "budget_revisions_plan")

    def test_adaptateur_configuration_changee_invalide_preuve(self):
        self.reproduire()
        self.corriger()
        self.pilote.actualiser_configuration("nouveau-prompt")
        self.assertFalse(self.pilote.terminer().reussi)

    def test_adaptateur_lecteur_indisponible_interdit_action_sans_compter(self):
        self.erreur_version = True
        decision = self.pilote.avant_outil("lire", {}, cible="fichier", lecture_seule=True,
                                          permission=self.permission)
        self.assertEqual(decision.motif, "versions_indisponibles")
        self.assertEqual(self.pilote.tache.vue_locale()["outils"], 0)

    def test_adaptateur_reprise_lecture_transitoire_une_fois(self):
        self.action(etat="echec")
        decision = self.pilote.avant_outil("lire", {}, cible="fichier", lecture_seule=True,
                                          permission=self.permission, reprise_transitoire=True)
        self.assertTrue(decision.autorisee)
        self.pilote.recevoir_resultat("reussi", texte="défaut", progres_pertinent=True)
        self.assertTrue(self.pilote.verifier_etape().reussi)
        decision = self.pilote.avant_outil("lire", {}, cible="fichier", lecture_seule=True,
                                          permission=self.permission, reprise_transitoire=True)
        self.assertFalse(decision.autorisee)

    def test_adaptateur_permission_booleenne_non_acceptee(self):
        with self.assertRaises(ValueError):
            self.pilote.avant_outil("lire", {}, cible="fichier", lecture_seule=True, permission=True)

    def test_adaptateur_budget_duree_pendant_lecture_version(self):
        self.pilote._lire_version = lambda cible: setattr(self, "temps", 600.0) or "v1"
        decision = self.pilote.avant_outil("lire", {}, cible="fichier", lecture_seule=True,
                                          permission=self.permission)
        self.assertFalse(decision.autorisee)
        self.assertEqual(self.pilote.tache.motif, "budget_duree")

    def test_adaptateur_aucune_lecture_apres_stop(self):
        lectures = []
        self.pilote._lire_version = lambda cible: lectures.append(cible) or "v1"
        self.pilote.annuler()
        self.assertFalse(self.pilote.avant_outil(
            "lire", {}, cible="fichier", lecture_seule=True,
            permission=self.permission).autorisee)
        self.assertFalse(self.pilote.verifier_etape().reussi)
        self.assertFalse(self.pilote.terminer().reussi)
        self.assertEqual(lectures, [])


    def test_adaptateur_retour_tardif_ne_relit_pas_versions(self):
        self.assertTrue(self.pilote.avant_outil(
            "lire", {}, cible="fichier", lecture_seule=True,
            permission=self.permission).autorisee)
        lectures = []
        self.pilote._lire_version = lambda cible: lectures.append(cible) or "v1"
        self.temps = 600.0
        with self.assertRaises(ValueError):
            self.pilote.recevoir_resultat("reussi", texte="défaut")
        self.assertEqual(lectures, [])


class OutilsOptionnels(unittest.TestCase):
    def setUp(self):
        for objet, nom in [(socket, "getaddrinfo"), (socket, "create_connection"),
                           (socket.socket, "connect"), (socket.socket, "connect_ex")]:
            garde = patch.object(objet, nom, side_effect=AssertionError("Réseau interdit"))
            garde.start()
            self.addCleanup(garde.stop)
        self.temps = 0.0
        self.fabrications = 0
        self.version = "v1"
        self.capacite = CapaciteAutonomie({"controle_local": self.fabriquer})

    def fabriquer(self):
        self.fabrications += 1
        controle = ControleLocal("CRITERE_PRIVE", "CIBLE_PRIVEE", "v1", lambda o: o.texte == "attendu")
        return PiloteAutonomie("OBJECTIF_PRIVE", [PhaseLocale(
            Etape("IDENTIFIANT_PRIVE", "ACTION_PRIVEE", "CONDITION_PRIVEE"), (controle,))],
            (controle,), configuration="v1", lire_version=lambda cible: self.version,
            horloge=lambda: self.temps)

    def fournir_preuve(self):
        pilote = self.capacite.pilote_local
        self.assertTrue(pilote.avant_outil("lire", {}, cible="CIBLE_PRIVEE", lecture_seule=True,
                                         permission=Decision(True, "locale")).autorisee)
        pilote.recevoir_resultat("reussi", texte="attendu", progres_pertinent=True)

    def test_outils_inactifs_sans_profil(self):
        capacite = CapaciteAutonomie({})
        self.assertEqual(capacite.outils(), {})
        self.assertEqual(json.loads(capacite.etat()), {"statut": "inactif"})

    def test_table_outils_compatible_moteur_et_profils_bornes(self):
        outils = self.capacite.outils()
        self.assertEqual(len(outils), 6)
        for outil in outils.values():
            self.assertEqual(set(outil), {"fn", "risque", "schema"})
            self.assertTrue(callable(outil["fn"]))
            self.assertFalse(outil["schema"]["parameters"]["additionalProperties"])
        schema = outils["autonomie_demarrer"]["schema"]["parameters"]
        self.assertEqual(schema["properties"]["profil"]["enum"], ["controle_local"])
        self.assertEqual(schema["required"], ["profil"])

    def test_profil_inconnu_sans_echo_ni_fabrique(self):
        retour = self.capacite.demarrer("ENTREE_PRIVEE")
        self.assertNotIn("ENTREE_PRIVEE", retour)
        self.assertEqual(self.fabrications, 0)
        self.assertEqual(json.loads(self.capacite.demarrer("controle_local"))["statut"], "active")

    def test_pas_de_reinitialisation_par_demarrage_repete(self):
        self.capacite.demarrer("controle_local")
        self.capacite.pilote_local.avant_requete()
        retour = json.loads(self.capacite.demarrer("controle_local"))
        self.assertEqual(retour["erreur"], "demarrage_deja_tente")
        self.assertEqual(retour["etat"]["requetes"], 1)
        self.assertEqual(self.fabrications, 1)

    def test_parcours_outils_et_hooks_moteur(self):
        outils = self.capacite.outils()
        outils["autonomie_demarrer"]["fn"](profil="controle_local")
        self.fournir_preuve()
        resultat = json.loads(outils["autonomie_verifier_etape"]["fn"]())
        self.assertTrue(resultat["reussi"])
        resultat = json.loads(outils["autonomie_terminer"]["fn"]())
        self.assertTrue(resultat["reussi"])
        self.assertEqual(resultat["etat"]["statut"], "terminee")

    def test_projection_ne_divulgue_pas_objectif_cible_ou_criteres(self):
        self.capacite.demarrer("controle_local")
        self.fournir_preuve()
        retours = self.capacite.etat() + self.capacite.verifier_etape() + self.capacite.terminer()
        for prive in ("OBJECTIF_PRIVE", "CIBLE_PRIVEE", "CRITERE_PRIVE", "IDENTIFIANT_PRIVE",
                      "ACTION_PRIVEE", "CONDITION_PRIVEE", "attendu"):
            self.assertNotIn(prive, retours)

    def test_texte_fini_ne_valide_pas_sans_observation(self):
        self.capacite.demarrer("controle_local")
        self.assertFalse(json.loads(self.capacite.verifier_etape())["reussi"])
        self.assertFalse(json.loads(self.capacite.terminer())["reussi"])

    def test_erreur_fabrique_non_divulguee_et_pas_rejouee(self):
        essais = []
        def echouer():
            essais.append(True)
            raise RuntimeError("DETAIL_PRIVE")
        capacite = CapaciteAutonomie({"controle": echouer})
        self.assertNotIn("DETAIL_PRIVE", capacite.demarrer("controle"))
        capacite.demarrer("controle")
        self.assertEqual(essais, [True])
        self.assertEqual(json.loads(capacite.etat())["statut"], "indisponible")

    def test_fabrique_sans_pilote_refusee(self):
        capacite = CapaciteAutonomie({"controle": lambda: "fini"})
        self.assertEqual(json.loads(capacite.demarrer("controle"))["erreur"], "preparation_indisponible")

    def test_arret_ne_retire_pas_le_pilote_et_empeche_redemarrage(self):
        self.capacite.demarrer("controle_local")
        pilote = self.capacite.pilote_local
        self.assertEqual(json.loads(self.capacite.arreter())["statut"], "annulee")
        self.assertIs(self.capacite.pilote_local, pilote)
        self.assertFalse(pilote.avant_requete().autorisee)
        self.capacite.demarrer("controle_local")
        self.assertEqual(self.fabrications, 1)

    def test_verification_sans_suivi(self):
        for action in (self.capacite.verifier_etape, self.capacite.terminer,
                       self.capacite.reprendre_verification, self.capacite.arreter):
            self.assertEqual(json.loads(action())["erreur"], "aucun_suivi")

    def test_etat_controle_expiration_sans_lire_versions(self):
        self.capacite.demarrer("controle_local")
        self.capacite.pilote_local._lire_version = lambda cible: self.fail("Lecture tardive")
        self.temps = 600.0
        self.assertEqual(json.loads(self.capacite.etat())["statut"], "incomplete")

    def test_reprise_apres_version_perimee_par_outil(self):
        self.capacite.demarrer("controle_local")
        self.fournir_preuve()
        self.capacite.verifier_etape()
        self.version = "v2"
        self.assertFalse(json.loads(self.capacite.terminer())["reussi"])
        self.assertTrue(json.loads(self.capacite.reprendre_verification())["autorisee"])
        self.fournir_preuve()
        self.assertTrue(json.loads(self.capacite.verifier_etape())["reussi"])
        self.assertTrue(json.loads(self.capacite.terminer())["reussi"])

    def test_erreur_controle_ne_divulgue_pas_exception(self):
        self.capacite.demarrer("controle_local")
        with patch.object(self.capacite.pilote_local, "verifier_etape", side_effect=RuntimeError("DETAIL_PRIVE")):
            resultat = self.capacite.verifier_etape()
        self.assertNotIn("DETAIL_PRIVE", resultat)
        self.assertEqual(json.loads(resultat)["erreur"], "verification_indisponible")



class ValidationSuitePython(unittest.TestCase):
    RAPPORT = "[code 0]\n.\n----------------------------------------------------------------------\nRan 1 test in 0.001s\n\nOK\n"

    def setUp(self):
        for objet, nom in [(socket, "getaddrinfo"), (socket, "create_connection"),
                           (socket.socket, "connect"), (socket.socket, "connect_ex")]:
            garde = patch.object(objet, nom, side_effect=AssertionError("Réseau interdit"))
            garde.start()
            self.addCleanup(garde.stop)
        self.version = "v1"
        self.temps = 0.0
        self.contexte = True
        self.profil = ProfilTestsPython(
            ("test_calcul",), nombre_minimum=1, lire_version=lambda cible: self.version,
            contexte_valide=lambda: self.contexte, configuration="python-local-v1",
            horloge=lambda: self.temps,
        )
        self.capacite = CapaciteAutonomie({"tests_python": self.profil.preparer})
        self.capacite.demarrer("tests_python")

    def avant(self, permission=True):
        return self.profil.avant_outil("terminal", {"commande": self.profil.commande},
                                       permission=Decision(permission, "locale"))

    def finir(self, rapport=None, **options):
        self.assertTrue(self.avant().autorisee)
        self.profil.recevoir_resultat(rapport if rapport is not None else self.RAPPORT, **options)
        bilan = json.loads(self.capacite.verifier_etape())
        if bilan["reussi"]:
            return json.loads(self.capacite.terminer())["reussi"]
        return False

    def test_suite_reelle_synthetique_dans_sous_processus(self):
        with tempfile.TemporaryDirectory() as dossier:
            fichier = Path(dossier) / "test_calcul.py"
            fichier.write_text("import unittest\nclass Calcul(unittest.TestCase):\n"
                               "    def test_addition(self):\n        self.assertEqual(2 + 3, 5)\n", encoding="utf-8")
            self.profil._lire_version = lambda cible: empreinte_texte(fichier.read_text(encoding="utf-8"))
            self.capacite.pilote_local._lire_version = self.profil._lire_version
            self.assertTrue(self.avant().autorisee)
            execution = subprocess.run([sys.executable, "-B", "-m", "unittest", "test_calcul"],
                                       cwd=dossier, capture_output=True, text=True, timeout=5)
            self.profil.recevoir_resultat(f"[code {execution.returncode}]\n{execution.stdout}{execution.stderr}")
            self.assertTrue(json.loads(self.capacite.verifier_etape())["reussi"])
            self.assertTrue(json.loads(self.capacite.terminer())["reussi"])

    def test_rapport_succes(self):
        self.assertTrue(self.finir())

    def test_creation_capacite_stable_et_commande_disponible(self):
        capacite, outils = self.profil.creer_capacite()
        meme_capacite, autres_outils = self.profil.creer_capacite()
        self.assertIs(capacite, meme_capacite)
        description = outils["autonomie_demarrer"]["schema"]["description"]
        self.assertIn(self.profil.commande, description)
        self.assertEqual(outils.keys(), autres_outils.keys())

    def test_zero_tests_ne_valide_pas(self):
        self.assertFalse(self.finir(self.RAPPORT.replace("1 test", "0 tests")))

    def test_code_non_nul_malgre_rapport_ok(self):
        self.assertFalse(self.finir(self.RAPPORT.replace("[code 0]", "[code 1]")))

    def test_mot_ok_seul_ne_prouve_pas_tests(self):
        self.assertFalse(self.finir("[code 0]\nOK\n"))

    def test_tests_ignores_ne_valident_pas_le_profil(self):
        self.assertFalse(self.finir(self.RAPPORT.replace("OK", "OK (skipped=1)")))

    def test_sources_changees_pendant_execution_refusees(self):
        self.assertTrue(self.avant().autorisee)
        self.version = "v2"
        self.profil.recevoir_resultat(self.RAPPORT)
        self.assertFalse(json.loads(self.capacite.verifier_etape())["reussi"])

    def test_version_changee_entre_deux_lectures_du_retour_refusee(self):
        self.assertTrue(self.avant().autorisee)
        lectures = iter(["v1", "v2", "v2", "v2"])
        lecteur = lambda cible: next(lectures, "v2")
        self.profil._lire_version = lecteur
        self.capacite.pilote_local._lire_version = lecteur
        self.profil.recevoir_resultat(self.RAPPORT)
        self.assertFalse(json.loads(self.capacite.verifier_etape())["reussi"])

    def test_commande_ajoutee_hors_profil_refusee(self):
        for commande in (self.profil.commande + "; echo OK", "cat fichier", self.profil.commande + " test_autre"):
            with self.subTest(commande=commande):
                decision = self.profil.avant_outil("terminal", {"commande": commande},
                                                  permission=Decision(True, "locale"))
                self.assertEqual(decision.motif, "commande_hors_profil")
        self.assertEqual(self.capacite.pilote_local.tache.vue_locale()["outils"], 0)

    def test_contexte_incorrect_refuse_execution(self):
        self.contexte = False
        self.assertEqual(self.avant().motif, "contexte_execution_incorrect")

    def test_permission_refusee_reste_refusee(self):
        self.assertFalse(self.avant(permission=False).autorisee)
        self.assertEqual(self.capacite.pilote_local.tache.statut, "attente_utilisateur")
        self.assertFalse(self.avant().autorisee)

    def test_rapport_tronque_refuse(self):
        self.assertFalse(self.finir(tronquee=True))

    def test_retour_sans_appel_refuse(self):
        with self.assertRaises(ValueError):
            self.profil.recevoir_resultat(self.RAPPORT)

    def test_module_injecte_refuse_a_la_configuration(self):
        with self.assertRaises(ValueError):
            ProfilTestsPython(("test_a; echo OK",), nombre_minimum=1,
                              lire_version=lambda cible: "v1", contexte_valide=lambda: True,
                              configuration="v1")

    def test_retour_apres_delai_ne_lit_pas_contexte(self):
        self.assertTrue(self.avant().autorisee)
        self.profil._contexte_valide = lambda: self.fail("Lecture après délai")
        self.temps = 600.0
        with self.assertRaises(ValueError):
            self.profil.recevoir_resultat(self.RAPPORT)

    def test_empreinte_fichiers_python_reels_et_modification(self):
        with tempfile.TemporaryDirectory() as dossier:
            fichier = Path(dossier) / "calcul.py"
            fichier.write_text("valeur = 1\n", encoding="utf-8")
            premiere = empreinte_suite_python(dossier)
            self.assertIsInstance(premiere, str)
            self.assertEqual(premiere, empreinte_suite_python(dossier))
            fichier.write_text("valeur = 2\n", encoding="utf-8")
            self.assertNotEqual(premiere, empreinte_suite_python(dossier))

    def test_empreinte_n_ouvre_pas_fichier_de_configuration(self):
        with tempfile.TemporaryDirectory() as dossier:
            (Path(dossier) / "calcul.py").write_text("valeur = 1\n", encoding="utf-8")
            premiere = empreinte_suite_python(dossier)
            (Path(dossier) / "configuration.env").write_text("MARQUEUR_PRIVE_FICTIF", encoding="utf-8")
            self.assertEqual(premiere, empreinte_suite_python(dossier))

    def test_empreinte_refuse_ajout_pendant_capture(self):
        with tempfile.TemporaryDirectory() as dossier:
            fichier = Path(dossier) / "calcul.py"
            fichier.write_text("valeur = 1\n", encoding="utf-8")
            lire = Path.read_bytes

            def lire_et_ajouter(chemin):
                contenu = lire(chemin)
                (Path(dossier) / "ajout.py").write_text("valeur = 2\n", encoding="utf-8")
                return contenu

            with patch.object(Path, "read_bytes", lire_et_ajouter):
                self.assertIsNone(empreinte_suite_python(dossier))

    def test_empreinte_refuse_changement_fichier_deja_lu(self):
        with tempfile.TemporaryDirectory() as dossier:
            premier = Path(dossier) / "a.py"
            second = Path(dossier) / "b.py"
            premier.write_text("valeur = 1\n", encoding="utf-8")
            second.write_text("valeur = 2\n", encoding="utf-8")
            lire = Path.read_bytes

            def lire_et_modifier(chemin):
                contenu = lire(chemin)
                if chemin == second:
                    premier.write_text("valeur = 12345\n", encoding="utf-8")
                return contenu

            with patch.object(Path, "read_bytes", lire_et_modifier):
                self.assertIsNone(empreinte_suite_python(dossier))

    def test_empreinte_refuse_symlink_et_dossier_vide(self):
        with tempfile.TemporaryDirectory() as dossier:
            self.assertIsNone(empreinte_suite_python(dossier))
            (Path(dossier) / "cible.txt").write_text("marqueur", encoding="utf-8")
            (Path(dossier) / "calcul.py").symlink_to(Path(dossier) / "cible.txt")
            self.assertIsNone(empreinte_suite_python(dossier))


class ImmuniteDuPilote(unittest.TestCase):
    def setUp(self):
        for objet, nom in [(socket, "getaddrinfo"), (socket, "create_connection"),
                           (socket.socket, "connect"), (socket.socket, "connect_ex")]:
            garde = patch.object(objet, nom, side_effect=AssertionError("Réseau interdit"))
            garde.start()
            self.addCleanup(garde.stop)
        from immunite import Immunite
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.magasin = Immunite(Path(dossier.name) / "regles.db")
        self.regle = RegleImmunitaire("acces", "Écart connu", "erreur_connue", "v1")
        self.immunite = ImmuniteControlee(self.magasin, (self.regle,))
        self.registre_avant = RegistrePreuves("configuration-v1")
        self.registre_avant.actualiser_cible("cible_privee", "v1")
        self.avant = self.registre_avant.enregistrer(
            outil="lire", cible="cible_privee", version="v1",
            texte="MARQUEUR_BRUT_FICTIF erreur_connue", code_sortie=0)
        self.registre_apres = RegistrePreuves("configuration-v1")
        self.registre_apres.actualiser_cible("cible_privee", "v2")
        self.verifiee = True
        self.registre_apres.ajouter_critere(
            "source_corrigee", "cible_privee", version_controle="v1",
            verifier=lambda o: self.verifiee and o.texte == "forme corrigee")
        self.apres = self.registre_apres.enregistrer(
            outil="lire", cible="cible_privee", version="v2", texte="forme corrigee", code_sortie=0)
        self.preuves = {"source_corrigee": [{"observation": self.apres.identifiant,
                                           "ligne": 1, "citation": self.apres.texte}]}

    def apprendre(self, immunite=None, **options):
        arguments = dict(avant=self.avant, apres=self.apres, registre_avant=self.registre_avant,
                         registre_apres=self.registre_apres, preuves_apres=self.preuves)
        arguments.update(options)
        return (immunite or self.immunite).apprendre("acces", **arguments)

    def capturer(self, texte="erreur_connue", **options):
        registre = RegistrePreuves("configuration-v1")
        registre.actualiser_cible("cible_privee", "v3")
        return registre.enregistrer(outil="lire", cible="cible_privee", version="v3", texte=texte, **options)

    def test_apprentissage_et_stockage_empreintes_sans_bruts(self):
        self.assertEqual(self.apprendre().statut, "apprise")
        actifs = self.magasin.actifs()
        self.assertEqual(len(actifs), 1)
        origine = json.loads(actifs[0]["origine"])
        self.assertEqual(origine["avant"], self.avant.empreinte)
        self.assertEqual(origine["apres"], self.apres.empreinte)
        self.assertNotIn("MARQUEUR_BRUT_FICTIF", json.dumps(actifs))
        self.assertNotIn("cible_privee", json.dumps(actifs))

    def test_correspondances_candidates_sans_journaliser_extraits(self):
        self.assertEqual(self.apprendre().statut, "apprise")
        bilan = self.immunite.reperer(self.capturer("erreur_connue puis erreur_connue"))
        self.assertEqual(bilan.statut, "recherchee")
        self.assertEqual([(c.debut, c.fin) for c in bilan.candidats], [(0, 13), (19, 32)])
        self.assertNotIn("erreur_connue", repr(bilan))
        self.assertEqual(self.magasin.rencontres_de(self.magasin.actifs()[0]["id"]), [])

    def test_detecteur_touche_corrige_refuse(self):
        regle = replace(self.regle, detecteur="erreur_connue|forme")
        bilan = self.apprendre(ImmuniteControlee(self.magasin, (regle,)))
        self.assertEqual(bilan.statut, "refuse")
        self.assertEqual(self.magasin.actifs(), [])

    def test_detecteur_rate_avant_refuse(self):
        bilan = self.apprendre(ImmuniteControlee(self.magasin, (replace(self.regle, detecteur="absent"),)))
        self.assertEqual(bilan.statut, "refuse")

    def test_detecteur_reconnait_vide_refuse(self):
        regle = replace(self.regle, detecteur="erreur_connue|^$")
        self.assertEqual(self.apprendre(ImmuniteControlee(self.magasin, (regle,))).statut, "refuse")

    def test_detecteur_sans_fragment_consomme_refuse(self):
        regle = replace(self.regle, detecteur="(?=erreur_connue)")
        self.assertEqual(self.apprendre(ImmuniteControlee(self.magasin, (regle,))).statut, "refuse")

    def test_correction_non_verifiee_ne_peut_pas_etre_apprise(self):
        self.verifiee = False
        self.assertEqual(self.apprendre().motif, "correction_non_prouvee")
        self.assertEqual(self.magasin.actifs(), [])

    def test_preuve_apres_perimee_refusee(self):
        self.registre_apres.actualiser_cible("cible_privee", "v3")
        self.assertEqual(self.apprendre().motif, "correction_non_prouvee")

    def test_captures_forgees_ne_sont_pas_celles_des_registres(self):
        for options in ({"avant": replace(self.avant, texte="autre")},
                        {"apres": replace(self.apres, outil="autre")},
                        {"avant": replace(self.avant, identifiant="obs-inventee")}):
            with self.subTest(options=options):
                self.assertEqual(self.apprendre(**options).motif, "captures_correction_invalides")

    def test_registre_valide_sur_autre_capture_ne_suffit_pas(self):
        registre = RegistrePreuves("configuration-v1")
        registre.actualiser_cible("cible_privee", "v2")
        registre.actualiser_cible("autre", "v2")
        registre.ajouter_critere("autre", "autre", version_controle="v1", verifier=lambda o: True)
        apres = registre.enregistrer(outil="lire", cible="cible_privee", version="v2", texte="forme corrigee")
        autre = registre.enregistrer(outil="lire", cible="autre", version="v2", texte="autre")
        preuves = {"autre": [{"observation": autre.identifiant, "ligne": 1, "citation": "autre"}]}
        self.assertEqual(self.apprendre(apres=apres, registre_apres=registre, preuves_apres=preuves).motif,
                         "correction_non_prouvee")

    def test_regle_non_validee_ou_importee_ne_s_active_pas(self):
        self.magasin.apprendre(self.regle.libelle, self.regle.detecteur, "provenance non verifiee")
        bilan = self.immunite.reperer(self.capturer())
        self.assertEqual(bilan.statut, "non_verifie")
        self.assertEqual(bilan.candidats, ())

    def test_redemarrage_n_invente_pas_validation_persistante(self):
        self.apprendre()
        nouveau = ImmuniteControlee(self.magasin, (self.regle,))
        self.assertEqual(nouveau.reperer(self.capturer()).statut, "non_verifie")

    def test_oubli_desactive_sans_reactivation_silencieuse(self):
        self.apprendre()
        self.assertTrue(self.immunite.oublier("acces"))
        self.assertEqual(self.immunite.reperer(self.capturer()).candidats, ())
        self.assertEqual(self.apprendre().motif, "regle_oubliee")

    def test_scan_incomplet_ne_declenche_pas_de_conclusion_saine(self):
        self.apprendre()
        for observation in (self.capturer(tronquee=True), self.capturer(etat_execution="echec"),
                            self.capturer(code_sortie=1)):
            self.assertEqual(self.immunite.reperer(observation).statut, "inconnu")

    def test_nombre_de_correspondances_borne(self):
        immunite = ImmuniteControlee(self.magasin, (self.regle,), correspondances_maximum=2)
        self.assertEqual(self.apprendre(immunite).statut, "apprise")
        bilan = immunite.reperer(self.capturer("erreur_connue " * 4))
        self.assertEqual(bilan.statut, "partiel")
        self.assertEqual(len(bilan.candidats), 2)

    def test_regex_invalide_sans_fuite_de_message(self):
        regle = replace(self.regle, detecteur="(")
        bilan = self.apprendre(ImmuniteControlee(self.magasin, (regle,)))
        self.assertEqual(bilan.statut, "inconnu")
        self.assertEqual(self.magasin.actifs(), [])

    def test_calcul_couteux_arrete_et_processus_recolte(self):
        import multiprocessing
        avant = {p.pid for p in multiprocessing.active_children()}
        debut = time.monotonic()
        retour = _calculer_immunite([r"(a+)+$"], ["a" * 80 + "!"], delai=0.6)
        self.assertEqual(retour, {"erreur": "delai_immunite"})
        self.assertLess(time.monotonic() - debut, 5)
        self.assertEqual({p.pid for p in multiprocessing.active_children()}, avant)

    def test_regle_locale_inconnue_et_limites_invalides(self):
        self.assertEqual(self.immunite.apprendre("inconnue", avant=self.avant, apres=self.apres,
                         registre_avant=self.registre_avant, registre_apres=self.registre_apres,
                         preuves_apres=self.preuves).motif, "regle_locale_inconnue")
        with self.assertRaises(ValueError):
            ImmuniteControlee(self.magasin, (self.regle,), delai=float("nan"))

    def test_stockage_en_erreur_ne_divulgue_pas_detail(self):
        with patch.object(self.magasin, "apprendre", side_effect=RuntimeError("DETAIL_PRIVE")):
            bilan = self.apprendre()
        self.assertEqual(bilan.motif, "stockage_immunite_indisponible")
        self.assertNotIn("DETAIL_PRIVE", repr(bilan))

    def test_isolation_indisponible_ne_divulgue_pas_erreur(self):
        import multiprocessing
        with patch.object(multiprocessing, "get_context", side_effect=RuntimeError("DETAIL_PRIVE")):
            bilan = self.apprendre()
        self.assertEqual(bilan.motif, "calcul_immunite_indisponible")
        self.assertNotIn("DETAIL_PRIVE", repr(bilan))
        self.assertEqual(self.magasin.actifs(), [])

    def test_correction_changee_pendant_controle_ne_devient_pas_regle(self):
        def calcul(*args, **options):
            self.registre_apres.actualiser_cible("cible_privee", "v3")
            return {"presences": [True, False, False], "premiere_non_vide": True}
        with patch("verification._calculer_immunite", side_effect=calcul):
            bilan = self.apprendre()
        self.assertEqual(bilan.motif, "correction_devenue_non_prouvee")
        self.assertEqual(self.magasin.actifs(), [])

    def test_pilote_recoit_alerte_et_projection_sans_texte(self):
        self.apprendre()
        version = ["v3"]
        controle = ControleLocal("presence", "cible_privee", "v1", lambda o: True)
        pilote = PiloteAutonomie("Inspection locale", [PhaseLocale(
            Etape("inspection", "Inspecter", "Observation actuelle"), (controle,))], (controle,),
            configuration="v1", lire_version=lambda cible: version[0], immunite=self.immunite)
        self.assertTrue(pilote.avant_outil("lire", {}, cible="cible_privee", lecture_seule=True,
                                         permission=Decision(True, "locale")).autorisee)
        pilote.recevoir_resultat("reussi", texte="erreur_connue", progres_pertinent=True)
        self.assertEqual(len(pilote.candidats_immunite_locaux), 1)
        capacite = CapaciteAutonomie({"inspection": lambda: pilote})
        capacite.demarrer("inspection")
        etat = capacite.etat()
        self.assertEqual(json.loads(etat)["immunite"]["candidats"], 1)
        self.assertNotIn("erreur_connue", etat)
        self.assertNotIn("cible_privee", etat)
        self.assertEqual(pilote.tache.statut, "active")
        version[0] = "v4"
        self.assertFalse(pilote.verifier_etape().reussi)
        self.assertEqual(pilote.candidats_immunite_locaux, ())


if __name__ == "__main__":
    unittest.main()
