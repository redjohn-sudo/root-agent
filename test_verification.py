"""Régressions du portage, uniquement synthétiques et sans modèle ni navigateur.

Reprend les contre-exemples de Contingency (fausse preuve parmi de vraies,
référence inexacte, version changée) et d'Oblivion (succès ancien, autre cible,
états observés à des instants différents).
"""

import json
import socket
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

from verification import RegistrePreuves, empreinte_configuration, empreinte_texte


class VerificationPreuves(unittest.TestCase):
    def setUp(self):
        # Aucune régression ne doit solliciter le réseau, même indirectement.
        for nom in ("getaddrinfo", "create_connection"):
            garde = patch.object(socket, nom, side_effect=AssertionError("Réseau interdit"))
            garde.start()
            self.addCleanup(garde.stop)
        for nom in ("connect", "connect_ex"):
            garde = patch.object(socket.socket, nom, side_effect=AssertionError("Réseau interdit"))
            garde.start()
            self.addCleanup(garde.stop)
        self.registre = RegistrePreuves("configuration-v1")
        self.registre.actualiser_cible("exemple.py", "version-v1")
        self.registre.ajouter_critere(
            "bug-corrige", "exemple.py", version_controle="regression-v1",
            verifier=self.controler_regression,
        )

    @staticmethod
    def controler_regression(observation):
        # Le callback est du code de confiance, pas du Python produit par le modèle.
        if observation.outil != "test_local" or observation.code_sortie != 0:
            return False
        compte_rendu = json.loads(observation.texte)
        return (compte_rendu == {"cas": "regression_bug", "executes": 3, "echecs": 0})

    def observer(self, *, registre=None, texte=None, **options):
        registre = registre or self.registre
        arguments = {
            "outil": "test_local", "cible": "exemple.py", "version": "version-v1",
            "texte": texte if texte is not None else
                '{"cas": "regression_bug", "executes": 3, "echecs": 0}',
            "code_sortie": 0,
        }
        arguments.update(options)
        return registre.enregistrer(**arguments)

    @staticmethod
    def citer(observation, ligne=1, citation=None):
        return [{"observation": observation.identifiant, "ligne": ligne,
                 "citation": observation.texte.splitlines()[ligne - 1]
                 if citation is None else citation}]

    def test_regression_verifiee_apres_observation_reelle(self):
        observation = self.observer()
        bilan = self.registre.conclure({"bug-corrige": self.citer(observation)})
        self.assertTrue(bilan.reussi)

    def test_code_zero_et_ok_ne_prouvent_pas_la_correction(self):
        observation = self.observer(texte="OK")
        self.assertFalse(self.registre.conclure({"bug-corrige": self.citer(observation)}).reussi)

    def test_sortie_valide_mais_mauvais_resultat_metier(self):
        observation = self.observer(texte='{"cas":"regression_bug","executes":3,"echecs":1}')
        self.assertEqual(self.registre.verifier("bug-corrige", self.citer(observation)).statut, "non_verifie")

    def test_aucun_test_execute_ne_suffit_pas(self):
        observation = self.observer(texte='{"cas":"regression_bug","executes":0,"echecs":0}')
        self.assertFalse(self.registre.conclure({"bug-corrige": self.citer(observation)}).reussi)

    def test_texte_de_page_imite_un_rapport_de_test(self):
        observation = self.observer(outil="web_voir")
        self.assertEqual(self.registre.verifier("bug-corrige", self.citer(observation)).statut, "non_verifie")

    def test_citation_inventee_refusee(self):
        observation = self.observer()
        resultat = self.registre.verifier("bug-corrige", self.citer(observation, citation="succès inventé"))
        self.assertEqual(resultat.motif, "citation_inexacte")

    def test_vraie_citation_avec_mauvais_repere(self):
        observation = self.observer(texte="ligne neutre\nOK")
        preuve = self.citer(observation, ligne=1, citation="OK")
        self.assertEqual(self.registre.verifier("bug-corrige", preuve).motif, "citation_inexacte")

    def test_sous_chaine_ne_remplace_pas_la_ligne_exacte(self):
        observation = self.observer(texte="résultat : OK mais erreur persistante")
        self.assertEqual(self.registre.verifier("bug-corrige", self.citer(observation, citation="OK")).motif,
                         "citation_inexacte")

    def test_une_fausse_preuve_parmi_deux_bloque_tout(self):
        observation = self.observer()
        preuves = self.citer(observation) + self.citer(observation, citation="autre contenu")
        self.assertEqual(self.registre.verifier("bug-corrige", preuves).statut, "invalide")

    def test_observation_inventee_ou_provenant_autre_registre(self):
        autre = RegistrePreuves("configuration-v1")
        autre.actualiser_cible("exemple.py", "version-v1")
        observation = self.observer(registre=autre)
        self.assertEqual(self.registre.verifier("bug-corrige", self.citer(observation)).motif,
                         "observation_absente")

    def test_autre_cible_avec_meme_texte_ne_suffit_pas(self):
        self.registre.actualiser_cible("autre.py", "version-v1")
        observation = self.observer(cible="autre.py")
        self.assertEqual(self.registre.verifier("bug-corrige", self.citer(observation)).motif,
                         "cible_incorrecte")

    def test_pas_de_fusion_de_captures_distinctes(self):
        avant = self.observer(texte="premier état attendu")
        apres = self.observer(texte="second état attendu")
        preuves = self.citer(avant) + self.citer(apres)
        self.assertEqual(self.registre.verifier("bug-corrige", preuves).motif, "observations_melangees")

    def test_succes_ancien_remplace_par_echec(self):
        succes = self.observer()
        self.observer(texte="erreur revenue", etat_execution="echec", code_sortie=1)
        self.assertEqual(self.registre.verifier("bug-corrige", self.citer(succes)).motif,
                         "observation_remplacee")

    def test_document_modifie_invalide_la_preuve(self):
        observation = self.observer()
        self.registre.actualiser_cible("exemple.py", "version-v2")
        self.assertEqual(self.registre.verifier("bug-corrige", self.citer(observation)).motif,
                         "version_cible_perimee")

    def test_retour_a_ancienne_version_ne_reactive_pas_la_preuve(self):
        observation = self.observer()
        self.registre.actualiser_cible("exemple.py", "version-v2")
        self.registre.actualiser_cible("exemple.py", "version-v1")
        self.assertFalse(self.registre.conclure({"bug-corrige": self.citer(observation)}).reussi)

    def test_nouvelle_observation_apres_modification_debloque(self):
        self.registre.actualiser_cible("exemple.py", "version-v2")
        observation = self.observer(version="version-v2")
        self.assertTrue(self.registre.conclure({"bug-corrige": self.citer(observation)}).reussi)

    def test_actualisation_identique_ne_perime_pas(self):
        observation = self.observer()
        self.registre.actualiser_cible("exemple.py", "version-v1")
        self.registre.actualiser_configuration("configuration-v1")
        self.assertTrue(self.registre.conclure({"bug-corrige": self.citer(observation)}).reussi)

    def test_version_inconnue_interdit_la_conclusion(self):
        observation = self.observer()
        self.registre.actualiser_cible("exemple.py", None)
        self.assertEqual(self.registre.verifier("bug-corrige", self.citer(observation)).motif,
                         "version_cible_inconnue")

    def test_configuration_changee_meme_si_retablie(self):
        observation = self.observer()
        self.registre.actualiser_configuration("configuration-v2")
        self.registre.actualiser_configuration("configuration-v1")
        self.assertEqual(self.registre.verifier("bug-corrige", self.citer(observation)).motif,
                         "configuration_perimee")

    def test_champs_et_types_proposes_sont_stricts(self):
        observation = self.observer()
        reference = self.citer(observation)[0]
        mauvaises = [None, [], {}, [None], [{**reference, "statut": "verifie"}],
                     [{**reference, "ligne": True}], [{**reference, "ligne": 0}],
                     [{**reference, "ligne": "1"}], [{**reference, "citation": ""}],
                     [{**reference, "observation": []}]]
        for preuves in mauvaises:
            with self.subTest(preuves=preuves):
                self.assertEqual(self.registre.verifier("bug-corrige", preuves).statut, "invalide")

    def test_execution_inconnue_echouee_ou_tronquee_ne_passe_pas(self):
        for options in ({"etat_execution": "inconnu"}, {"etat_execution": "echec"},
                        {"code_sortie": 1}, {"tronquee": True}):
            with self.subTest(options=options):
                observation = self.observer(**options)
                self.assertFalse(self.registre.conclure({"bug-corrige": self.citer(observation)}).reussi)

    def test_registre_borne_et_source_purgee_inconnue(self):
        registre = RegistrePreuves("configuration-v1", limite_observations=1)
        registre.actualiser_cible("exemple.py", "version-v1")
        registre.ajouter_critere("controle", "exemple.py", version_controle="v1", verifier=lambda o: True)
        ancien = self.observer(registre=registre)
        self.observer(registre=registre)
        self.assertEqual(registre.verifier("controle", self.citer(ancien)).motif, "observation_absente")

    def test_critere_defini_apres_la_preuve_ne_la_valide_pas(self):
        observation = self.observer()
        self.registre.ajouter_critere("tardif", "exemple.py", version_controle="v1", verifier=lambda o: True)
        self.assertEqual(self.registre.verifier("tardif", self.citer(observation)).motif,
                         "observation_anterieure_au_critere")

    def test_impossible_d_affaiblir_un_critere_existant(self):
        with self.assertRaises(ValueError):
            self.registre.ajouter_critere("bug-corrige", "exemple.py", version_controle="v2",
                                         verifier=lambda o: True)

    def test_tous_les_criteres_sont_obligatoires(self):
        self.registre.ajouter_critere("regression-voisine", "exemple.py", version_controle="v1",
                                     verifier=lambda o: False)
        observation = self.observer()
        preuve = self.citer(observation)
        self.assertFalse(self.registre.conclure({"bug-corrige": preuve}).reussi)
        self.assertFalse(self.registre.conclure({"bug-corrige": preuve, "regression-voisine": preuve}).reussi)
        self.assertFalse(self.registre.conclure({"bug-corrige": preuve, "invente": preuve}).reussi)

    def test_aucun_critere_ne_donne_pas_un_succes_vide(self):
        self.assertFalse(RegistrePreuves("config").conclure({}).reussi)

    def test_erreur_controle_sans_recopier_son_message(self):
        marqueur = "VALEUR_FICTIVE_PRIVEE_NE_PAS_RECOPIER"

        def echouer(observation):
            raise RuntimeError(marqueur)

        self.registre.ajouter_critere("indisponible", "exemple.py", version_controle="v1", verifier=echouer)
        observation = self.observer(texte=marqueur)
        resultat = self.registre.verifier("indisponible", self.citer(observation))
        self.assertEqual(resultat.motif, "erreur_controle_local")
        self.assertNotIn(marqueur, repr(resultat))
        self.assertNotIn(marqueur, repr(observation))

    def test_controle_qui_retourne_un_objet_truthy_n_est_pas_un_succes(self):
        self.registre.ajouter_critere("malforme", "exemple.py", version_controle="v1",
                                     verifier=lambda o: {"statut": "verifie"})
        observation = self.observer()
        self.assertEqual(self.registre.verifier("malforme", self.citer(observation)).motif,
                         "reponse_controle_invalide")

    def test_observation_figee_et_alteration_detectee(self):
        observation = self.observer()
        with self.assertRaises(FrozenInstanceError):
            observation.texte = "modifié"
        # Simule une corruption dans le processus local, hors API normale.
        object.__setattr__(observation, "texte", "contenu altéré")
        self.assertEqual(self.registre.verifier("bug-corrige", self.citer(observation)).motif,
                         "observation_alteree")

    def test_nouvelle_conclusion_reverifie_apres_modification(self):
        observation = self.observer()
        proposition = {"bug-corrige": self.citer(observation)}
        self.assertTrue(self.registre.conclure(proposition).reussi)
        self.registre.actualiser_cible("exemple.py", "version-v2")
        self.assertFalse(self.registre.conclure(proposition).reussi)

    def test_invariants_d_entree_locale(self):
        with self.assertRaises(ValueError):
            RegistrePreuves("config", limite_observations=True)
        with self.assertRaises(ValueError):
            self.observer(version="version-non-observee")
        with self.assertRaises(ValueError):
            self.observer(code_sortie=True)
        with self.assertRaises(ValueError):
            self.observer(tronquee="false")

    def test_empreinte_configuration_independante_ordre_et_sensible_aux_reglages(self):
        reference = {"modele": "faux-modele-v1", "prompt": "v1", "schema": "v1", "effort": "high"}
        self.assertEqual(empreinte_configuration(reference), empreinte_configuration(dict(reversed(list(reference.items())))))
        for cle in reference:
            self.assertNotEqual(empreinte_configuration(reference), empreinte_configuration({**reference, cle: "v2"}))
        with self.assertRaises(ValueError):
            empreinte_configuration({"valeur": float("nan")})
        self.assertNotEqual(empreinte_texte("avant"), empreinte_texte("après"))


if __name__ == "__main__":
    unittest.main()
