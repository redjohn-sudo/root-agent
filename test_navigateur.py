"""Tests hors ligne du pilotage d'onglets (navigateur.py) : résolution d'un
onglet par indice/id/titre, marquage de l'onglet actif, normalisation d'URL et
repli PUT->GET à l'ouverture. Aucun Brave lancé, aucune connexion réelle."""

import unittest
from unittest import mock

import navigateur

PAGES = [
    {"type": "page", "id": "A", "title": "Accueil", "url": "https://exemple.fr/"},
    {"type": "page", "id": "B", "title": "Docs CDP", "url": "https://docs.exemple.fr/cdp"},
    {"type": "page", "id": "C", "title": "", "url": "about:blank"},
]


class TestResoudre(unittest.TestCase):
    def test_par_indice_1_based(self):
        self.assertEqual(navigateur.Brave._resoudre(2, PAGES)["id"], "B")
        self.assertEqual(navigateur.Brave._resoudre("3", PAGES)["id"], "C")

    def test_indice_hors_borne(self):
        self.assertIsNone(navigateur.Brave._resoudre(0, PAGES))
        self.assertIsNone(navigateur.Brave._resoudre(9, PAGES))

    def test_par_id_exact(self):
        self.assertEqual(navigateur.Brave._resoudre("B", PAGES)["title"], "Docs CDP")

    def test_par_bout_de_titre_ou_url(self):
        self.assertEqual(navigateur.Brave._resoudre("cdp", PAGES)["id"], "B")
        self.assertEqual(navigateur.Brave._resoudre("exemple.fr/cdp", PAGES)["id"], "B")

    def test_booleen_rejete(self):
        # True vaut 1 en Python : on ne doit pas le confondre avec l'onglet 1
        self.assertIsNone(navigateur.Brave._resoudre(True, PAGES))


class TestOnglets(unittest.TestCase):
    def test_marque_l_actif(self):
        b = navigateur.Brave()
        b._cible = "B"
        with mock.patch.object(b, "_pages_brutes", return_value=PAGES):
            ongl = b.onglets()
        self.assertEqual([o["n"] for o in ongl], [1, 2, 3])
        self.assertTrue(ongl[1]["actif"] and not ongl[0]["actif"])


class TestNouvelOnglet(unittest.TestCase):
    def test_normalise_url_et_bascule(self):
        b = navigateur.Brave()
        vu = {}

        def faux_http(chemin, methode="GET"):
            vu["chemin"], vu["methode"] = chemin, methode
            return {"id": "Z", "webSocketDebuggerUrl": "ws://x"}

        with mock.patch.object(b, "_http", side_effect=faux_http), \
             mock.patch.object(b, "_connecter_cible") as conn, \
             mock.patch.object(b, "_attendre"), \
             mock.patch.object(b, "apercu", return_value={"texte": "ok"}):
            b.nouvel_onglet("exemple.fr")
        self.assertEqual(vu["methode"], "PUT")
        self.assertIn("https%3A%2F%2Fexemple.fr", vu["chemin"])  # URL normalisée + encodée
        conn.assert_called_once()

    def test_repli_put_vers_get(self):
        b = navigateur.Brave()
        appels = []

        def faux_http(chemin, methode="GET"):
            appels.append(methode)
            if methode == "PUT":
                raise RuntimeError("405")
            return {"id": "Z", "webSocketDebuggerUrl": "ws://x"}

        with mock.patch.object(b, "_http", side_effect=faux_http), \
             mock.patch.object(b, "_connecter_cible"), \
             mock.patch.object(b, "_attendre"), \
             mock.patch.object(b, "apercu", return_value={"texte": "ok"}):
            b.nouvel_onglet("https://exemple.fr")
        self.assertEqual(appels, ["PUT", "GET"])  # a bien tenté PUT puis replié sur GET


class TestFermer(unittest.TestCase):
    def test_ref_introuvable(self):
        b = navigateur.Brave()
        with mock.patch.object(b, "_pages_brutes", return_value=PAGES):
            r = b.fermer_onglet("inexistant")
        self.assertIn("introuvable", r["texte"])


if __name__ == "__main__":
    unittest.main()
