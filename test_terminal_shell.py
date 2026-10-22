"""Le vrai terminal (PTY) : un shell démarre, répond à ce qu'on tape, se
redimensionne et s'arrête proprement. Aucun réseau. Sauté si pas d'os PTY."""

import importlib.util
import time
import unittest

DISPO = importlib.util.find_spec("pty") is not None
if DISPO:
    import terminal_shell


@unittest.skipUnless(DISPO, "pty absent")
class TestShell(unittest.TestCase):
    def test_demarre_execute_et_rend_la_sortie(self):
        recu = []
        sh = terminal_shell.Shell(lambda d: recu.append(d), shell="/bin/sh")
        self.assertTrue(sh.demarrer(80, 24))
        self.addCleanup(sh.arreter)
        time.sleep(0.4)
        sh.ecrire(b"echo PONG_123\n")
        time.sleep(0.5)
        sortie = b"".join(recu).decode("utf-8", "replace")
        self.assertIn("PONG_123", sortie)
        self.assertTrue(sh.vivant)

    def test_fin_appelee_quand_le_shell_se_termine(self):
        fini = []
        sh = terminal_shell.Shell(lambda d: None, fin=lambda: fini.append(True), shell="/bin/sh")
        sh.demarrer(80, 24)
        self.addCleanup(sh.arreter)
        sh.ecrire(b"exit\n")
        for _ in range(20):
            if fini:
                break
            time.sleep(0.1)
        self.assertTrue(fini)
        self.assertFalse(sh.vivant)

    def test_redimensionner_ne_plante_pas(self):
        sh = terminal_shell.Shell(lambda d: None, shell="/bin/sh")
        sh.demarrer(80, 24)
        self.addCleanup(sh.arreter)
        sh.redimensionner(120, 40)                 # ne lève pas

    def test_arreter_est_idempotent(self):
        sh = terminal_shell.Shell(lambda d: None, shell="/bin/sh")
        sh.demarrer(80, 24)
        sh.arreter()
        sh.arreter()                               # second appel sans erreur
        self.assertFalse(sh.vivant)

    def test_encoder_decoder(self):
        self.assertEqual(terminal_shell.decoder(terminal_shell.encoder(b"\x00\xff\x7e")), b"\x00\xff\x7e")


if __name__ == "__main__":
    unittest.main()
