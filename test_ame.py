"""L'âme de Root : socle gravé lu, couche modulable éditable, prompt complet.
Dossier temporaire, aucune écriture dans le vrai ame.md."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import ame


class Base(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp(prefix="test-ame-"))
        base = tmp / "ame.md"
        base.write_text("Tu es Root, directe.\n\n## Tes règles prioritaires\n1. Sincérité.\n2. Aucune fuite.\n\n## Autonomie\n- Agis seule sur l'inoffensif.\n", encoding="utf-8")
        for nom, val in (("BASE_FICHIER", base), ("PERSO_FICHIER", tmp / "perso.json")):
            p = mock.patch.object(ame, nom, val); p.start(); self.addCleanup(p.stop)


class TestSocle(Base):
    def test_sections_decoupe_le_socle(self):
        s = ame.sections()
        titres = [x["titre"] for x in s]
        self.assertEqual(titres, ["Identité", "Tes règles prioritaires", "Autonomie"])
        self.assertTrue(all(x["grave"] for x in s))
        self.assertIn("Sincérité", s[1]["contenu"])

    def test_socle_sans_perso_le_prompt_est_le_socle(self):
        self.assertEqual(ame.ame_complete(), ame.base())


class TestModulable(Base):
    def test_ton_sajoute_au_prompt(self):
        ame.ton("Bref et pédagogue, tutoie.")
        c = ame.ame_complete()
        self.assertIn(ame.ENTETE_PERSO, c)
        self.assertIn("Bref et pédagogue", c)
        self.assertTrue(c.startswith("Tu es Root"))        # le socle reste en tête

    def test_regles_ajouter_modifier_retirer(self):
        self.assertTrue(ame.ajouter_regle("Toujours une action suivante."))
        self.assertFalse(ame.ajouter_regle("Toujours une action suivante."))   # doublon
        self.assertFalse(ame.ajouter_regle("   "))
        self.assertIn("- Toujours une action suivante.", ame.ame_complete())
        self.assertTrue(ame.modifier_regle("Toujours une action suivante.", "Jamais de bonne nuit."))
        self.assertIn("Jamais de bonne nuit.", ame.perso()["regles"])
        self.assertTrue(ame.retirer_regle("Jamais de bonne nuit."))
        self.assertEqual(ame.perso()["regles"], [])

    def test_modifier_vers_vide_retire_la_regle(self):
        ame.ajouter_regle("une règle")
        ame.modifier_regle("une règle", "")
        self.assertEqual(ame.perso()["regles"], [])

    def test_le_socle_reste_devant_les_reglages(self):
        ame.ton("x"); ame.ajouter_regle("y")
        c = ame.ame_complete()
        self.assertLess(c.index("Tu es Root"), c.index(ame.ENTETE_PERSO))
        self.assertIn("ne remplacent", c.lower().replace("\n", " ") and c)  # mention que ça ne remplace pas le gravé
        self.assertIn("jamais tes règles gravées", c)

    def test_etat_complet(self):
        ame.ton("t"); ame.ajouter_regle("r")
        e = ame.etat()
        self.assertEqual(e["ton"], "t")
        self.assertEqual(e["regles"], ["r"])
        self.assertTrue(e["sections"])
        self.assertIn("## Réglages de Vincent", e["complete"])


if __name__ == "__main__":
    unittest.main()
