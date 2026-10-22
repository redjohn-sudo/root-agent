"""Édition de la mémoire depuis la fenêtre : les règles de memoire.py tiennent
(sensible, doublon, plafond, tombes), et les gestes de Vincent marchent.
Tout se passe dans un dossier temporaire : le vrai memoire.md n'est pas touché."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import memoire
import memoire_edition as me


class TestEdition(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp(prefix="test-mem-"))
        for nom, val in (("MEMOIRE_FICHIER", tmp / "memoire.md"), ("TOMBES_FICHIER", tmp / "tombes.json")):
            p = mock.patch.object(memoire, nom, val)
            p.start()
            self.addCleanup(p.stop)

    def faits(self):
        return {c["nom"]: [f["texte"] for f in c["faits"]] for c in me.lire()["categories"]}

    def test_vide(self):
        d = me.lire()
        self.assertEqual((d["categories"], d["taille"]), ([], 0))
        self.assertIn("Cadre de travail", d["proposees"])

    def test_ajouter_par_categorie_et_jauge(self):
        self.assertTrue(me.ajouter("Cybersécurité", "Fait des CTF sur Root-Me")["ok"])
        self.assertTrue(me.ajouter("Profil", "Vit à Paris")["ok"])
        self.assertEqual(self.faits(), {"Cybersécurité": ["Fait des CTF sur Root-Me"], "Profil": ["Vit à Paris"]})
        self.assertGreater(me.lire()["taille"], 0)

    def test_les_regles_de_memoire_tiennent(self):
        self.assertFalse(me.ajouter("Profil", "mon mot de passe est truc")["ok"])
        me.ajouter("Profil", "Vincent code en C et en Python tous les jours")
        r = me.ajouter("Profil", "Vincent code en C et en Python tous les jours.")
        self.assertFalse(r["ok"])
        self.assertIn("quasi-doublon", r["message"])
        self.assertFalse(me.modifier("Vincent code en C et en Python tous les jours", "password: x")["ok"])

    def test_modifier_sur_place(self):
        me.ajouter("Profil", "Vit à Paris")
        self.assertTrue(me.modifier("Vit à Paris", "Vit à Paris, dans le 11e")["ok"])
        self.assertEqual(self.faits(), {"Profil": ["Vit à Paris, dans le 11e"]})
        self.assertFalse(me.modifier("introuvable", "x")["ok"])

    def test_retirer_sans_tombe_oublier_avec_tombe(self):
        me.ajouter("Profil", "Fait A sans rapport")
        me.ajouter("Profil", "Autre chose de très différent")
        self.assertTrue(me.retirer("Fait A sans rapport"))            # Annuler
        self.assertTrue(me.ajouter("Profil", "Fait A sans rapport")["ok"])  # réapprenable
        self.assertTrue(me.oublier("Fait A sans rapport"))
        r = me.ajouter("Profil", "Fait A sans rapport")
        self.assertTrue(r["tombe"])                                   # bloqué par la tombe
        self.assertTrue(me.lever_tombe("Fait A sans rapport"))        # Vincent le remet lui-même
        self.assertTrue(me.ajouter("Profil", "Fait A sans rapport")["ok"])

    def test_categorie_vide_disparait_et_renommer(self):
        me.ajouter("Temporaire", "Seul fait de la catégorie")
        me.ajouter("Profil", "Vit à Paris")
        me.retirer("Seul fait de la catégorie")
        self.assertNotIn("## Temporaire", memoire.MEMOIRE_FICHIER.read_text())
        self.assertTrue(me.renommer_categorie("Profil", "Qui je suis"))
        self.assertFalse(me.renommer_categorie("Qui je suis", "Qui je suis"))
        self.assertEqual(self.faits(), {"Qui je suis": ["Vit à Paris"]})

    def test_lies_sans_mots_vides(self):
        me.ajouter("Cybersécurité", "S'entraîne en CTF sur Root-Me")
        me.ajouter("Profil", "Il est étudiant à 42")
        self.assertEqual(me.lies("quelle heure est il"), [])
        self.assertEqual(me.lies("aide moi sur un ctf"), ["S'entraîne en CTF sur Root-Me"])


if __name__ == "__main__":
    unittest.main()
