"""Bac à sable d'exécution : calcul, timeout, isolation du disque, accès aux
bibliothèques de Root. Sauté si sandbox-exec absent (autre OS)."""

import os
import shutil
import unittest

import sandbox

DISPO = shutil.which("sandbox-exec") is not None


@unittest.skipUnless(DISPO, "sandbox-exec absent")
class TestSandbox(unittest.TestCase):
    def test_calcul_simple(self):
        r = sandbox.executer("print(6*7)")
        self.assertTrue(r["ok"])
        self.assertIn("42", r["sortie"])

    def test_timeout_coupe_une_boucle(self):
        r = sandbox.executer("while True: pass", timeout=1)
        self.assertTrue(r["timeout"])
        self.assertFalse(r["ok"])

    def test_ecriture_hors_zone_bloquee(self):
        cible = os.path.expanduser("~/PREUVE_TEST_SANDBOX.txt")
        try:
            r = sandbox.executer(f"open({cible!r}, 'w').write('x')")
            self.assertFalse(r["ok"])
            self.assertFalse(os.path.exists(cible))     # le fichier n'a pas été créé
        finally:
            if os.path.exists(cible):
                os.remove(cible)

    def test_ecriture_locale_permise(self):
        r = sandbox.executer("open('t.txt','w').write('ok'); print('écrit')")
        self.assertTrue(r["ok"])
        self.assertIn("écrit", r["sortie"])

    def test_bibliotheques_de_root_disponibles(self):
        r = sandbox.executer("from sympy import factorint; print(factorint(21))")
        self.assertTrue(r["ok"])
        self.assertIn("3", r["sortie"])

    def test_bash(self):
        r = sandbox.executer("echo bonjour", langage="bash")
        self.assertTrue(r["ok"])
        self.assertIn("bonjour", r["sortie"])

    def test_langage_inconnu(self):
        r = sandbox.executer("x", langage="brainfuck")
        self.assertFalse(r["ok"])
        self.assertIn("non géré", r["erreur"])

    def test_timeout_borne(self):
        import sandbox as s
        # un timeout délirant est ramené au plafond, pas d'exception
        r = s.executer("print(1)", timeout=99999)
        self.assertTrue(r["ok"])


class TestOutilScript(unittest.TestCase):
    def test_outil_via_root(self):
        import importlib.util
        if not importlib.util.find_spec("rich"):
            self.skipTest("rich absent")
        import root
        self.assertIn("executer_script", root.OUTILS)
        self.assertEqual(root.OUTILS["executer_script"]["risque"], "sandbox")
        # en autonomie large, le sandbox ne demande pas (essais répétés) ; en prudente oui
        root.AUTONOMIE = "large"
        self.assertFalse(root.doit_demander("executer_script", {"code": "x"}))
        root.AUTONOMIE = "prudente"
        self.assertTrue(root.doit_demander("executer_script", {"code": "x"}))
        root.AUTONOMIE = "large"


if __name__ == "__main__":
    unittest.main()
