"""Registre des outils externes : structure, détection, et refus propres à
l'installation. Aucune vraie installation lancée."""

import unittest
from unittest import mock

import outils_externes as ext


class TestRegistre(unittest.TestCase):
    def test_les_22_sont_la_et_bien_formes(self):
        self.assertEqual(len(ext.OUTILS), 22)
        ids = [o["id"] for o in ext.OUTILS]
        self.assertEqual(len(set(ids)), 22)                 # pas de doublon
        for o in ext.OUTILS:
            self.assertIn(o["role"], ext.ROLES)
            self.assertTrue(o["source"].startswith("https://github.com/"))
            self.assertTrue(o["detect"])

    def test_etat_groupe_et_compte(self):
        d = ext.etat()
        self.assertEqual(d["total"], 22)
        total_dans_groupes = sum(len(g["outils"]) for g in d["groupes"])
        self.assertEqual(total_dans_groupes, 22)
        self.assertLessEqual(d["installes"], 22)

    def test_detection_import_et_which(self):
        self.assertTrue(ext._installe({"detect": ("import", "json")}))     # stdlib présent
        self.assertFalse(ext._installe({"detect": ("import", "paquet_qui_nexiste_pas_xyz")}))
        self.assertFalse(ext._installe({"detect": ("manuel",)}))

    def test_installer_outil_inconnu(self):
        self.assertFalse(ext.installer("nexiste_pas")["ok"])

    def test_installer_refuse_si_deja_la(self):
        with mock.patch.object(ext, "_installe", return_value=True):
            r = ext.installer("mlx_lm")
            self.assertTrue(r["ok"]); self.assertTrue(r.get("deja"))

    def test_installer_manuel_renvoie_la_source(self):
        r = ext.installer("purplellama")
        self.assertFalse(r["ok"]); self.assertIn("github.com", r["message"])

    def test_installer_sans_le_gestionnaire_prevenu(self):
        # container a besoin de brew ; si brew absent, message clair, rien n'est lancé
        with mock.patch.object(ext, "_installe", return_value=False), \
             mock.patch.object(ext.shutil, "which", return_value=None), \
             mock.patch.object(ext.subprocess, "run", side_effect=AssertionError("ne doit pas lancer")):
            r = ext.installer("container")
            self.assertFalse(r["ok"])
            self.assertIn("Homebrew", r["message"])


if __name__ == "__main__":
    unittest.main()
