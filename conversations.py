"""
Conversations : toutes celles de Vincent, de tous ses LLM, au même endroit.

Sources, lues sans jamais être modifiées :
  - Root      : ~/.local/root-conversations/root/<id>.json (écrites par la fenêtre)
  - Claude    : ~/.claude/projects/*/<session>.jsonl (Claude Code)
  - Codex     : ~/.codex/state_5.sqlite (liste) + le fichier « rollout » de chaque fil
  - Hermes    : ~/.hermes/state.db (et les profils qui ont des sessions)

Ce que Vincent décide (titre, projet, épingle, masquée) vit dans un seul fichier
à Root, meta.json : les fichiers des autres outils ne sont jamais touchés.

Le balayage est mis en cache par (taille, date) de chaque fichier : le premier
passage lit tout, les suivants ne relisent que ce qui a changé. Le texte de chaque
conversation est gardé à part (textes/) pour la recherche.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import time
import unicodedata
import uuid
from contextlib import closing
from pathlib import Path

DOSSIER = Path.home() / ".local" / "root-conversations"
CLAUDE_PROJETS = Path.home() / ".claude" / "projects"
CODEX_DB = Path.home() / ".codex" / "state_5.sqlite"
HERMES = Path.home() / ".hermes"

SOURCES = {"root": "Root", "claude": "Claude Code", "codex": "Codex", "hermes": "Hermes"}
PROJETS_DE_DEPART = ["Contingency", "Hackathon Munich", "Root"]
TEXTE_MAX = 8000          # caractères gardés par message pour l'affichage
REPRISE_MAX = 12000       # caractères d'historique donnés au cerveau pour continuer

_verrou = threading.Lock()


# ── Petits outils ───────────────────────────────────────────────────────────
def _root_dir() -> Path:
    return DOSSIER / "root"


def _normal(s: str) -> str:
    """minuscules, sans accents : « Hackathon Münich » → « hackathon munich »."""
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _titre_de(texte: str, n: int = 70) -> str:
    t = " ".join((texte or "").split())
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def _court(t: str) -> str:
    return t if len(t) <= TEXTE_MAX else t[:TEXTE_MAX] + "\n…"


def _bruit(texte: str) -> bool:
    """Messages techniques injectés par les outils (consignes, rappels, commandes)."""
    t = texte.lstrip()
    return (not t or t.startswith("<") or t.startswith("# AGENTS.md")
            or t.startswith("This session is being continued from a previous conversation"))


def _ajouter(fil: list, role: str, texte: str = "", nom: str = "") -> None:
    """Pose un élément dans le fil simplifié ; les outils qui se suivent sont
    regroupés en une seule puce, et les doublons consécutifs écartés."""
    if role == "outil":
        if fil and fil[-1]["r"] == "outils":
            fil[-1]["noms"].append(nom)
        else:
            fil.append({"r": "outils", "noms": [nom]})
        return
    texte = (texte or "").strip()
    if not texte:
        return
    if fil and fil[-1]["r"] == role and fil[-1].get("t") == _court(texte):
        return
    fil.append({"r": role, "t": _court(texte)})


def _texte_parties(contenu) -> str:
    if isinstance(contenu, str):
        return contenu
    if isinstance(contenu, list):
        return "\n".join(p.get("text", "") for p in contenu
                         if isinstance(p, dict) and p.get("type") in ("text", "input_text", "output_text"))
    return ""


# ── Lecteurs : un par source. Chacun rend (infos, fil). ─────────────────────
def lire_claude(chemin: Path):
    fil, titre, cwd, modele, premier, fin, entree = [], "", "", "", "", 0.0, ""
    with open(chemin, encoding="utf-8", errors="replace") as f:
        for ligne in f:
            if ligne.startswith('{"type"'):           # titres, et les lignes lourdes sans intérêt
                if '"ai-title"' in ligne[:30] or '"custom-title"' in ligne[:30]:
                    try:
                        d = json.loads(ligne)
                        titre = d.get("customTitle") or d.get("aiTitle") or titre
                    except json.JSONDecodeError:
                        pass
                continue
            try:
                d = json.loads(ligne)
            except json.JSONDecodeError:
                continue
            genre = d.get("type")
            if genre not in ("user", "assistant") or d.get("isSidechain") or d.get("isMeta"):
                continue
            cwd = cwd or d.get("cwd", "")
            entree = entree or d.get("entrypoint", "")
            fin = d.get("timestamp") or fin
            contenu = (d.get("message") or {}).get("content")
            if genre == "user":
                if isinstance(contenu, list) and all(isinstance(p, dict) and p.get("type") == "tool_result"
                                                     for p in contenu):
                    continue
                t = _texte_parties(contenu)
                if d.get("isCompactSummary") or _bruit(t):
                    continue
                premier = premier or t
                _ajouter(fil, "toi", t)
            else:
                modele = (d.get("message") or {}).get("model") or modele
                for p in contenu if isinstance(contenu, list) else []:
                    if p.get("type") == "text":
                        _ajouter(fil, "root", p.get("text", ""))
                    elif p.get("type") == "tool_use":
                        _ajouter(fil, "outil", nom=p.get("name", "outil"))
    return {"titre": titre or _titre_de(premier), "cwd": cwd, "cerveau": modele,
            "date": _horodatage(fin) or chemin.stat().st_mtime, "premier": premier,
            "auto": entree == "sdk-cli"}, fil


def lire_rollout_codex(chemin: Path):
    fil, premier = [], ""
    with open(chemin, encoding="utf-8", errors="replace") as f:
        for ligne in f:
            if '"response_item"' not in ligne[:160]:
                continue
            try:
                p = json.loads(ligne).get("payload") or {}
            except json.JSONDecodeError:
                continue
            if p.get("type") == "message" and p.get("role") in ("user", "assistant"):
                t = _texte_parties(p.get("content"))
                if p["role"] == "user":
                    if _bruit(t):
                        continue
                    premier = premier or t
                    _ajouter(fil, "toi", t)
                else:
                    _ajouter(fil, "root", t)
            elif p.get("type") in ("custom_tool_call", "function_call"):
                _ajouter(fil, "outil", nom=p.get("name", "outil"))
    return premier, fil


def lire_hermes(db: Path, ident: str):
    fil = []
    with _ouvrir_ro(db) as cx:
        for role, contenu, appels, outil in cx.execute(
                "select role, content, tool_calls, tool_name from messages "
                "where session_id=? order by id", (ident,)):
            if role == "user" and not _bruit(contenu or ""):
                _ajouter(fil, "toi", contenu or "")
            elif role == "assistant":
                _ajouter(fil, "root", contenu or "")
                for a in _json_liste(appels):
                    _ajouter(fil, "outil", nom=(a.get("function") or {}).get("name") or a.get("name") or "outil")
    return fil


def lire_root(chemin: Path):
    d = json.loads(chemin.read_text(encoding="utf-8"))
    fil, premier = [], ""
    for m in d.get("messages", []):
        role = m.get("role")
        if role == "user":
            t = _texte_parties(m.get("content"))
            premier = premier or t
            _ajouter(fil, "toi", t)
        elif role == "assistant":
            _ajouter(fil, "root", _texte_parties(m.get("content")))
            for a in m.get("tool_calls") or []:
                _ajouter(fil, "outil", nom=(a.get("function") or {}).get("name", "outil"))
    return d, premier, fil


def _horodatage(iso) -> float:
    if isinstance(iso, (int, float)):
        return float(iso)
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _json_liste(brut):
    try:
        v = json.loads(brut) if brut else []
        return v if isinstance(v, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _ouvrir_ro(db: Path):
    return closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=3))


def _hermes_bases() -> list[tuple[str, Path]]:
    bases = [("", HERMES / "state.db")]
    for p in sorted((HERMES / "profiles").glob("*/state.db")):
        bases.append((p.parent.name, p))
    return [(profil, b) for profil, b in bases if b.exists()]


# ── Le cache ────────────────────────────────────────────────────────────────
def _cache_fichier() -> Path:
    return DOSSIER / "index.json"


def _lire_json(chemin: Path, defaut):
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaut


def _ecrire_json(chemin: Path, valeur) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_suffix(".tmp")
    tmp.write_text(json.dumps(valeur, ensure_ascii=False), encoding="utf-8")
    tmp.replace(chemin)


def _texte_cle(cle: str) -> Path:
    return DOSSIER / "textes" / (hashlib.sha1(cle.encode()).hexdigest() + ".txt")


def _garder_texte(cle: str, info: dict, fil: list) -> None:
    morceaux = [info.get("titre", ""), info.get("cwd", "")]
    morceaux += [x.get("t", "") for x in fil]
    f = _texte_cle(cle)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(_normal("\n".join(morceaux)), encoding="utf-8")


def _empreinte(chemin: Path) -> str:
    s = chemin.stat()
    return f"{s.st_size}:{int(s.st_mtime)}"


def balayer() -> list[dict]:
    """Toutes les conversations, de toutes les sources (sans le choix de Vincent)."""
    with _verrou:
        ancien = _lire_json(_cache_fichier(), {})
        neuf, liste = {}, []

        def par_fichier(cle, chemin, lire):
            emp = _empreinte(chemin)
            if ancien.get(cle, {}).get("emp") == emp:
                info = ancien[cle]["info"]
            else:
                info, fil = lire()
                info["n"] = len(fil)
                _garder_texte(cle, info, fil)
            neuf[cle] = {"emp": emp, "info": info}
            if not info.get("auto"):          # appels automatiques (claude -p, codex exec…)
                liste.append({"cle": cle, **info})

        # Root
        for f in sorted(_root_dir().glob("*.json")) if _root_dir().is_dir() else []:
            def lire(f=f):
                d, premier, fil = lire_root(f)
                return {"titre": d.get("titre") or _titre_de(premier), "cwd": "",
                        "cerveau": d.get("cerveau", ""), "date": d.get("maj", f.stat().st_mtime),
                        "premier": premier[:300]}, fil
            par_fichier(f"root:{f.stem}", f, lire)

        # Claude Code (les sous-agents sont dans des sous-dossiers : écartés)
        if CLAUDE_PROJETS.is_dir():
            for f in CLAUDE_PROJETS.glob("*/*.jsonl"):
                def lire(f=f):
                    info, fil = lire_claude(f)
                    info["premier"] = info["premier"][:300]
                    return info, fil
                try:
                    par_fichier(f"claude:{f.stem}", f, lire)
                except OSError:
                    continue

        # Codex : la base donne la liste et le titre, le rollout donne le texte
        if CODEX_DB.exists():
            try:
                with _ouvrir_ro(CODEX_DB) as cx:
                    lignes = cx.execute(
                        "select id, rollout_path, title, name, cwd, model, updated_at, first_user_message "
                        "from threads where archived=0 and coalesce(thread_source,'') != 'subagent' "
                        "and source not like '%subagent%' and source != 'exec'").fetchall()
            except sqlite3.Error:
                lignes = []
            for ident, rollout, titre, nom, cwd, modele, maj, premier_db in lignes:
                chemin = Path(rollout or "")
                if not chemin.exists():
                    continue
                def lire(chemin=chemin, titre=titre, nom=nom, cwd=cwd, modele=modele, maj=maj, premier_db=premier_db):
                    premier, fil = lire_rollout_codex(chemin)
                    return {"titre": nom or titre or _titre_de(premier or premier_db or ""), "cwd": cwd or "",
                            "cerveau": modele or "", "date": float(maj or chemin.stat().st_mtime),
                            "premier": (premier or premier_db or "")[:300]}, fil
                par_fichier(f"codex:{ident}", chemin, lire)

        # Hermes : sessions en base, relues à chaque fois (requête rapide)
        for profil, db in _hermes_bases():
            try:
                with _ouvrir_ro(db) as cx:
                    sessions = cx.execute(
                        "select id, title, model, cwd, started_at, last_activity_at, message_count "
                        "from sessions where coalesce(hidden,0)=0 and coalesce(archived,0)=0 "
                        "and coalesce(source,'cli') not in ('cron','subagent','tool') "
                        "and coalesce(message_count,0) > 0").fetchall()
            except sqlite3.Error:
                continue
            for ident, titre, modele, cwd, debut, maj, n in sessions:
                cle = f"hermes:{profil + '/' if profil else ''}{ident}"
                emp = f"{n}:{maj}"
                if ancien.get(cle, {}).get("emp") == emp:
                    info = ancien[cle]["info"]
                else:
                    fil = lire_hermes(db, ident)
                    premier = next((x["t"] for x in fil if x["r"] == "toi"), "")
                    info = {"titre": titre or _titre_de(premier), "cwd": cwd or "", "cerveau": modele or "",
                            "date": float(maj or debut or 0), "premier": premier[:300], "n": len(fil),
                            "profil": profil}
                    _garder_texte(cle, info, fil)
                neuf[cle] = {"emp": emp, "info": info}
                liste.append({"cle": cle, **info})

        _ecrire_json(_cache_fichier(), neuf)
        return liste


# ── Le choix de Vincent : titres, projets, épingles (meta.json) ─────────────
def _meta_fichier() -> Path:
    return DOSSIER / "meta.json"


def meta() -> dict:
    m = _lire_json(_meta_fichier(), None)
    if m is None:
        m = {"projets": [{"id": _id_projet(n), "nom": n} for n in PROJETS_DE_DEPART], "conv": {}}
        _ecrire_json(_meta_fichier(), m)
    m.setdefault("projets", [])
    m.setdefault("conv", {})
    return m


def _id_projet(nom: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", _normal(nom)).strip("-") or "projet"
    return f"{base}-{uuid.uuid4().hex[:4]}"


def _changer_conv(cle: str, **valeurs) -> None:
    with _verrou:
        m = meta()
        m["conv"].setdefault(cle, {}).update(valeurs)
        _ecrire_json(_meta_fichier(), m)


def renommer(cle: str, titre: str) -> None:
    _changer_conv(cle, titre=titre.strip()[:120])


def ranger(cle: str, projet: str | None) -> None:
    """projet = id d'un projet, ou "" pour « Non classées » (choix explicite)."""
    _changer_conv(cle, projet=projet or "")


def epingler(cle: str, oui: bool) -> None:
    _changer_conv(cle, epingle=bool(oui))


def masquer(cle: str) -> None:
    _changer_conv(cle, masque=True)


def creer_projet(nom: str) -> dict:
    with _verrou:
        m = meta()
        p = {"id": _id_projet(nom), "nom": nom.strip()[:60] or "Projet"}
        m["projets"].append(p)
        _ecrire_json(_meta_fichier(), m)
        return p


def renommer_projet(ident: str, nom: str) -> None:
    with _verrou:
        m = meta()
        for p in m["projets"]:
            if p["id"] == ident:
                p["nom"] = nom.strip()[:60] or p["nom"]
        _ecrire_json(_meta_fichier(), m)


def supprimer_projet(ident: str) -> None:
    """Le projet disparaît ; ses conversations reviennent dans « Non classées »."""
    with _verrou:
        m = meta()
        m["projets"] = [p for p in m["projets"] if p["id"] != ident]
        for c in m["conv"].values():
            if c.get("projet") == ident:
                c["projet"] = ""
        _ecrire_json(_meta_fichier(), m)


def suggerer(entree: dict, projets: list[dict]) -> str | None:
    """Projet proposé d'après les mots de son nom : tous doivent apparaître
    (en mot entier, pluriel admis) dans le titre, le dossier ou le premier message."""
    texte = _normal(" ".join([entree.get("titre", ""), entree.get("cwd", ""), entree.get("premier", "")]))
    for p in projets:
        mots = [w for w in re.findall(r"[a-z0-9]+", _normal(p["nom"])) if len(w) >= 3]
        if mots and all(re.search(r"(?<![a-z0-9])" + re.escape(w) + r"s?(?![a-z0-9])", texte) for w in mots):
            return p["id"]
    return None


def lister(entrees: list[dict] | None = None) -> dict:
    """La liste prête pour le panneau : chaque conversation avec son titre,
    son projet (choisi ou proposé), son épingle. Plus récentes d'abord."""
    entrees = balayer() if entrees is None else entrees
    m = meta()
    ids = {p["id"] for p in m["projets"]}
    sortie = []
    for e in entrees:
        choix = m["conv"].get(e["cle"], {})
        if choix.get("masque"):
            continue
        source = e["cle"].split(":", 1)[0]
        if "projet" in choix:
            projet, auto = (choix["projet"] if choix["projet"] in ids else ""), False
        else:
            projet, auto = (suggerer(e, m["projets"]) or ""), True
        sortie.append({"cle": e["cle"], "source": source, "titre": choix.get("titre") or e.get("titre") or "Sans titre",
                       "cerveau": e.get("cerveau", ""), "date": e.get("date", 0), "cwd": e.get("cwd", ""),
                       "n": e.get("n", 0), "projet": projet, "auto": auto and bool(projet),
                       "epingle": bool(choix.get("epingle"))})
    sortie.sort(key=lambda x: x["date"], reverse=True)
    return {"projets": m["projets"], "liste": sortie}


def chercher(requete: str, cles: list[str]) -> list[str]:
    """Les clés dont le texte contient tous les mots de la requête."""
    mots = _normal(requete).split()
    if not mots:
        return cles
    trouvees = []
    for cle in cles:
        try:
            texte = _texte_cle(cle).read_text(encoding="utf-8")
        except OSError:
            continue
        if all(w in texte for w in mots):
            trouvees.append(cle)
    return trouvees


# ── Lire une conversation entière ───────────────────────────────────────────
def ouvrir(cle: str) -> dict:
    source, ident = cle.split(":", 1)
    if source == "root":
        d, premier, fil = lire_root(_root_dir() / f"{ident}.json")
        return {"source": source, "fil": fil, "brut": d}
    if source == "claude":
        chemin = next(CLAUDE_PROJETS.glob(f"*/{ident}.jsonl"), None)
        if chemin is None:
            raise FileNotFoundError(cle)
        info, fil = lire_claude(chemin)
        return {"source": source, "fil": fil, "cwd": info["cwd"]}
    if source == "codex":
        with _ouvrir_ro(CODEX_DB) as cx:
            r = cx.execute("select rollout_path, cwd from threads where id=?", (ident,)).fetchone()
        if not r:
            raise FileNotFoundError(cle)
        _, fil = lire_rollout_codex(Path(r[0]))
        return {"source": source, "fil": fil, "cwd": r[1] or ""}
    if source == "hermes":
        profil, _, sid = ident.rpartition("/")
        db = (HERMES / "profiles" / profil / "state.db") if profil else HERMES / "state.db"
        with _ouvrir_ro(db) as cx:
            r = cx.execute("select cwd from sessions where id=?", (sid,)).fetchone()
        return {"source": source, "fil": lire_hermes(db, sid), "cwd": (r[0] if r else "") or "", "profil": profil}
    raise ValueError(cle)


def contexte_reprise(cle: str, titre: str, fil: list) -> str:
    """Le texte donné au cerveau pour continuer une conversation d'un autre outil :
    le premier message, puis les derniers échanges qui tiennent dans REPRISE_MAX."""
    nom = SOURCES.get(cle.split(":", 1)[0], "un autre outil")
    lignes = [f"{'Vincent' if x['r'] == 'toi' else nom} : {x['t']}" for x in fil if x["r"] in ("toi", "root")]
    if not lignes:
        return f"Cette conversation reprend « {titre} » ({nom}), qui ne contient pas de texte."
    debut, fin, taille = lignes[0], [], len(lignes[0])
    for l in reversed(lignes[1:]):
        if taille + len(l) > REPRISE_MAX:
            break
        fin.insert(0, l)
        taille += len(l)
    saut = len(lignes) - 1 - len(fin)
    corps = [debut] + ([f"[… {saut} messages omis …]"] if saut else []) + fin
    return (f"Cette conversation reprend un échange que Vincent a eu dans {nom}, intitulé « {titre} ». "
            "Voici son début et ses derniers échanges, en texte seul (les actions d'outils ne sont pas "
            "reprises). Continue à partir de là.\n\n" + "\n\n".join(corps))


def commande_reprise(cle: str, info: dict) -> list[str] | None:
    """La commande qui rouvre la session dans son outil d'origine."""
    source, ident = cle.split(":", 1)
    if source == "claude":
        return ["claude", "--resume", ident]
    if source == "codex":
        return ["codex", "resume", ident]
    if source == "hermes" and not info.get("profil"):
        return ["hermes", "--resume", ident.rpartition("/")[2]]
    return None


# ── Les conversations de Root ───────────────────────────────────────────────
def nouvel_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]


def _sans_images(messages: list[dict]) -> list[dict]:
    """Les captures en base64 pèseraient des Mo : on garde leur étiquette."""
    propres = []
    for m in messages:
        c = m.get("content")
        if isinstance(c, list):
            c = [p if not (isinstance(p, dict) and p.get("type") == "image_url")
                 else {"type": "text", "text": "[image retirée de la sauvegarde]"} for p in c]
        propres.append({k: v for k, v in m.items() if k != "content"} | {"content": c})
    return propres


def sauver_root(ident: str, messages: list[dict], cerveau: str, origine: str = "") -> None:
    f = _root_dir() / f"{ident}.json"
    ancien = _lire_json(f, {})
    premier = next((_texte_parties(m.get("content")) for m in messages if m.get("role") == "user"), "")
    d = {"id": ident, "titre": ancien.get("titre") or _titre_de(premier),
         "cree": ancien.get("cree", time.time()), "maj": time.time(), "cerveau": cerveau,
         "origine": origine or ancien.get("origine", ""), "messages": _sans_images(messages)}
    _ecrire_json(f, d)


def supprimer_root(ident: str) -> None:
    (_root_dir() / f"{ident}.json").unlink(missing_ok=True)
    cle = f"root:{ident}"
    _texte_cle(cle).unlink(missing_ok=True)
    with _verrou:
        m = meta()
        m["conv"].pop(cle, None)
        _ecrire_json(_meta_fichier(), m)
