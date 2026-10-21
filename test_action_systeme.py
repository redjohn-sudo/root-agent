"""Tests hors ligne de action_systeme : on vérifie les arguments passés à
cliclick, SANS jamais cliquer ni taper pour de vrai (on remplace `_lancer`)."""

import unittest

import action_systeme


class TestActionSysteme(unittest.TestCase):
    def setUp(self):
        self._vrai = action_systeme._lancer
        self.appels = []
        action_systeme._lancer = lambda args, entree=None: (self.appels.append(args) or "")

    def tearDown(self):
        action_systeme._lancer = self._vrai

    def test_cliquer(self):
        msg = action_systeme.cliquer(10, 20)
        self.assertEqual(self.appels[-1], ["c:10,20"])
        self.assertIn("10", msg)

    def test_cliquer_convertit_en_entier(self):
        action_systeme.cliquer(10.9, 20.2)
        self.assertEqual(self.appels[-1], ["c:10,20"])

    def test_double_cliquer(self):
        action_systeme.double_cliquer(3, 4)
        self.assertEqual(self.appels[-1], ["dc:3,4"])

    def test_clic_droit(self):
        action_systeme.clic_droit(5, 6)
        self.assertEqual(self.appels[-1], ["rc:5,6"])

    def test_taper(self):
        action_systeme.taper("bonjour")
        self.assertEqual(self.appels[-1], ["t:bonjour"])

    def test_touche(self):
        action_systeme.touche("return")
        self.assertEqual(self.appels[-1], ["kp:return"])

    def test_position_lecture_seule(self):
        action_systeme._lancer = lambda args, entree=None: "100,200"
        self.assertEqual(action_systeme.position_souris(), "100,200")


if __name__ == "__main__":
    unittest.main()
