"""Tests hors ligne du consentement lié à l'empreinte. Fichier temporaire, zéro réseau."""

import tempfile
import unittest
from pathlib import Path

import consentement


class TestConsentement(unittest.TestCase):
    def setUp(self):
        self._vrai = consentement.FICHIER
        consentement.FICHIER = Path(tempfile.mkdtemp()) / "c.json"

    def tearDown(self):
        consentement.FICHIER = self._vrai

    def test_sans_accord_refuse(self):
        ok, _ = consentement.peut_agir("Envoi X", "a@ex.org", "email")
        self.assertFalse(ok)

    def test_accord_valide(self):
        consentement.accorder("Envoi X", "a@ex.org", "email")
        ok, _ = consentement.peut_agir("Envoi X", "a@ex.org", "email")
        self.assertTrue(ok)

    def test_texte_change_perime_accord(self):
        consentement.accorder("Envoi X", "a@ex.org", "email")
        ok, _ = consentement.peut_agir("Envoi Y", "a@ex.org", "email")
        self.assertFalse(ok)

    def test_destinataire_change_perime_accord(self):
        consentement.accorder("Envoi X", "a@ex.org", "email")
        ok, _ = consentement.peut_agir("Envoi X", "b@ex.org", "email")
        self.assertFalse(ok)

    def test_idempotence(self):
        consentement.accorder("Envoi X", "a@ex.org", "email")
        consentement.marquer_fait("Envoi X", "a@ex.org", "email")
        ok, motif = consentement.peut_agir("Envoi X", "a@ex.org", "email")
        self.assertFalse(ok)
        self.assertIn("refaire", motif)

    def test_oublier(self):
        consentement.accorder("Envoi X", "a@ex.org", "email")
        consentement.oublier("Envoi X", "a@ex.org", "email")
        ok, _ = consentement.peut_agir("Envoi X", "a@ex.org", "email")
        self.assertFalse(ok)

    def test_normalisation_casse_espaces(self):
        consentement.accorder("Envoi   X", "A@Ex.org")
        ok, _ = consentement.peut_agir("envoi x", "a@ex.org")
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
