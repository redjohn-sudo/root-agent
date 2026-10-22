"""Réglages : masquer des icônes du dock, moins d'animations, fond par défaut.
reglages.local.json temporaire, aucun effet sur la vraie config."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock


class TestReglages(unittest.TestCase):
    def setUp(self):
        import importlib.util
        if not importlib.util.find_spec("webview"):
            self.skipTest("pywebview absent")
        import fenetre
        self.fenetre = fenetre
        p = mock.patch.object(fenetre, "REGLAGES", Path(tempfile.mkdtemp()) / "r.json")
        p.start(); self.addCleanup(p.stop)
        # un Pont sans fenêtre réelle ni réseau
        self.pont = fenetre.Pont.__new__(fenetre.Pont)
        self.pont.window = None
        self.pont.messages = [{"role": "system", "content": "x"}]

    def test_masquer_et_remontrer_une_icone(self):
        etat = self.pont.reglages_etat()
        self.assertTrue(all(p["visible"] for p in etat["panneaux"]))
        self.pont.reglage_dock("pentest", False)
        etat = self.pont.reglages_etat()
        pentest = next(p for p in etat["panneaux"] if p["id"] == "pentest")
        self.assertFalse(pentest["visible"])
        self.pont.reglage_dock("pentest", True)
        pentest = next(p for p in self.pont.reglages_etat()["panneaux"] if p["id"] == "pentest")
        self.assertTrue(pentest["visible"])

    def test_moins_animations_persiste(self):
        self.pont.reglage_animations(True)
        self.assertTrue(self.pont.reglages_etat()["moins_animations"])
        self.pont.reglage_animations(False)
        self.assertFalse(self.pont.reglages_etat()["moins_animations"])

    def test_fond_par_defaut(self):
        self.fenetre.ecrire_reglages(fond="fond.local.jpg")
        self.assertEqual(self.pont.reglages_etat()["fond"], "fond.local.jpg")
        self.pont.reglage_fond_defaut()
        self.assertEqual(self.pont.reglages_etat()["fond"], "")

    def test_apropos_present(self):
        a = self.pont.reglages_etat()["apropos"]
        self.assertEqual(a["nom"], "Root")
        self.assertIn("publique", a["note"])


if __name__ == "__main__":
    unittest.main()
