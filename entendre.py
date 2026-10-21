"""
Entendre : capturer un court extrait audio et le transcrire en texte pour Root.

Root « voit » l'écran (capture + frames). « Entendre » est le pendant audio, mais
macOS ne laisse pas capturer l'audio SYSTÈME sans pièce dédiée : il faut un
périphérique virtuel (BlackHole) ou ScreenCaptureKit. Sans ça, on capture le
micro, toujours présent (utile pour une réunion, une consigne orale, une vidéo
écoutée à voix haute). La transcription a besoin d'un transcripteur local
(faster-whisper ou whisper) ; s'il manque, on le dit clairement plutôt que
d'inventer un texte entendu. Le cerveau de Root (DeepSeek) ne lit que du texte.

Aucune capture n'a lieu à l'import. La capture déclenche l'autorisation micro de
macOS la première fois, et reste bornée en durée pour ne pas chauffer la machine.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

DUREE_MAX = 60          # secondes : une capture plus longue est tronquée
FREQUENCE = 16000       # 16 kHz mono : ce qu'attendent les transcripteurs


def disponible_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def peripheriques() -> list[tuple[int, str]]:
    """Liste les périphériques audio d'entrée (AVFoundation) : [(index, nom), …].
    Un simple listing, sans capture ni autorisation."""
    if not disponible_ffmpeg():
        return []
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        capture_output=True, text=True)
    devices, dans_audio = [], False
    for ligne in p.stderr.splitlines():
        bas = ligne.lower()
        if "audio devices" in bas:
            dans_audio = True
            continue
        if "video devices" in bas:
            dans_audio = False
            continue
        if dans_audio:
            m = re.search(r"\[(\d+)\]\s+(.*)", ligne)
            if m:
                devices.append((int(m.group(1)), m.group(2).strip()))
    return devices


def transcripteur() -> str | None:
    """Nom du transcripteur Python local utilisable, ou None s'il faut en poser un."""
    for module in ("faster_whisper", "whisper"):
        if importlib.util.find_spec(module) is not None:
            return module
    return None


def capturer(secondes: int = 8, peripherique: int = 0, dossier: str | None = None) -> str:
    """Enregistre un extrait audio du périphérique donné dans un .wav mono 16 kHz.
    Renvoie le chemin du fichier. Déclenche l'autorisation micro la première fois."""
    if not disponible_ffmpeg():
        raise RuntimeError("ffmpeg absent : brew install ffmpeg.")
    secondes = max(1, min(int(secondes), DUREE_MAX))
    sortie = Path(dossier or tempfile.mkdtemp()) / "extrait.wav"
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-y", "-f", "avfoundation", "-i", f":{int(peripherique)}",
         "-t", str(secondes), "-ac", "1", "-ar", str(FREQUENCE), str(sortie)],
        capture_output=True, text=True)
    if r.returncode != 0 or not sortie.exists():
        detail = r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "cause inconnue"
        raise RuntimeError(f"capture audio échouée : {detail}")
    return str(sortie)


def transcrire(wav: str) -> str:
    """Transcrit un .wav en texte via le transcripteur local. Lève un message clair
    disant quoi poser s'il n'y en a pas."""
    module = transcripteur()
    if module is None:
        raise RuntimeError(
            "aucun transcripteur local : pose faster-whisper "
            "(~/.local/root-venv/bin/pip install faster-whisper) pour entendre en texte.")
    if module == "faster_whisper":
        from faster_whisper import WhisperModel
        segments, _ = WhisperModel("base").transcribe(wav)
        return " ".join(s.text.strip() for s in segments).strip()
    import whisper
    return whisper.load_model("base").transcribe(wav)["text"].strip()


def ecouter(secondes: int = 8, peripherique: int = 0) -> str:
    """Capture puis transcrit. Renvoie le texte entendu, et nettoie le fichier."""
    wav = capturer(secondes, peripherique)
    try:
        return transcrire(wav)
    finally:
        try:
            os.remove(wav)
        except OSError:
            pass


def etat() -> str:
    """Résumé honnête de ce qui est possible ici, sans rien capturer."""
    devices = peripheriques()
    noms = ", ".join(f"[{i}] {n}" for i, n in devices) or "aucun"
    systeme = any("blackhole" in n.lower() or "aggregate" in n.lower() or "loopback" in n.lower()
                  for _, n in devices)
    t = transcripteur()
    return (f"Périphériques audio : {noms}.\n"
            f"Audio système : {'capturable' if systeme else 'non (pose BlackHole pour l entendre)'}.\n"
            f"Transcripteur : {t or 'aucun (pose faster-whisper)'}.")


if __name__ == "__main__":
    print(etat())
