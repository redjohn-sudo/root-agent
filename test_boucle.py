"""Contrat moteur <-> écran : la boucle un_tour ne parle qu'à l'objet `ecran`.
On remplace le modèle par un faux (aucun réseau) et on vérifie la suite exacte
des événements : outil, résultat, réponse, fin ; et qu'un refus est respecté.
Sauté si rich/prompt_toolkit ne sont pas installés (CI minimale)."""

import importlib.util
import unittest
from unittest import mock

DISPO = all(importlib.util.find_spec(m) for m in ("rich", "prompt_toolkit"))


class FauxEcran:
    def __init__(self, reponses, autoriser=True):
        self.reponses = list(reponses)
        self.autoriser = autoriser
        self.evenements = []

    def appeler(self, messages, cle):
        return self.reponses.pop(0)

    def demander(self, nom, args):
        self.evenements.append(("demande", nom))
        return self.autoriser

    def outil(self, nom, args, illisible=False):
        self.evenements.append(("outil", nom))

    def resultat(self, nom, texte):
        self.evenements.append(("resultat", nom, texte))

    def image(self, chemin):
        self.evenements.append(("image", chemin))

    def reponse(self, texte):
        self.evenements.append(("reponse", texte))

    def fin(self, secondes, usage=None):
        self.evenements.append(("fin",))
        self.usage = usage

    def arret(self, texte):
        self.evenements.append(("arret", texte))


def _appel(nom, args="{}"):
    return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": nom, "arguments": args}}]}}],
        "usage": {}}


def _texte(t):
    return {"choices": [{"message": {"role": "assistant", "content": t}}], "usage": {}}


@unittest.skipUnless(DISPO, "rich/prompt_toolkit absents")
class TestBoucle(unittest.TestCase):
    def setUp(self):
        import root
        self.root = root
        self.jour = {"entree": 0, "sortie": 0}
        # Pas d'écriture disque pendant ces tests. Remis en place après chaque
        # test : sinon les tests de mémoire lancés ensuite verraient ces vides.
        for cible, nom in ((root, "tokens_ajouter"),
                           (root.memoire, "enregistrer_tokens_reels"),
                           (root.memoire, "journaliser")):
            remplacement = mock.patch.object(cible, nom, lambda *a, **k: None)
            remplacement.start()
            self.addCleanup(remplacement.stop)

    def test_outil_sur_puis_reponse(self):
        e = FauxEcran([_appel("lister", '{"chemin": "."}'), _texte("Voilà.")])
        msgs = [{"role": "user", "content": "liste"}]
        self.root.un_tour(msgs, "cle", self.jour, ecran=e)
        types = [ev[0] for ev in e.evenements]
        self.assertEqual(types, ["outil", "resultat", "reponse", "fin"])  # outil sûr : pas de demande
        self.assertEqual(e.evenements[2], ("reponse", "Voilà."))

    def test_refus_respecte(self):
        e = FauxEcran([_appel("ecrire_fichier", '{"chemin": "/tmp/x", "contenu": "y"}'),
                       _texte("D'accord, je n'écris pas.")], autoriser=False)
        msgs = [{"role": "user", "content": "écris"}]
        self.root.un_tour(msgs, "cle", self.jour, ecran=e)
        self.assertIn(("demande", "ecrire_fichier"), e.evenements)
        self.assertIn(("resultat", "ecrire_fichier", "refusé"), e.evenements)
        outil_msg = [m for m in msgs if m.get("role") == "tool"][0]
        self.assertEqual(outil_msg["content"], "Refusé par l'utilisateur.")

    def test_tokens_du_tour_additionnes(self):
        a, b = _appel("lister", '{"chemin": "."}'), _texte("Fini.")
        a["usage"] = {"prompt_tokens": 100, "completion_tokens": 7}
        b["usage"] = {"prompt_tokens": 140, "completion_tokens": 20}
        e = FauxEcran([a, b])
        self.root.un_tour([{"role": "user", "content": "x"}], "cle", self.jour, ecran=e)
        self.assertEqual(e.usage, {"entree": 240, "sortie": 27})

    def test_arguments_illisibles(self):
        e = FauxEcran([_appel("lister", "{pas du json"), _texte("Corrigé.")])
        self.root.un_tour([{"role": "user", "content": "x"}], "cle", self.jour, ecran=e)
        self.assertIn(("resultat", "lister", "arguments JSON invalides"), e.evenements)


if __name__ == "__main__":
    unittest.main()
