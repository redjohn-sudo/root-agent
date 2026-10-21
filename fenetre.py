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
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

import webview

import cerveaux        # les LLM interchangeables (cerveaux.json)
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

    def appeler(self, messages, cle):
        self.pont.emettre({"type": "etat", "valeur": "reflechit"})
        return root.appeler_modele_robuste(messages, cle)

    def demander(self, nom, args):
        return self.pont.attendre_accord(nom, args)

    def outil(self, nom, args, illisible=False):
        detail = "arguments illisibles" if illisible else json.dumps(args or {}, ensure_ascii=False)
        self.pont.emettre({"type": "outil", "nom": nom, "args": detail[:300]})

    def resultat(self, nom, texte):
        self.pont.emettre({"type": "resultat", "nom": nom, "texte": texte})

    def image(self, chemin):
        miniature = self.pont.miniature(chemin)
        if miniature:
            self.pont.emettre({"type": "image", "src": miniature})

    def reponse(self, texte):
        self.pont.emettre({"type": "root", "texte": texte})

    def fin(self, secondes, usage=None):
        usage = usage or {"entree": 0, "sortie": 0}
        c = self.pont.cerveau
        self.pont.emettre({"type": "fin", "secondes": secondes, "cerveau": c["nom"],
                           "tokens": usage["entree"] + usage["sortie"],
                           "cout": cerveaux.cout(c, usage["entree"], usage["sortie"])})

    def arret(self, texte):
        self.pont.emettre({"type": "arret", "texte": texte})


class Pont:
    """Ce que la fenêtre peut appeler (côté JS : window.pywebview.api.*)."""

    def __init__(self):
        self.window = None
        self.cerveau = cerveaux.par_id(lire_reglages().get("cerveau", "")) or cerveaux.defaut()
        root.CERVEAU_COURANT = self.cerveau
        self.cle = root.charger_cle()            # clé DeepSeek, gardée pour resumer_blocs
        self.jour = root.tokens_charger()
        self.occupe = threading.Lock()
        self._accords: dict[int, dict] = {}
        self._n = 0
        self.nouvelle()

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
        self.messages = [{"role": "system", "content": root.AME}]
        souvenirs = root.memoire.memoire_pour_prompt()
        if souvenirs.strip():
            self.messages.append({"role": "system",
                                  "content": "Mémoire durable de Root :\n" + souvenirs})
        return True

    # ── moteur ──────────────────────────────────────────────────────────────
    def _tour(self, texte):
        try:
            self.messages.append({"role": "user", "content": texte})
            if not cerveaux.cle(self.cerveau):
                self.emettre({"type": "root", "texte":
                              f"Pas de clé pour {self.cerveau['nom']} : choisis un autre cerveau."})
                return
            root.un_tour(self.messages, self.cle, self.jour, ecran=EcranFenetre(self))
        except Exception as e:                      # réseau, API… la fenêtre ne meurt pas
            self.emettre({"type": "arret", "texte": f"Erreur : {root.securite.rediger_secrets(str(e))}"})
        finally:
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
