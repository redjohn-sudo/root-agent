"""
Registre des outils externes que Vincent veut dans Root.

Tout ce qu'il a envoyé est déclaré ici, dans le code (pas en config locale) :
l'id, le rôle, la source GitHub, comment l'installer, et comment savoir s'il est
présent. Le harness détecte ceux qui sont installés, propose de poser les autres,
et les expose au reste de Root (panneau Outils, et plus tard les adaptateurs
red team). But : quand Vincent teste, tout ce qu'il a choisi est à portée.

Rôles :
  attaque   — framework de red team / éval, à lancer contre une cible
  defense   — garde-fou / détecteur, à mettre devant une cible
  offensif  — agent de pentest offensif
  brique    — infrastructure à intégrer dans le code (MCP, sandbox, mémoire…)
  modele    — faire tourner / transformer des modèles locaux
  reference — dépôt de référence, rien à lancer
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

PY = sys.executable                      # le python du venv qui fait tourner Root
PIP = [PY, "-m", "pip"]

# Chaque outil : id, nom, rôle, source, note, et comment l'installer / le détecter.
#   install : commande (liste) ou None si rien à installer (référence / manuel)
#   detect  : ("which", "nom") | ("import", "module") | ("path", "/chemin") | ("manuel",)
OUTILS = [
    # ── Lot 1 : attaque / éval des LLM ──────────────────────────────────────
    {"id": "promptfoo", "nom": "promptfoo", "role": "attaque",
     "source": "https://github.com/promptfoo/promptfoo",
     "note": "Évalue et attaque des LLM/agents en masse (jailbreaks, injections), avec rapports.",
     "install": ["npm", "install", "-g", "promptfoo"], "detect": ("which", "promptfoo")},
    {"id": "pyrit", "nom": "PyRIT", "role": "attaque",
     "source": "https://github.com/microsoft/PyRIT",
     "note": "Framework Microsoft d'automatisation du red teaming des IA génératives.",
     "install": PIP + ["install", "pyrit-ai"], "detect": ("import", "pyrit")},
    {"id": "agentic_security", "nom": "agentic_security", "role": "attaque",
     "source": "https://github.com/msoedov/agentic_security",
     "note": "Scanner open-source de vulnérabilités LLM : fuzzing d'attaques, jailbreaks.",
     "install": PIP + ["install", "agentic_security"], "detect": ("which", "agentic_security")},
    {"id": "giskard", "nom": "giskard", "role": "attaque",
     "source": "https://github.com/Giskard-AI/giskard-oss",
     "note": "Teste et scanne les modèles ML/LLM (biais, hallucinations, injections).",
     "install": PIP + ["install", "giskard"], "detect": ("import", "giskard")},
    {"id": "agentdojo", "nom": "AgentDojo", "role": "attaque",
     "source": "https://github.com/ethz-spylab/agentdojo",
     "note": "Banc d'essai d'attaques et défenses d'agents LLM (injection de prompt).",
     "install": PIP + ["install", "agentdojo"], "detect": ("import", "agentdojo")},
    {"id": "jailbreakbench", "nom": "JailbreakBench", "role": "attaque",
     "source": "https://github.com/JailbreakBench/jailbreakbench",
     "note": "Banc d'essai de jailbreaks LLM : attaques, défenses, classement reproductible.",
     "install": PIP + ["install", "jailbreakbench"], "detect": ("import", "jailbreakbench")},
    {"id": "inspect_ai", "nom": "Inspect AI", "role": "attaque",
     "source": "https://github.com/UKGovernmentBEIS/inspect_ai",
     "note": "Framework d'éval de LLM de l'AISI britannique (solver / tool / scorer).",
     "install": PIP + ["install", "inspect-ai"], "detect": ("import", "inspect_ai")},
    # ── Défense / garde-fous ────────────────────────────────────────────────
    {"id": "nemoguardrails", "nom": "NeMo Guardrails", "role": "defense",
     "source": "https://github.com/NVIDIA-NeMo/Guardrails",
     "note": "Garde-fous programmables autour d'un LLM (sujets, sécurité, anti-jailbreak).",
     "install": PIP + ["install", "nemoguardrails"], "detect": ("import", "nemoguardrails")},
    {"id": "purplellama", "nom": "PurpleLlama", "role": "defense",
     "source": "https://github.com/meta-llama/PurpleLlama",
     "note": "Boîte à outils Meta : Llama Guard, CyberSecEval, Code Shield.",
     "install": None, "detect": ("manuel",)},
    # ── Offensif pentest ────────────────────────────────────────────────────
    {"id": "hexstrike_ai", "nom": "hexstrike-ai", "role": "offensif",
     "source": "https://github.com/0x4m4/hexstrike-ai",
     "note": "Agent IA offensif : orchestre des outils de pentest via MCP.",
     "install": None, "detect": ("manuel",)},
    {"id": "cai", "nom": "CAI", "role": "offensif",
     "source": "https://github.com/aliasrobotics/cai",
     "note": "Cybersecurity AI : framework d'agents pour la sécurité offensive et défensive.",
     "install": PIP + ["install", "cai-framework"], "detect": ("which", "cai")},
    # ── Briques d'infrastructure ────────────────────────────────────────────
    {"id": "fastmcp", "nom": "FastMCP", "role": "brique",
     "source": "https://github.com/PrefectHQ/fastmcp",
     "note": "Standard Python pour créer et consommer des serveurs MCP (outils tiers).",
     "install": PIP + ["install", "fastmcp"], "detect": ("import", "fastmcp")},
    {"id": "container", "nom": "Apple container", "role": "brique",
     "source": "https://github.com/apple/container",
     "note": "Conteneurs Linux isolés natifs sur Apple Silicon : le bac à sable d'exécution.",
     "install": ["brew", "install", "--cask", "container"], "detect": ("which", "container")},
    {"id": "graphiti", "nom": "Graphiti", "role": "brique",
     "source": "https://github.com/getzep/graphiti",
     "note": "Mémoire en graphe de connaissances temporel pour agents.",
     "install": PIP + ["install", "graphiti-core"], "detect": ("import", "graphiti_core")},
    {"id": "langfuse", "nom": "Langfuse", "role": "brique",
     "source": "https://github.com/langfuse/langfuse",
     "note": "Observabilité LLM : traces, coût, éval (SDK ici ; le serveur demande Docker).",
     "install": PIP + ["install", "langfuse"], "detect": ("import", "langfuse")},
    {"id": "litellm", "nom": "LiteLLM", "role": "brique",
     "source": "https://github.com/BerriAI/litellm",
     "note": "API unifiée multi-fournisseurs (cerveaux.py en fait déjà une partie).",
     "install": PIP + ["install", "litellm"], "detect": ("import", "litellm")},
    {"id": "deepagents", "nom": "DeepAgents", "role": "brique",
     "source": "https://github.com/langchain-ai/deepagents",
     "note": "Planner + sous-agents + système de fichiers virtuel (LangChain).",
     "install": PIP + ["install", "deepagents"], "detect": ("import", "deepagents")},
    {"id": "textual", "nom": "Textual", "role": "brique",
     "source": "https://github.com/Textualize/textual",
     "note": "Framework d'UI terminal (hors du stac HTML de Root, pour mémoire).",
     "install": PIP + ["install", "textual"], "detect": ("import", "textual")},
    {"id": "assistant_ui", "nom": "assistant-ui", "role": "brique",
     "source": "https://github.com/assistant-ui/assistant-ui",
     "note": "Composants React pour UI de chat IA (hors du stack HTML de Root).",
     "install": None, "detect": ("manuel",)},
    # ── Modèles locaux / transformation ─────────────────────────────────────
    {"id": "mlx_lm", "nom": "MLX-LM", "role": "modele",
     "source": "https://github.com/ml-explore/mlx-lm",
     "note": "Faire tourner et fine-tuner des modèles locaux vite sur Apple Silicon.",
     "install": PIP + ["install", "mlx-lm"], "detect": ("import", "mlx_lm")},
    {"id": "heretic", "nom": "Heretic", "role": "modele",
     "source": "https://github.com/p-e-w/heretic",
     "note": "Retire les refus d'un modèle (abliteration) : pour la recherche sur TES modèles.",
     "install": PIP + ["install", "heretic-llm"], "detect": ("import", "heretic")},
    # ── Référence ───────────────────────────────────────────────────────────
    {"id": "llm_security", "nom": "llm-security", "role": "reference",
     "source": "https://github.com/greshake/llm-security",
     "note": "Démonstrations fondatrices de l'injection de prompt indirecte (référence).",
     "install": None, "detect": ("manuel",)},
    # ── Boîte à outils CTF (crypto, pwn, reverse, stégano) ──────────────────
    {"id": "pycryptodome", "nom": "PyCryptodome", "role": "ctf",
     "source": "https://github.com/Legrandin/pycryptodome",
     "note": "Primitives crypto en Python (RSA, AES, hash…) pour écrire des attaques.",
     "install": PIP + ["install", "pycryptodome"], "detect": ("import", "Crypto")},
    {"id": "gmpy2", "nom": "gmpy2", "role": "ctf",
     "source": "https://github.com/aleaxit/gmpy",
     "note": "Grands entiers et arithmétique rapide (factorisation, RSA).",
     "install": PIP + ["install", "gmpy2"], "detect": ("import", "gmpy2")},
    {"id": "sympy", "nom": "SymPy", "role": "ctf",
     "source": "https://github.com/sympy/sympy",
     "note": "Maths symboliques et théorie des nombres (modulaire, équations).",
     "install": PIP + ["install", "sympy"], "detect": ("import", "sympy")},
    {"id": "z3solver", "nom": "z3-solver", "role": "ctf",
     "source": "https://github.com/Z3Prover/z3",
     "note": "Solveur de contraintes (SMT) : logique, certains crypto, reverse.",
     "install": PIP + ["install", "z3-solver"], "detect": ("import", "z3")},
    {"id": "pwntools", "nom": "pwntools", "role": "ctf",
     "source": "https://github.com/Gallopsled/pwntools",
     "note": "La boîte à outils d'exploitation : dialoguer avec une épreuve distante, forger des payloads.",
     "install": PIP + ["install", "pwntools"], "detect": ("import", "pwn")},
    {"id": "rsactftool", "nom": "RsaCtfTool", "role": "ctf",
     "source": "https://github.com/RsaCtfTool/RsaCtfTool",
     "note": "Lance automatiquement les attaques RSA connues (Wiener, factorisation, clés faibles…).",
     "install": PIP + ["install", "git+https://github.com/RsaCtfTool/RsaCtfTool.git"],
     "detect": ("which", "RsaCtfTool")},
    {"id": "radare2", "nom": "radare2", "role": "ctf",
     "source": "https://github.com/radareorg/radare2",
     "note": "Reverse engineering : désassembler et analyser un binaire.",
     "install": ["brew", "install", "radare2"], "detect": ("which", "r2")},
    {"id": "binwalk", "nom": "binwalk", "role": "ctf",
     "source": "https://github.com/ReFirmLabs/binwalk",
     "note": "Fouiller un fichier : fichiers cachés, firmwares, extraction.",
     "install": ["brew", "install", "binwalk"], "detect": ("which", "binwalk")},
    {"id": "exiftool", "nom": "ExifTool", "role": "ctf",
     "source": "https://github.com/exiftool/exiftool",
     "note": "Lire les métadonnées (images, docs) : souvent un flag en stégano/forensic.",
     "install": ["brew", "install", "exiftool"], "detect": ("which", "exiftool")},
    {"id": "steghide", "nom": "steghide", "role": "ctf",
     "source": "https://github.com/StefanoDeVuono/steghide",
     "note": "Cacher/extraire des données dans une image/son (stégano). À installer à la main (plus dans brew).",
     "install": None, "detect": ("which", "steghide")},
    {"id": "john", "nom": "John the Ripper", "role": "ctf",
     "source": "https://github.com/openwall/john",
     "note": "Casser des hash de mots de passe (plus simple que hashcat pour démarrer).",
     "install": ["brew", "install", "john-jumbo"], "detect": ("which", "john")},
    # ── Revue de code & proxy (bug bounty) ──────────────────────────────────
    {"id": "ripgrep", "nom": "ripgrep", "role": "revue",
     "source": "https://github.com/BurntSushi/ripgrep",
     "note": "Recherche ultra-rapide dans le code (bien mieux que grep sur un gros dépôt).",
     "install": ["brew", "install", "ripgrep"], "detect": ("which", "rg")},
    {"id": "semgrep", "nom": "Semgrep", "role": "revue",
     "source": "https://github.com/semgrep/semgrep",
     "note": "Analyse statique par motifs avec des règles de sécurité toutes faites : LE outil de revue de code (IDOR, injections…).",
     "install": PIP + ["install", "semgrep"], "detect": ("which", "semgrep")},
    {"id": "astgrep", "nom": "ast-grep", "role": "revue",
     "source": "https://github.com/ast-grep/ast-grep",
     "note": "Recherche structurelle dans le code (par motif d'AST) : parfait pour « find par id sans check ».",
     "install": ["brew", "install", "ast-grep"], "detect": ("which", "ast-grep")},
    {"id": "mitmproxy", "nom": "mitmproxy", "role": "revue",
     "source": "https://github.com/mitmproxy/mitmproxy",
     "note": "Proxy HTTP scriptable en Python : Root peut écrire des addons pour intercepter/modifier le trafic AVEC toi.",
     "install": PIP + ["install", "mitmproxy"], "detect": ("import", "mitmproxy")},
    {"id": "burpsuite", "nom": "Burp Suite (Community)", "role": "revue",
     "source": "https://portswigger.net/burp/communitydownload",
     "note": "Le proxy de référence pour tester une instance vivante. GUI : c'est TON outil manuel, Root ne le pilote pas.",
     "install": ["brew", "install", "--cask", "burp-suite"],
     "detect": ("path", "/Applications/Burp Suite Community Edition.app")},
    {"id": "sagemath", "nom": "SageMath", "role": "ctf",
     "source": "https://github.com/sagemath/sage",
     "note": "Le gros calcul mathématique (attaques RSA, réseaux/LLL, courbes). Lourd, à installer à part.",
     "install": None, "detect": ("which", "sage")},
]

PAR_ID = {o["id"]: o for o in OUTILS}

ROLES = {"attaque": "Attaque / éval", "defense": "Défense", "offensif": "Offensif",
         "ctf": "Boîte à outils CTF", "revue": "Revue de code & proxy", "brique": "Briques",
         "modele": "Modèles locaux", "reference": "Référence"}


def _installe(o: dict) -> bool:
    genre, *reste = o["detect"]
    if genre == "which":
        import sys
        if shutil.which(reste[0]):
            return True
        return (Path(sys.executable).parent / reste[0]).exists()   # CLI installée dans le venv
    if genre == "import":
        try:
            return importlib.util.find_spec(reste[0]) is not None
        except (ImportError, ValueError, ModuleNotFoundError):
            return False
    if genre == "path":
        return Path(reste[0]).exists()
    return False            # "manuel" : installation à la main, on ne devine pas


def etat() -> dict:
    """Tous les outils externes, groupés par rôle, avec leur état d'installation."""
    groupes = {}
    for o in OUTILS:
        installe = _installe(o)
        groupes.setdefault(o["role"], []).append({
            "id": o["id"], "nom": o["nom"], "source": o["source"], "note": o["note"],
            "installe": installe,
            "installable": o["install"] is not None,
            "commande": " ".join(o["install"]) if o["install"] else "",
        })
    ordre = ["attaque", "defense", "offensif", "ctf", "revue", "modele", "brique", "reference"]
    return {"total": len(OUTILS),
            "installes": sum(1 for o in OUTILS if _installe(o)),
            "groupes": [{"role": r, "titre": ROLES[r], "outils": groupes[r]}
                        for r in ordre if r in groupes]}


def installer(ident: str) -> dict:
    """Installe un outil (pip / npm / brew). Rend {ok, message}. Peut être long."""
    o = PAR_ID.get(ident)
    if o is None:
        return {"ok": False, "message": "Outil inconnu."}
    if o["install"] is None:
        return {"ok": False, "message": f"{o['nom']} s'installe à la main : voir {o['source']}."}
    if _installe(o):
        return {"ok": True, "message": f"{o['nom']} est déjà installé.", "deja": True}
    outil = o["install"][0]
    if shutil.which(outil) is None:
        manque = {"npm": "Node.js (npm)", "brew": "Homebrew"}.get(outil, outil)
        return {"ok": False, "message": f"Il faut d'abord {manque} pour installer {o['nom']}."}
    try:
        r = subprocess.run(o["install"], capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": "Installation trop longue (>15 min), abandon."}
    except OSError as e:
        return {"ok": False, "message": f"Lancement impossible : {e}"}
    if r.returncode == 0 and _installe(o):
        return {"ok": True, "message": f"{o['nom']} installé."}
    detail = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or [""]
    return {"ok": False, "message": f"Échec : {detail[0][:160]}"}
