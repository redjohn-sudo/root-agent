"""
Pilotage de Brave par le protocole DevTools (CDP), pour que Root voie les pages
web en entier et agisse dessus (naviguer, lire, cliquer, écrire) toute seule.

Brave est un Chromium : on le lance en mode pilotable sur un profil dédié à Root
(persistant, dans ~/.config/root-brave), visible à l'écran pour que l'utilisateur suive
en direct. On parle au navigateur en JSON sur un websocket (CDP).

Pourquoi un profil dédié et pas le Brave perso de l'utilisateur : Brave récent (≥ 136)
refuse le pilotage à distance sur le profil par défaut, pour empêcher le vol de
cookies. Le profil Root est donc séparé ; l'utilisateur s'y connecte aux sites utiles
une fois, et ça reste. On pourra y importer ses connexions actuelles s'il veut.
"""

import base64
import json
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

# websocket-client n'est importé qu'au moment d'ouvrir une connexion réelle, pour
# que la logique (onglets, résolution d'URL) reste importable et testable sans lui.

BRAVE = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
PORT = 9222
PROFIL = Path.home() / ".config" / "root-brave"


class Brave:
    """Une connexion au navigateur. On la démarre à la demande."""

    def __init__(self, port=PORT, visible=True):
        self.port = port
        self.visible = visible
        self.ws = None
        self._id = 0
        self._cible = None          # id CDP de l'onglet actuellement piloté

    # ── démarrage ────────────────────────────────────────────────────────────
    def _http(self, chemin, methode="GET"):
        # /json/new exige PUT depuis Chromium 110+ ; le reste accepte GET.
        requete = urllib.request.Request(
            f"http://localhost:{self.port}{chemin}", method=methode)
        return json.load(urllib.request.urlopen(requete, timeout=3))

    def en_ligne(self):
        try:
            self._http("/json/version")
            return True
        except Exception:
            return False

    def demarrer(self):
        if self.en_ligne():
            return
        PROFIL.mkdir(parents=True, exist_ok=True)
        args = [BRAVE, f"--remote-debugging-port={self.port}",
                f"--user-data-dir={PROFIL}",
                f"--remote-allow-origins=http://localhost:{self.port}",
                "--no-first-run", "--no-default-browser-check"]
        if not self.visible:
            args.append("--headless=new")
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(80):
            if self.en_ligne():
                time.sleep(0.5)
                return
            time.sleep(0.25)
        raise RuntimeError("Brave n'a pas démarré en mode pilotable.")

    def _pages_brutes(self):
        """Les onglets réels (targets CDP de type page), dans l'ordre du navigateur."""
        return [c for c in self._http("/json") if c.get("type") == "page"]

    def _page(self):
        pages = self._pages_brutes()
        if self._cible is not None:                         # garder l'onglet piloté
            for p in pages:
                if p.get("id") == self._cible:
                    return p
        if pages:
            return pages[0]
        return self._ouvrir_target("about:blank")           # aucun onglet : on en crée un

    def _ouvrir_target(self, url="about:blank"):
        """Crée un onglet réel et renvoie sa cible CDP (PUT, repli GET)."""
        chemin = "/json/new?" + urllib.parse.urlencode({"url": url})
        try:
            return self._http(chemin, methode="PUT")
        except Exception:
            return self._http(chemin)

    def _connecter_cible(self, target):
        """(Re)branche le pilotage sur un onglet précis et le retient comme actif."""
        import websocket                       # dépendance réelle, chargée à l'usage
        if self.ws is not None:
            try:
                self.ws.close()
            except Exception:
                pass
        self.ws = websocket.create_connection(
            target["webSocketDebuggerUrl"], max_size=None, timeout=30)
        self._cible = target.get("id")
        self.cmd("Page.enable")
        self.cmd("Runtime.enable")

    def connecter(self):
        self.demarrer()
        self._connecter_cible(self._page())

    @staticmethod
    def _resoudre(ref, pages):
        """Trouve un onglet par indice (1..n), par id CDP, ou par bout de titre/URL."""
        if isinstance(ref, bool):
            return None
        if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
            i = int(ref)
            return pages[i - 1] if 1 <= i <= len(pages) else None
        for p in pages:                                     # id CDP exact
            if p.get("id") == ref:
                return p
        bas = str(ref).lower()                              # sinon titre ou URL
        for p in pages:
            if bas in (p.get("title", "") + " " + p.get("url", "")).lower():
                return p
        return None

    # ── dialogue CDP ───────────────────────────────────────────────────────────
    def cmd(self, method, params=None):
        if self.ws is None:
            self.connecter()
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": method,
                                 "params": params or {}}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == self._id:
                if "error" in m:
                    raise RuntimeError(m["error"].get("message"))
                return m.get("result", {})

    def js(self, expression):
        r = self.cmd("Runtime.evaluate", {"expression": expression,
                                          "returnByValue": True,
                                          "awaitPromise": True})
        return r.get("result", {}).get("value")

    # ── regarder ───────────────────────────────────────────────────────────────
    def _attendre(self, t=12):
        """Attend que la page soit prête ET stable : document.readyState complet,
        puis le DOM qui ne bouge plus (deux relevés identiques). Évite de lire une
        page JS encore en train de se construire après un clic ou une navigation."""
        fin = time.time() + t
        dernier, stable = -1, 0
        while time.time() < fin:
            try:
                if self.js("document.readyState") != "complete":
                    stable, dernier = 0, -1
                    time.sleep(0.25)
                    continue
                n = self.js("document.getElementsByTagName('*').length") or 0
                if n == dernier:
                    stable += 1
                    if stable >= 2:          # DOM stable sur ~0.6 s
                        return
                else:
                    stable, dernier = 0, n
            except Exception:
                pass
            time.sleep(0.3)

    def url(self):
        return self.js("location.href")

    def titre(self):
        return self.js("document.title")

    def texte(self, limite=12000):
        t = self.js("document.body ? document.body.innerText : ''") or ""
        return t[:limite] + ("\n… (tronqué)" if len(t) > limite else "")

    def source(self, limite=40000):
        """Le code source HTML BRUT de la page, commentaires <!-- --> compris."""
        h = self.js("document.documentElement ? document.documentElement.outerHTML : ''") or ""
        return h[:limite] + ("\n… (tronqué)" if len(h) > limite else "")

    def capture(self):
        r = self.cmd("Page.captureScreenshot",
                     {"format": "png", "captureBeyondViewport": True})
        p = Path(tempfile.mkdtemp(prefix="root-web-")) / "page.png"
        p.write_bytes(base64.b64decode(r["data"]))
        return p

    def apercu(self):
        """Ce que Root reçoit après une action : URL, titre, texte + une capture."""
        texte = f"URL : {self.url()}\nTitre : {self.titre()}\n\n{self.texte()}"
        return {"_image": self.capture(), "texte": texte}

    # ── agir ─────────────────────────────────────────────────────────────────
    def naviguer(self, url):
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        self.cmd("Page.navigate", {"url": url})
        self._attendre()
        return self.apercu()

    def cliquer(self, cible):
        """cible = un sélecteur CSS, sinon un bout de texte visible du bouton/lien."""
        expr = """
        (function(c){
          let el=null;
          try{ el=document.querySelector(c); }catch(e){}
          if(!el){
            const t=[...document.querySelectorAll('a,button,input,[role=button],[onclick],summary,label,[tabindex]')];
            el=t.find(e=>((e.innerText||e.value||e.getAttribute('aria-label')||'').trim().toLowerCase().includes(c.toLowerCase())));
          }
          if(!el) return 'INTROUVABLE';
          el.scrollIntoView({block:'center'}); el.click();
          return 'OK cliqué : '+((el.innerText||el.value||el.tagName)+'').trim().slice(0,60);
        })(%s)
        """ % json.dumps(cible)
        r = self.js(expr)
        self._attendre(6)
        ap = self.apercu()
        ap["texte"] = r + "\n\n" + ap["texte"]
        return ap

    def ecrire(self, champ, texte):
        """Focalise un champ (sélecteur, ou placeholder/nom/label approchant) et tape."""
        expr = """
        (function(c){
          let el=null;
          try{ el=document.querySelector(c); }catch(e){}
          if(!el){
            const ch=[...document.querySelectorAll('input,textarea,[contenteditable=true]')];
            el=ch.find(e=>((e.placeholder||e.name||e.getAttribute('aria-label')||'')+'').toLowerCase().includes(c.toLowerCase()))||ch[0];
          }
          if(!el) return 'INTROUVABLE';
          el.focus();
          if('value' in el) el.value='';
          return 'OK';
        })(%s)
        """ % json.dumps(champ)
        r = self.js(expr)
        if r != "OK":
            return {"texte": f"Champ introuvable : {champ}"}
        self.cmd("Input.insertText", {"text": texte})
        return {"texte": f"OK écrit « {texte} » dans {champ}"}

    def touche(self, nom="Enter"):
        codes = {"Enter": 13, "Tab": 9, "Escape": 27}
        for t in ("keyDown", "keyUp"):
            self.cmd("Input.dispatchKeyEvent",
                     {"type": t, "key": nom, "code": nom,
                      "windowsVirtualKeyCode": codes.get(nom, 0)})
        self._attendre(6)
        return self.apercu()

    def defiler(self, pixels=800):
        self.js(f"window.scrollBy(0,{int(pixels)})")
        time.sleep(0.3)
        return self.apercu()

    # ── onglets ──────────────────────────────────────────────────────────────
    def onglets(self):
        """Liste numérotée des onglets, avec un repère sur celui qui est piloté."""
        pages = self._pages_brutes()
        return [{"n": i, "titre": p.get("title"), "url": p.get("url"),
                 "id": p.get("id"), "actif": p.get("id") == self._cible}
                for i, p in enumerate(pages, 1)]

    def nouvel_onglet(self, url="about:blank"):
        """Ouvre un onglet et bascule le pilotage dessus."""
        if url and not url.startswith(("http://", "https://", "about:")):
            url = "https://" + url
        chemin = "/json/new?" + urllib.parse.urlencode({"url": url}) if url else "/json/new"
        try:
            target = self._http(chemin, methode="PUT")      # Chromium 110+
        except Exception:
            target = self._http(chemin)                      # repli ancien (GET)
        self._connecter_cible(target)
        self._attendre()
        return self.apercu()

    def basculer(self, ref):
        """Pilote un autre onglet (indice, id, ou bout de titre/URL) et le met devant."""
        cible = self._resoudre(ref, self._pages_brutes())
        if cible is None:
            return {"texte": f"Onglet introuvable : {ref}"}
        try:
            self._http(f"/json/activate/{cible['id']}")      # met l'onglet au premier plan
        except Exception:
            pass
        self._connecter_cible(cible)
        return self.apercu()

    def fermer_onglet(self, ref):
        """Ferme un onglet ; si c'était celui piloté, reprend sur un autre."""
        pages = self._pages_brutes()
        cible = self._resoudre(ref, pages)
        if cible is None:
            return {"texte": f"Onglet introuvable : {ref}"}
        etait_actif = cible.get("id") == self._cible
        try:
            self._http(f"/json/close/{cible['id']}")
        except Exception as e:
            return {"texte": f"Fermeture impossible : {e}"}
        if etait_actif:
            self.ws, self._cible = None, None
            restants = self._pages_brutes()
            if restants:
                self._connecter_cible(restants[0])
                ap = self.apercu()
                ap["texte"] = "Onglet fermé. Pilotage repris sur un autre.\n\n" + ap["texte"]
                return ap
            return {"texte": "Onglet fermé. Plus aucun onglet ouvert."}
        return {"texte": f"Onglet fermé : {cible.get('title') or cible.get('url')}"}
