"""
Agir hors du navigateur : clics et frappes au niveau du système macOS.

Root voit l'écran avec `capture_ecran`, puis agit ici : elle peut cliquer et
taper dans n'importe quelle application, pas seulement dans Brave.

Outil utilisé : **cliclick** (binaire MIT), jamais osascript keystroke — c'est
une règle, après un incident où une frappe est partie dans la mauvaise fenêtre.
cliclick clique et tape à des coordonnées précises, ce qui est plus sûr.

Prérequis : l'autorisation « Accessibilité » pour le terminal (Ghostty) dans
Réglages Système > Confidentialité et sécurité. macOS la demande à la première
action ; tant qu'elle n'est pas donnée, les clics et frappes n'ont aucun effet.

Toutes ces actions sont marquées « système » dans root.py : Root demande la
permission de l'utilisateur avant chacune, par défaut (elles sont puissantes).
"""

import subprocess

CLICLICK = "/opt/homebrew/bin/cliclick"


def _lancer(args, entree=None):
    r = subprocess.run([CLICLICK] + args, capture_output=True, text=True,
                       timeout=15, input=entree)
    return (r.stdout + r.stderr).strip()


def position_souris() -> str:
    """Position actuelle du curseur, au format 'x,y'. Lecture seule, sans effet."""
    return _lancer(["p:."]) or "(position indisponible)"


def cliquer(x: int, y: int) -> str:
    _lancer([f"c:{int(x)},{int(y)}"])
    return f"Clic à ({int(x)}, {int(y)})."


def double_cliquer(x: int, y: int) -> str:
    _lancer([f"dc:{int(x)},{int(y)}"])
    return f"Double-clic à ({int(x)}, {int(y)})."


def clic_droit(x: int, y: int) -> str:
    _lancer([f"rc:{int(x)},{int(y)}"])
    return f"Clic droit à ({int(x)}, {int(y)})."


def taper(texte: str) -> str:
    """Tape le texte dans la fenêtre active (frappe par frappe). Les accents
    dépendent de la disposition clavier courante ; pour un texte complexe,
    préférer un champ web via navigateur.py quand c'est possible."""
    _lancer([f"t:{texte}"])
    return f"Tapé : {texte[:60]}" + ("…" if len(texte) > 60 else "")


def touche(nom: str = "return") -> str:
    """Appuie une touche spéciale : return, esc, space, tab, delete,
    arrow-up/down/left/right, page-up/down, home, end, fn, f1…f16."""
    _lancer([f"kp:{nom}"])
    return f"Touche : {nom}"
