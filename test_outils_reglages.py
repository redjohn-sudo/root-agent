"""Panneau Outils : couper, restreindre, l'autonomie et l'auto-exécution du
terminal. On vérifie surtout que l'auto-exécution est ÉTEINTE par défaut et ne
saute la demande QUE si Vincent l'a activée et a autorisé la commande."""

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

DISPO = importlib.util.find_spec("rich") is not None
if DISPO:
    import root
    import outils_reglages as ou


@unittest.skipUnless(DISPO, "rich absent")
class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="test-ou-")) / "reglages.json"
        import fenetre
        p = mock.patch.object(fenetre, "REGLAGES", self.tmp)
        p.start(); self.addCleanup(p.stop)
        for nom, val in (("OUTILS_COUPES", set()), ("OUTILS_STRICTS", set()),
                         ("TERMINAL_AUTO_ACTIF", False), ("TERMINAL_AUTO", []), ("AUTONOMIE", "large")):
            q = mock.patch.object(root, nom, type(val)(val) if val != "large" else val)
            q.start(); self.addCleanup(q.stop)


class TestCouperRestreindre(Base):
    def test_couper_retire_du_schema_et_resynchro(self):
        avant = len(root.schema_pour_deepseek())
        ou.basculer("entendre", True)
        self.assertIn("entendre", root.OUTILS_COUPES)
        self.assertEqual(len(root.schema_pour_deepseek()), avant - 1)
        self.assertNotIn("entendre", [f["function"]["name"] for f in root.schema_pour_deepseek()])
        ou.basculer("entendre", False)
        self.assertNotIn("entendre", root.OUTILS_COUPES)

    def test_strict_force_la_demande_sur_un_outil_sur(self):
        self.assertFalse(root.doit_demander("lire_fichier", {"chemin": "x"}))
        ou.rendre_strict("lire_fichier", True)
        self.assertTrue(root.doit_demander("lire_fichier", {"chemin": "x"}))

    def test_prereglage_lecture_seule(self):
        ou.appliquer_prereglage("lecture")
        self.assertIn("ecrire_fichier", root.OUTILS_COUPES)
        self.assertIn("web_cliquer", root.OUTILS_COUPES)
        self.assertNotIn("lire_fichier", root.OUTILS_COUPES)
        self.assertEqual(ou.etat()["actif"], "lecture")

    def test_etat_liste_les_familles(self):
        d = ou.etat()
        noms = [o["id"] for f in d["familles"] for o in f["outils"]]
        self.assertIn("terminal", noms)
        self.assertEqual(d["terminal_auto"], {"actif": False, "prefixes": []})


class TestAutoTerminal(Base):
    def cmd(self, c):
        return root.doit_demander("terminal", {"commande": c})

    def test_eteint_par_defaut_demande_pour_commande_dangereuse(self):
        self.assertFalse(ou.etat()["terminal_auto"]["actif"])
        self.assertTrue(self.cmd("curl http://exemple"))     # dangereuse → demande
        self.assertFalse(self.cmd("ls -la"))                 # inoffensive en large → pas de demande

    def test_active_sans_prefixe_ne_saute_rien(self):
        ou.terminal_auto_activer(True)
        self.assertTrue(root.TERMINAL_AUTO_ACTIF)
        self.assertTrue(self.cmd("curl http://exemple"))     # activé mais aucun préfixe autorisé

    def test_prefixe_autorise_saute_la_demande(self):
        ou.terminal_auto_activer(True)
        ou.terminal_auto_prefixes(["curl http://10.0.0.1", "nmap"])
        self.assertFalse(self.cmd("nmap -sV 10.0.0.1"))      # autorisé → pas de demande
        self.assertFalse(self.cmd("curl http://10.0.0.1/x")) # autorisé
        self.assertTrue(self.cmd("curl http://autre-cible")) # hors liste → demande

    def test_desactiver_remet_la_demande(self):
        # curl est dangereux : en large il déclenche la demande, sauf s'il est autorisé
        ou.terminal_auto_activer(True); ou.terminal_auto_prefixes(["curl http://10.0.0.1"])
        self.assertFalse(self.cmd("curl http://10.0.0.1/x"))
        ou.terminal_auto_activer(False)
        self.assertTrue(self.cmd("curl http://10.0.0.1/x"))

    def test_prudente_demande_meme_si_autorise(self):
        ou.terminal_auto_activer(True); ou.terminal_auto_prefixes(["ls"])
        self.assertFalse(self.cmd("ls -la"))                 # large + autorisé : pas de demande
        ou.choisir_autonomie("prudente")
        self.assertTrue(self.cmd("ls -la"))                  # prudente : on demande pour tout

    def test_prefixes_nettoyes(self):
        ou.terminal_auto_prefixes(["  nmap ", "nmap", "", "  "])
        self.assertEqual(ou.terminal_auto()["prefixes"], ["nmap"])


if __name__ == "__main__":
    unittest.main()
