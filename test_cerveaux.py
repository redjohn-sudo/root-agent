"""Tests hors ligne de cerveaux.py : configuration saine (aucune clé en clair),
adaptation de l'historique entre cerveaux, requête, coût. Aucun réseau."""

import json
import re
import unittest

import cerveaux

DS = {"id": "ds", "fournisseur": "DeepSeek", "modele": "deepseek-flash", "vision": True}
NB = {"id": "nb", "fournisseur": "Nebius", "modele": "zai-org/GLM-5.3", "vision": False,
      "effort": "medium", "prix": [1.40, 4.40], "max_tokens": 8000}

HISTO = [
    {"role": "system", "content": "âme"},
    {"role": "user", "content": [{"type": "text", "text": "regarde"},
                                 {"type": "image_url", "image_url": {"url": "data:x"}}]},
    {"role": "assistant", "content": "vu", "reasoning_content": "je pense…",
     "_par": "DeepSeek", "_cerveau": "ds"},
]


class TestConfiguration(unittest.TestCase):
    def test_fichier_valide_et_defaut_existe(self):
        d = cerveaux.charger()
        ids = [c["id"] for c in d["cerveaux"]]
        self.assertEqual(len(ids), len(set(ids)), "identifiants en double")
        self.assertIn(d["defaut"], ids)

    def test_aucune_cle_en_clair(self):
        texte = cerveaux.FICHIER.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"sk-[A-Za-z0-9]{8,}|eyJ[A-Za-z0-9_-]{20,}", texte))
        for c in cerveaux.liste():
            if c["cle"]:  # cle vide = cerveau sans clé API (pont Max)
                self.assertRegex(c["cle"], r"^[A-Z0-9_]+$", "le champ cle doit être un NOM de variable")

    def test_champs_requis(self):
        for c in cerveaux.liste():
            for champ in ("id", "nom", "fournisseur", "url", "modele", "cle", "outils", "vision"):
                self.assertIn(champ, c, f"{c.get('id')} : {champ} manquant")


class TestPreparer(unittest.TestCase):
    def test_meme_fournisseur_garde_la_reflexion(self):
        p = cerveaux.preparer(HISTO, DS)
        self.assertEqual(p[2]["reasoning_content"], "je pense…")

    def test_autre_fournisseur_retire_la_reflexion(self):
        p = cerveaux.preparer(HISTO, NB)
        self.assertNotIn("reasoning_content", p[2])

    def test_champs_prives_jamais_envoyes(self):
        for cerveau in (DS, NB):
            for m in cerveaux.preparer(HISTO, cerveau):
                self.assertFalse(any(k.startswith("_") for k in m))

    def test_image_remplacee_si_pas_de_vision(self):
        p = cerveaux.preparer(HISTO, NB)
        self.assertEqual(p[1]["content"][1], {"type": "text", "text": cerveaux.IMAGE_ABSENTE})
        self.assertEqual(cerveaux.preparer(HISTO, DS)[1]["content"][1]["type"], "image_url")

    def test_historique_original_intact(self):
        avant = json.dumps(HISTO, sort_keys=True)
        cerveaux.preparer(HISTO, NB)
        self.assertEqual(json.dumps(HISTO, sort_keys=True), avant)


class TestRequeteEtCout(unittest.TestCase):
    def test_effort_et_outils(self):
        c = cerveaux.corps_requete(NB, HISTO, outils=[{"type": "function"}])
        self.assertEqual(c["reasoning_effort"], "medium")
        self.assertEqual(c["tool_choice"], "auto")
        self.assertEqual(c["max_tokens"], 8000)
        self.assertNotIn("reasoning_effort", cerveaux.corps_requete(DS, HISTO))

    def test_cout(self):
        self.assertAlmostEqual(cerveaux.cout(NB, 1_000_000, 1_000_000), 5.80)
        self.assertIsNone(cerveaux.cout(DS, 1000, 1000))   # prix non confirmé : rien d'inventé


if __name__ == "__main__":
    unittest.main()
