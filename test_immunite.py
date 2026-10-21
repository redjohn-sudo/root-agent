"""Tests hors ligne de la mémoire immunitaire (immunite.py).

Base SQLite dans un fichier temporaire, aucune donnée sortante, aucun réseau.
On couvre : apprendre, déduplication par empreinte, chercher trouve un jumeau,
oublier désactive, export/import aller-retour, regex invalide gérée.
"""

import os
import tempfile
import unittest

import immunite


class TestImmunite(unittest.TestCase):
    def setUp(self):
        # Chaque test a sa propre base jetable, dans un fichier temporaire.
        descripteur, chemin = tempfile.mkstemp(suffix=".db", prefix="root-immunite-test-")
        os.close(descripteur)
        self.chemin = chemin
        self.mem = immunite.Immunite(chemin)

    def tearDown(self):
        try:
            os.remove(self.chemin)
        except OSError:
            pass

    # Le détecteur généralisé de l'exemple du cahier des charges : items.get(3).unwrap().
    DETECTEUR = r"\w+\.get\(\d+\)\.unwrap\(\)"

    def test_apprendre_renvoie_empreinte(self):
        identifiant = self.mem.apprendre("unwrap sur get() indexé", self.DETECTEUR, "correction-42")
        self.assertEqual(identifiant, immunite.Immunite.empreinte(self.DETECTEUR))
        actifs = self.mem.actifs()
        self.assertEqual(len(actifs), 1)
        self.assertEqual(actifs[0]["regle"], "unwrap sur get() indexé")
        self.assertEqual(actifs[0]["origine"], "correction-42")

    def test_dedup_par_empreinte_garde_premiere_origine(self):
        id1 = self.mem.apprendre("règle A", self.DETECTEUR, "origine-premiere")
        id2 = self.mem.apprendre("règle B", self.DETECTEUR, "origine-seconde")
        # Même détecteur => même anticorps, un seul en base, première origine conservée.
        self.assertEqual(id1, id2)
        actifs = self.mem.actifs()
        self.assertEqual(len(actifs), 1)
        self.assertEqual(actifs[0]["origine"], "origine-premiere")
        self.assertEqual(actifs[0]["regle"], "règle A")

    def test_chercher_trouve_un_jumeau(self):
        self.mem.apprendre("unwrap sur get() indexé", self.DETECTEUR, "correction-42")
        code = "let a = items.get(3).unwrap();\nlet b = cache.get(10).unwrap();\nlet c = ok();"
        trouvailles = self.mem.chercher(code, lieu="src/lib.rs")
        extraits = sorted(t["extrait"] for t in trouvailles)
        self.assertEqual(extraits, ["cache.get(10).unwrap()", "items.get(3).unwrap()"])
        self.assertTrue(all(t["lieu"] == "src/lib.rs" for t in trouvailles))
        # Les rencontres sont journalisées.
        histoire = self.mem.rencontres_de(trouvailles[0]["anticorps"])
        self.assertEqual(len(histoire), 2)

    def test_chercher_sans_jumeau(self):
        self.mem.apprendre("unwrap sur get() indexé", self.DETECTEUR, "correction-42")
        self.assertEqual(self.mem.chercher("let x = safe_value;"), [])

    def test_rencontre_journalisee_une_seule_fois(self):
        ident = self.mem.apprendre("règle", self.DETECTEUR, "o")
        texte = "items.get(3).unwrap()"
        self.mem.chercher(texte, lieu="f.rs")
        self.mem.chercher(texte, lieu="f.rs")
        # Même (anticorps, lieu, extrait) : une seule entrée.
        self.assertEqual(len(self.mem.rencontres_de(ident)), 1)

    def test_oublier_desactive_mais_garde_histoire(self):
        ident = self.mem.apprendre("règle", self.DETECTEUR, "o")
        self.mem.chercher("items.get(3).unwrap()", lieu="f.rs")
        self.assertTrue(self.mem.oublier(ident))
        # Plus actif : chercher ne le déclenche plus.
        self.assertEqual(self.mem.actifs(), [])
        self.assertEqual(self.mem.chercher("items.get(3).unwrap()"), [])
        # Mais l'historique reste lisible.
        self.assertEqual(len(self.mem.rencontres_de(ident)), 1)

    def test_oublier_inconnu(self):
        self.assertFalse(self.mem.oublier("empreinte-qui-n-existe-pas"))

    def test_export_import_aller_retour(self):
        self.mem.apprendre("règle 1", self.DETECTEUR, "origine-1")
        self.mem.apprendre("règle 2", r"TODO:\s*\w+", "origine-2")
        paquet = self.mem.exporter()
        self.assertEqual(paquet["format"], "antibodies-v1")
        self.assertEqual(len(paquet["anticorps"]), 2)

        # On importe dans une base neuve : on doit retrouver les deux anticorps.
        descripteur, autre = tempfile.mkstemp(suffix=".db", prefix="root-immunite-test2-")
        os.close(descripteur)
        self.addCleanup(lambda: os.path.exists(autre) and os.remove(autre))
        recue = immunite.Immunite(autre)
        ajoutes = recue.importer(paquet)
        self.assertEqual(ajoutes, 2)
        # Réimporter le même paquet n'ajoute rien (déjà connus).
        self.assertEqual(recue.importer(paquet), 0)
        regles = sorted(a["regle"] for a in recue.actifs())
        self.assertEqual(regles, ["règle 1", "règle 2"])

    def test_import_id_falsifie_refuse(self):
        paquet = {"format": "antibodies-v1", "anticorps": [
            {"id": "empreinte-bidon", "regle": "r", "detecteur": self.DETECTEUR, "origine": "o"}]}
        with self.assertRaises(immunite.FormatInvalide):
            self.mem.importer(paquet)

    def test_import_mauvais_format_refuse(self):
        with self.assertRaises(immunite.FormatInvalide):
            self.mem.importer({"format": "autre-chose", "anticorps": []})
        with self.assertRaises(immunite.FormatInvalide):
            self.mem.importer({"format": "antibodies-v1"})

    def test_regex_invalide_a_apprendre(self):
        with self.assertRaises(immunite.RegexInvalide):
            self.mem.apprendre("parenthèse ouverte", r"items\.get\((unclosed", "o")
        # Rien n'a été enregistré.
        self.assertEqual(self.mem.actifs(), [])

    def test_regex_invalide_a_importer(self):
        detecteur = r"items\.get\((unclosed"
        paquet = {"format": "antibodies-v1", "anticorps": [
            {"id": immunite.Immunite.empreinte(detecteur), "regle": "r",
             "detecteur": detecteur, "origine": "o"}]}
        with self.assertRaises(immunite.RegexInvalide):
            self.mem.importer(paquet)


if __name__ == "__main__":
    unittest.main()
