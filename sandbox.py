"""
Exécuter un script dans un bac à sable, pour que Root écrive et lance son propre
code en toute sûreté, et itère sur plusieurs essais (le vrai levier pour le CTF).

macOS `sandbox-exec` (intégré, aucune installation) confine le processus :
  - écriture limitée au dossier de travail temporaire (pas le reste du disque) ;
  - lecture autorisée (les outils ont besoin de leurs libs) ;
  - réseau autorisé par défaut (une épreuve CTF distante en a besoin), coupable.
Et surtout un TIMEOUT dur : un script qui boucle ne fige jamais Root.

Le dossier de travail est jetable. Rien n'est exécuté sans que l'appelant le
veuille : côté Root, l'outil passe par la demande d'autorisation habituelle.
"""

from __future__ import annotations

import os
import shutil
import sys
import subprocess
import tempfile
from pathlib import Path

# Python = celui de Root (ses bibliothèques installées : sympy, pwntools, Crypto…).
INTERPRETEURS = {
    "python": [sys.executable],
    "bash": ["bash"],
    "sh": ["sh"],
}
SORTIE_MAX = 20000                   # caractères de sortie gardés
TIMEOUT_DEFAUT = 30
TIMEOUT_MAX = 300


def _profil(travail: Path, reseau: bool) -> str:
    """Profil Seatbelt : lecture ok, écriture seulement dans le dossier de travail,
    réseau selon le drapeau. Volontairement simple et lisible."""
    lignes = [
        "(version 1)",
        "(allow default)",                        # base permissive, on retire ensuite
        "(deny file-write*)",                     # pas d'écriture…
        f'(allow file-write* (subpath "{travail}"))',   # …sauf le dossier de travail
        '(allow file-write* (subpath "/private/tmp") (subpath "/private/var/folders"))',
        "(allow file-write-data (literal \"/dev/null\") (literal \"/dev/stdout\") (literal \"/dev/stderr\"))",
    ]
    if not reseau:
        lignes.append("(deny network*)")
    return "\n".join(lignes)


def executer(code: str, langage: str = "python", timeout: int = TIMEOUT_DEFAUT,
             reseau: bool = True, args: list[str] | None = None) -> dict:
    """Écrit `code`, le lance en bac à sable avec un timeout, rend le résultat.
    Retourne {ok, code_retour, sortie, timeout, erreur}."""
    base = INTERPRETEURS.get(langage)
    if base is None:
        return {"ok": False, "erreur": f"Langage non géré : {langage}. Choisis python, bash ou sh."}
    exe = base[0] if Path(base[0]).exists() else shutil.which(base[0])
    if exe is None:
        return {"ok": False, "erreur": f"Interpréteur introuvable : {base[0]}."}
    timeout = max(1, min(int(timeout or TIMEOUT_DEFAUT), TIMEOUT_MAX))

    travail = Path(tempfile.mkdtemp(prefix="root-bac-"))
    ext = {"python": "py", "bash": "sh", "sh": "sh"}[langage]
    script = travail / f"script.{ext}"
    script.write_text(code, encoding="utf-8")
    profil = travail / "profil.sb"
    profil.write_text(_profil(travail, reseau), encoding="utf-8")

    cmd = ["sandbox-exec", "-f", str(profil), exe, *base[1:], str(script), *(args or [])]
    env = {"PATH": str(Path(sys.executable).parent) + ":/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin",
           "HOME": str(travail), "TMPDIR": str(travail),
           "PYTHONPATH": os.environ.get("PYTHONPATH", "")}
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           cwd=str(travail), env=env)
    except subprocess.TimeoutExpired as e:
        return {"ok": False, "timeout": True,
                "sortie": _borner((e.stdout or "") + (e.stderr or "")),
                "erreur": f"Script arrêté : plus de {timeout} s."}
    except OSError as e:
        return {"ok": False, "erreur": f"Lancement impossible : {e}"}
    finally:
        shutil.rmtree(travail, ignore_errors=True)

    sortie = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr.strip() else "")
    return {"ok": r.returncode == 0, "code_retour": r.returncode,
            "sortie": _borner(sortie) or "(aucune sortie)", "timeout": False}


def _borner(t: str) -> str:
    t = t or ""
    return t if len(t) <= SORTIE_MAX else t[:SORTIE_MAX] + "\n… (sortie tronquée)"
