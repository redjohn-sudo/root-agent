"""\
Mémoire et contexte de Root — module de Kimi K3, non intégré à la boucle active.

Ce fichier est un squelette HORS LIGNE : fonctions pures, aucun appel réseau,
aucun import de root.py. Il matérialise les mécanismes proposés dans
CONCEPTION-MEMOIRE.md. L'intégration dans root.py / navigateur.py (réservés à
Claude) consistera à appeler ces fonctions aux bons endroits ; elle n'est PAS
faite ici.

Règles tenues par ce module :
- Sincérité : une fonction dont le résultat n'est pas mesuré ne prétend rien.
- Protection : tout ce qui peut partir au cloud (projections injectées dans le
  prompt, memoire.md) est construit comme une donnée qui sort de la machine.
  Les bruts (images, pages, sorties complètes) ne sont jamais stockés ici.

Dépendances : bibliothèque standard seule. Le nettoyage des secrets est délégué
à securite.rediger_secrets quand il est disponible, avec repli local sinon —
ce module ne casse pas si securite.py change.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Réglages
# ─────────────────────────────────────────────────────────────────────────────

# Budget de la fenêtre d'entrée du modèle, marge comprise. À calibrer avec les
# valeurs réelles d'`usage.prompt_tokens` (voir ETAT_FICHIER).
BUDGET_FENETRE = 100_000          # tokens
SEUIL_COMPRESSION = 0.70          # on compresse passé 70 % du budget
CARACTERES_PAR_TOKEN = 4          # borne haute : 1 token ≈ 4 caractères (texte)
TOKENS_PAR_IMAGE = 1_100          # forfait par image encore présente (à mesurer)

MESSAGES_PROTEGES = 6             # derniers échanges jamais compressés

TRONC_OUTIL_BUDGET = 20_000       # caractères, remplace les '20000' en dur
PART_TETE = 0.4                   # part du budget gardée en tête (reste en queue)

MEMOIRE_FICHIER = Path(__file__).parent / "memoire.md"
MEMOIRE_PLAFOND = 8_000           # caractères (≈ 2 000 tokens) — dur, refus au-delà
SESSIONS_DOSSIER = Path.home() / ".local" / "root-sessions"
ETAT_FICHIER = Path.home() / ".local" / "root-etat.json"
MESURES_FICHIER = Path.home() / ".local" / "root-tokens-mesures.jsonl"

# Calibrage automatique d'estimer_tokens à partir des mesures réelles.
# - une mesure = paire (estime, reel) captée par la boucle à chaque appel modèle,
# - la série est bornée (les plus anciennes mesures sortent d'abord),
# - la fonction calibrer_constantes() n'ajuste que si assez de points et un
#   écart > SEUIL_ECART_CALIBRE — sinon elle ne fait rien.
CALIBRATION_MIN_POINTS = 5         # en dessous : pas de décision
CALIBRATION_MAX_SERIE = 50         # série bornée pour rester légère
SEUIL_ECART_CALIBRE = 0.25         # 25 % d'écart moyen déclenche l'ajustement


# ---------------------------------------------------------------------------
# Écriture atomique / lecture tolérante (ajout 4b)
# ---------------------------------------------------------------------------

def _ecrire_texte_atomique(chemin: Path, contenu: str) -> None:
    """Écrit `contenu` dans `chemin` sans jamais laisser de fichier tronqué :
    écrit d'abord dans `<chemin>.tmp` (même dossier pour rester sur le même
    volume), fsync, puis os.replace() — atomique sur POSIX comme NT.
    Un Crash(tm) entre write et replace laisse le .tmp orphelin (inoffensif),
    l'ancien fichier intact. Si tout échoue (volume), retombe sur l'écriture
    directe historique — au pire on régresse au comportement d'avant.
    """
    tmp = chemin.with_suffix(chemin.suffix + ".tmp")
    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(contenu, encoding="utf-8")
        with tmp.open("rb") as f:
            os.fsync(f.fileno())
        os.replace(tmp, chemin)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        chemin.write_text(contenu, encoding="utf-8")


def _lire_json_tolerant(chemin: Path, defaut):
    """Lit un JSON sans jamais lever : si `chemin` est absent ou corrompu,
    regarde `<chemin>.bak` (dernière bonne copie faite à l'écriture), sinon
    retourne `defaut`. Règle d'or 4b : un démarrage ne doit JAMAIS planter
    sur un fichier de données.
    """
    for candidat in (chemin, chemin.with_suffix(chemin.suffix + ".bak")):
        try:
            if candidat.exists():
                return json.loads(candidat.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
    return defaut


def _lire_texte_tolerant(chemin: Path) -> str:
    """Lecture sûre d'un fichier texte : absent, illisible ou en codage
    inattendu → ''. Utilisé pour MEMOIRE_FICHIER, dont chaque lecture fait
    potentiellement partie du démarrage de Root."""
    try:
        if not chemin.exists():
            return ""
        return chemin.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Nettoyage des secrets : on délègue à securite.py, avec repli local
# ─────────────────────────────────────────────────────────────────────────────

def _rediger(texte: str) -> str:
    """Masque les secrets d'un texte destiné à être stocké puis (un jour)
    injecté dans le prompt. Délègue à securite.rediger_secrets si importable,
    sinon applique un repli minimal local. Ce repli n'est PAS une garantie ;
    la barrière principale reste la règle de curation (jamais de perso)."""
    try:
        import securite  # type: ignore
        return securite.rediger_secrets(texte)
    except Exception:
        pass
    # Repli minimal : masquage des motifs de clés les plus courants.
    motifs = [
        r"sk-[A-Za-z0-9]{20,}",                     # clés style OpenAI
        r"Bearer\s+[A-Za-z0-9._\-]{20,}",           # jetons Bearer
        r"(?i)(api[_-]?key|token|secret)\s*[:=]\s*\S+",  # paires clé=valeur
    ]
    for motif in motifs:
        texte = re.sub(motif, "[masqué]", texte)
    return texte


# ─────────────────────────────────────────────────────────────────────────────
# HORIZON 1 — tenir dans la fenêtre
# ─────────────────────────────────────────────────────────────────────────────

def _longueur_contenu(contenu) -> int:
    """Longueur approximative (caractères) du champ content d'un message,
    qu'il soit une chaîne ou une liste de parties (texte + images)."""
    if isinstance(contenu, str):
        return len(contenu)
    if isinstance(contenu, list):
        total = 0
        for partie in contenu:
            if isinstance(partie, dict) and partie.get("type") == "text":
                total += len(partie.get("text", ""))
        return total
    return 0


def _nombre_images(contenu) -> int:
    if not isinstance(contenu, list):
        return 0
    return sum(1 for p in contenu
               if isinstance(p, dict) and p.get("type") == "image_url")


def estimer_tokens(messages: list[dict]) -> int:
    """Borne haute du coût en entrée de `messages`.

    Surestimation volontaire : on déclenche SOUS le seuil, donc une marge trop
    grande coûte une compression un peu tôt, jamais un dépassement de fenêtre.
    Le texte vaut ~1 token / 4 caractères ; chaque image ajoute son forfait.
    """
    caracteres = sum(_longueur_contenu(m.get("content")) for m in messages)
    images = sum(_nombre_images(m.get("content")) for m in messages)
    # int() : CARACTERES_PAR_TOKEN peut devenir un float après calibrage
    # automatique (ex. 4.25) ; le contrat rend un int dans tous les cas.
    return int(caracteres / CARACTERES_PAR_TOKEN) + images * TOKENS_PAR_IMAGE


def enregistrer_tokens_reels(prompt_tokens: int, estime: int | None = None,
                             images: int = 0) -> None:
    """Appelée par la boucle après chaque réponse modèle : conserve le coût
    réellement facturé *et* ce qu'on avait estimé, pour permettre le calibrage.

    Signature rétro-compatible : appelée avec seul `prompt_tokens`, conserve
    juste la dernière valeur dans ETAT_FICHIER (comportement initial). Quand
    `estime` est fourni, écrit une ligne JSONL dans MESURES_FICHIER
    (série bornée à CALIBRATION_MAX_SERIE, les plus anciennes sortent d'abord).
    `images` = nombre d'images présentes dans le tour — utile pour isoler
    l'écart texte de l'écart image lors du calibrage.

    Ne plante jamais : un souci d'écriture ne doit pas casser un tour de boucle.
    """
    try:
        ETAT_FICHIER.parent.mkdir(parents=True, exist_ok=True)
        # Écriture atomique + copie de secours .bak (règle 4b : démarrage
        # sûr même après interruption / corruption).
        contenu = json.dumps({
            "dernier_prompt_tokens": prompt_tokens,
            "ts": datetime.now().isoformat(timespec="seconds"),
        })
        _ecrire_texte_atomique(ETAT_FICHIER, contenu)
        try:
            _ecrire_texte_atomique(
                ETAT_FICHIER.with_suffix(ETAT_FICHIER.suffix + ".bak"), contenu)
        except OSError:
            pass  # la copie de secours est un confort, pas une raison d'échouer
    except OSError:
        pass  # l'état est un confort, jamais une raison de casser un tour

    if estime is None or images < 0 or prompt_tokens <= 0 or estime < 0:
        return
    try:
        MESURES_FICHIER.parent.mkdir(parents=True, exist_ok=True)
        ligne = json.dumps({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "estime": estime,
            "reel": prompt_tokens,
            "images": images,
        }, ensure_ascii=False)
        with MESURES_FICHIER.open("a", encoding="utf-8") as f:
            f.write(ligne + "\n")
        _mesures_borner()
    except OSError:
        pass


def _mesures_borner() -> None:
    """Tronque MESURES_FICHIER aux CALIBRATION_MAX_SERIE lignes les plus
    récentes. Écriture atomique : un kill -9 pendant l'élagage ne doit pas
    perdre les mesures encore valides."""
    try:
        lignes = MESURES_FICHIER.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    if len(lignes) <= CALIBRATION_MAX_SERIE:
        return
    garder = lignes[-CALIBRATION_MAX_SERIE:]
    _ecrire_texte_atomique(MESURES_FICHIER, "\n".join(garder) + "\n")


def _mesures_charger() -> list[dict]:
    """Charge la série de mesures. Tolère les lignes corrompues / tronquées
    (JSONDecodeError ignorée) — une crash en cours d'écriture ne doit pas
    empêcher l'analyse des mesures saines."""
    if not MESURES_FICHIER.exists():
        return []
    try:
        lignes = MESURES_FICHIER.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    mesures = []
    for l in lignes:
        l = l.strip()
        if not l:
            continue
        try:
            m = json.loads(l)
        except json.JSONDecodeError:
            continue
        if not isinstance(m, dict):
            continue
        try:
            mesures.append({
                "estime": int(m["estime"]),
                "reel": int(m["reel"]),
                "images": int(m.get("images", 0)),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return mesures


def analyser_calibration() -> dict:
    """Bilan honnête des mesures collectées : combien, écart moyen et médian
    entre estimé et réel. Aucune décision ici — seulement les nombres.

    L'écart est exprimé *relativement au réel* : positif = surestimation,
    négatif = sous-estimation. On regarde aussi séparément les tours sans
    image (isole CARACTERES_PAR_TOKEN) et avec image (isole TOKENS_PAR_IMAGE).
    """
    mesures = _mesures_charger()
    if not mesures:
        return {
            "points": 0,
            "ecart_moyen": None,
            "ecart_median": None,
            "as_suffisant": False,
            "texte_seul": {"points": 0, "rapport_median": None},
            "avec_image": {"points": 0, "rapport_median": None},
        }

    def _ecarts(mesures_locales):
        return [(m["estime"] - m["reel"]) / m["reel"] for m in mesures_locales]

    def _mediane(xs):
        xs = sorted(xs)
        n = len(xs)
        return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2

    ecarts = _ecarts(mesures)

    def _densite_tokens_par_caractere(m):
        """Tokens réels rapportés aux caractères du tour, hors images.
        Ex. 0.25 ⇔ 4 caractères par token."""
        car = (m["estime"] - m["images"] * TOKENS_PAR_IMAGE) * CARACTERES_PAR_TOKEN
        if car <= 0 or m["images"] > 0:
            return None
        return m["reel"] / car

    def _densite_tokens_par_image(m):
        """Tokens réels attribuables aux images, par image. Suppose le texte
        correctement estimé par CARACTERES_PAR_TOKEN ; les tours dont le texte
        absorberait tout le réel sont écartés (tokens_reels_images <= 0)."""
        if m["images"] == 0:
            return None
        tokens_texte = (m["estime"] - m["images"] * TOKENS_PAR_IMAGE)
        tokens_reels_images = m["reel"] - tokens_texte
        if tokens_reels_images <= 0:
            return None
        return tokens_reels_images / m["images"]

    texte_seul = [m for m in mesures if m["images"] == 0]
    avec_image = [m for m in mesures if m["images"] > 0]

    def _rapports(mesures_locales, f):
        rs = [r for r in (f(m) for m in mesures_locales) if r is not None]
        return {
            "points": len(rs),
            "rapport_median": _mediane(rs) if rs else None,
        }

    return {
        "points": len(mesures),
        "ecart_moyen": sum(ecarts) / len(ecarts),
        "ecart_median": _mediane(ecarts),
        "as_suffisant": len(mesures) >= CALIBRATION_MIN_POINTS,
        "texte_seul": _rapports(texte_seul, _densite_tokens_par_caractere),
        "avec_image": _rapports(avec_image, _densite_tokens_par_image),
    }


def calibrer_constantes() -> dict:
    """Ajuste CARACTERES_PAR_TOKEN et TOKENS_PAR_IMAGE à partir des mesures
    réelles, uniquement si c'est justifié.

    Renvoie un dict honnête : {"ajusté": bool, "raison": str, "avant": {...},
    "apres": {...}}. Ne bouge à rien si :
    - moins de CALIBRATION_MIN_POINTS collectés (pas assez de recul), ou
    - écart moyen < SEUIL_ECART_CALIBRE (l'estimé est déjà honnête).

    Côté décision : BUDGET_FENETRE n'est jamais touché automatiquement — c'est
    une limite de sécurité, pas une mesure. On peut recommander, pas imposer.
    """
    global CARACTERES_PAR_TOKEN, TOKENS_PAR_IMAGE
    stats = analyser_calibration()
    avant = {
        "CARACTERES_PAR_TOKEN": CARACTERES_PAR_TOKEN,
        "TOKENS_PAR_IMAGE": TOKENS_PAR_IMAGE,
    }
    resultat = {"ajusté": False, "raison": "", "avant": dict(avant),
                "apres": dict(avant), "stats": stats}

    if not stats["as_suffisant"]:
        resultat["raison"] = (f"seulement {stats['points']} mesures "
                              f"(< {CALIBRATION_MIN_POINTS}) : pas de décision")
        return resultat
    ecart_moyen = stats["ecart_moyen"]
    if ecart_moyen is None or abs(ecart_moyen) < SEUIL_ECART_CALIBRE:
        resultat["raison"] = (f"écart moyen {ecart_moyen:+.1%} sous le seuil "
                              f"de {SEUIL_ECART_CALIBRE:.0%} : constantes gardées")
        return resultat

    # Ajustement sur le texte seul (cas le plus fréquent et le mieux mesuré).
    ts = stats["texte_seul"]
    if ts["points"] >= 3 and ts["rapport_median"] is not None:
        # rapport_median = densité observée = tokens_reels / caractère (ex. 0.5).
        # On en déduit le CARACTERES_PAR_TOKEN réel observé = inverse de la
        # densité (ex. 1 / 0.5 = 2 caractères par token si l'API en compte
        # vraiment le double de ce qu'on croyait). Borne minimale volontaire
        # : on ne descend jamais sous 2 caractères/token, la fenêtre serait
        # trop compressée par peur du pire.
        densite = ts["rapport_median"]
        if densite > 0:
            nouveau = 1.0 / densite
            # arrondi au pas de 0,25 pour rester lisible (4.0, 4.25, 4.5…)
            # et éviter qu'une mesure médiane bancale ne fasse dériver le
            # réglage de 4 vers 3.97.
            nouveau = round(nouveau * 4) / 4
            CARACTERES_PAR_TOKEN = max(2.0, nouveau)

    # Ajustement pour les images, si on en a assez mesurées.
    ai = stats["avec_image"]
    if ai["points"] >= 3 and ai["rapport_median"] is not None:
        # La "densité" ici est déjà des TOKENS PAR IMAGE observés (ex. 1850),
        # pas un ratio à re-multiplier. On arrondit au pas de 50 pour rester
        # lisible, borné à [200, 4000] : forfait minimum raisonnable pour une
        # image low-res, maximum raisonnable pour une photo dense.
        TOKENS_PAR_IMAGE = max(200, min(4000, round(ai["rapport_median"] / 50) * 50))

    resultat["apres"] = {
        "CARACTERES_PAR_TOKEN": CARACTERES_PAR_TOKEN,
        "TOKENS_PAR_IMAGE": TOKENS_PAR_IMAGE,
    }
    resultat["ajusté"] = resultat["apres"] != resultat["avant"]
    if resultat["ajusté"]:
        resultat["raison"] = (f"écart moyen {ecart_moyen:+.1%} — constantes ajustées "
                              f"(caractères/token {avant['CARACTERES_PAR_TOKEN']}→{CARACTERES_PAR_TOKEN}, "
                              f"tokens/image {avant['TOKENS_PAR_IMAGE']}→{TOKENS_PAR_IMAGE})")
    else:
        resultat["raison"] = (f"écart moyen {ecart_moyen:+.1%} mais pas assez de "
                              f"mesures par type — constantes gardées")
    return resultat


def tronquer_outil(texte: str, budget: int = TRONC_OUTIL_BUDGET) -> str:
    """Tronque un résultat d'outil en gardant la tête ET la queue.

    Règles : jamais de coupe silencieuse ; on aligne sur un saut de ligne ;
    une ligne explicite indique combien de caractères ont été omis au milieu.
    Le début porte le contexte, la fin porte le plus souvent l'erreur ou le
    code de sortie — perdre l'un des deux fait mal conclure.
    """
    if len(texte) <= budget:
        return texte
    tete_cible = int(budget * PART_TETE)
    queue_cible = budget - tete_cible
    # On recule/avance jusqu'au saut de ligne le plus proche pour ne pas
    # trancher une ligne en deux.
    fin_tete = texte.rfind("\n", 0, tete_cible)
    fin_tete = fin_tete if fin_tete > 0 else tete_cible
    debut_queue = texte.find("\n", len(texte) - queue_cible)
    debut_queue = debut_queue if 0 < debut_queue < len(texte) else len(texte) - queue_cible
    omis = debut_queue - fin_tete
    if omis <= 0:  # chevauchement : la note prendrait plus de place que le gain
        return texte
    note = f"\n… ({omis} caractères omis au milieu, début et fin conservés) …\n"
    return texte[:fin_tete] + note + texte[debut_queue:]


def ligne_image(outil: str, description: str = "") -> str:
    """La ligne qui remplace une image élaguée, pour qu'elle reste utile.

    Appelée par la boucle au moment de l'élagage : à la place de
    "[image vue plus tôt]", on met une trace de ce que l'image montrait.
    `description` vient soit de l'outil, soit d'un appel de description fait
    par la boucle pendant que l'image était encore là — pas de ce module.
    """
    heure = datetime.now().strftime("%H:%M")
    desc = f" : {description.strip()}" if description.strip() else ""
    return f"[image via {outil} à {heure}{desc}]"


def _est_message_systeme(msg: dict) -> bool:
    return msg.get("role") == "system"


def _frontiere_sure(corps: list[dict], debut: int) -> int:
    """Recule `debut` pour ne pas couper une séquence d'outil en deux.

    Une séquence saine : assistant(avec tool_calls) suivi de ses messages
    'tool' (un par appel), puis un assistant conclusif. Couper entre le
    tool_calls et ses résultats laisserait un 'tool' orphelin dans la zone
    protégée — l'API le refuse. On recule donc tant que le message à `debut`
    est un 'tool' ou qu'il ouvre une séquence dont les résultats sont après.
    """
    debut = max(0, debut)
    while debut > 0:
        m = corps[debut]
        role = m.get("role")
        if role == "tool":
            # Le partenaire tool_calls est avant : on le prend avec la zone
            # protégée (sinon il serait compressé et le tool serait orphelin).
            debut -= 1
            continue
        if role == "assistant" and m.get("tool_calls"):
            ids = {tc.get("id") for tc in m.get("tool_calls", [])}
            # Tous les résultats de ces appels doivent être dans la zone
            # protégée (>= debut). S'il en manque une avant, on recule.
            manque = any(
                corps[j].get("role") == "tool"
                and corps[j].get("tool_call_id") in ids
                for j in range(debut)
            )
            if manque:
                debut -= 1
                continue
        break
    return debut


def compresser_milieu(messages: list[dict], resumer_blocs=None) -> list[dict]:
    """Compresse le milieu de la conversation, en protégeant tête et fin.

    - Jamais touché : le(s) message(s) system (l'âme) et les MESSAGES_PROTEGES
      derniers échanges.
    - Le milieu est découpé en blocs complets user→(assistant/tool…), résumé
      en une mention par bloc. Le découpage ne coupe jamais au milieu d'un
      appel d'outil, pour ne pas laisser un message 'tool' orphelin.

    `resumer_blocs` : fonction optionnelle fournie PAR LA BOUCLE, qui reçoit la
    liste des blocs et renvoie une liste de phrases (typiquement un appel
    modèle). Sans elle, on dégrade sans appel : première ligne utilisateur +
    noms des outils + dernière ligne des résultats de chaque bloc.

    Règles de robustesse (4c) :
      - si `resumer_blocs` lève, on retombe sur le résumé local (jamais de
        propagation), sinon la boucle perdrait son contexte alors qu'on
        pouvait encore le compresser ;
      - si le callback renvoie moins de phrases que de blocs, les blocs
        manquants tombent sur le résumé local plutôt que d'être omis ;
      - une phrase non-str ou vide est remplacée par le repli local, jamais
        par "" (sinon le bloc disparaît du résumé injecté).
    """
    if len(messages) <= MESSAGES_PROTEGES + 2:
        return list(messages)

    tete = [m for m in messages if _est_message_systeme(m)]
    corps = [m for m in messages if not _est_message_systeme(m)]
    if len(corps) <= MESSAGES_PROTEGES:
        return list(messages)

    # Frontière de la zone protégée : on ne coupe JAMAIS au milieu d'une
    # séquence d'outil. Si le message qui ouvrirait la zone protégée est un
    # 'tool' (ou fait partie d'une séquence dont le 'tool_calls' amont est
    # dans la zone à compresser), on recule la frontière jusqu'à un point sûr.
    # Sinon on laisserait un 'tool' orphelin, que l'API refuse.
    debut = len(corps) - MESSAGES_PROTEGES
    debut = _frontiere_sure(corps, debut)

    a_proteger = corps[debut:]
    milieu = corps[:debut]

    # Découpage en blocs : un bloc commence à un message 'user' et s'arrête
    # juste avant le 'user' suivant. Jamais de coupure entre un assistant avec
    # tool_calls et ses messages 'tool'.
    blocs: list[list[dict]] = []
    bloc_courant: list[dict] = []
    for m in milieu:
        if m.get("role") == "user" and bloc_courant:
            blocs.append(bloc_courant)
            bloc_courant = []
        bloc_courant.append(m)
    if bloc_courant:
        blocs.append(bloc_courant)

    def _resume_local(bloc: list[dict]) -> str:
        """Repli local sans appel modèle. Ne renvoie JAMAIS une chaîne vide
        (sinon le bloc serait silencieusement perdu dans le résumé)."""
        premiere = ""
        outils: list[str] = []
        dernieres: list[str] = []
        for m in bloc:
            role = m.get("role")
            if role == "user" and not premiere:
                premiere = _premiere_ligne(m.get("content"))
            elif role == "assistant" and m.get("tool_calls"):
                for tc in m.get("tool_calls", []):
                    nom = (tc.get("function") or {}).get("name") or "?"
                    outils.append(nom)
            elif role == "tool":
                dernieres.append(_derniere_ligne(m.get("content")))
        phrase = premiere
        if outils:
            phrase += f" — outils : {', '.join(outils)}"
        if dernieres:
            phrase += f" — dernier résultat : {dernieres[-1]}"
        phrase = phrase.strip(" —")
        if not phrase:
            # Bloc entièrement outil/assistant sans contenu utilisateur
            # lisible : on garde une trace factuelle de sa présence.
            phrase = (f"(bloc de {len(bloc)} message(s) sans contenu "
                      f"utilisateur lisible)")
        return phrase

    phrases: list[str] = []
    if resumer_blocs is not None:
        brutes = None
        try:
            brutes = resumer_blocs(blocs)
        except Exception:
            # Jamais de propagation : repli complet sur le résumé local.
            brutes = None
        if not isinstance(brutes, list) or len(brutes) < len(blocs):
            # Callback défectueux (mauvais type, exception, pas assez de
            # phrases) : repli local pour TOUS les blocs.
            phrases = [_resume_local(b) for b in blocs]
        else:
            # Normaliser chaque entrée : non-str ou vide → repli local pour
            # ce bloc (jamais "", sinon le bloc serait omis du résumé).
            for i, b in enumerate(blocs):
                p = brutes[i]
                if not isinstance(p, str):
                    p = ""
                p = p.strip()
                if not p:
                    p = _resume_local(b)
                phrases.append(p)
    else:
        phrases = [_resume_local(b) for b in blocs]

    heure = datetime.now().strftime("%H:%M")
    resume = {
        "role": "assistant",
        "content": (
            f"Résumé des échanges anciens (fait à {heure}, "
            f"{len(blocs)} bloc(s)) :\n" +
            "\n".join(f"- {p}" for p in phrases if p) +
            "\n(Fin du résumé — c'est du passé, revérifier l'état actuel avant d'agir.)"
        ),
    }
    return tete + [resume] + a_proteger


def _premiere_ligne(contenu) -> str:
    if isinstance(contenu, list):
        for p in contenu:
            if isinstance(p, dict) and p.get("type") == "text":
                contenu = p.get("text", "")
                break
    return (contenu or "").strip().splitlines()[:1][0][:160] if contenu else ""


def _derniere_ligne(contenu) -> str:
    if isinstance(contenu, str):
        lignes = [l for l in contenu.strip().splitlines() if l.strip()]
        return lignes[-1][:160] if lignes else ""
    return ""


def signature_action(nom_outil: str, args: dict, resultat: str) -> str:
    """Une signature courte et comparable d'une action réalisée.

    Sert à repérer « cette action a déjà été faite sur cette cible » sans
    stocker le résultat brut. La décision « c'est une répétition » appartient
    au suivi de tâche (Codex) ; ici on rend les faits comparables.
    """
    import hashlib
    args_canon = json.dumps(args, sort_keys=True, ensure_ascii=False,
                            default=str)
    # On hache le résultat (pas le résultat lui-même) pour comparer sans
    # conserver de données potentiellement sensibles.
    empreinte = hashlib.sha256(_rediger(resultat).encode()).hexdigest()[:16]
    return f"{nom_outil}|{args_canon}|{empreinte}"


# ─────────────────────────────────────────────────────────────────────────────
# HORIZON 2 — se souvenir entre les sessions
# ─────────────────────────────────────────────────────────────────────────────

def journal_du_jour() -> Path:
    SESSIONS_DOSSIER.mkdir(parents=True, exist_ok=True)
    return SESSIONS_DOSSIER / f"{datetime.now():%Y-%m-%d}.jsonl"


def journaliser(entree: dict) -> bool:
    """Ajoute UNE ligne au journal de session du jour (append-only).

    La ligne ne doit contenir que des résumés et des signatures — jamais de
    brut (pas d'image, pas de page brute, pas de secret). On ne relit jamais
    ce journal pour le réinjecter en entier dans le prompt.
    """
    entree = dict(entree)
    entree.setdefault("ts", datetime.now().isoformat(timespec="seconds"))
    try:
        texte = json.dumps(entree, ensure_ascii=False)
        texte = _rediger(texte)  # barrière, pas garantie (voir _rediger)
        with journal_du_jour().open("a", encoding="utf-8") as f:
            f.write(texte + "\n")
        return True
    except OSError:
        return False


def relire_journal(chemin: Path) -> list[dict]:
    """Relit un journal JSONL. Tolère une dernière ligne coupée en deux par un
    crash en cours d'écriture (on ignore proprement la ligne incomplète)."""
    lignes = []
    try:
        for ligne in Path(chemin).read_text(encoding="utf-8").splitlines():
            ligne = ligne.strip()
            if not ligne:
                continue
            try:
                lignes.append(json.loads(ligne))
            except json.JSONDecodeError:
                continue  # ligne incomplète : ignorée, pas fatale
    except OSError:
        pass
    return lignes


def proposer_reprise() -> str | None:
    """Si le dernier journal s'arrête en plein milieu, renvoie une courte
    projection à proposer à Vincent pour reprendre — sinon None.

    La projection est destinée à être injectée comme UN message system
    additionnel, pas à recharger les anciens messages. Elle parle au passé et
    invite à revérifier l'état courant.
    """
    if not SESSIONS_DOSSIER.is_dir():
        return None
    fichiers = sorted(SESSIONS_DOSSIER.glob("*.jsonl"))
    if not fichiers:
        return None
    entrees = relire_journal(fichiers[-1])
    if not entrees or entrees[-1].get("type") == "fin":
        return None

    faits = [e.get("resume", "") for e in entrees if e.get("type") == "fait"]
    suspens = [e.get("resume", "") for e in entrees if e.get("type") == "suspens"]
    date = fichiers[-1].stem
    blocs = [f"Reprise d'une session du {date}."]
    if faits:
        blocs.append("Déjà fait : " + " ; ".join(faits[-5:]))
    if suspens:
        blocs.append("En suspens : " + " ; ".join(suspens[-3:]))
    blocs.append("C'est du passé : revérifier l'état actuel avant d'agir.")
    return "\n".join(blocs)


# ─────────────────────────────────────────────────────────────────────────────
# Quasi-doublons et pierres tombales — inspirés de soulbook et d'Oblivion.
#
# Refus des quasi-doublons : memoire.md n'accueille pas deux fois la même
# phrase à un mot près. Mesure du rapprochement = recouvrement de mots
# (Jaccard) plutôt que SimHash (Charikar), car SimHash est fait pour de LONGS
# textes et perd sa localité sur les phrases très courtes qui composent
# memoire.md — soulbook trust/oubli.ts le signale aussi. SimHash reste exposé
# : il peut servir à d'autres modules (textes longs), mais pas à celui-ci.
#
# Pierres tombales (reprises d'Oblivion via soulbook trust/oubli.ts) : ce qu'on
# oublie ne doit pas revenir. memoire_oublier dépose l'empreinte (sha256 du
# texte plié) des lignes retirées ; memoire_noter refuse ensuite toute
# réintroduction du même fait à casse/accents/blancs près. Jamais le texte
# oublié n'est conservé — seulement son empreinte.
# ─────────────────────────────────────────────────────────────────────────────

TOMBES_FICHIER = Path.home() / ".local" / "root-tombes.json"

def _plier(texte: str) -> str:
    """Pli utilisé avant hachage : même texte à espaces, casse et accents près.
    Comme citations.plier chez soulbook — sinon « État » et «état » feraient
    deux empreintes différentes du même fait."""
    texte = unicodedata.normalize("NFKC", texte).lower()
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return " ".join(texte.split())

def _mots(texte: str) -> list[str]:
    """Tokens normalisés pour comparer deux phrases courtes : on retire la
    ponctuation courante (le point final, la virgule, le tiret typographique,
    etc.) pour que « root-harness-git. » et « root-harness-git » comptent
    comme le même mot. Sans ce nettoyage, la ponctuation terminale masque
    artificiellement la similarité Jaccard d'une phrase réécrite."""
    bruts = re.findall(r"[\w’'._/-]+", _plier(texte), flags=re.UNICODE)
    return [t.strip(".,;:!?'’—-") for t in bruts if t.strip(".,;:!?'’—-")]

SIMHASH_SEUIL = 3  # distance de Hamming max sur 64 bits entre quasi-doublons

def simhash(texte: str) -> int:
    """SimHash 64 bits du texte, sur ses 3-grammes de mots (repris de
    soulbook engine/distill/empreinte.ts, porté en Python hors ligne)."""
    from hashlib import blake2b
    m = _mots(texte)
    if not m:
        return 0
    v = [0] * 64
    def empreinte(f: str) -> int:
        return int.from_bytes(blake2b(f.encode("utf-8"), digest_size=8).digest(), "big")
    def ajouter(f: str) -> None:
        a = empreinte(f)
        b = empreinte("\x00" + f)  # deux hachages indépendants
        for i in range(32):
            v[i] += 1 if (a >> i) & 1 else -1
            v[32 + i] += 1 if (b >> i) & 1 else -1
    if len(m) < 3:
        for f in m:
            ajouter(f)
    for i in range(len(m) - 2):
        ajouter(f"{m[i]} {m[i+1]} {m[i+2]}")
    h = 0
    for i in range(64):
        if v[i] > 0:
            h |= 1 << i
    return h

def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")

def _lignes_faits(contenu: str) -> list[str]:
    """Les lignes de faits de memoire.md, sans leur suffixe _(noté le …)_."""
    lignes = []
    for l in contenu.splitlines():
        l = l.strip()
        if l.startswith("- "):
            lignes.append(re.sub(r"\s+_\(noté le [^)]+\)_\s*$", "", l[2:]))
    return lignes

def _quasi_doublon(nouveau: str, existants: list[str]) -> str | None:
    """Renvoie la ligne existante quasi-identique à `nouveau`, sinon None.

    Détail honnête : SimHash (Charikar) est fait pour de LONGS textes (des
    pages, des captures) — sur un texte très court (les faits de memoire.md
    font souvent < 15 mots), un seul mot changé déplace trop de bits, la
    localité ne tient plus. soulbook trust/oubli.ts le dit aussi d'une autre
    façon (« l'empreinte reconnaît la même phrase, pas une paraphrase »).
    Pour memoire.md on mesure donc DIRECTEMENT le recouvrement de mots
    (Jaccard), qui reste fiable même court. SimHash reste exposé (utile à
    d'autres modules pour des textes longs)."""
    def mots_ensemble(t: str) -> set:
        return set(_mots(t))
    n_mots = mots_ensemble(nouveau)
    if not n_mots:
        return None
    for ligne in existants:
        e_mots = mots_ensemble(ligne)
        if not e_mots:
            continue
        inter = len(n_mots & e_mots)
        union = len(n_mots | e_mots)
        if union and inter / union >= SIMILARITE_SEUIL_FAIT:
            return ligne
    return None

SIMILARITE_SEUIL_FAIT = 0.65  # seuil Jaccard : au-delà, c'est le même fait

def _empreinte_chaine(texte: str) -> str:
    """Empreinte utilisée pour les pierres tombales. Normalise à la fois la
    casse/accents (`_plier`) ET la ponctuation terminal — sinon « fait. »
    et « fait » produisent deux empreintes et la tombe se laisse contourner."""
    from hashlib import sha256
    texte_plie = _plier(texte)
    # On retire la ponctuation en fin de chaîne, non pas en interne.
    texte_net = texte_plie.rstrip(".,;:!?'’—-")
    return sha256(texte_net.encode("utf-8")).hexdigest()

def _tombes_charger() -> list[str]:
    """Charge le registre des pierres tombales. Règle 4b : JSON corrompu
    ou absent → regarde le .bak ; échec partout → liste vide. Jamais lever,
    sinon un démarrage planterait sur un simple fichier abîmé."""
    data = _lire_json_tolerant(TOMBES_FICHIER, [])
    if not isinstance(data, list):
        return []
    # Ne garde que les empreintes valides (sha256 hexa = 64 chars).
    return [e for e in data if isinstance(e, str) and len(e) == 64]


def _tombes_deposer(faits: list[str]) -> None:
    if not faits:
        return
    tombes = set(_tombes_charger())
    tombes.update(_empreinte_chaine(f) for f in faits)
    try:
        TOMBES_FICHIER.parent.mkdir(parents=True, exist_ok=True)
        contenu = json.dumps(sorted(tombes), ensure_ascii=False)
        # Écriture atomique + copie .bak — règle 4b.
        _ecrire_texte_atomique(TOMBES_FICHIER, contenu)
        try:
            _ecrire_texte_atomique(
                TOMBES_FICHIER.with_suffix(TOMBES_FICHIER.suffix + ".bak"),
                contenu)
        except OSError:
            pass  # pas grave : le fichier principal existe déjà
    except OSError:
        pass


# ─── La mémoire longue durée curée : memoire.md ─────────────────────────────

MOTIFS_SENSIBLES = [
    r"sk-[A-Za-z0-9]{20,}",
    r"Bearer\s+[A-Za-z0-9._\-]{20,}",
    r"(?i)(mot de passe|password|carte bancaire|cb\s*\d)",
    r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b",   # numéro de carte
]


def _fait_sensible(texte: str) -> bool:
    return any(re.search(m, texte) for m in MOTIFS_SENSIBLES)


def memoire_noter(categorie: str, fait: str) -> str:
    """Ajoute un fait curé à memoire.md, borné et filtré.

    Retourne un message de statut. Refuse (sans écrire) si le fait est
    manifestement sensible, s'il ressemble trop à un fait déjà noté (SimHash,
    porté de soulbook), s'il a été oublié (pierre tombale, portée d'Oblivion),
    ou si le fichier dépasserait MEMOIRE_PLAFOND.
    La décision de CE QUI mérite d'être noté relève du prompt (Codex), pas
    de cette fonction — elle ne fait qu'appliquer les bornes.
    """
    fait = unicodedata.normalize("NFC", fait.strip())
    if not fait:
        return "Refusé : fait vide."
    if _fait_sensible(fait):
        return "Refusé : le fait ressemble à une donnée sensible, on ne le stocke pas."

    # Pierre tombale : ce fait-là a été explicitement oublié — il ne revient pas.
    if _empreinte_chaine(fait) in set(_tombes_charger()):
        return ("Refusé : ce fait a été oublié (pierre tombale). "
                "Pour le réintroduire, il faut d'abord lever la tombe.")

    ligne = f"- {fait}  _(noté le {datetime.now():%Y-%m-%d})_\n"
    # Lecture tolérante (règle 4b) : un memoire.md récemment tronqué abîme
    # le démarrage sinon.
    existant = _lire_texte_tolerant(MEMOIRE_FICHIER)

    # SimHash : ne pas noter une deuxième fois le même fait à un mot près.
    doublon = _quasi_doublon(fait, _lignes_faits(existant))
    if doublon is not None:
        return (f"Refusé (quasi-doublon) : « {fait} » ressemble trop à "
                f"« {doublon} » déjà noté. Pour le remplacer, supprime l'ancien "
                f"avec memoire_oublier puis note le nouveau.")

    total = len(existant) + len(ligne)
    if total > MEMOIRE_PLAFOND:
        return (f"Refusé : memoire.md dépasserait le plafond "
                f"({MEMOIRE_PLAFOND} caractères). Purger d'abord des faits.")

    entete = f"## {categorie.strip()}"
    if entete in existant:
        nouveau = existant.replace(entete, entete + "\n" + ligne.rstrip("\n"), 1)
    else:
        nouveau = (existant.rstrip("\n") + f"\n\n{entete}\n" + ligne
                   if existant else f"# Mémoire de Root — faits durables\n\n{entete}\n" + ligne)
    # Écriture atomique (rule 4b) : memoire.md est le seul artefact persistent
    # de l'axe, une interruption ne doit jamais le laisser tronqué.
    _ecrire_texte_atomique(MEMOIRE_FICHIER, nouveau)
    return f"Noté ({len(nouveau)}/{MEMOIRE_PLAFOND} caractères)."


def memoire_oublier(motif: str) -> str:
    """Supprime de memoire.md les lignes qui contiennent `motif`
    (insensible à la casse, sur le texte normalisé).

    Après suppression, l'empreinte (sha256 du texte plié) de chaque ligne
    retirée est déposée dans le registre des pierres tombales
    (~/.local/root-tombes.json) : memoire_noter refusera ensuite toute
    réintroduction du même fait (à casse/accents/blancs près). Jamais le
    texte oublié n'est conservé — seulement son empreinte.
    """
    if not MEMOIRE_FICHIER.exists():
        return "Rien à oublier : memoire.md n'existe pas."
    # Lecture tolérante : un memoire.md partiellement illisible est vidé
    # plutôt que de planter en plein redémarrage.
    lignes = _lire_texte_tolerant(MEMOIRE_FICHIER).splitlines()
    motif_n = unicodedata.normalize("NFC", motif).lower()
    supprimees_textes = [re.sub(r"\s+_\(noté le [^)]+\)_\s*$", "", l[2:])
                         for l in lignes
                         if l.startswith("- ") and motif_n in l.lower()]
    gardees = [l for l in lignes
               if not l.startswith("- ") or motif_n not in l.lower()]
    supprimees = len(supprimees_textes)
    if supprimees:
        _ecrire_texte_atomique(MEMOIRE_FICHIER, "\n".join(gardees) + "\n")
        _tombes_deposer(supprimees_textes)
    return f"{supprimees} ligne(s) supprimée(s)."


def memoire_pour_prompt() -> str:
    """Contenu de memoire.md prêt à être injecté dans le prompt (au démarrage).

    Borné à MEMOIRE_PLAFOND, filtré une dernière fois. C'est la SEULE donnée
    persistée qui entre telle quelle dans le prompt — donc tout ce qu'elle
    contient part au cloud à chaque session : ne jamais y stocker ce qu'on
    ne veut pas chez DeepSeek.
    """
    if not MEMOIRE_FICHIER.exists():
        return ""
    # Lecture tolérante (règle 4b) : un redémarrage après corruption doit
    # renvoyer un prompt vide, pas planter.
    texte = _lire_texte_tolerant(MEMOIRE_FICHIER)
    return _rediger(texte[:MEMOIRE_PLAFOND])


# ─────────────────────────────────────────────────────────────────────────────
# Rappel par pertinence — sélection des faits durables au moment d'une demande
# ─────────────────────────────────────────────────────────────────────────────
#
# Contrairement à memoire_pour_prompt() (qui renvoie TOUT le contenu persisté,
# borné au plafond, pour le démarrage d'une session), rappel_pertinent() et
# rappel_pour_prompt() répondent à la question « quels souvenirs sont utiles
# MAINTENANT pour cette demande précise ? ». La boucle (root.py) est censée les
# appeler à chaque tour utilisateur et les injecter à côté du message, en plus
# du bloc de démarrage. Le rappel court-circuite le plafond : même une mémoire
# longue peut « remonter » le fait d'il y a trois mois qui colle à la demande.
#
# Stratégie : purement lexicale, bibliothèque standard uniquement, AUCUN appel
# modèle. On réutilise `_plier` (NFKC + retrait des accents) et `_mots`
# (tokenisation tolérante à la ponctuation) qui servent déjà aux quasi-doublons
# : même normalisation, mêmes ensembles, deux usages.
#
# Métrique = Jaccard classique : |A ∩ B| / |A ∪ B| entre les mots de la demande
# et les mots du fait. Un fait sans aucun mot commun a score 0 et n'est PAS
# renvoyé : mieux vaut une liste vide qu'un « top 5 » rempli de bruit.
# Le départage des scores égaux se fait par ordre d'apparition dans memoire.md
# (le fait le plus ancien gagne : stabilité déterministe, aucun aléas).

def rappel_pertinent(demande: str, n: int = 5) -> list:
    """Renvoie les n faits durables les plus pertinents pour `demande`.

    - `demande` vide ou mémoire vide → liste vide.
    - Aucun recouvrement (score nul pour tous les faits) → liste vide : on
      préfère « rien à rappeler » à « rappeler du bruit ».
    - Accents et casse normalisés via `_plier` (idem quasi-doublons).
    - Départage stable : en cas d'égalité stricte, le fait le plus ancien
      (index le plus petit dans memoire.md) gagne — déterministe, aucune
      dépendance à l'ordre interne d'un dict ou d'un set.

    Ne modifie rien sur disque ; lecteur pur. Renvoie une liste de str (les
    lignes de fait brutes, sans `- ` ni mention « (noté le ...) » ajoutée lors
    de `memoire_noter`), dans l'ordre de pertinence décroissante.
    """
    # Mémoire absente ou illisible → liste vide, sans jamais lever (règle 4b).
    if not MEMOIRE_FICHIER.exists():
        return []
    texte = _lire_texte_tolerant(MEMOIRE_FICHIER)
    if not texte.strip():
        return []
    faits = _lignes_faits(texte)
    if not faits:
        return []

    mots_demande = set(_mots(demande))
    if not mots_demande:
        return []

    # Scoring : Jaccard(demande, fait). On calcule une fois par fait, on garde
    # (score, index, texte) pour pouvoir départager en (-score, index asc).
    scores: list[tuple[float, int, str]] = []
    for i, fait in enumerate(faits):
        mots_fait = set(_mots(fait))
        if not mots_fait:
            continue
        inter = len(mots_demande & mots_fait)
        if inter == 0:
            continue  # aucun recouvrement : on préfère « rien » au bruit
        union = len(mots_demande | mots_fait)
        score = inter / union
        scores.append((score, i, fait))

    if not scores:
        return []

    # Tri : score décroissant ; en cas d'égalité, index croissant (fait le plus
    # ancien d'abord). n <= 0 → liste vide quoi qu'il arrive.
    if n <= 0:
        return []
    scores.sort(key=lambda item: (-item[0], item[1]))
    return [fait for _score, _i, fait in scores[:n]]


def rappel_pour_prompt(demande: str, n: int = 5) -> str:
    """Formate le rappel pertinent pour injection dans le prompt.

    Style calqué sur memoire_pour_prompt (retourne une str prête à coller
    dans un message système, ou "" si rien à rappeler). Cohérent avec la
    logique du dépôt : texte nu, pas de décorateur caché, aucune injection
    surprise. Le header est bref et se suffit à lui-même pour que le modèle
    comprenne ce qu'il lit.
    """
    faits = rappel_pertinent(demande, n)
    if not faits:
        return ""
    lignes = ["Souvenirs durables pertinents pour la demande actuelle :"]
    lignes.extend(f"- {fait}" for fait in faits)
    return "\n".join(lignes)


# ─────────────────────────────────────────────────────────────────────────────
# Auto-tests hors ligne (python memoire.py) — aucun réseau, aucun accès modèle
# ─────────────────────────────────────────────────────────────────────────────

def _auto_tests() -> None:
    # tronquer_outil garde tête et queue, et le signale
    gros = "début\n" + ("ligne de remplissage\n" * 3000) + "FIN_ERREUR\n"
    tronque = tronquer_outil(gros, budget=5_000)
    assert "début" in tronque and "FIN_ERREUR" in tronque, "tête/queue perdues"
    assert "caractères omis au milieu" in tronque, "coupure non signalée"
    assert len(tronque) < 6_000, "troncature trop grande"

    # pas de troncation si sous le budget
    assert tronquer_outil("court") == "court"

    # estimer_tokens croît avec le contenu et les images
    m_texte = [{"role": "user", "content": "x" * 4_000}]
    assert estimer_tokens(m_texte) >= 1_000
    m_img = [{"role": "user", "content": [
        {"type": "text", "text": "regarde"},
        {"type": "image_url", "image_url": {"url": "data:..."}},
    ]}]
    assert estimer_tokens(m_img) >= TOKENS_PAR_IMAGE

    # compresser_milieu protège system + les derniers échanges
    conv = [{"role": "system", "content": "AME"}]
    for i in range(20):
        conv.append({"role": "user", "content": f"question {i}"})
        conv.append({"role": "assistant", "content": f"réponse {i}"})
    comp = compresser_milieu(conv)
    assert comp[0]["content"] == "AME", "message system altéré"
    assert comp[-1]["content"] == "réponse 19", "fin non protégée"
    assert any("Résumé des échanges anciens" in str(m.get("content"))
               for m in comp), "résumé absent"
    assert len(comp) < len(conv), "pas de compression"

    # signature stable et comparable
    s1 = signature_action("lire_fichier", {"chemin": "/a"}, "contenu")
    s2 = signature_action("lire_fichier", {"chemin": "/a"}, "contenu")
    s3 = signature_action("lire_fichier", {"chemin": "/b"}, "contenu")
    assert s1 == s2 and s1 != s3

    # memoire_noter borne et filtre (sur un fichier temporaire)
    global MEMOIRE_FICHIER
    sauve = MEMOIRE_FICHIER
    import tempfile
    MEMOIRE_FICHIER = Path(tempfile.mkdtemp()) / "memoire.md"
    try:
        assert "Noté" in memoire_noter("Pièges", "web_cliquer recharge lentement")
        assert "Refusé" in memoire_noter("X", "mon mot de passe est chou")
        texte = memoire_pour_prompt()
        assert "web_cliquer" in texte and "chou" not in texte
        memoire_oublier("web_cliquer")
        assert "web_cliquer" not in memoire_pour_prompt()
    finally:
        MEMOIRE_FICHIER = sauve

    # journal JSONL : append, relire, tolère une ligne coupée
    import tempfile
    global SESSIONS_DOSSIER
    sauve_d = SESSIONS_DOSSIER
    SESSIONS_DOSSIER = Path(tempfile.mkdtemp())
    try:
        assert journaliser({"type": "fait", "resume": "premier"})
        chemin = journal_du_jour()
        with chemin.open("a") as f:
            f.write('{"type": "coup')  # ligne volontairement incomplète
        entrees = relire_journal(chemin)
        assert len(entrees) == 1 and entrees[0]["resume"] == "premier"
    finally:
        SESSIONS_DOSSIER = sauve_d

    print("auto-tests mémoire : OK")


if __name__ == "__main__":
    _auto_tests()
