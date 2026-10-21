"""Tests hors ligne de entendre.py : parsing des périphériques, détection du
transcripteur, bornes de durée, dégradation honnête. Aucune capture réelle."""

import subprocess
import unittest
from unittest import mock

import entendre

SORTIE_FFMPEG = """\
[AVFoundation indev] AVFoundation video devices:
[AVFoundation indev] [0] FaceTime HD Camera
[AVFoundation indev] AVFoundation audio devices:
[AVFoundation indev] [0] Micro MacBook Pro
[AVFoundation indev] [1] BlackHole 2ch
"""


class TestEntendre(unittest.TestCase):
    def test_peripheriques_parse_audio_seulement(self):
        faux = mock.Mock(stderr=SORTIE_FFMPEG, returncode=0)
        with mock.patch.object(entendre.shutil, "which", return_value="/x/ffmpeg"), \
             mock.patch.object(entendre.subprocess, "run", return_value=faux):
            devs = entendre.peripheriques()
        # on ne garde que la section audio, pas la caméra
        self.assertEqual(devs, [(0, "Micro MacBook Pro"), (1, "BlackHole 2ch")])

    def test_peripheriques_sans_ffmpeg(self):
        with mock.patch.object(entendre.shutil, "which", return_value=None):
            self.assertEqual(entendre.peripheriques(), [])

    def test_transcrire_sans_transcripteur_dit_quoi_poser(self):
        with mock.patch.object(entendre, "transcripteur", return_value=None):
            with self.assertRaises(RuntimeError) as e:
                entendre.transcrire("/tmp/x.wav")
        self.assertIn("faster-whisper", str(e.exception))

    def test_capturer_borne_la_duree(self):
        vu = {}

        def faux_run(cmd, **kw):
            vu["cmd"] = cmd
            # simule un échec propre pour ne rien écrire sur le disque
            return mock.Mock(returncode=1, stderr="boom")

        with mock.patch.object(entendre.shutil, "which", return_value="/x/ffmpeg"), \
             mock.patch.object(entendre.subprocess, "run", side_effect=faux_run):
            with self.assertRaises(RuntimeError):
                entendre.capturer(secondes=9999, peripherique=0)
        self.assertIn(str(entendre.DUREE_MAX), vu["cmd"])  # tronqué à DUREE_MAX

    def test_capturer_sans_ffmpeg(self):
        with mock.patch.object(entendre.shutil, "which", return_value=None):
            with self.assertRaises(RuntimeError):
                entendre.capturer()

    def test_etat_ne_capture_rien(self):
        with mock.patch.object(entendre, "peripheriques", return_value=[(0, "Micro MacBook Pro")]), \
             mock.patch.object(entendre, "transcripteur", return_value=None):
            texte = entendre.etat()
        self.assertIn("Micro MacBook Pro", texte)
        self.assertIn("BlackHole", texte)      # suggère quoi poser pour l'audio système
        self.assertIn("faster-whisper", texte)


if __name__ == "__main__":
    unittest.main()
