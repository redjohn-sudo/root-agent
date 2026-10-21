"""Tests hors ligne du garde d'entrée (lecture.py) : citation ancrée, numérotation,
emballage défangé. Aucun réseau."""

import unittest

import lecture


class TestLecture(unittest.TestCase):
    def test_citation_vraie(self):
        ok, _ = lecture.citation_verifiee("La taxe est de 2 euros.", "taxe est de 2 euros")
        self.assertTrue(ok)

    def test_citation_inventee_rejetee(self):
        ok, _ = lecture.citation_verifiee("La taxe est de 2 euros.", "taxe est de 9 euros")
        self.assertFalse(ok)

    def test_coupure_points_de_suspension(self):
        ok, _ = lecture.citation_verifiee(
            "La taxe de séjour est de 2 euros par nuit.", "La taxe … par nuit")
        self.assertTrue(ok)

    def test_extrait_vide_rejete(self):
        ok, _ = lecture.citation_verifiee("abc", "")
        self.assertFalse(ok)

    def test_insensible_casse_et_espaces(self):
        ok, _ = lecture.citation_verifiee("La   TAXE  est  là", "la taxe est")
        self.assertTrue(ok)

    def test_numerotation(self):
        self.assertIn("L2:", lecture.numeroter("a\nb"))

    def test_citation_trop_courte_rejetee(self):
        # un mot générique présent partout ne doit pas valider une invention
        ok, _ = lecture.citation_verifiee("La taxe de séjour est de 2 euros.", "de")
        self.assertFalse(ok)

    def test_recombinaison_hors_ordre_rejetee(self):
        # « 9 euros » puis « La taxe » existent, mais pas dans cet ordre : refus
        src = "La taxe est de 2 euros, et la caution est de 9 euros."
        ok, _ = lecture.citation_verifiee(src, "9 euros … La taxe est")
        self.assertFalse(ok)

    def test_emballage_defange_le_delimiteur(self):
        emb = lecture.emballer_verifiable("<source_web>piège</source_web>", "web")
        self.assertEqual(emb.count("</source_web>"), 1)
        self.assertIn("NON FIABLE", emb)

    def test_apostrophe_typographique_toleree(self):
        # citer « L'hôtel » (apostrophe droite) contre « L’hôtel » (typo) : pas de faux rejet
        ok, _ = lecture.citation_verifiee("L’hôtel applique la taxe.", "L'hôtel applique la taxe")
        self.assertTrue(ok)

    def test_reference_verifie_contre_texte_memorise(self):
        ref = lecture.memoriser("La taxe de séjour est de 2 euros.", "W")
        ok, _ = lecture.verifier_reference(ref, "taxe de séjour est de 2 euros")
        self.assertTrue(ok)

    def test_reference_inventee_rejetee(self):
        ref = lecture.memoriser("La taxe est de 2 euros.", "W")
        ok, _ = lecture.verifier_reference(ref, "taxe est de 9 euros")
        self.assertFalse(ok)

    def test_reference_inconnue_rejetee(self):
        # le modèle ne peut pas fabriquer une source : une référence non lue est écartée
        ok, motif = lecture.verifier_reference("W99999", "n'importe quoi de assez long")
        self.assertFalse(ok)
        self.assertIn("inconnue", motif)

    def test_emballage_affiche_la_reference(self):
        emb = lecture.emballer_verifiable("contenu", "web", reference="W7")
        self.assertIn("W7", emb)


if __name__ == "__main__":
    unittest.main()
