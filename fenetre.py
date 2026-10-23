"""
La fenêtre de Root : une vraie app, pas un terminal.

L'interface est peinte en HTML/CSS/JS (dossier ui/), affichée dans une fenêtre
native macOS par pywebview (WebKit). Le moteur est celui du terminal : la même
boucle `root.un_tour`, avec les 36 outils, la mémoire et les gardes de sécurité.
Seul le visage change : `EcranFenetre` remplace `EcranTerminal`.

Le dock d'actions en un clic est décrit dans ui/actions.json (personnel, hors du
dépôt) ou, à défaut, ui/actions.exemple.json. Les actions ne sont déclenchées que
par un clic ou un raccourci de l'utilisateur, jamais par le modèle.

Lancer :  ~/.local/root-venv/bin/python fenetre.py
"""

from __future__ import annotations

import base64
import json
import os
import shlex
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

import webview

import cerveaux        # les LLM interchangeables (cerveaux.json)
import conversations   # toutes les conversations, de tous les LLM
import memoire_edition # voir et retoucher la mémoire durable
import outils_reglages # le panneau Outils (couper, restreindre, autonomie)
import outils_externes # registre des outils que Vincent a envoyés (install + détection)
import ame             # l'âme de Root (socle gravé + couche modulable de Vincent)
import terminal_shell  # un vrai shell (PTY) dans la fenêtre, piloté par Vincent
import redteam         # cœur de red team IA (probe/detector/generator/harnais)
import pentest_journal  # trace durable des campagnes de pentest
import root            # le moteur : boucle, outils, mémoire, sécurité

ICI = Path(__file__).parent
UI = ICI / "ui"
REGLAGES = ICI / "reglages.local.json"     # choix de l'utilisateur, hors du dépôt


def lire_reglages() -> dict:
    try:
        return json.loads(REGLAGES.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def ecrire_reglages(**valeurs) -> None:
    r = lire_reglages()
    r.update(valeurs)
    REGLAGES.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
ENTETE_MEMOIRE = "Mémoire durable de Root :"

# Quand le cerveau est Anthropic, son filtre de sécurité refuse le contexte red
# team (observé le 23/10, refus reproductible même sur « salut »). On retire
# alors les sections dédiées cyber EN ENTIER, puis les puces sensibles
# éparpillées ailleurs. Les autres cerveaux (DeepSeek, Nebius, local) reçoivent
# la mémoire complète. Mesuré : sans ce filtre, refusal ; avec, end_turn.
SECTIONS_HORS_CLAUDE = ("cybersécurité", "cybersecurite", "certifs")
MOTS_HORS_CLAUDE = ("red team", "pentest", "offensif", "offensive", "exploit",
                    "faille", "vulnér", "vulner", "attaq", "garak", "ctf",
                    "bug bounty", "cyber", "hack", "immunit", "root-me",
                    "audit", "semgrep", "chiffr", "crypt", "scanner")


def _plier(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower())
                   if not unicodedata.combining(c))


def memoire_pour_cerveau(souvenirs: str, cerveau: dict | None) -> str:
    """Retire de la mémoire le contexte red team quand le cerveau est Claude :
    sections dédiées entières, puis puces sensibles ailleurs. Les titres de
    section restent comme repères. Les autres cerveaux reçoivent tout."""
    if not cerveau or cerveau.get("fournisseur") != "Anthropic":
        return souvenirs
    mots = [_plier(m) for m in MOTS_HORS_CLAUDE]
    out, saute = [], False
    for ligne in souvenirs.splitlines():
        if ligne.startswith("## "):
            saute = any(ligne[3:].strip().lower().startswith(p) for p in SECTIONS_HORS_CLAUDE)
            out.append(ligne)
            continue
        if saute:
            continue
        if ligne.strip() and not ligne.startswith("#") and any(m in _plier(ligne) for m in mots):
            continue
        out.append(ligne)
    return "\n".join(out)

VERSION = "1.0"
PANNEAUX_DOCK = [("cerveaux","Cerveaux"),("conversations","Conversations"),("memoire","Mémoire"),("outils","Outils"),("terminal","Terminal"),("pentest","Pentest"),("ame","Âme"),("proxy","Proxy")]
ATTENTE_MAX = 600      # secondes pour répondre à une demande d'autorisation
CHEMINS_CMD = [Path.home() / "bin", Path.home() / ".local" / "bin", Path("/opt/homebrew/bin")]


def charger_actions() -> list[dict]:
    for nom in ("actions.json", "actions.exemple.json"):
        f = UI / nom
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
    return []


class EcranFenetre:
    """Le visage fenêtre : mêmes méthodes que root.EcranTerminal, mais chaque
    événement part vers l'interface au lieu d'être imprimé."""

    def __init__(self, pont: "Pont"):
        self.pont = pont
        self.derniers_args = {}

    def appeler(self, messages, cle):
        self.pont.emettre({"type": "etat", "valeur": "reflechit"})
        return root.appeler_modele_robuste(messages, cle)

    def demander(self, nom, args):
        return self.pont.attendre_accord(nom, args)

    def outil(self, nom, args, illisible=False):
        self.derniers_args[nom] = args or {}
        detail = "arguments illisibles" if illisible else json.dumps(args or {}, ensure_ascii=False)
        self.pont.emettre({"type": "outil", "nom": nom, "args": detail[:300]})

    def resultat(self, nom, texte):
        self.pont.emettre({"type": "resultat", "nom": nom, "texte": texte})
        if nom in ("memoire_noter", "memoire_oublier"):        # la mémoire a bougé : on le montre
            self.pont.memoire_changee()
            args = self.derniers_args.get(nom, {})
            if nom == "memoire_noter" and texte.startswith("Noté"):
                self.pont.emettre({"type": "retenu", "fait": args.get("fait", ""),
                                   "categorie": args.get("categorie", "")})

    def image(self, chemin):
        miniature = self.pont.miniature(chemin)
        if miniature:
            self.pont.emettre({"type": "image", "src": miniature})

    def reponse(self, texte):
        self.pont.emettre({"type": "root", "texte": texte})

    def fin(self, secondes, usage=None):
        usage = usage or {"entree": 0, "sortie": 0}
        c = self.pont.cerveau
        demande = next((m.get("content") for m in reversed(self.pont.messages)
                        if m.get("role") == "user" and isinstance(m.get("content"), str)), "")
        self.pont.emettre({"type": "fin", "secondes": secondes, "cerveau": c["nom"],
                           "tokens": usage["entree"] + usage["sortie"],
                           "cout": cerveaux.cout(c, usage["entree"], usage["sortie"]),
                           "lies": memoire_edition.lies(demande, 3)})

    def arret(self, texte):
        self.pont.emettre({"type": "arret", "texte": texte})


class Pont:
    """Ce que la fenêtre peut appeler (côté JS : window.pywebview.api.*)."""

    def __init__(self):
        self.window = None
        self.cerveau = cerveaux.par_id(lire_reglages().get("cerveau", "")) or cerveaux.defaut()
        root.CERVEAU_COURANT = self.cerveau
        outils_reglages.appliquer_au_moteur()   # choix de Vincent → variables du moteur
        self.cle = root.charger_cle()            # clé DeepSeek, gardée pour resumer_blocs
        self.jour = root.tokens_charger()
        self.occupe = threading.Lock()
        self._accords: dict[int, dict] = {}
        self._shell = None            # le vrai terminal (PTY), à la demande
        self._n = 0
        self.nouvelle()
        # premier balayage des conversations en fond (1 à 2 s la première fois)
        threading.Thread(target=self._indexer, daemon=True).start()

    # ── appelé par le JS ────────────────────────────────────────────────────
    def pret(self):
        texte = (f"Me voilà, je pense avec **{self.cerveau['nom']}**. "
                 "Change de cerveau quand tu veux : l'icône à gauche, ou ⌘1.")
        if not cerveaux.cle(self.cerveau):
            texte = (f"La clé de {self.cerveau['fournisseur']} ({self.cerveau['cle']}) est absente : "
                     "choisis un autre cerveau à gauche, ou pose la clé.")
        self.emettre({"type": "cerveau", "id": self.cerveau["id"], "nom": self.cerveau["nom"]})
        self.emettre({"type": "root", "texte": texte})
        return True

    # ── cerveaux ────────────────────────────────────────────────────────────
    def cerveaux(self):
        champs = ("id", "nom", "fournisseur", "modele", "prix", "outils", "vision", "raisonnement", "note")
        return {"actif": self.cerveau["id"],
                "liste": [{k: c.get(k) for k in champs} for c in cerveaux.liste()]}

    def sonder_cerveaux(self):
        """Ping de chaque fournisseur en parallèle (une fois par fournisseur)."""
        resultats, fils = {}, []
        par_fournisseur = {}
        for c in cerveaux.liste():
            par_fournisseur.setdefault(c["fournisseur"], c)
        def sonder(f, c):
            resultats[f] = cerveaux.sonder(c)
        for f, c in par_fournisseur.items():
            t = threading.Thread(target=sonder, args=(f, c)); t.start(); fils.append(t)
        for t in fils:
            t.join(12)
        return {c["id"]: resultats.get(c["fournisseur"], {"ok": False}) for c in cerveaux.liste()}

    def choisir_cerveau(self, ident, repartir=False):
        c = cerveaux.par_id(ident)
        if c is None:
            return False
        if self.occupe.locked():
            self.emettre({"type": "toast", "texte": "Attends que Root ait fini de répondre.", "ok": False})
            return False
        self.cerveau = c
        root.CERVEAU_COURANT = c
        ecrire_reglages(cerveau=c["id"])
        if repartir:
            self.nouvelle()
        else:
            self._memoire_dans_prompt()   # re-filtre la mémoire selon le nouveau cerveau
        self.emettre({"type": "cerveau", "id": c["id"], "nom": c["nom"]})
        self.emettre({"type": "toast", "ok": True,
                      "texte": f"Root pense avec {c['nom']}" + (" · nouvelle conversation" if repartir else "")})
        return True

    def actions(self):
        return [{k: a.get(k) for k in ("id", "label", "icone", "raccourci", "type", "aide", "prefixe")}
                for a in charger_actions()]

    def envoyer(self, texte):
        if not self.occupe.acquire(blocking=False):
            self.emettre({"type": "toast", "texte": "Root est encore sur ta demande précédente.", "ok": False})
            return False
        threading.Thread(target=self._tour, args=(texte,), daemon=True).start()
        return True

    def repondre(self, ident, accord):
        attente = self._accords.get(int(ident))
        if attente:
            attente["accord"] = bool(accord)
            attente["evenement"].set()
        return True

    def action(self, ident):
        a = next((x for x in charger_actions() if x.get("id") == ident), None)
        if a is None:
            return False
        genre = a.get("type")
        if genre == "root":
            self.emettre({"type": "toi", "texte": a.get("prompt", "")})
            return self.envoyer(a.get("prompt", ""))
        if genre == "url":
            subprocess.Popen(["open", "-a", a.get("navigateur", "Brave Browser"), a["url"]])
            self.emettre({"type": "toast", "texte": f"{a['label']} : ouvert", "ok": True})
            return True
        if genre == "commande":
            threading.Thread(target=self._commande, args=(a,), daemon=True).start()
            return True
        return False

    def nouvelle(self):
        self.conv_id = conversations.nouvel_id()   # sauvegardée dès le premier message
        self.origine = ""                           # conversation d'un autre outil reprise ici
        self.lecture = None                         # conversation d'un autre outil affichée
        self.messages = [{"role": "system", "content": ame.ame_complete()}]
        self._memoire_dans_prompt()
        return True

    def _memoire_dans_prompt(self):
        """Pose (ou remet à jour) la mémoire durable juste après l'âme."""
        self.messages[:] = [m for m in self.messages
                            if not (m.get("role") == "system"
                                    and str(m.get("content", "")).startswith(ENTETE_MEMOIRE))]
        souvenirs = memoire_pour_cerveau(root.memoire.memoire_pour_prompt(), self.cerveau)
        if souvenirs.strip():
            self.messages.insert(1, {"role": "system", "content": ENTETE_MEMOIRE + "\n" + souvenirs})

    # ── pentest (red team sur les cerveaux) ─────────────────────────────────
    def pentest_etat(self):
        return {"probes": redteam.probes_disponibles(),
                "cerveaux": [{"id": c["id"], "nom": c["nom"], "fournisseur": c["fournisseur"]}
                             for c in cerveaux.liste() if cerveaux.cle(c)],
                "cibles_locales": redteam.cibles_locales(),
                "campagnes": pentest_journal.lister(),
                "failles": pentest_journal.failles()}

    def pentest_campagne(self, cid):
        return pentest_journal.campagne(int(cid))

    def pentest_mandat(self):
        return {"mandat": redteam.mandat(), "defaut": redteam.MANDAT_DEFAUT,
                "perso": (redteam.mandat() != redteam.MANDAT_DEFAUT)}

    def pentest_mandat_ecrire(self, texte):
        redteam.ecrire_mandat(texte)
        return True

    def pentest_supprimer(self, cid):
        pentest_journal.supprimer(int(cid))
        return True

    def pentest_lancer_cible(self, modele, essais=1):
        if not self.occupe.acquire(blocking=False):
            self.emettre({"type": "toast", "texte": "Root est occupé, réessaie après.", "ok": False})
            return False
        threading.Thread(target=self._pentest_cible, args=(modele, int(essais)), daemon=True).start()
        return True

    def _pentest_cible(self, modele, essais):
        try:
            gen, probe, secret = redteam.banc_cible(modele)
            total = len(list(probe.cas())) * max(1, essais)
            self.emettre({"type": "pentest_debut", "total": total, "cerveau": gen.nom})
            fait = [0]
            def progres(r):
                fait[0] += 1
                self.emettre({"type": "pentest_progres", "fait": fait[0], "total": total,
                              "probe": r.probe, "reussite": r.reussite, "indetermine": r.indetermine})
            rapport = redteam.Harnais(essais=essais).lancer([probe], gen, progres=progres)
            cid = pentest_journal.enregistrer(rapport, f"local:{modele}", ["extraction_secret"], essais)
            self.emettre({"type": "pentest_fini", "campagne_id": cid, "resume": rapport.texte()})
        except Exception as e:
            self.emettre({"type": "pentest_fini", "erreur": root.securite.rediger_secrets(str(e))})
        finally:
            self.occupe.release()

    def pentest_lancer(self, cerveau_id, probes_ids, essais=1):
        if not self.occupe.acquire(blocking=False):
            self.emettre({"type": "toast", "texte": "Root est occupé, réessaie après.", "ok": False})
            return False
        threading.Thread(target=self._pentest, args=(cerveau_id, list(probes_ids), int(essais)),
                         daemon=True).start()
        return True

    def _pentest(self, cerveau_id, probes_ids, essais):
        try:
            c = cerveaux.par_id(cerveau_id)
            if c is None or not cerveaux.cle(c):
                self.emettre({"type": "pentest_fini", "erreur": "Cerveau indisponible ou sans clé."})
                return
            probes = [redteam.PROBES_PAR_ID[i] for i in probes_ids if i in redteam.PROBES_PAR_ID]
            if not probes:
                self.emettre({"type": "pentest_fini", "erreur": "Aucune attaque choisie."})
                return
            total = sum(len(list(p.cas())) for p in probes) * max(1, essais)
            self.emettre({"type": "pentest_debut", "total": total, "cerveau": c["nom"]})
            fait = [0]
            def progres(r):
                fait[0] += 1
                self.emettre({"type": "pentest_progres", "fait": fait[0], "total": total,
                              "probe": r.probe, "reussite": r.reussite, "indetermine": r.indetermine})
            gen = redteam.CerveauGenerator(cerveau_id)
            rapport = redteam.Harnais(essais=essais).lancer(probes, gen, progres=progres)
            cid = pentest_journal.enregistrer(rapport, cerveau_id, probes_ids, essais)
            self.emettre({"type": "pentest_fini", "campagne_id": cid, "resume": rapport.texte()})
        except Exception as e:
            self.emettre({"type": "pentest_fini", "erreur": root.securite.rediger_secrets(str(e))})
        finally:
            self.occupe.release()

    # ── terminal (un vrai shell, c'est Vincent qui tape) ────────────────────
    def terminal_demarrer(self, colonnes=80, lignes=24):
        if self._shell and self._shell.vivant:
            return True
        def sortie(data):
            self.emettre({"type": "term", "data": terminal_shell.encoder(data)})
        def fin():
            self.emettre({"type": "term_fin"})
            self._shell = None
        self._shell = terminal_shell.Shell(sortie, fin)
        cwd = str(Path.home())
        self._shell.demarrer(colonnes, lignes, cwd)
        return True

    def terminal_entree(self, data):
        if self._shell:
            self._shell.ecrire(terminal_shell.decoder(data))
        return True

    def terminal_taille(self, colonnes, lignes):
        if self._shell:
            self._shell.redimensionner(colonnes, lignes)
        return True

    def terminal_arreter(self):
        if self._shell:
            self._shell.arreter()
            self._shell = None
        return True

    # ── outils ──────────────────────────────────────────────────────────────
    def outils(self):
        return outils_reglages.etat()

    def outil_basculer(self, nom, coupe):
        return outils_reglages.basculer(nom, coupe)

    def outil_strict(self, nom, strict):
        return outils_reglages.rendre_strict(nom, strict)

    def outils_prereglage(self, ident):
        return outils_reglages.appliquer_prereglage(ident)

    def outils_autonomie(self, mode):
        return outils_reglages.choisir_autonomie(mode)

    def terminal_auto_activer(self, actif):
        return outils_reglages.terminal_auto_activer(actif)

    def terminal_auto_prefixes(self, prefixes):
        return outils_reglages.terminal_auto_prefixes(prefixes)

    # Outils externes (ce que Vincent a envoyé : registre dans le code)
    def outils_externes(self):
        return outils_externes.etat()

    def outil_externe_installer(self, ident):
        threading.Thread(target=self._installer_externe, args=(ident,), daemon=True).start()
        self.emettre({"type": "toast", "texte": f"Installation de {ident} lancée…", "ok": True})
        return True

    def _installer_externe(self, ident):
        r = outils_externes.installer(ident)
        self.emettre({"type": "outil_installe", "id": ident, "ok": r["ok"], "message": r["message"]})

    # Mes outils (ajoutés par Vincent)
    def outil_perso_ajouter(self, nom, description, commande, argument=False, quand="", toujours_demander=True, source=""):
        return outils_reglages.ajouter_outil_perso(nom, description, commande, argument, quand, toujours_demander, source)

    def outil_perso_retirer(self, ident):
        return outils_reglages.retirer_outil_perso(ident)

    def outil_depuis_github(self, url):
        return outils_reglages.lire_readme_github(url)

    def ouvrir_lien(self, url):
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            subprocess.Popen(["open", "-a", "Brave Browser", url])
            return True
        return False

    # ── proxy / apprendre le test web ───────────────────────────────────────
    def proxy_etat(self):
        burp = Path("/Applications/Burp Suite.app").exists()
        import sys as _s
        venvbin = Path(_s.executable).parent
        mitm = bool(shutil.which("mitmdump") or (venvbin / "mitmdump").exists())
        return {"burp": burp, "mitmproxy": mitm}

    def ouvrir_burp(self):
        app = Path("/Applications/Burp Suite.app")
        if app.exists():
            subprocess.Popen(["open", "-a", "Burp Suite"])
            self.emettre({"type": "toast", "texte": "Burp Suite ouvert", "ok": True})
        else:
            subprocess.Popen(["open", "-a", "Brave Browser",
                              "https://portswigger.net/burp/communitydownload"])
            self.emettre({"type": "toast", "texte": "Burp non installé : page de téléchargement ouverte", "ok": False})
        return True

    # ── réglages ────────────────────────────────────────────────────────────
    def reglages_etat(self):
        r = lire_reglages()
        masques = set(r.get("dock_masques", []))
        return {"panneaux": [{"id": i, "label": l, "visible": i not in masques} for i, l in PANNEAUX_DOCK],
                "moins_animations": bool(r.get("moins_animations")),
                "fond": r.get("fond", ""),
                "apropos": {"nom": "Root", "version": VERSION,
                            "edition": "privée (cybersécurité incluse)",
                            "note": "Édition publique open source pour les 42 prévue (cœur sans la cyber)."}}

    def reglage_dock(self, ident, visible):
        r = lire_reglages()
        masques = set(r.get("dock_masques", []))
        masques.discard(ident) if visible else masques.add(ident)
        ecrire_reglages(dock_masques=sorted(masques))
        return True

    def reglage_animations(self, moins):
        ecrire_reglages(moins_animations=bool(moins))
        return True

    def choisir_fond(self):
        dlg = getattr(getattr(webview, "FileDialog", None), "OPEN", None)
        if dlg is None:
            dlg = webview.OPEN_DIALOG
        chemins = self.window.create_file_dialog(
            dlg, allow_multiple=False,
            file_types=("Images (*.jpg;*.jpeg;*.png)",))
        if not chemins:
            return None
        src = Path(chemins[0])
        dest = UI / "fond.local.jpg"
        try:
            if src.suffix.lower() in (".jpg", ".jpeg"):
                shutil.copy(src, dest)
            else:                                   # png → jpeg, pour rester léger
                subprocess.run(["sips", "-s", "format", "jpeg", str(src), "--out", str(dest)],
                               capture_output=True, timeout=20)
            ecrire_reglages(fond="fond.local.jpg")
            return "fond.local.jpg"
        except (OSError, subprocess.SubprocessError):
            return None

    def reglage_fond_defaut(self):
        ecrire_reglages(fond="")
        return True

    # ── âme ─────────────────────────────────────────────────────────────────
    def ame(self):
        return ame.etat()

    def ame_ton(self, texte):
        ame.ton(texte)
        self._ame_rafraichir()
        return True

    def ame_regle_ajouter(self, texte):
        ok = ame.ajouter_regle(texte)
        if ok:
            self._ame_rafraichir()
        return ok

    def ame_regle_modifier(self, ancien, nouveau):
        ok = ame.modifier_regle(ancien, nouveau)
        if ok:
            self._ame_rafraichir()
        return ok

    def ame_regle_retirer(self, texte):
        ok = ame.retirer_regle(texte)
        if ok:
            self._ame_rafraichir()
        return ok

    def _ame_rafraichir(self):
        """Met à jour le prompt système actif tout de suite, sans relancer."""
        if self.messages and self.messages[0].get("role") == "system":
            self.messages[0]["content"] = ame.ame_complete()
        self.emettre({"type": "ame"})

    # ── mémoire ─────────────────────────────────────────────────────────────
    def memoire(self):
        d = memoire_edition.lire()
        d["contexte"] = {"tokens": root.memoire.estimer_tokens(self.messages),
                         "budget": root.memoire.BUDGET_FENETRE, "seuil": root.SEUIL_TOKENS}
        return d

    def memoire_ajouter(self, categorie, fait, lever=False):
        if lever:
            memoire_edition.lever_tombe(fait)
        r = memoire_edition.ajouter(categorie, fait)
        if r["ok"]:
            self.memoire_changee()
        return r

    def memoire_modifier(self, ancien, nouveau):
        r = memoire_edition.modifier(ancien, nouveau)
        if r["ok"]:
            self.memoire_changee()
        return r

    def memoire_oublier(self, fait):
        ok = memoire_edition.oublier(fait)
        self.memoire_changee()
        return ok

    def memoire_retirer(self, fait):
        """Le bouton Annuler : retiré sans tombe, Root pourra le réapprendre."""
        ok = memoire_edition.retirer(fait)
        self.memoire_changee()
        return ok

    def memoire_renommer_categorie(self, ancien, nouveau):
        ok = memoire_edition.renommer_categorie(ancien, nouveau)
        self.memoire_changee()
        return ok

    def memoire_changee(self):
        self._memoire_dans_prompt()
        self.emettre({"type": "memoire"})

    # ── conversations ───────────────────────────────────────────────────────
    def conversations(self):
        d = conversations.lister()
        d["actuelle"] = self.lecture["cle"] if self.lecture else f"root:{self.conv_id}"
        self._liste = {e["cle"]: e for e in d["liste"]}
        return d

    def chercher_conversations(self, requete):
        return conversations.chercher(requete, list(getattr(self, "_liste", {}) or {}))

    def ouvrir_conversation(self, cle):
        if self.occupe.locked():
            self.emettre({"type": "toast", "texte": "Attends que Root ait fini de répondre.", "ok": False})
            return None
        try:
            r = conversations.ouvrir(cle)
        except (OSError, ValueError, KeyError) as e:
            self.emettre({"type": "toast", "texte": f"Conversation illisible : {e}", "ok": False})
            return None
        entree = getattr(self, "_liste", {}).get(cle, {})
        titre = entree.get("titre", "Sans titre")
        if r["source"] == "root":
            brut = r["brut"]
            self.messages = brut.get("messages") or [{"role": "system", "content": root.AME}]
            if self.messages and self.messages[0].get("role") == "system":
                self.messages[0]["content"] = ame.ame_complete()  # l'âme à jour
            self._memoire_dans_prompt()                         # et la mémoire du jour
            self.conv_id, self.origine, self.lecture = cle.split(":", 1)[1], brut.get("origine", ""), None
            c = cerveaux.par_id(brut.get("cerveau", ""))
            if c and c["id"] != self.cerveau["id"] and cerveaux.cle(c):
                self.cerveau = c
                root.CERVEAU_COURANT = c
                ecrire_reglages(cerveau=c["id"])
                self.emettre({"type": "cerveau", "id": c["id"], "nom": c["nom"]})
            return {"cle": cle, "source": "root", "titre": titre, "fil": r["fil"], "lecture": False}
        self.lecture = {"cle": cle, "titre": titre, "fil": r["fil"], "cwd": r.get("cwd", ""),
                        "profil": r.get("profil", ""), "projet": entree.get("projet", "")}
        return {"cle": cle, "source": r["source"], "titre": titre, "fil": r["fil"], "lecture": True,
                "cwd": r.get("cwd", ""), "date": entree.get("date", 0), "cerveau": entree.get("cerveau", ""),
                "rouvrir": conversations.commande_reprise(cle, self.lecture) is not None}

    def continuer_conversation(self):
        """« Continuer avec Root » : la conversation lue devient une conversation Root."""
        if not self.lecture or self.occupe.locked():
            return False
        self._reprendre()
        self.emettre({"type": "toast", "ok": True, "texte": f"Root reprend la conversation avec {self.cerveau['nom']}"})
        return True

    def rouvrir_conversation(self, cle):
        """Rouvre la session dans son outil d'origine, dans un nouveau Terminal."""
        info = self.lecture if self.lecture and self.lecture["cle"] == cle else {}
        cmd = conversations.commande_reprise(cle, info)
        if cmd is None:
            return False
        script = Path(tempfile.mkdtemp(prefix="root-reprise-")) / "reprendre.command"
        cwd = info.get("cwd") or str(Path.home())
        script.write_text(f"#!/bin/zsh -l\ncd {shlex.quote(cwd)} 2>/dev/null\nexec {shlex.join(cmd)}\n",
                          encoding="utf-8")
        script.chmod(0o700)
        subprocess.Popen(["open", "-a", "Terminal", str(script)])
        self.emettre({"type": "toast", "ok": True, "texte": f"Ouvert dans {conversations.SOURCES[cle.split(':')[0]]}"})
        return True

    def renommer_conversation(self, cle, titre):
        if titre.strip():
            conversations.renommer(cle, titre)
        return True

    def ranger_conversation(self, cle, projet):
        conversations.ranger(cle, projet)
        return True

    def epingler_conversation(self, cle, oui):
        conversations.epingler(cle, oui)
        return True

    def supprimer_conversation(self, cle):
        """Root : supprimée pour de bon. Autres outils : seulement masquée ici."""
        source, ident = cle.split(":", 1)
        if source == "root":
            if ident == self.conv_id:
                self.nouvelle()
            conversations.supprimer_root(ident)
        else:
            conversations.masquer(cle)
        return True

    def creer_projet(self, nom):
        return conversations.creer_projet(nom)

    def renommer_projet(self, ident, nom):
        conversations.renommer_projet(ident, nom)
        return True

    def supprimer_projet(self, ident):
        conversations.supprimer_projet(ident)
        return True

    def _reprendre(self):
        lec = self.lecture
        self.nouvelle()
        self.origine = lec["cle"]
        self.messages.append({"role": "system",
                              "content": conversations.contexte_reprise(lec["cle"], lec["titre"], lec["fil"])})
        cle = f"root:{self.conv_id}"
        conversations.renommer(cle, lec["titre"])
        if lec.get("projet"):
            conversations.ranger(cle, lec["projet"])
        self._sauver(force=True)

    def _sauver(self, force=False):
        if force or any(m.get("role") == "user" for m in self.messages):
            try:
                conversations.sauver_root(self.conv_id, self.messages, self.cerveau["id"], self.origine)
            except OSError as e:
                self.emettre({"type": "toast", "texte": f"Sauvegarde impossible : {e}", "ok": False})

    def _indexer(self):
        try:
            conversations.balayer()
            self.emettre({"type": "conversations"})
        except Exception:
            pass

    # ── moteur ──────────────────────────────────────────────────────────────
    def _tour(self, texte):
        try:
            if self.lecture:                         # on écrit sous une conversation d'un autre outil
                self._reprendre()
            self.messages.append({"role": "user", "content": texte})
            self._sauver()
            if not cerveaux.cle(self.cerveau):
                self.emettre({"type": "root", "texte":
                              f"Pas de clé pour {self.cerveau['nom']} : choisis un autre cerveau."})
                return
            root.un_tour(self.messages, self.cle, self.jour, ecran=EcranFenetre(self))
        except Exception as e:                      # réseau, API… la fenêtre ne meurt pas
            self.emettre({"type": "arret", "texte": f"Erreur : {root.securite.rediger_secrets(str(e))}"})
        finally:
            self._sauver()
            self.emettre({"type": "etat", "valeur": "prete"})
            self.occupe.release()

    def attendre_accord(self, nom, args) -> bool:
        self._n += 1
        ident = self._n
        attente = {"evenement": threading.Event(), "accord": False}
        self._accords[ident] = attente
        self.emettre({"type": "demande", "id": ident, "nom": nom,
                      "args": json.dumps(args, ensure_ascii=False)[:400]})
        attente["evenement"].wait(ATTENTE_MAX)
        self._accords.pop(ident, None)
        return attente["accord"]

    def _commande(self, a):
        nom = a["commande"][0]
        exe = shutil.which(nom) or next((str(p / nom) for p in CHEMINS_CMD if (p / nom).exists()), None)
        if exe is None:
            self.emettre({"type": "toast", "texte": f"Commande introuvable : {nom}", "ok": False})
            return
        env = dict(os.environ, PATH=":".join(map(str, CHEMINS_CMD)) + ":" + os.environ.get("PATH", ""))
        try:
            r = subprocess.run([exe, *a["commande"][1:]], capture_output=True, text=True,
                               timeout=30, env=env)
            ok = r.returncode == 0
        except subprocess.TimeoutExpired:
            ok = False
        self.emettre({"type": "toast", "texte": f"{a['label']} : {'fait' if ok else 'échec'}", "ok": ok})

    def miniature(self, chemin) -> str | None:
        """Réduit une capture pour l'afficher dans le fil (JPEG 900 px, en data URL)."""
        try:
            sortie = Path(tempfile.mkdtemp(prefix="root-mini-")) / "m.jpg"
            subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "78",
                            "-Z", "900", str(chemin), "--out", str(sortie)],
                           capture_output=True, timeout=20)
            return "data:image/jpeg;base64," + base64.b64encode(sortie.read_bytes()).decode()
        except Exception:
            return None

    def emettre(self, ev):
        if self.window is not None:
            self.window.evaluate_js("window.rootEvent && window.rootEvent(%s)"
                                    % json.dumps(ev, ensure_ascii=False))


def lancer():
    pont = Pont()
    pont.window = webview.create_window(
        "Root", str(UI / "index.html"), js_api=pont,
        width=980, height=720, min_size=(620, 520),
        background_color="#0b0f0e")
    webview.start()


if __name__ == "__main__":
    lancer()
