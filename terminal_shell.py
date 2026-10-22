"""
Un vrai terminal dans la fenêtre de Root : un shell interactif (PTY).

Rien à voir avec l'outil `terminal` que le cerveau utilise. Ici, c'est Vincent
qui tape, comme dans Ghostty ou Terminal.app : un pseudo-terminal relié à son
shell. Le harness ne lit pas ce que tape Vincent et ne l'envoie nulle part ;
l'entrée et la sortie restent entre le PTY et la fenêtre.

fenetre.py relie ça à xterm.js : la sortie du shell part vers l'affichage
(octets en base64), les frappes reviennent vers le PTY.
"""

from __future__ import annotations

import base64
import fcntl
import os
import pty
import signal
import struct
import termios
import threading


def shell_par_defaut() -> str:
    return os.environ.get("SHELL") or "/bin/zsh"


class Shell:
    """Un shell interactif derrière un pseudo-terminal. `sortie` reçoit les
    octets bruts produits par le shell, au fil de l'eau, dans un fil dédié."""

    def __init__(self, sortie, fin=None, shell=None):
        self.sortie = sortie          # appelé avec des bytes
        self.fin = fin                # appelé (sans argument) quand le shell meurt
        self.shell = shell or shell_par_defaut()
        self.pid = None
        self.fd = None
        self._lecteur = None
        self._vivant = False

    def demarrer(self, colonnes=80, lignes=24, cwd=None) -> bool:
        if self._vivant:
            return True
        pid, fd = pty.fork()
        if pid == 0:                  # enfant : devient le shell
            try:
                if cwd and os.path.isdir(cwd):
                    os.chdir(cwd)
            except OSError:
                pass
            env = dict(os.environ, TERM="xterm-256color", COLORTERM="truecolor")
            env.pop("LINES", None)
            env.pop("COLUMNS", None)
            os.execvpe(self.shell, [self.shell, "-l"], env)
            os._exit(1)               # execvpe a échoué
        # parent
        self.pid, self.fd, self._vivant = pid, fd, True
        self.redimensionner(colonnes, lignes)
        self._lecteur = threading.Thread(target=self._lire, daemon=True)
        self._lecteur.start()
        return True

    def _lire(self):
        while self._vivant:
            try:
                data = os.read(self.fd, 65536)
            except OSError:
                break
            if not data:
                break
            try:
                self.sortie(data)
            except Exception:
                pass
        self._vivant = False
        if self.fin:
            try:
                self.fin()
            except Exception:
                pass

    def ecrire(self, data: bytes) -> None:
        if self._vivant and self.fd is not None:
            try:
                os.write(self.fd, data)
            except OSError:
                pass

    def redimensionner(self, colonnes: int, lignes: int) -> None:
        if self.fd is None:
            return
        try:
            paquet = struct.pack("HHHH", max(1, int(lignes)), max(1, int(colonnes)), 0, 0)
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, paquet)
            if self.pid:
                os.kill(self.pid, signal.SIGWINCH)
        except OSError:
            pass

    def arreter(self) -> None:
        self._vivant = False
        if self.pid:
            for sig in (signal.SIGHUP, signal.SIGTERM):
                try:
                    os.kill(self.pid, sig)
                except OSError:
                    pass
            try:
                os.waitpid(self.pid, os.WNOHANG)
            except OSError:
                pass
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
        self.pid = self.fd = None

    @property
    def vivant(self) -> bool:
        return self._vivant


def encoder(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def decoder(texte: str) -> bytes:
    return base64.b64decode(texte.encode("ascii"))
