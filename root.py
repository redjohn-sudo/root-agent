#!/usr/bin/env python3
"""
Root — un harness d'agent écrit de zéro, habillé comme Claude Code.

Un « harness », c'est toute la machinerie autour du modèle :
  1. on envoie au modèle la conversation + la liste des outils qu'il peut appeler ;
  2. le modèle répond soit par du texte, soit par une demande d'appel d'outil ;
  3. si c'est un outil, on l'exécute (après vérification des permissions) et on
     renvoie le résultat au modèle ;
  4. on recommence jusqu'à ce que le modèle n'ait plus d'outil à appeler.

C'est exactement ce que fait Claude Code. Ici tout est visible, ligne à ligne,
et l'allure du terminal est la même : ton message sur fond gris, ses réponses
derrière un point vert, les appels d'outils comme des puces, la zone de saisie
entre deux traits et la barre d'état en bas.

Le cerveau : DeepSeek, en direct (API compatible OpenAI).
Ancienne version (sans l'habillage) : ~/Projets/root-harness/root.py.avant-claude
"""

import base64
import datetime
import json
import math
import mimetypes
import os
import random
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

import securite        # masquage des secrets, gardes fichiers/URL/chemins (Lot 2)
import memoire         # contexte + mémoire durable (conception de Kimi K3)
import action_systeme  # cliquer/taper hors navigateur (puissance d'action)
import recherche       # recherche web approfondie et sourcée (Claude cloud)
import autonomie       # suivi de tâche et budgets (Codex) — budget de durée câblé
import verification    # registre de preuves (Codex), support d'autonomie
import immunite        # Hide and Seek : erreur rencontrée une fois, retrouvée ailleurs (Codex)
import entendre        # capture audio + transcription : le pendant de « voir l'écran »
import consentement    # accord humain pour un acte irréversible, lié à l'empreinte exacte (Codex)
import sandbox         # exécuter un script isolé avec timeout (le levier CTF)
import cerveaux        # plusieurs LLM interchangeables derrière la même âme (fenêtre)
import lecture         # garde d'entrée : lecture ancrée du contenu non fiable

from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.segment import Segment, Segments
from rich.table import Table
from rich.text import Text
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style

# ─────────────────────────────────────────────────────────────────────────────
# Réglages
# ─────────────────────────────────────────────────────────────────────────────

ICI = Path(__file__).parent
AME = (ICI / "ame.md").read_text(encoding="utf-8")

# Cerveau de Root. Deux backends possibles :
#   "claude"   : API Anthropic (crédits de l'utilisateur), modèle fort, via un adaptateur.
#   "deepseek" : API compatible OpenAI, en direct.
CERVEAU = "deepseek"
BASE_URL = "https://api.deepseek.com"
MODELE = "deepseek-flash"          # DeepSeek V4.1 Flash (id confirmé via /models)
MODELE_CLAUDE = "claude-sonnet-5-5"   # cerveau Claude (bon rapport puissance/coût)
URL_CLAUDE = "https://api.anthropic.com/v1/messages"
MODELE_ACTIF = MODELE_CLAUDE if CERVEAU == "claude" else MODELE

# La clé vit dans le .env du profil Hermes, on la lit sans l'afficher.
def charger_cle():
    var = "ANTHROPIC_API_KEY" if CERVEAU == "claude" else "DEEPSEEK_API_KEY"
    if os.environ.get(var):
        return os.environ[var]
    env = Path.home() / ".hermes" / "profiles" / "racine" / ".env"
    if env.exists():
        for ligne in env.read_text(encoding="utf-8").splitlines():
            if ligne.startswith(var + "="):
                return ligne.split("=", 1)[1].strip().strip('"').strip("'")
    return None

# Autonomie de Root. « large » = elle agit seule, SAUF pour ce qui détruit des
# données ou sort de la machine : là, elle demande à l'utilisateur. Mets "prudente"
# pour qu'elle demande à chaque action qui modifie quoi que ce soit.
AUTONOMIE = "large"

# Pilotés par le panneau Outils de la fenêtre (outils_reglages.py). Par défaut,
# rien n'est coupé, rien n'est rendu plus strict, et l'auto-exécution terminal
# est ÉTEINTE : aucune commande ne saute la demande d'accord tant que Vincent
# ne l'a pas activée lui-même et n'a pas listé ce qu'il autorise.
OUTILS_COUPES: set[str] = set()
OUTILS_STRICTS: set[str] = set()
OUTILS_PERSO: set[str] = set()      # noms des outils ajoutés par Vincent (outils_reglages)
TERMINAL_AUTO_ACTIF = False
TERMINAL_AUTO: list[str] = []

# Garde-fous de la boucle (Lot 1, inspiré d'Hermes).
MAX_ETAPES = 30          # nombre maxi d'allers-retours modèle dans un seul tour
REPRISES = 4             # tentatives sur erreur réseau / surcharge du serveur
SEUIL_TOKENS = int(memoire.BUDGET_FENETRE * memoire.SEUIL_COMPRESSION)  # compression du contexte

VERT = "#3f9d84"; VERT_FONCE = "#2c7a66"; GRIS = "#8a8a96"
DIODE_ON, DIODE_OFF = "#7fd0ff", "#3a6a88"
FOND_TOI = "#3a3a40"
console = Console(highlight=False)

# Compteur de tokens, cumulé par jour dans un petit fichier (chiffres seulement).
TOKENS_FICHIER = Path.home() / ".local" / "root-tokens.json"


def tokens_charger():
    """Les tokens déjà consommés aujourd'hui (entrée, sortie)."""
    aujourdhui = datetime.date.today().isoformat()
    base = {}
    if TOKENS_FICHIER.exists():
        try:
            base = json.loads(TOKENS_FICHIER.read_text(encoding="utf-8"))
        except Exception:
            base = {}
    j = base.get(aujourdhui, {"entree": 0, "sortie": 0})
    return {"entree": j.get("entree", 0), "sortie": j.get("sortie", 0)}


def tokens_ajouter(jour, entree, sortie):
    """Ajoute les tokens d'un appel au total du jour et sauvegarde."""
    jour["entree"] += entree
    jour["sortie"] += sortie
    aujourdhui = datetime.date.today().isoformat()
    base = {}
    if TOKENS_FICHIER.exists():
        try:
            base = json.loads(TOKENS_FICHIER.read_text(encoding="utf-8"))
        except Exception:
            base = {}
    base[aujourdhui] = {"entree": jour["entree"], "sortie": jour["sortie"]}
    TOKENS_FICHIER.parent.mkdir(parents=True, exist_ok=True)
    TOKENS_FICHIER.write_text(json.dumps(base), encoding="utf-8")


def fmt_k(n):
    return f"{n/1000:.1f}k" if n >= 1000 else str(n)

# Ce qu'elle fait pendant qu'elle réfléchit, comme les verbes de Claude Code.
VERBES = ["Réfléchit", "Écoute la Machine", "Cherche le mot juste",
          "Pèse le pour et le contre", "Relit son âme", "Prépare ses outils",
          "Suit le fil", "Tend l'oreille"]

# Son symbole : l'oreillette, copiée de ~/Projets/root-identite/symbole.py.
OREILLETTE = [
    "................",
    "...oooo....L....",
    "..owwhho....L...",
    ".ouuwwwwo.L..L..",
    ".ouuwwLLo..L..L.",
    ".owwwwLLo..L..L.",
    "..owwwwso.L..L..",
    "...owwwso...L...",
    "....owso........",
    "....owso........",
    "....owso........",
    "....owso........",
    "....owso........",
    "....owso........",
    ".....oo.........",
    "................",
]
TEINTES = {"o": "#8a8a96", "w": "#d8d8de", "h": "#ffffff", "s": "#aeaeb8",
           "u": "#3e3e48", "L": "#7fd0ff"}
DIODE = [(6, 4), (7, 4), (6, 5), (7, 5)]


def logo(diode=True):
    """Les 16x16 pixels en 8 lignes de demi-blocs : chaque caractère porte
    deux pixels l'un sur l'autre. La diode est allumée quand Root est prête."""
    def teinte(x, y):
        c = OREILLETTE[y][x]
        if c == "L" and (x, y) in DIODE:
            return DIODE_ON if diode else DIODE_OFF
        if c == "L":   # les ondes : la voix de la Machine
            return TEINTES["L"] if diode else None
        return TEINTES.get(c)
    lignes = []
    for y in range(0, 16, 2):
        t = Text()
        for x in range(16):
            haut, bas = teinte(x, y), teinte(x, y + 1)
            if haut and bas:
                t.append("▀", style=f"{haut} on {bas}")
            elif haut:
                t.append("▀", style=haut)
            elif bas:
                t.append("▄", style=bas)
            else:
                t.append(" ")
        lignes.append(t)
    return lignes


def puce(couleur, contenu):
    """Un point de couleur devant un bloc, le bloc en retrait, comme Claude Code."""
    g = Table.grid(padding=(0, 1))
    g.add_column(width=1, no_wrap=True)
    g.add_column(ratio=1)
    g.add_row(Text("●", style=couleur), contenu)
    return g


# ── La signature « Console de la Machine » ───────────────────────────────────
# Root est une présence qui écoute : une onde qui pulse, et sa voix encadrée d'un
# liseré vert vertical, comme une transmission qui descend le long de l'écran.
_NIVEAUX = "▁▂▃▄▅▆▇█"


def onde(largeur=9, phase=0.0):
    """Une petite onde sonore en demi-blocs verts, décalée par `phase` (animation)."""
    t = Text()
    for i in range(largeur):
        v = (math.sin(phase + i * 0.7) + 1) / 2          # 0..1, vague qui défile
        t.append(_NIVEAUX[min(len(_NIVEAUX) - 1, int(v * len(_NIVEAUX)))], style=VERT)
    return t


def transmission(contenu, couleur=VERT):
    """Un renderable précédé d'un liseré vertical ┃ sur CHAQUE ligne : la voix de
    Root, sa signature visuelle. Marche avec du texte comme avec du Markdown."""
    options = console.options.update_width(max(10, console.width - 2))
    style = console.get_style(couleur)
    segments = []
    for ligne in console.render_lines(contenu, options, pad=False):
        segments.append(Segment("┃ ", style))
        segments.extend(ligne)
        segments.append(Segment("\n"))
    return Segments(segments)


def message_toi(texte):
    """Ton message sur fond gris, comme dans Claude Code."""
    largeur = console.width
    for i, ligne in enumerate(texte.split("\n")):
        t = Text(("› " if i == 0 else "  ") + ligne, style=f"on {FOND_TOI}")
        t.pad_right(max(0, largeur - t.cell_len))
        console.print(t, no_wrap=False, crop=False)


class Attente:
    """La ligne d'attente : diode qui respire, verbe qui tourne, secondes."""
    def __init__(self):
        self.debut = time.time()
        self.premier = random.randrange(len(VERBES))

    def __rich_console__(self, cons, options):
        ecoule = time.time() - self.debut
        verbe = VERBES[(self.premier + int(ecoule) // 8) % len(VERBES)]
        t = Text()
        t.append_text(onde(7, phase=ecoule * 3))        # l'onde qui pulse pendant qu'elle réfléchit
        t.append("  " + verbe + "… ", style=VERT)
        t.append(f"({int(ecoule)}s · ctrl-c pour l'interrompre)", style=GRIS)
        yield t


# ─────────────────────────────────────────────────────────────────────────────
# Les médias : montrer des photos et des vidéos à Root
#   DeepSeek sait lire les images (png, jpeg, webp, gif). Il ne lit pas la vidéo
#   en mouvement : pour une vidéo, on extrait quelques images réparties avec
#   ffmpeg et on les lui montre — elle voit des captures, pas le film.
# ─────────────────────────────────────────────────────────────────────────────

IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
VID_EXT = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
FRAMES_VIDEO = 6        # nombre d'images extraites d'une vidéo


def image_en_data_url(p: Path) -> str:
    """Encode une image en data URL base64 pour l'API (format OpenAI)."""
    mime = mimetypes.guess_type(str(p))[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"


def extraire_frames(video: Path, n: int = FRAMES_VIDEO, largeur: int = 768):
    """Extrait n images réparties dans la vidéo (via ffmpeg). Renvoie leurs chemins."""
    dossier = Path(tempfile.mkdtemp(prefix="root-frames-"))
    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
        capture_output=True, text=True).stdout.strip()
    try:
        dur = float(dur)
    except ValueError:
        dur = 0.0
    frames = []
    instants = [dur * (i + 0.5) / n for i in range(n)] if dur > 0 else [0.0]
    for i, t in enumerate(instants):
        out = dossier / f"f{i:02d}.png"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(video),
             "-frames:v", "1", "-vf", f"scale={largeur}:-1", str(out)],
            capture_output=True)
        if out.is_file():
            frames.append(out)
    return frames


def extraire_medias(saisie: str):
    """Sépare la saisie en (texte, images, vidéos) : tout bout qui est un chemin
    vers un fichier image ou vidéo existant devient un média, le reste est le texte.
    Gère les chemins glissés dans le terminal (espaces échappés, guillemets)."""
    try:
        morceaux = shlex.split(saisie)
    except ValueError:
        return saisie, [], []       # guillemet non fermé : on prend tout comme texte
    images, videos, mots = [], [], []
    for m in morceaux:
        p = Path(m).expanduser()
        ext = p.suffix.lower()
        if p.is_file() and ext in IMG_EXT:
            images.append(p)
        elif p.is_file() and ext in VID_EXT:
            videos.append(p)
        else:
            mots.append(m)
    if not images and not videos:
        return saisie, [], []       # aucun média : on garde la saisie telle quelle
    return " ".join(mots), images, videos


def construire_contenu(texte, images, frames_video, source="média"):
    """Construit le champ content du message : du texte simple s'il n'y a pas de
    média, sinon une liste texte + images au format attendu par l'API.

    Chaque image est précédée d'une étiquette horodatée (memoire.ligne_image) :
    quand elaguer_images retirera l'image, cette étiquette reste, pour que Root
    sache ce qu'elle avait vu et quand, sans garder les octets."""
    if not images and not frames_video:
        return texte
    note = texte or "Regarde."
    if frames_video:
        note += (f"\n\n(Pour la vidéo : {len(frames_video)} images extraites à "
                 "intervalles réguliers. Tu vois des captures, pas le mouvement.)")
    parties = [{"type": "text", "text": note}]
    for p in images:
        parties.append({"type": "text", "text": memoire.ligne_image(source)})
        parties.append({"type": "image_url", "image_url": {"url": image_en_data_url(p)}})
    for p in frames_video:
        parties.append({"type": "text", "text": memoire.ligne_image(source + " (vidéo)")})
        parties.append({"type": "image_url", "image_url": {"url": image_en_data_url(p)}})
    return parties


# ─────────────────────────────────────────────────────────────────────────────
# Les outils : chacun est une vraie fonction Python + sa description pour le modèle
# ─────────────────────────────────────────────────────────────────────────────

def outil_lire_fichier(chemin: str) -> str:
    bloque = securite.lecture_bloquee(chemin)   # .env, ~/.ssh, clés… : lecture interdite
    if bloque:
        return bloque
    p = Path(chemin).expanduser()
    if not p.is_file():
        return f"ERREUR : {chemin} n'est pas un fichier."
    texte = p.read_text(encoding="utf-8", errors="replace")
    return securite.rediger_secrets(texte, lecture_fichier=True)  # troncation faite dans un_tour


def outil_lister(chemin: str = ".") -> str:
    p = Path(chemin).expanduser()
    if not p.is_dir():
        return f"ERREUR : {chemin} n'est pas un dossier."
    entrees = sorted(e.name + ("/" if e.is_dir() else "") for e in p.iterdir())
    return "\n".join(entrees) or "(dossier vide)"


def outil_terminal(commande: str) -> str:
    # Garde : empêcher le terminal de contourner la liste noire de fichiers
    # (ex. `cat .env`, lecture de ~/.ssh). On inspecte chaque argument.
    try:
        jetons = shlex.split(commande)
    except ValueError:
        jetons = commande.split()
    for jeton in jetons:
        bloque = securite.lecture_bloquee(jeton) or securite.ecriture_bloquee(jeton)
        if bloque:
            return f"Refusé (sécurité) : {bloque}"
    r = subprocess.run(commande, shell=True, capture_output=True, text=True,
                       timeout=120, cwd=os.getcwd())
    sortie = (r.stdout or "") + (r.stderr or "")
    # La sortie peut contenir des secrets lus dans un fichier : masquage agressif.
    return securite.rediger_secrets(
        f"[code {r.returncode}]\n{sortie or '(aucune sortie)'}", lecture_fichier=True)


def outil_ecrire_fichier(chemin: str, contenu: str) -> str:
    bloque = securite.ecriture_bloquee(chemin)  # ne pas écraser clés/credentials/système
    if bloque:
        return bloque
    p = Path(chemin).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(contenu, encoding="utf-8")
    return f"Écrit : {p} ({len(contenu)} caractères)."


def capturer_ecran() -> Path:
    """Prend une capture silencieuse de l'écran principal et renvoie son chemin.
    `screencapture -x` = sans le son d'obturateur ; demande l'autorisation
    « Enregistrement de l'écran » à l'app (macOS la demande une fois). On réduit
    l'image à 1680 px de large avec `sips` (toujours présent sur macOS, aucune
    dépendance), pour qu'elle parte vite sans perdre le texte."""
    dossier = Path(tempfile.mkdtemp(prefix="root-ecran-"))
    brute = dossier / "brute.png"
    subprocess.run(["screencapture", "-x", str(brute)], capture_output=True)
    if not brute.is_file():
        return brute
    reduite = dossier / "ecran.png"
    try:
        subprocess.run(["sips", "-Z", "1680", str(brute), "--out", str(reduite)],
                       capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return brute
    return reduite if reduite.is_file() else brute


def outil_executer_script(code: str, langage: str = "python", timeout: int = 30) -> str:
    r = sandbox.executer(code, langage=langage, timeout=timeout)
    if not r.get("ok") and r.get("erreur") and "sortie" not in r:
        return "ERREUR : " + r["erreur"]
    tete = ""
    if r.get("timeout"):
        tete = r["erreur"] + "\n"
    elif not r.get("ok"):
        tete = f"(code de retour {r.get('code_retour')})\n"
    return tete + r.get("sortie", "")


def outil_capture_ecran() -> dict:
    """Outil appelé par Root : capture l'écran pour qu'elle le voie."""
    out = capturer_ecran()
    if not out.is_file():
        return {"texte": "ERREUR : Root n'a pas l'autorisation « Enregistrement de "
                "l'écran » sur ce Mac. N'insiste pas et n'essaie pas une commande "
                "terminal : dis à l'utilisateur d'aller dans Réglages Système > "
                "Confidentialité et sécurité > Enregistrement de l'écran, et d'y "
                "cocher Root. Pour une PAGE WEB, utilise web_voir, qui renvoie déjà "
                "une capture, sans cette autorisation."}
    return {"_image": out, "texte": "Écran capturé."}


# ── Le navigateur : Root voit et pilote les pages web dans Brave ──────────────
_BRAVE = None


def nav():
    """Le navigateur de Root, démarré à la première utilisation (fenêtre visible)."""
    global _BRAVE
    if _BRAVE is None:
        import navigateur
        _BRAVE = navigateur.Brave(visible=True)
    return _BRAVE


def _sans_image(r):
    """Retire la capture : les ACTIONS renvoient l'état en texte, pas une image.
    Seuls web_voir et capture_ecran montrent une image (quand Vincent veut voir)."""
    return {k: v for k, v in r.items() if k != "_image"} if isinstance(r, dict) else r


def outil_web_naviguer(url: str) -> dict:
    ok, raison = securite.url_sure(url)         # bloque IP internes + métadonnées cloud
    if not ok:
        return {"texte": f"URL bloquée (sécurité) : {raison}"}
    return _sans_image(nav().naviguer(url))


def outil_web_voir() -> dict:
    return nav().apercu()


def outil_web_source() -> str:
    return nav().source()


def outil_web_cliquer(cible: str) -> dict:
    return _sans_image(nav().cliquer(cible))


def outil_web_ecrire(champ: str, texte: str) -> dict:
    return _sans_image(nav().ecrire(champ, texte))


def outil_web_entree() -> dict:
    return _sans_image(nav().touche("Enter"))


def outil_web_defiler(pixels: int = 800) -> dict:
    return _sans_image(nav().defiler(pixels))


def outil_web_onglets() -> str:
    onglets = nav().onglets()
    if not onglets:
        return "Aucun onglet ouvert."
    return "\n".join(
        f"{o['n']}. {'▶ ' if o['actif'] else '  '}{o['titre'] or '(sans titre)'} — {o['url']}"
        for o in onglets)


def outil_web_nouvel_onglet(url: str = "") -> dict:
    if url:
        ok, raison = securite.url_sure(url)
        if not ok:
            return {"texte": f"URL bloquée (sécurité) : {raison}"}
    return _sans_image(nav().nouvel_onglet(url or "about:blank"))


def outil_web_basculer(onglet: str) -> dict:
    return _sans_image(nav().basculer(onglet))


def outil_web_fermer_onglet(onglet: str) -> dict:
    return _sans_image(nav().fermer_onglet(onglet))


def outil_memoire_noter(categorie: str, fait: str) -> str:
    return memoire.memoire_noter(categorie, fait)


def outil_memoire_oublier(motif: str) -> str:
    return memoire.memoire_oublier(motif)


def outil_verifier_citation(reference: str, extrait: str) -> str:
    # On vérifie contre le texte RÉELLEMENT lu (mémorisé par le harness sous cette
    # référence), pas contre une source fournie par le modèle : sinon il pourrait
    # inventer la source et l'extrait ensemble et « s'auto-vérifier ».
    ok, motif = lecture.verifier_reference(reference, extrait)
    return ("VÉRIFIÉ : " if ok else "REJETÉ : ") + motif


# ── Immunité (Codex) : Hide and Seek. Une erreur corrigée une fois devient un
# anticorps ; si le même motif reparaît ailleurs, Root est alertée. Les alertes
# sont des CANDIDATS, jamais une correction automatique : la boucle reste libre.
_IMMUNITE = None


def _immu():
    # Instance paresseuse : l'import de root.py ne crée pas la base locale.
    global _IMMUNITE
    if _IMMUNITE is None:
        _IMMUNITE = immunite.Immunite()
    return _IMMUNITE


def outil_immunite_verifier(texte: str, lieu: str = "") -> str:
    trouvailles = _immu().chercher(texte, lieu)
    if not trouvailles:
        return "Aucun anticorps déclenché : rien de déjà rencontré ici."
    lignes = [f"⚠ {t['regle']} — déclenché par « {t['extrait'][:80]} »"
              f"{' (origine : ' + t['origine'] + ')' if t['origine'] else ''}"
              for t in trouvailles]
    return ("Alertes candidates (aucune correction automatique, à toi de juger) :\n"
            + "\n".join(lignes))


def outil_immunite_apprendre(regle: str, detecteur: str, origine: str = "") -> str:
    try:
        ident = _immu().apprendre(regle, detecteur, origine)
    except immunite.RegexInvalide:
        return "Détecteur refusé : la regex ne compile pas. Reformule le motif."
    return f"Anticorps retenu ({ident[:12]}). Ce motif sera signalé s'il reparaît ailleurs."


def outil_immunite_actifs() -> str:
    actifs = _immu().actifs()
    if not actifs:
        return "Aucun anticorps actif pour l'instant."
    return "\n".join(f"{a['id'][:12]} — {a['regle']}" for a in actifs)


def outil_immunite_oublier(anticorps_id: str) -> str:
    return "Anticorps oublié." if _immu().oublier(anticorps_id) else "Aucun anticorps avec cet identifiant."


# ── Entendre : capturer un extrait audio et le transcrire en texte. Le pendant
# de « voir l'écran ». La capture est bornée en durée et demande confirmation.
def outil_entendre_etat() -> str:
    return entendre.etat()


def outil_entendre(secondes: int = 8, peripherique: int = 0) -> str:
    try:
        texte = entendre.ecouter(secondes, peripherique)
    except RuntimeError as e:
        return f"Impossible d'entendre : {e}"
    return f"Entendu (transcription) : {texte}" if texte else "Entendu : silence (aucune parole captée)."


# ── Consentement : pour un acte IRRÉVERSIBLE (envoyer, publier, soumettre), Root
# demande l'accord de l'utilisateur, lié au contenu et à la cible EXACTS. Si la
# charge change, l'accord est périmé. Après l'acte, marquer_fait évite de le
# rejouer. C'est additif : rien ne bloque la boucle libre, Root s'en sert d'elle-même.
def outil_consentement_verifier(description: str, cible: str, canal: str = "") -> str:
    ok, motif = consentement.peut_agir(description, cible, canal)
    return ("ACCORDÉ : " if ok else "PAS D'ACCORD : ") + motif


def outil_consentement_demander(description: str, cible: str, canal: str = "") -> str:
    # Cet outil est à risque « systeme » : le harness demande confirmation à
    # l'utilisateur AVANT de l'exécuter. S'il approuve, on arrive ici et on
    # enregistre l'accord durable ; s'il refuse, cette fonction n'est jamais appelée.
    consentement.accorder(description, cible, canal)
    return f"Accord enregistré pour cette charge exacte (cible : {cible[:60]}). Tu peux agir."


def outil_consentement_marquer_fait(description: str, cible: str, canal: str = "") -> str:
    consentement.marquer_fait(description, cible, canal)
    return "Marqué comme fait : cet acte exact ne sera pas rejoué (idempotence)."


def outil_consentement_oublier(description: str, cible: str, canal: str = "") -> str:
    consentement.oublier(description, cible, canal)
    return "Accord oublié pour cette charge."


# ── Action système : agir hors du navigateur (clics/frappes via cliclick) ─────
def outil_ecran_position() -> str:
    return action_systeme.position_souris()


def outil_ecran_cliquer(x: int, y: int) -> str:
    return action_systeme.cliquer(x, y)


def outil_ecran_double_cliquer(x: int, y: int) -> str:
    return action_systeme.double_cliquer(x, y)


def outil_ecran_taper(texte: str) -> str:
    return action_systeme.taper(texte)


def outil_ecran_touche(nom: str = "return") -> str:
    return action_systeme.touche(nom)


# La table des outils : la fonction + son schéma (ce que le modèle voit) + le
# niveau de risque (pour la permission). "sûr" = lecture seule, "modifie" =
# touche au disque, "sortie" = agit vers l'extérieur.
OUTILS = {
    "lire_fichier": {
        "fn": outil_lire_fichier, "risque": "sûr",
        "schema": {"description": "Lire le contenu d'un fichier texte.",
                   "parameters": {"type": "object", "properties": {
                       "chemin": {"type": "string"}}, "required": ["chemin"]}},
    },
    "lister": {
        "fn": outil_lister, "risque": "sûr",
        "schema": {"description": "Lister le contenu d'un dossier.",
                   "parameters": {"type": "object", "properties": {
                       "chemin": {"type": "string"}}, "required": []}},
    },
    "terminal": {
        "fn": outil_terminal, "risque": "variable",
        "schema": {"description": "Exécuter une commande shell et renvoyer sa sortie.",
                   "parameters": {"type": "object", "properties": {
                       "commande": {"type": "string"}}, "required": ["commande"]}},
    },
    "executer_script": {
        "fn": outil_executer_script, "risque": "sandbox",
        "schema": {"description": "Écrire et exécuter un script (python, bash) dans un "
                   "BAC À SABLE isolé, avec un timeout. Pour calculer, résoudre un "
                   "challenge, ou lancer un outil (pwntools, RsaCtfTool, sympy…). "
                   "L'écriture est limitée à un dossier jetable, le réseau est permis. "
                   "Préfère cet outil au terminal pour du code sur plusieurs lignes et "
                   "les essais répétés : il n'affecte pas le reste de la machine.",
                   "parameters": {"type": "object", "properties": {
                       "code": {"type": "string"},
                       "langage": {"type": "string", "enum": ["python", "bash", "sh"]},
                       "timeout": {"type": "integer"}}, "required": ["code"]}},
    },
    "ecrire_fichier": {
        "fn": outil_ecrire_fichier, "risque": "modifie",
        "schema": {"description": "Écrire (ou écraser) un fichier texte.",
                   "parameters": {"type": "object", "properties": {
                       "chemin": {"type": "string"}, "contenu": {"type": "string"}},
                   "required": ["chemin", "contenu"]}},
    },
    "capture_ecran": {
        "fn": outil_capture_ecran, "risque": "sûr",
        "schema": {"description": "Capturer TOUT l'écran du Mac (les autres apps, le "
                   "bureau). Pour une page web, utilise plutôt web_voir. N'emploie "
                   "jamais une commande terminal (screencapture…) pour voir l'écran. "
                   "Demande l'autorisation Enregistrement de l'écran sur le Mac.",
                   "parameters": {"type": "object", "properties": {}, "required": []}},
    },
    "web_naviguer": {
        "fn": outil_web_naviguer, "risque": "web",
        "schema": {"description": "Ouvrir une page web dans le navigateur de Root "
                   "(Brave). Renvoie l'URL, le titre, tout le texte de la page et une "
                   "capture. C'est par là qu'on commence une tâche sur le web.",
                   "parameters": {"type": "object", "properties": {
                       "url": {"type": "string"}}, "required": ["url"]}},
    },
    "web_voir": {
        "fn": outil_web_voir, "risque": "sûr",
        "schema": {"description": "Regarder la page web actuelle : URL, titre, tout "
                   "son texte ET une capture de la page. C'est l'outil pour prendre "
                   "une photo/screenshot d'une page web (pas capture_ecran).",
                   "parameters": {"type": "object", "properties": {}, "required": []}},
    },
    "web_cliquer": {
        "fn": outil_web_cliquer, "risque": "web",
        "schema": {"description": "Cliquer sur un élément de la page : donne un bout "
                   "du texte visible du bouton/lien, ou un sélecteur CSS. Renvoie la "
                   "page après le clic.",
                   "parameters": {"type": "object", "properties": {
                       "cible": {"type": "string"}}, "required": ["cible"]}},
    },
    "web_ecrire": {
        "fn": outil_web_ecrire, "risque": "web",
        "schema": {"description": "Écrire du texte dans un champ : donne le champ "
                   "(placeholder, nom, label ou sélecteur) et le texte à saisir.",
                   "parameters": {"type": "object", "properties": {
                       "champ": {"type": "string"}, "texte": {"type": "string"}},
                   "required": ["champ", "texte"]}},
    },
    "web_entree": {
        "fn": outil_web_entree, "risque": "web",
        "schema": {"description": "Appuyer sur Entrée (valider une recherche, un "
                   "formulaire). Renvoie la page après.",
                   "parameters": {"type": "object", "properties": {}, "required": []}},
    },
    "web_defiler": {
        "fn": outil_web_defiler, "risque": "sûr",
        "schema": {"description": "Faire défiler la page vers le bas (ou vers le haut "
                   "avec un nombre négatif de pixels).",
                   "parameters": {"type": "object", "properties": {
                       "pixels": {"type": "integer"}}, "required": []}},
    },
    "web_source": {
        "fn": outil_web_source, "risque": "sûr",
        "schema": {"description": "Lire le code source HTML BRUT de la page actuelle, "
                   "avec les commentaires <!-- --> et les balises cachées. À utiliser "
                   "pour inspecter la source (challenges web, débogage), là où web_voir "
                   "ne montre que le texte visible.",
                   "parameters": {"type": "object", "properties": {}, "required": []}},
    },
    "web_onglets": {
        "fn": outil_web_onglets, "risque": "sûr",
        "schema": {"description": "Lister les onglets ouverts, numérotés, avec un repère "
                   "▶ sur celui que tu pilotes. Sert à t'y retrouver avant de basculer.",
                   "parameters": {"type": "object", "properties": {}, "required": []}},
    },
    "web_nouvel_onglet": {
        "fn": outil_web_nouvel_onglet, "risque": "web",
        "schema": {"description": "Ouvrir un nouvel onglet (sur une URL ou vide) et "
                   "basculer le pilotage dessus. Garde les autres onglets intacts.",
                   "parameters": {"type": "object", "properties": {
                       "url": {"type": "string"}}, "required": []}},
    },
    "web_basculer": {
        "fn": outil_web_basculer, "risque": "web",
        "schema": {"description": "Piloter un autre onglet : donne son numéro (voir "
                   "web_onglets), ou un bout de son titre ou de son URL. Le met devant.",
                   "parameters": {"type": "object", "properties": {
                       "onglet": {"type": "string"}}, "required": ["onglet"]}},
    },
    "web_fermer_onglet": {
        "fn": outil_web_fermer_onglet, "risque": "modifie",
        "schema": {"description": "Fermer un onglet (son numéro, titre ou URL). Si c'était "
                   "celui piloté, le pilotage reprend sur un autre onglet.",
                   "parameters": {"type": "object", "properties": {
                       "onglet": {"type": "string"}}, "required": ["onglet"]}},
    },
    "memoire_noter": {
        "fn": outil_memoire_noter, "risque": "sûr",
        "schema": {"description": "Noter un fait durable et utile au long cours dans "
                   "la mémoire de Root (convention de l'utilisateur, piège rencontré, "
                   "préférence). Jamais de donnée personnelle ni de secret. Donne une "
                   "catégorie courte et le fait en une phrase.",
                   "parameters": {"type": "object", "properties": {
                       "categorie": {"type": "string"}, "fait": {"type": "string"}},
                   "required": ["categorie", "fait"]}},
    },
    "memoire_oublier": {
        "fn": outil_memoire_oublier, "risque": "modifie",
        "schema": {"description": "Oublier (supprimer) de la mémoire durable les faits "
                   "qui contiennent ce motif.",
                   "parameters": {"type": "object", "properties": {
                       "motif": {"type": "string"}}, "required": ["motif"]}},
    },
    "verifier_citation": {
        "fn": outil_verifier_citation, "risque": "sûr",
        "schema": {"description": "Vérifier qu'un extrait que tu veux citer est bien "
                   "présent mot pour mot dans un contenu que tu as lu. Donne la "
                   "référence du contenu (W1, F1… telle qu'affichée dans le bloc lu) "
                   "et l'extrait. Les coupures « … » et les apostrophes sont gérées. "
                   "Sert à ne jamais affirmer un fait absent de la source.",
                   "parameters": {"type": "object", "properties": {
                       "reference": {"type": "string"}, "extrait": {"type": "string"}},
                   "required": ["reference", "extrait"]}},
    },
    "immunite_verifier": {
        "fn": outil_immunite_verifier, "risque": "sûr",
        "schema": {"description": "Confronter un texte (une erreur, une sortie, un message) "
                   "aux erreurs déjà rencontrées. Renvoie des ALERTES candidates si un motif "
                   "connu reparaît ; à toi de juger, rien n'est corrigé automatiquement. "
                   "« lieu » situe la rencontre (fichier, URL, étape).",
                   "parameters": {"type": "object", "properties": {
                       "texte": {"type": "string"}, "lieu": {"type": "string"}},
                   "required": ["texte"]}},
    },
    "immunite_apprendre": {
        "fn": outil_immunite_apprendre, "risque": "modifie",
        "schema": {"description": "Retenir une erreur que tu viens de comprendre, pour la "
                   "retrouver ailleurs plus tard. « regle » la décrit en une phrase, "
                   "« detecteur » est une expression régulière qui la repère, « origine » "
                   "dit d'où vient la leçon (une correction, un lieu, une date).",
                   "parameters": {"type": "object", "properties": {
                       "regle": {"type": "string"}, "detecteur": {"type": "string"},
                       "origine": {"type": "string"}},
                   "required": ["regle", "detecteur"]}},
    },
    "immunite_actifs": {
        "fn": outil_immunite_actifs, "risque": "sûr",
        "schema": {"description": "Lister les anticorps actifs (les erreurs retenues).",
                   "parameters": {"type": "object", "properties": {}, "required": []}},
    },
    "immunite_oublier": {
        "fn": outil_immunite_oublier, "risque": "modifie",
        "schema": {"description": "Désactiver un anticorps par son identifiant (son histoire "
                   "est gardée, il ne déclenche plus d'alerte).",
                   "parameters": {"type": "object", "properties": {
                       "anticorps_id": {"type": "string"}}, "required": ["anticorps_id"]}},
    },
    "entendre_etat": {
        "fn": outil_entendre_etat, "risque": "sûr",
        "schema": {"description": "Dire ce qui est possible côté audio : périphériques "
                   "d'entrée, si l'audio système est capturable, si un transcripteur est "
                   "posé. Ne capture rien. À consulter avant d'utiliser entendre.",
                   "parameters": {"type": "object", "properties": {}, "required": []}},
    },
    "entendre": {
        "fn": outil_entendre, "risque": "systeme",
        "schema": {"description": "Capturer un court extrait audio (le micro par défaut) et "
                   "le transcrire en texte. « secondes » borne la durée (max 60). "
                   "« peripherique » choisit l'entrée (voir entendre_etat). Sans "
                   "transcripteur posé, dit quoi installer au lieu d'inventer.",
                   "parameters": {"type": "object", "properties": {
                       "secondes": {"type": "integer"}, "peripherique": {"type": "integer"}},
                   "required": []}},
    },
    "consentement_verifier": {
        "fn": outil_consentement_verifier, "risque": "sûr",
        "schema": {"description": "Avant un acte IRRÉVERSIBLE (envoyer un message, publier, "
                   "soumettre un formulaire), vérifier si l'utilisateur a déjà donné son "
                   "accord pour ce contenu et cette cible EXACTS. Dit aussi si l'acte a "
                   "déjà été fait (ne pas le rejouer).",
                   "parameters": {"type": "object", "properties": {
                       "description": {"type": "string"}, "cible": {"type": "string"},
                       "canal": {"type": "string"}}, "required": ["description", "cible"]}},
    },
    "consentement_demander": {
        "fn": outil_consentement_demander, "risque": "systeme",
        "schema": {"description": "Demander à l'utilisateur son accord pour un acte "
                   "irréversible précis, décrit exactement (contenu, cible, canal). Son "
                   "approbation enregistre un accord durable pour cette charge exacte ; "
                   "si tu changes le contenu ou la cible ensuite, il faudra redemander.",
                   "parameters": {"type": "object", "properties": {
                       "description": {"type": "string"}, "cible": {"type": "string"},
                       "canal": {"type": "string"}}, "required": ["description", "cible"]}},
    },
    "consentement_marquer_fait": {
        "fn": outil_consentement_marquer_fait, "risque": "modifie",
        "schema": {"description": "APRÈS avoir réussi un acte irréversible, le marquer fait "
                   "pour qu'il ne soit jamais rejoué (idempotence, filet contre une reprise).",
                   "parameters": {"type": "object", "properties": {
                       "description": {"type": "string"}, "cible": {"type": "string"},
                       "canal": {"type": "string"}}, "required": ["description", "cible"]}},
    },
    "consentement_oublier": {
        "fn": outil_consentement_oublier, "risque": "modifie",
        "schema": {"description": "Oublier un accord enregistré pour une charge exacte.",
                   "parameters": {"type": "object", "properties": {
                       "description": {"type": "string"}, "cible": {"type": "string"},
                       "canal": {"type": "string"}}, "required": ["description", "cible"]}},
    },
    "ecran_position": {
        "fn": outil_ecran_position, "risque": "sûr",
        "schema": {"description": "Lire la position actuelle du curseur de la souris "
                   "(x,y). Utile pour se repérer avant de cliquer.",
                   "parameters": {"type": "object", "properties": {}, "required": []}},
    },
    "ecran_cliquer": {
        "fn": outil_ecran_cliquer, "risque": "systeme",
        "schema": {"description": "Cliquer à l'écran aux coordonnées x,y (hors "
                   "navigateur, dans n'importe quelle app). Regarde l'écran avec "
                   "capture_ecran d'abord pour viser juste.",
                   "parameters": {"type": "object", "properties": {
                       "x": {"type": "integer"}, "y": {"type": "integer"}},
                   "required": ["x", "y"]}},
    },
    "ecran_double_cliquer": {
        "fn": outil_ecran_double_cliquer, "risque": "systeme",
        "schema": {"description": "Double-cliquer à l'écran aux coordonnées x,y.",
                   "parameters": {"type": "object", "properties": {
                       "x": {"type": "integer"}, "y": {"type": "integer"}},
                   "required": ["x", "y"]}},
    },
    "ecran_taper": {
        "fn": outil_ecran_taper, "risque": "systeme",
        "schema": {"description": "Taper du texte dans la fenêtre active (hors "
                   "navigateur). À utiliser après avoir cliqué dans le bon champ.",
                   "parameters": {"type": "object", "properties": {
                       "texte": {"type": "string"}}, "required": ["texte"]}},
    },
    "ecran_touche": {
        "fn": outil_ecran_touche, "risque": "systeme",
        "schema": {"description": "Appuyer une touche spéciale dans la fenêtre active : "
                   "return, esc, space, tab, delete, arrow-up/down/left/right, etc.",
                   "parameters": {"type": "object", "properties": {
                       "nom": {"type": "string"}}, "required": []}},
    },
}

# Outils de recherche web approfondie et sourcée (module de Claude cloud).
OUTILS.update(recherche.OUTILS_RECHERCHE)

# Mots qui rendent une commande terminal dangereuse : on demandera avant.
VERBES_DANGEREUX = ("rm ", "rmdir", "mv ", "dd ", "mkfs", ">", ">>", "shutdown",
                    "reboot", "kill", "pkill", "chmod", "chown", "git push",
                    "curl", "wget", "scp", "ssh ", "nc ", "sudo")


def schema_pour_deepseek():
    """Traduit notre table d'outils dans le format attendu par l'API."""
    return [{"type": "function",
             "function": {"name": nom, **o["schema"]}} for nom, o in OUTILS.items()
            if nom not in OUTILS_COUPES]


# ─────────────────────────────────────────────────────────────────────────────
# La permission : faut-il demander à l'utilisateur avant cet appel d'outil ?
# ─────────────────────────────────────────────────────────────────────────────

def doit_demander(nom, args):
    o = OUTILS[nom]
    if nom in OUTILS_STRICTS:           # Vincent a demandé une confirmation sur cet outil
        return True
    if o["risque"] == "sûr":
        return False
    if o["risque"] == "systeme":
        # Cliquer/taper n'importe où sur le Mac est puissant et risqué : on
        # demande toujours, même en autonomie large (ajustable plus tard).
        return True
    if o["risque"] == "web":
        # Agir sur le web : en autonomie large, Root enchaîne seule (l'utilisateur ne
        # veut pas valider chaque clic) ; en prudente, on demande.
        return AUTONOMIE != "large"
    if o["risque"] == "sandbox":
        # Script isolé (écriture confinée + timeout) : comme le web, on demande en
        # prudente, on laisse faire en large pour permettre les essais répétés.
        return AUTONOMIE != "large"
    if o["risque"] == "modifie" or o["risque"] == "sortie":
        return True
    if nom == "terminal":
        cmd = args.get("commande", "")
        # Auto-exécution : seulement si Vincent l'a activée, en autonomie large, et
        # si la commande commence par un préfixe qu'il a lui-même autorisé. C'est
        # le SEUL endroit où une commande terminal peut sauter la demande.
        if AUTONOMIE == "large" and TERMINAL_AUTO_ACTIF and _terminal_autorise(cmd):
            return False
        dangereuse = any(v in cmd for v in VERBES_DANGEREUX)
        if AUTONOMIE == "large":
            return dangereuse           # large : on ne demande que si ça peut casser
        return True                     # prudente : on demande pour tout le terminal
    return True


def _terminal_autorise(cmd: str) -> bool:
    """La commande commence-t-elle par un des préfixes autorisés par Vincent ?
    Comparaison sur la commande nettoyée ; un préfixe vide n'autorise rien."""
    c = cmd.strip()
    return any(p.strip() and c.startswith(p.strip()) for p in TERMINAL_AUTO)


def demander(nom, args):
    console.print(puce("#e0a84a", Text.assemble(
        ("Root veut ", "#e0a84a"), (nom, "bold #e0a84a"),
        (f"  {json.dumps(args, ensure_ascii=False)}", GRIS))))
    rep = console.input(Text("  ⎿  autoriser ? [o/N] ", style=GRIS)).strip().lower()
    return rep in ("o", "oui", "y", "yes")


# ─────────────────────────────────────────────────────────────────────────────
# Le cerveau : un appel à DeepSeek, avec la ligne d'attente animée pendant
# ─────────────────────────────────────────────────────────────────────────────

# ── Adaptateur Claude : traduire entre le format OpenAI (celui du harness) et
#    l'API Anthropic, dans les deux sens, pour ne rien changer au reste du code.

def _outils_anthropic():
    """Nos outils OpenAI → format attendu par Anthropic."""
    return [{"name": nom, "description": o["schema"]["description"],
             "input_schema": o["schema"]["parameters"]}
            for nom, o in OUTILS.items()]


def _vers_anthropic(messages):
    """Convertit la conversation (format OpenAI) en (system, messages Anthropic).
    Fusionne les messages 'user' consécutifs (Anthropic préfère l'alternance)."""
    systeme, out = [], []

    def ajouter_user(blocs):
        if out and out[-1]["role"] == "user":
            out[-1]["content"].extend(blocs)
        else:
            out.append({"role": "user", "content": blocs})

    for m in messages:
        role, contenu = m.get("role"), m.get("content")
        if role == "system":
            if isinstance(contenu, str):
                systeme.append(contenu)
        elif role == "tool":
            txt = contenu if isinstance(contenu, str) else json.dumps(contenu)
            ajouter_user([{"type": "tool_result",
                           "tool_use_id": m.get("tool_call_id"), "content": txt}])
        elif role == "assistant":
            blocs = []
            if isinstance(contenu, str) and contenu:
                blocs.append({"type": "text", "text": contenu})
            elif isinstance(contenu, list):
                blocs += [{"type": "text", "text": p["text"]}
                          for p in contenu if isinstance(p, dict) and p.get("type") == "text"]
            for tc in (m.get("tool_calls") or []):
                try:
                    entree = json.loads(tc["function"].get("arguments") or "{}")
                except Exception:
                    entree = {}
                blocs.append({"type": "tool_use", "id": tc["id"],
                              "name": tc["function"]["name"], "input": entree})
            out.append({"role": "assistant", "content": blocs or [{"type": "text", "text": ""}]})
        else:  # user
            if isinstance(contenu, str):
                ajouter_user([{"type": "text", "text": contenu}])
            elif isinstance(contenu, list):
                blocs = []
                for p in contenu:
                    if not isinstance(p, dict):
                        continue
                    if p.get("type") == "text":
                        blocs.append({"type": "text", "text": p["text"]})
                    elif p.get("type") == "image_url":
                        url = p["image_url"]["url"]
                        if url.startswith("data:") and "," in url:
                            tete, b64 = url.split(",", 1)
                            media = tete.split(":", 1)[1].split(";", 1)[0]
                            blocs.append({"type": "image", "source": {
                                "type": "base64", "media_type": media, "data": b64}})
                ajouter_user(blocs or [{"type": "text", "text": ""}])
    return "\n\n".join(systeme), out


def appeler_modele_claude(messages, cle):
    """Appelle l'API Anthropic et renvoie une réponse au format OpenAI, pour que
    la boucle, le compteur de tokens et le reste du harness restent inchangés."""
    systeme, msgs = _vers_anthropic(messages)
    corps = json.dumps({
        "model": MODELE_CLAUDE, "max_tokens": 4000,
        "system": systeme, "messages": msgs, "tools": _outils_anthropic(),
    }).encode()
    req = urllib.request.Request(URL_CLAUDE, data=corps, headers={
        "content-type": "application/json", "x-api-key": cle,
        "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.load(r)
    texte, tool_calls = "", []
    for bloc in d.get("content", []):
        if bloc.get("type") == "text":
            texte += bloc.get("text", "")
        elif bloc.get("type") == "tool_use":
            tool_calls.append({"id": bloc["id"], "type": "function",
                "function": {"name": bloc["name"],
                             "arguments": json.dumps(bloc.get("input", {}), ensure_ascii=False)}})
    msg = {"role": "assistant", "content": texte or None}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    u = d.get("usage", {})
    return {"choices": [{"message": msg}],
            "usage": {"prompt_tokens": u.get("input_tokens", 0),
                      "completion_tokens": u.get("output_tokens", 0)}}


# Le cerveau choisi dans la fenêtre (un dict de cerveaux.json). None = le chemin
# historique ci-dessous (DeepSeek), celui du terminal.
CERVEAU_COURANT = None


def appeler_modele(messages, cle):
    if CERVEAU_COURANT is not None:
        return cerveaux.appeler(CERVEAU_COURANT, messages, schema_pour_deepseek())
    if CERVEAU == "claude":
        return appeler_modele_claude(messages, cle)
    corps = json.dumps({
        "model": MODELE,
        "messages": messages,
        "tools": schema_pour_deepseek(),
        "tool_choice": "auto",
        "max_tokens": 4000,
    }).encode()
    req = urllib.request.Request(
        BASE_URL + "/chat/completions", data=corps,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {cle}"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def appeler_modele_robuste(messages, cle):
    """Appelle le modèle en retentant sur les erreurs passagères (429, surcharge
    5xx, coupure réseau), avec un recul exponentiel + un peu d'aléa. Les erreurs
    définitives (400, 401, 402, 404) sont levées tout de suite : réessayer n'y
    changerait rien. Respecte l'en-tête Retry-After s'il est fourni."""
    derniere = None
    for tentative in range(REPRISES):
        try:
            return appeler_modele(messages, cle)
        except urllib.error.HTTPError as e:
            transitoire = (e.code == 429) or (500 <= e.code < 600)
            if not transitoire:
                raise
            derniere = e
            recul = min(60.0, 2.0 ** tentative) + random.uniform(0, 1)
            ra = e.headers.get("Retry-After") if e.headers else None
            if ra and str(ra).isdigit():
                recul = float(ra)
            time.sleep(recul)
        except urllib.error.URLError as e:
            derniere = e
            time.sleep(min(60.0, 2.0 ** tentative) + random.uniform(0, 1))
    raise derniere


def appeler_avec_attente(messages, cle):
    """Appelle DeepSeek dans un fil pendant qu'on anime la ligne d'attente.
    Renvoie la réponse JSON complète (message + usage des tokens)."""
    attente = Attente()
    boite = {}

    def tache():
        try:
            boite["data"] = appeler_modele_robuste(messages, cle)
        except Exception as e:
            boite["err"] = e

    fil = threading.Thread(target=tache)
    fil.start()
    with Live(attente, console=console, refresh_per_second=12, transient=True):
        while fil.is_alive():
            time.sleep(0.08)
    fil.join()
    if "err" in boite:
        raise boite["err"]
    return boite["data"]


# ─────────────────────────────────────────────────────────────────────────────
# La boucle de l'agent : le cœur du harness
# ─────────────────────────────────────────────────────────────────────────────

def executer_outil(nom, args):
    if nom not in OUTILS:
        return f"ERREUR : outil inconnu « {nom} »."
    try:
        return OUTILS[nom]["fn"](**args)
    except Exception as e:
        return f"ERREUR pendant {nom} : {e}"


def elaguer_images(messages):
    """Lot 3 : retire les images des vieux messages pour ne pas les renvoyer à
    chaque tour (elles coûtent cher et saturent la fenêtre). On garde seulement
    les images du DERNIER message qui en contient ; les autres deviennent un court
    texte. L'API ne voit donc qu'une image à la fois, la plus récente."""
    dernier = -1
    for i, m in enumerate(messages):
        c = m.get("content")
        if isinstance(c, list) and any(
                isinstance(p, dict) and p.get("type") == "image_url" for p in c):
            dernier = i
    if dernier < 0:
        return
    for i, m in enumerate(messages):
        if i == dernier:
            continue
        c = m.get("content")
        if isinstance(c, list):
            # On retire les images ; l'étiquette horodatée qui les précède
            # (posée par construire_contenu) reste et garde la trace.
            garde = [p for p in c
                     if not (isinstance(p, dict) and p.get("type") == "image_url")]
            m["content"] = garde or [{"type": "text", "text": "[image vue plus tôt]"}]


def resumer_blocs(blocs, cle):
    """Callback de compression (memoire.compresser_milieu) : résume chaque bloc en
    une phrase factuelle via le modèle. Un appel dédié, sans outils attendus. En
    cas d'échec, renvoie une liste vide : memoire retombe sur son résumé dégradé."""
    extraits = []
    for i, bloc in enumerate(blocs):
        texte = ""
        for m in bloc:
            c = m.get("content")
            if isinstance(c, str):
                texte += c[:400] + "\n"
        extraits.append(f"BLOC {i + 1} :\n{texte[:1200]}")
    prompt = ("Résume chaque BLOC en UNE phrase factuelle (but, action faite, "
              "résultat), une ligne par bloc, sans conclure ni inventer. Réponds "
              "seulement par les phrases, dans l'ordre :\n\n" + "\n\n".join(extraits))
    try:
        data = appeler_modele([{"role": "user", "content": prompt}], cle)
        rep = data["choices"][0]["message"].get("content") or ""
        return [l.strip(" -•\t") for l in rep.splitlines() if l.strip()]
    except Exception:
        return []


def _sequence_valide(msgs):
    """Vérifie qu'aucun message 'tool' n'est orphelin : chaque 'tool' doit suivre
    un 'assistant' qui l'a demandé (même tool_call_id). Sert à ne JAMAIS appliquer
    une compression qui casserait l'appariement attendu par l'API."""
    attendus = set()
    for m in msgs:
        r = m.get("role")
        if r == "assistant":
            attendus = {tc.get("id") for tc in (m.get("tool_calls") or [])}
        elif r == "tool":
            if m.get("tool_call_id") not in attendus:
                return False
        elif r == "user":
            attendus = set()
    return True


def _creer_tache(messages):
    """Crée un suivi de tâche léger (Codex) pour ce tour. On n'utilise que son
    budget de durée (continuer()), non bloquant pour les outils : l'intégration
    complète plan/preuves exige un flux planifié, à aligner avec Codex. Dégrade
    en None sans jamais casser la boucle."""
    try:
        objectif = next((m["content"] for m in reversed(messages)
                         if m.get("role") == "user" and isinstance(m.get("content"), str)), None)
        config = verification.empreinte_configuration({"modele": MODELE_ACTIF})
        return autonomie.Tache(
            objectif or "tâche de l'utilisateur",
            [autonomie.Etape("t1", "accomplir la demande de l'utilisateur", "demande satisfaite")],
            verification.RegistrePreuves(config),
            budgets=autonomie.Budgets())
    except Exception:
        return None


class EcranTerminal:
    """Le visage terminal de Root. La boucle ne parle qu'à cet objet : la fenêtre
    (fenetre.py) fournit le sien avec les mêmes méthodes. Un moteur, deux visages."""

    def appeler(self, messages, cle):
        return appeler_avec_attente(messages, cle)

    def demander(self, nom, args):
        return demander(nom, args)

    def outil(self, nom, args, illisible=False):
        detail = (("  arguments illisibles", GRIS) if illisible
                  else (f"  {json.dumps(args, ensure_ascii=False)}", GRIS))
        console.print(transmission(Text.assemble(("▸ ", VERT), (nom, "bold"), detail)))

    def resultat(self, nom, texte):
        console.print(Text("  ⎿  " + texte.replace("\n", "\n     "), style=GRIS))

    def image(self, chemin):
        pass                                  # le terminal ne montre pas les captures

    def reponse(self, texte):
        console.print(transmission(Markdown(texte)))

    def fin(self, secondes, usage=None):
        console.print(Text(f"\n✻ A réfléchi {secondes} s · {time.strftime('%H:%M')}",
                           style=GRIS))

    def arret(self, texte):
        console.print(Text(f"\n✻ {texte}", style="#e0a84a"))


def un_tour(messages, cle, jour, ecran=None):
    """Un tour = on parle au modèle, puis tant qu'il demande des outils, on les
    exécute et on lui rend la main. On s'arrête quand il répond en texte, au bout
    de MAX_ETAPES allers-retours, ou quand le budget de durée (Codex) est épuisé.
    Tout l'affichage passe par `ecran` (terminal par défaut, ou la fenêtre)."""
    ecran = ecran or EcranTerminal()
    t0 = time.time()
    total = {"entree": 0, "sortie": 0}       # tokens de tout le tour, pour le coût affiché
    tache = _creer_tache(messages)        # suivi de tâche (budget de durée)
    for etape in range(MAX_ETAPES):
        if tache is not None and not tache.continuer().autorisee:
            ecran.arret(f"Arrêt (budget tâche) : {tache.motif}")
            return
        elaguer_images(messages)          # Lot 3 : ne pas renvoyer les vieilles images
        # Mémoire (Kimi) : si on approche de la fenêtre, compresser le milieu —
        # mais seulement si la compression garde une séquence d'outils valide.
        if memoire.estimer_tokens(messages) > SEUIL_TOKENS:
            compresse = memoire.compresser_milieu(
                messages, resumer_blocs=lambda b: resumer_blocs(b, cle))
            if _sequence_valide(compresse):
                messages[:] = compresse
        data = ecran.appeler(messages, cle)
        usage = data.get("usage") or {}
        tokens_ajouter(jour, usage.get("prompt_tokens", 0),
                       usage.get("completion_tokens", 0))
        total["entree"] += usage.get("prompt_tokens", 0) or 0
        total["sortie"] += usage.get("completion_tokens", 0) or 0
        memoire.enregistrer_tokens_reels(usage.get("prompt_tokens", 0))  # calibrage
        msg = data["choices"][0]["message"]
        messages.append(msg)

        appels = msg.get("tool_calls")
        if not appels:
            # Réponse finale : du texte, plus d'outil demandé.
            if msg.get("content"):
                ecran.reponse(msg["content"])
            ecran.fin(int(time.time() - t0), total)
            return

        # Le modèle demande un ou plusieurs outils.
        images_vues = []       # images produites par les outils (ex. capture d'écran)
        for appel in appels:
            nom = appel["function"]["name"]
            # Dispatch robuste : des arguments JSON cassés ne tuent pas la session,
            # on renvoie l'erreur au modèle qui se corrige au tour suivant.
            brut = appel["function"].get("arguments") or "{}"
            try:
                args = json.loads(brut)
                if not isinstance(args, dict):
                    raise ValueError("pas un objet")
            except (json.JSONDecodeError, ValueError):
                ecran.outil(nom, None, illisible=True)
                ecran.resultat(nom, "arguments JSON invalides")
                messages.append({"role": "tool", "tool_call_id": appel["id"],
                                 "content": "ERREUR : arguments JSON invalides. "
                                 "Renvoie un objet JSON valide pour cet outil."})
                continue

            ecran.outil(nom, args)

            if doit_demander(nom, args) and not ecran.demander(nom, args):
                resultat = "Refusé par l'utilisateur."
                ecran.resultat(nom, "refusé")
            else:
                resultat = executer_outil(nom, args)

            # Un outil peut renvoyer une image (dict avec _image) au lieu de texte.
            if isinstance(resultat, dict):
                if resultat.get("_image"):
                    images_vues.append(resultat["_image"])
                    ecran.image(resultat["_image"])
                texte_res = resultat.get("texte", "(image)")
            else:
                texte_res = resultat

            # Mémoire (Kimi) : tronquer en gardant tête ET queue (l'erreur est
            # souvent à la fin). Puis sécurité (Lot 2) : masquer les secrets avant
            # l'envoi au cloud, et emballer le web comme donnée non fiable.
            texte_res = memoire.tronquer_outil(texte_res)
            texte_res = securite.rediger_secrets(texte_res)
            if nom.startswith("web_"):
                # Garde d'entrée : on MÉMORISE d'abord le texte réellement lu sous une
                # référence (W1, W2…), puis on l'emballe comme donnée non fiable avec
                # cette référence et ses lignes numérotées. verifier_citation vérifiera
                # contre ce texte mémorisé, jamais contre une source fournie par le
                # modèle (anti-injection + anti-hallucination + anti-auto-vérification).
                ref = lecture.memoriser(texte_res, "W")
                texte_res = lecture.emballer_verifiable(texte_res, source="web", reference=ref)
            memoire.journaliser({"type": "outil", "outil": nom,
                                 "resume": texte_res[:200]})  # journal de session

            if not (isinstance(resultat, str) and resultat == "Refusé par l'utilisateur."):
                apercu = texte_res if len(texte_res) < 500 else texte_res[:500] + "…"
                ecran.resultat(nom, apercu)

            # On renvoie le résultat (texte) au modèle, rattaché à son appel.
            messages.append({"role": "tool", "tool_call_id": appel["id"],
                             "content": texte_res})

        # Les images produites par les outils sont montrées au modèle au tour
        # suivant, comme un message de l'utilisateur (l'API ne met pas d'image dans un
        # résultat d'outil).
        if images_vues:
            messages.append({"role": "user",
                             "content": construire_contenu(
                                 "Voici ce que montre l'écran.", images_vues, [], source="écran")})

    # Cap atteint : on n'a pas eu de réponse finale en MAX_ETAPES étapes. On
    # s'arrête proprement plutôt que de boucler sans fin (et de brûler le crédit).
    ecran.arret(f"Arrêt : {MAX_ETAPES} étapes atteintes sans conclure. Reformule ou relance.")


# ─────────────────────────────────────────────────────────────────────────────
# L'habillage du terminal : bannière, barre d'état, saisie
# ─────────────────────────────────────────────────────────────────────────────

def banniere():
    titre = Text.assemble(("⌁ ROOT", f"bold {VERT}"), ("  ·  ", GRIS), ("à l'écoute", GRIS))
    textes = {2: titre + Text("   ") + onde(9),
              3: Text(f"harness maison  ·  {MODELE_ACTIF}", style=GRIS),
              5: Text("/q partir", style=GRIS)}
    console.print()
    for n, l in enumerate(logo(True)):
        ligne = Text("  ") + l
        if n in textes:
            ligne += Text("   ") + textes[n]
        console.print(ligne, no_wrap=True, crop=True)
    if console.is_terminal:
        # Trois clignements de la diode pour dire bonjour (ligne 2 du logo).
        monter = len(logo()) - 2
        for allume in (False, True, False, True, False, True):
            ligne = Text("  ") + logo(allume)[2] + Text("   ") + textes[2]
            console.file.write(f"\033[{monter}A\r")
            console.print(ligne, no_wrap=True, crop=True, end="")
            console.file.write(f"\033[{monter}B\r")
            console.file.flush(); time.sleep(0.25)
    # Le filet d'ouverture : la ligne de transmission commence ici.
    console.print(Text("  " + "─" * max(10, console.width - 3), style=VERT_FONCE))
    console.print()


STYLE = Style.from_dict({
    "trait": GRIS,
    "invite": "bold",
    "bottom-toolbar": "noreverse bg:default",
    "bottom-toolbar.text": "noreverse",
    "badge": f"bold #111111 bg:{VERT}",
    "gris": GRIS,
    "vert": VERT,
    "diode": DIODE_ON,
})


def barre(echanges, jour):
    """La barre d'état sous la saisie, comme celle de Claude Code."""
    def rendu():
        trait = "─" * max(10, console.width - 1)
        return HTML(
            f"<trait>{trait}</trait>\n"
            f"<badge> Root </badge> <gris>·</gris> <diode>●</diode> "
            f"<gris>harness maison · {MODELE_ACTIF} · "
            f"{echanges[0]} échange{'s' if echanges[0] > 1 else ''}</gris>\n"
            f"<vert>▸▸</vert> <gris>↑ {fmt_k(jour['entree'])} entrée · "
            f"↓ {fmt_k(jour['sortie'])} sortie aujourd'hui · /ecran voir · /q partir</gris>")
    return rendu


def main():
    cle = charger_cle()
    console.clear()          # écran net, comme Claude Code (vire le « Last login »)
    banniere()
    if not cle:
        console.print(puce("#e07a7a", Text(
            "clé DeepSeek absente — ajoute-la dans "
            "~/.hermes/profiles/racine/.env puis relance.", style="#e07a7a")))
        return

    messages = [{"role": "system", "content": AME}]
    m_longue = memoire.memoire_pour_prompt()      # mémoire durable curée (Kimi)
    if m_longue.strip():
        messages.append({"role": "system",
                         "content": "Mémoire durable de Root :\n" + m_longue})
    # Reprise de session (Kimi) : si la dernière session s'est arrêtée en plein
    # milieu, proposer une projection courte (pas de rechargement des messages).
    reprise = memoire.proposer_reprise()
    if reprise:
        try:
            r = console.input(Text("  reprendre la session précédente ? [o/N] ",
                                   style=GRIS)).strip().lower()
        except (EOFError, KeyboardInterrupt):
            r = ""
        if r in ("o", "oui", "y", "yes"):
            messages.append({"role": "system", "content": reprise})
            console.print(Text("  (contexte de reprise injecté)\n", style=GRIS))

    echanges = [0]
    jour = tokens_charger()
    session = PromptSession(style=STYLE, erase_when_done=True,
                            bottom_toolbar=barre(echanges, jour))
    while True:
        trait = "─" * max(10, console.width - 1)
        try:
            p = session.prompt(HTML(f"<trait>{trait}</trait>\n<invite>› </invite>")).strip()
        except (EOFError, KeyboardInterrupt):
            memoire.journaliser({"type": "fin"})  # session terminée proprement
            console.print(Text("  à bientôt", style=GRIS)); break
        if not p:
            continue
        if p == "/q":
            memoire.journaliser({"type": "fin"})  # session terminée proprement
            console.print(Text("  à bientôt", style=GRIS)); break

        # /ecran [question] : montrer l'écran de l'utilisateur à Root tout de suite.
        if p == "/ecran" or p.startswith("/ecran "):
            question = p[len("/ecran"):].strip() or "Regarde mon écran et dis ce que tu vois."
            message_toi(p)
            console.print(Text("  ⎿  capture de l'écran…", style=GRIS))
            ecran = capturer_ecran()
            if not ecran.is_file():
                console.print(puce("#e07a7a", Text(
                    "capture impossible — autorise « Enregistrement de l'écran » "
                    "pour Ghostty dans Réglages Système > Confidentialité.", style="#e07a7a")))
                continue
            messages.append({"role": "user",
                             "content": construire_contenu(question, [ecran], [], source="écran")})
            console.print()
            try:
                un_tour(messages, cle, jour)
                echanges[0] += 1
                session.bottom_toolbar = barre(echanges, jour)
            except Exception as e:
                console.print(puce("#e07a7a", Text(f"erreur : {e}", style="#e07a7a")))
            continue

        message_toi(p)

        # Photos et vidéos : on repère les fichiers joints dans la saisie.
        texte, images, videos = extraire_medias(p)
        for img in images:
            console.print(Text(f"  ⎿  photo : {img.name}", style=GRIS))
        frames_video = []
        for v in videos:
            console.print(Text(f"  ⎿  vidéo : {v.name} — extraction des images…",
                               style=GRIS))
            fr = extraire_frames(v)
            frames_video += fr
            console.print(Text(f"      {len(fr)} images extraites", style=GRIS))
        contenu = construire_contenu(texte, images, frames_video, source="photo")

        messages.append({"role": "user", "content": contenu})
        console.print()
        try:
            un_tour(messages, cle, jour)
            echanges[0] += 1
            session.bottom_toolbar = barre(echanges, jour)
        except KeyboardInterrupt:
            console.print(Text("  (interrompue)", style=GRIS))
        except urllib.error.HTTPError as e:
            console.print(puce("#e07a7a", Text(
                f"erreur DeepSeek {e.code} : {e.read().decode()[:300]}", style="#e07a7a")))
        except Exception as e:
            console.print(puce("#e07a7a", Text(f"erreur : {e}", style="#e07a7a")))


if __name__ == "__main__":
    main()
