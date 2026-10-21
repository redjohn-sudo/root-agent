"""Recherche approfondie et sourcée pour Root, axe de Claude (cloud).

But : répondre à une question en lisant de vraies pages, puis n'affirmer que ce
qui est relié à une citation exacte, recontrôlée localement dans le texte
réellement récupéré. Le modèle propose ; ce module vérifie.

Déroulé, piloté par le modèle à travers trois outils :
1. `recherche_web` : la question et quelques sous-requêtes partent vers un moteur
   de recherche, les pages trouvées sont récupérées sous budgets, le texte est
   extrait et les passages les plus pertinents reviennent au modèle, chacun
   rattaché à une source numérotée (S1, S2…).
2. `recherche_lire` : lire la suite d'une source précise, page par page.
3. `recherche_conclure` : le modèle rend ses affirmations, chacune avec des
   extraits copiés mot pour mot. Chaque extrait est recherché dans le texte de
   la source. Une affirmation sans extrait retrouvé n'est jamais présentée comme
   sourcée. Deux domaines indépendants la rendent « corroborée ».

Règles tenues :
- Sincérité : une citation retrouvée prouve que le texte existe dans la page
  consultée, pas qu'il soutient l'affirmation. Le rapport le dit. Les chiffres
  d'une affirmation absents de ses citations la font passer « à vérifier ».
- Protection : la requête sort de la machine, elle est donc refusée si elle
  contient un courriel, un téléphone, un numéro de carte, un IBAN, un chemin
  local, un secret ou un motif personnel connu de `securite`. Toute URL, y
  compris chaque redirection, passe par `securite.url_sure`. Le texte des pages
  est masqué par `securite.rediger_secrets` puis emballé comme donnée non fiable.
- Rien n'est écrit sur disque. Aucun import de root.py.

Dépendances : bibliothèque standard et `securite.py` du même dossier. Tout le
réseau passe par un transport et un moteur injectables : les tests tournent
hors ligne.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import socket
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import zlib
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Callable

import securite


VERSION = "recherche-sourcee-1"


# ─────────────────────────────────────────────────────────────────────────────
# Réglages
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Budgets:
    """Limites d'un dossier de recherche. Aucun compteur n'est remis à zéro
    par un nouvel appel d'approfondissement : seul un nouveau dossier le fait."""

    requetes_par_appel: int = 4
    requetes_total: int = 12
    pages_par_appel: int = 8
    pages_total: int = 24
    pages_par_domaine: int = 2
    references_par_page: int = 3
    resultats_par_requete: int = 8
    secondes_par_appel: float = 120.0
    delai_requete: float = 20.0
    octets_page: int = 5_000_000    # assez pour la plupart des PDF officiels
    caracteres_source: int = 200_000
    caracteres_passage: int = 600
    passages_par_source: int = 3
    caracteres_sortie: int = 10_000

    def __post_init__(self):
        for nom, valeur in self.__dict__.items():
            if type(valeur) not in (int, float) or not math.isfinite(valeur) or valeur <= 0:
                raise ValueError(f"Budget {nom} strictement positif requis.")


AGENT = "Root-recherche/1 (agent personnel, lecture seule)"
TYPES_ACCEPTES = ("text/html", "application/xhtml+xml", "text/plain", "application/pdf")
EXTENSIONS_IGNOREES = (".zip", ".gz", ".jpg", ".jpeg", ".png", ".gif",
                       ".webp", ".svg", ".mp4", ".mp3", ".doc", ".docx", ".xls",
                       ".xlsx", ".ppt", ".pptx", ".exe", ".dmg")
TEXTE_MINIMUM = 200          # caractères : en dessous, la page est jugée vide
LANGUES_RETENUES = ("fr", "en")   # pages dans une autre langue écartées
# Récence demandée par le modèle, traduite pour chaque moteur qui sait filtrer.
RECENCES = {"jour": {"brave": "pd", "duckduckgo": "d"},
            "semaine": {"brave": "pw", "duckduckgo": "w"},
            "mois": {"brave": "pm", "duckduckgo": "m"},
            "annee": {"brave": "py", "duckduckgo": "y"}}


def appeler_moteur(moteur, requete: str, n: int, delai: float, recence: str | None):
    """Passe la récence seulement aux moteurs qui la déclarent comprendre."""
    if recence is not None and getattr(moteur, "accepte_recence", False):
        return moteur(requete, n, delai, recence=recence)
    return moteur(requete, n, delai)

# Mots très fréquents de langues voisines, pour les pages sans attribut lang.
# Choisis pour ne pas exister en français ni en anglais.
_MARQUEURS_LANGUE = {
    "de": {"der", "die", "und", "das", "ist", "nicht", "mit", "auf", "sich", "dem",
           "auch", "wird", "werden", "oder", "wir", "nach", "bei", "einer", "eines"},
    "es": {"los", "las", "del", "por", "una", "para", "como", "pero", "sus", "muy",
           "esta", "este", "tiene", "hay", "puede", "entre", "desde", "sobre"},
    "it": {"della", "gli", "sono", "che", "nel", "degli", "delle", "anche",
           "questo", "alla", "molto", "essere", "sua", "loro", "dei"},
    "nl": {"het", "een", "niet", "zijn", "voor", "worden", "ook", "bij", "naar",
           "deze", "wordt", "werd", "maar", "geen", "heeft", "onder"},
}
_MARQUEURS_FR_EN = {"le", "la", "les", "des", "est", "une", "pour", "dans", "qui",
                    "pas", "sur", "avec", "the", "and", "of", "to", "is", "that",
                    "for", "with", "are", "this", "was", "from"}
CITATION_MIN, CITATION_MAX = 20, 500
PARAMETRES_PISTAGE = re.compile(
    r"^(utm_[a-z]+|fbclid|gclid|dclid|msclkid|mc_cid|mc_eid|igshid|yclid|_hsenc|_hsmi)$",
    re.IGNORECASE)


class ErreurRecherche(Exception):
    """Échec local avec un motif fermé, sans détail susceptible de fuiter."""

    def __init__(self, motif: str):
        super().__init__(motif)
        self.motif = motif


# ─────────────────────────────────────────────────────────────────────────────
# 1. Garde des requêtes : ce qui sort vers le moteur de recherche
# ─────────────────────────────────────────────────────────────────────────────

_COURRIEL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_TELEPHONE = re.compile(r"(?<!\d)(?:\+\d{1,3}[ .\-]?)?(?:\d[ .\-]?){9,}\d(?!\d)")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){3,7}(?:[ ]?[A-Z0-9]{1,4})?\b")
_CHEMIN_LOCAL = re.compile(r"(?:/Users/|/home/|/root/|~/|[A-Za-z]:\\\\?Users)")
_SUITE_CHIFFRES = re.compile(r"(?:\d[ \-]?){13,19}")


def _luhn(chiffres: str) -> bool:
    total, double = 0, False
    for c in reversed(chiffres):
        n = int(c)
        if double:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
        double = not double
    return total % 10 == 0


def requete_sure(requete: object) -> tuple[bool, str]:
    """(True, "") si la requête peut partir vers un moteur public, sinon
    (False, motif). Politique fermée : dans le doute, la requête reste ici."""
    if type(requete) is not str:
        return False, "requete_non_textuelle"
    q = requete.strip()
    if len(q) < 2:
        return False, "requete_vide"
    if len(q) > 300:
        return False, "requete_trop_longue"
    if "\n" in q or "\r" in q:
        return False, "requete_multiligne"
    if _COURRIEL.search(q):
        return False, "courriel_dans_la_requete"
    if _IBAN.search(q.upper().replace("-", " ")) and re.search(r"\d{6,}", q.replace(" ", "")):
        return False, "iban_dans_la_requete"
    for m in _SUITE_CHIFFRES.finditer(q):
        chiffres = re.sub(r"\D", "", m.group())
        if 13 <= len(chiffres) <= 19 and _luhn(chiffres):
            return False, "numero_de_carte_dans_la_requete"
    for m in _TELEPHONE.finditer(q):
        groupes = re.findall(r"\d+", m.group())
        annees = len(groupes) > 1 and all(len(g) == 4 and g[:2] in ("19", "20") for g in groupes)
        if not annees:
            return False, "telephone_dans_la_requete"
    if _CHEMIN_LOCAL.search(q):
        return False, "chemin_local_dans_la_requete"
    if "://" in q and "@" in q:
        return False, "identifiant_dans_une_url"
    # Clés, jetons, en-têtes et motifs personnels déclarés localement.
    if securite.rediger_secrets(q) != q:
        return False, "secret_ou_motif_personnel"
    return True, ""


# ─────────────────────────────────────────────────────────────────────────────
# 2. URL : normalisation et domaine racine
# ─────────────────────────────────────────────────────────────────────────────

_SUFFIXES_DOUBLES = {
    "co.uk", "org.uk", "ac.uk", "gov.uk", "me.uk", "com.au", "net.au", "org.au",
    "gov.au", "co.nz", "co.jp", "ne.jp", "or.jp", "com.br", "com.cn", "com.mx",
    "co.za", "co.in", "com.tr", "com.ar", "co.kr", "gouv.qc.ca",
}


def normaliser_url(url: str) -> str | None:
    """Forme canonique pour dédoublonner : schéma et hôte en minuscules, port
    par défaut, fragment et paramètres de pistage retirés. None si illisible
    ou si le schéma n'est pas http(s)."""
    try:
        p = urllib.parse.urlsplit(url.strip())
        port = p.port
    except (ValueError, AttributeError):
        return None
    if p.scheme.lower() not in ("http", "https") or not p.hostname:
        return None
    schema = p.scheme.lower()
    hote = p.hostname.lower().rstrip(".")
    if port and not ((schema == "http" and port == 80) or (schema == "https" and port == 443)):
        hote = f"{hote}:{port}"
    paires = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
              if not PARAMETRES_PISTAGE.match(k)]
    requete = urllib.parse.urlencode(paires, doseq=True)
    chemin = p.path or "/"
    return urllib.parse.urlunsplit((schema, hote, chemin, requete, ""))


def domaine_racine(url: str) -> str:
    """Domaine enregistrable approché, pour juger l'indépendance de deux sources.
    Approximation sans liste publique complète des suffixes : documentée."""
    try:
        hote = (urllib.parse.urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""
    if not hote:
        return ""
    if re.fullmatch(r"[\d.]+", hote) or ":" in hote:
        return hote
    etiquettes = hote.split(".")
    if len(etiquettes) >= 3 and ".".join(etiquettes[-2:]) in _SUFFIXES_DOUBLES:
        return ".".join(etiquettes[-3:])
    if len(etiquettes) >= 4 and ".".join(etiquettes[-3:]) in _SUFFIXES_DOUBLES:
        return ".".join(etiquettes[-4:])
    return ".".join(etiquettes[-2:])


# ─────────────────────────────────────────────────────────────────────────────
# 3. Extraction du texte d'une page HTML (bibliothèque standard seule)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PageExtraite:
    titre: str
    texte: str
    description: str = ""
    date_publication: str = ""
    langue: str = ""
    canonique: str = ""
    liens_externes: tuple = ()     # ((url, texte), …) : références d'un wiki


_IGNORES = {"script", "style", "noscript", "template", "svg", "iframe", "canvas",
            "nav", "footer", "aside", "form", "button", "select", "object", "math"}
_VIDES = {"br", "hr", "img", "meta", "link", "input", "source", "wbr", "area",
          "base", "col", "embed", "param", "track"}
_BLOCS = {"p", "div", "section", "article", "main", "header", "li", "ul", "ol",
          "h1", "h2", "h3", "h4", "h5", "h6", "br", "hr", "tr", "table", "thead",
          "tbody", "blockquote", "pre", "dd", "dt", "dl", "figcaption", "figure",
          "address", "details", "summary", "td", "th", "caption"}
_META_DATE = {"article:published_time", "og:published_time", "date", "dc.date",
              "dcterms.date", "dc.date.issued", "pubdate", "publish-date",
              "publication_date", "citation_publication_date", "datepublished",
              "sailthru.date", "parsely-pub-date"}


# Classes de bruit, surtout MediaWiki : liens « modifier », appels de note,
# bandeaux de navigation, bibliographie. Leur texte est écarté, mais les liens
# externes qu'elles contiennent restent relevés (les références sont suivies).
_CLASSES_BRUIT = {"mw-editsection", "navbox", "reference", "references", "reflist",
                  "mw-references-wrap", "noprint", "catlinks", "mw-jump-link",
                  "printfooter", "sistersitebox", "bandeau-portail", "navigation-only",
                  "mw-indicators", "autres-projets"}


class _Extracteur(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.morceaux: list[str] = []
        self.titre: list[str] = []
        self.description = self.date = self.date_time = self.langue = self.canonique = ""
        self._ignore = 0
        self._dans_titre = False
        self._dans_tete = False
        # Conteneur principal : <main>, <article> ou role="main". Seul le premier
        # rencontré compte ; les balises de même nom imbriquées sont comptées.
        self.principal: list[str] = []
        self._balise_principale: str | None = None
        self._niveau_principal = 0
        self.liens_externes: list[tuple[str, str]] = []
        self._lien_externe: list | None = None
        self._balise_bruit: str | None = None
        self._niveau_bruit = 0

    def _ajouter(self, morceau: str) -> None:
        if self._niveau_bruit > 0:
            return
        self.morceaux.append(morceau)
        if self._niveau_principal > 0:
            self.principal.append(morceau)

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag not in _VIDES:
            if self._niveau_bruit > 0 and tag == self._balise_bruit:
                self._niveau_bruit += 1
            elif self._niveau_bruit == 0 and _CLASSES_BRUIT & set(a.get("class", "").split()):
                self._balise_bruit, self._niveau_bruit = tag, 1
        if tag not in _VIDES and self._ignore == 0:
            if self._balise_principale is None and not self.principal and (
                    tag in ("main", "article") or a.get("role", "").lower() == "main"):
                self._balise_principale, self._niveau_principal = tag, 1
            elif tag == self._balise_principale and self._niveau_principal > 0:
                self._niveau_principal += 1
        if (tag == "a" and self._ignore == 0 and "external" in a.get("class", "").split()
                and a.get("href", "").startswith(("http://", "https://"))
                and len(self.liens_externes) < 500):
            self._lien_externe = [a["href"], []]
        if tag == "html" and a.get("lang"):
            self.langue = a["lang"][:12]
        elif tag == "head":
            self._dans_tete = True
        elif tag == "title":
            self._dans_titre = True
        elif tag == "meta":
            cle = (a.get("name") or a.get("property") or a.get("itemprop") or "").lower()
            contenu = a.get("content", "").strip()
            if cle in ("description", "og:description") and not self.description:
                self.description = contenu[:500]
            elif cle in _META_DATE and not self.date:
                self.date = contenu
        elif tag == "link" and "canonical" in a.get("rel", "").lower().split():
            self.canonique = a.get("href", "")
        elif tag == "time" and a.get("datetime") and not self.date_time:
            self.date_time = a["datetime"]
        if tag in _IGNORES and tag not in _VIDES:
            self._ignore += 1
        if tag in _BLOCS:
            self._ajouter("\n")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in _IGNORES and tag not in _VIDES:
            self._ignore = max(0, self._ignore - 1)

    def handle_endtag(self, tag):
        if tag == "a" and self._lien_externe is not None:
            texte = re.sub(r"\s+", " ", "".join(self._lien_externe[1])).strip()[:300]
            self.liens_externes.append((self._lien_externe[0], texte))
            self._lien_externe = None
        if tag == "head":
            self._dans_tete = False
        elif tag == "title":
            self._dans_titre = False
        if tag in _IGNORES and tag not in _VIDES:
            self._ignore = max(0, self._ignore - 1)
        if tag in _BLOCS:
            self._ajouter("\n")
        if tag == self._balise_principale and self._niveau_principal > 0:
            self._niveau_principal -= 1
            if self._niveau_principal == 0:
                self._balise_principale = "fini"   # un seul conteneur principal
        if tag == self._balise_bruit and self._niveau_bruit > 0:
            self._niveau_bruit -= 1
            if self._niveau_bruit == 0:
                self._balise_bruit = None

    def handle_data(self, data):
        if self._dans_titre:
            self.titre.append(data)
        elif self._ignore == 0 and not self._dans_tete:
            self._ajouter(data)
            if self._lien_externe is not None:
                self._lien_externe[1].append(data)   # même dans une zone de bruit


def _nettoyer_lignes(texte: str) -> str:
    lignes = []
    for ligne in texte.replace("\r", "\n").split("\n"):
        ligne = re.sub(r"[ \t   \f\v]+", " ", ligne).strip()
        if ligne:
            lignes.append(ligne)
    return "\n".join(lignes)


def _date_courte(brute: str) -> str:
    m = re.match(r"\s*(\d{4}-\d{2}-\d{2})", brute or "")
    return m.group(1) if m else (brute or "").strip()[:40]


TEXTE_PRINCIPAL_MIN = 400   # caractères : en dessous, le conteneur est ignoré


def html_vers_texte(html: str) -> PageExtraite:
    """Texte lisible d'une page : scripts, styles, menus, pieds de page et
    formulaires retirés ; un bloc HTML par ligne. Si la page a un conteneur
    principal assez fourni (<main>, <article>, role="main"), seul son texte
    est gardé, ce qui écarte bandeaux et listes de liens annexes."""
    ex = _Extracteur()
    try:
        ex.feed(html)
        ex.close()
    except Exception:
        pass  # HTML cassé : on garde ce qui a été lu
    titre = re.sub(r"\s+", " ", "".join(ex.titre)).strip()[:300]
    principal = _nettoyer_lignes("".join(ex.principal))
    texte = principal if len(principal) >= TEXTE_PRINCIPAL_MIN else _nettoyer_lignes("".join(ex.morceaux))
    return PageExtraite(
        titre=titre,
        texte=texte,
        description=ex.description,
        date_publication=_date_courte(ex.date or ex.date_time),
        langue=ex.langue,
        canonique=ex.canonique,
        liens_externes=tuple(ex.liens_externes),
    )


def _decoder(corps: bytes, charset: str | None) -> str:
    candidats = []
    if charset:
        candidats.append(charset)
    m = re.search(rb"""<meta[^>]+charset=["']?([A-Za-z0-9_\-]+)""", corps[:4096], re.I)
    if m:
        candidats.append(m.group(1).decode("ascii", "ignore"))
    candidats.append("utf-8")
    for c in candidats:
        try:
            return corps.decode(c, errors="replace")
        except LookupError:
            continue
    return corps.decode("utf-8", errors="replace")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Transport HTTP, chaque redirection recontrôlée
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Reponse:
    url_finale: str
    statut: int
    type_contenu: str
    charset: str | None
    corps: bytes = field(repr=False)
    tronquee: bool = False


class _SansRedirection(urllib.request.HTTPRedirectHandler):
    """Les redirections sont suivies à la main pour passer chacune par la garde."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


Garde = Callable[[str], "tuple[bool, str]"]


class TransportHTTP:
    """GET borné en taille et en temps. `ouvrir(requete, delai)` est injectable
    pour les tests ; par défaut, un opener urllib sans redirection automatique
    (le proxy système éventuel est respecté par urllib)."""

    def __init__(self, garde_url: Garde | None = None, *, octets_max: int = 1_500_000,
                 redirections_max: int = 5, ouvrir: Callable | None = None):
        self.garde_url = garde_url or securite.url_sure
        self.octets_max = octets_max
        self.redirections_max = redirections_max
        if ouvrir is None:
            opener = urllib.request.build_opener(_SansRedirection())
            ouvrir = lambda req, delai: opener.open(req, timeout=delai)
        self._ouvrir = ouvrir

    def __call__(self, url: str, delai: float, *,
                 en_tetes_secrets: dict | None = None) -> Reponse:
        """`en_tetes_secrets` (clé d'API par exemple) ne sont envoyés qu'à
        l'hôte demandé, jamais à l'hôte d'une redirection."""
        courante = url
        hote_origine = (urllib.parse.urlsplit(url).hostname or "").lower()
        for _ in range(self.redirections_max + 1):
            ok, _raison = self.garde_url(courante)
            if not ok:
                raise ErreurRecherche("url_refusee_par_la_garde")
            en_tetes = {
                "User-Agent": AGENT,
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9",
                "Accept-Language": "fr,en;q=0.8",
            }
            if en_tetes_secrets and (urllib.parse.urlsplit(courante).hostname or "").lower() == hote_origine:
                en_tetes.update(en_tetes_secrets)
            req = urllib.request.Request(courante, headers=en_tetes)
            try:
                rep = self._ouvrir(req, delai)
            except urllib.error.HTTPError as e:
                try:
                    e.close()   # la réponse d'erreur garde le socket ouvert sinon
                except Exception:
                    pass        # Python 3.9 : une erreur sans corps ne sait pas se fermer
                if e.code in (301, 302, 303, 307, 308):
                    cible = e.headers.get("Location") if e.headers else None
                    if not cible:
                        raise ErreurRecherche("redirection_sans_cible")
                    courante = urllib.parse.urljoin(courante, cible)
                    continue
                raise ErreurRecherche(f"http_{e.code}")
            except (socket.timeout, TimeoutError):
                raise ErreurRecherche("delai_depasse")
            except urllib.error.URLError as e:
                if isinstance(getattr(e, "reason", None), (socket.timeout, TimeoutError)):
                    raise ErreurRecherche("delai_depasse")
                raise ErreurRecherche("reseau")
            except (OSError, ValueError):
                raise ErreurRecherche("reseau")
            with rep:
                corps = rep.read(self.octets_max + 1)
                en_tetes = rep.headers
                type_complet = en_tetes.get("Content-Type", "") if en_tetes else ""
                charset = en_tetes.get_content_charset() if hasattr(en_tetes, "get_content_charset") else None
                statut = getattr(rep, "status", 200) or 200
                finale = rep.geturl() if hasattr(rep, "geturl") else courante
            return Reponse(
                url_finale=finale or courante, statut=statut,
                type_contenu=type_complet.split(";")[0].strip().lower(),
                charset=charset, corps=corps[: self.octets_max],
                tronquee=len(corps) > self.octets_max,
            )
        raise ErreurRecherche("trop_de_redirections")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Moteur de recherche : DuckDuckGo HTML, sans clé
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ResultatMoteur:
    url: str
    titre: str
    extrait: str = ""


_CLASSES_LIEN_DDG = {"result__a", "result-link"}          # html. et lite.
_CLASSES_EXTRAIT_DDG = {"result__snippet", "result-snippet"}
_MARQUES_ANTI_ROBOT = ("anomaly-modal", "anomaly.js", "bots use duckduckgo too",
                       "challenge-form", "g-recaptcha", "h-captcha")


class _AnalyseDDG(HTMLParser):
    """Lit les deux mises en page connues de DuckDuckGo (html. et lite.) et
    garde à part tous les liens de redirection `uddg`, pour un repli générique."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.resultats: list[dict] = []
        self.liens_uddg: list[dict] = []
        self.classes_liens: Counter = Counter()
        self.formulaires: list[str] = []
        self.titre: list[str] = []
        self._dans_titre = False
        self._lien: dict | None = None
        self._lien_brut: dict | None = None
        self._extrait: dict | None = None

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        classes = set(a.get("class", "").split())
        if tag == "title":
            self._dans_titre = True
        elif tag == "form":
            self.formulaires.append(a.get("action", "")[:80])
        if tag == "a":
            href = a.get("href", "")
            for c in classes:
                self.classes_liens[c] += 1
            if classes & _CLASSES_LIEN_DDG:
                self._lien = {"href": href, "titre": [], "extrait": []}
                self.resultats.append(self._lien)
            elif "uddg=" in href:
                self._lien_brut = {"href": href, "titre": [], "extrait": []}
                self.liens_uddg.append(self._lien_brut)
        if classes & _CLASSES_EXTRAIT_DDG and self.resultats and self._extrait is None:
            self._extrait = self.resultats[-1]
            self._extrait["_profondeur"] = 0
        if self._extrait is not None and tag not in _VIDES:
            self._extrait["_profondeur"] = self._extrait.get("_profondeur", 0) + 1

    def handle_endtag(self, tag):
        if tag == "title":
            self._dans_titre = False
        if tag == "a":
            self._lien = self._lien_brut = None
        if self._extrait is not None and tag not in _VIDES:
            self._extrait["_profondeur"] -= 1
            if self._extrait["_profondeur"] <= 0:
                self._extrait = None

    def handle_data(self, data):
        if self._dans_titre:
            self.titre.append(data)
        if self._lien is not None:
            self._lien["titre"].append(data)
        elif self._lien_brut is not None:
            self._lien_brut["titre"].append(data)
        elif self._extrait is not None:
            self._extrait["extrait"].append(data)


def _url_cible_ddg(href: str) -> str | None:
    href = href.strip()
    if href.startswith("//"):
        href = "https:" + href
    elif href.startswith("/"):
        href = "https://duckduckgo.com" + href      # lien relatif /l/?uddg=…
    try:
        p = urllib.parse.urlsplit(href)
    except ValueError:
        return None
    hote = (p.hostname or "").lower()
    if hote == "duckduckgo.com" or hote.endswith(".duckduckgo.com"):
        if p.path.startswith("/l/"):
            cible = urllib.parse.parse_qs(p.query).get("uddg", [""])[0]
            return cible if cible.startswith(("http://", "https://")) else None
        return None  # liens internes et annonces (y.js)
    return href if p.scheme in ("http", "https") else None


def page_anti_robot(html: str) -> bool:
    """Vrai si la page ressemble au contrôle anti-robot de DuckDuckGo."""
    bas = html[:200_000].lower()
    return any(m in bas for m in _MARQUES_ANTI_ROBOT)


def _analyse_ddg(html: str) -> _AnalyseDDG:
    an = _AnalyseDDG()
    try:
        an.feed(html)
        an.close()
    except Exception:
        pass
    return an


def analyser_duckduckgo(html: str, n: int) -> list[ResultatMoteur]:
    """Résultats d'une page DuckDuckGo. Lève `anti_robot` sur une page de
    contrôle, pour ne jamais confondre un blocage avec une absence de résultats."""
    an = _analyse_ddg(html)
    bruts = an.resultats or an.liens_uddg
    sortie, vues = [], set()
    for r in bruts:
        url = _url_cible_ddg(r["href"])
        cle = normaliser_url(url) if url else None
        if not cle or cle in vues:
            continue
        vues.add(cle)
        sortie.append(ResultatMoteur(
            url=url,
            titre=re.sub(r"\s+", " ", "".join(r["titre"])).strip()[:300],
            extrait=re.sub(r"\s+", " ", "".join(r["extrait"])).strip()[:500],
        ))
        if len(sortie) >= n:
            break
    if not sortie and page_anti_robot(html):
        raise ErreurRecherche("anti_robot")
    return sortie


def diagnostiquer_duckduckgo(html: str) -> dict:
    """Structure d'une page reçue, sans son texte : de quoi adapter l'analyseur
    à distance sans recopier la page."""
    an = _analyse_ddg(html)
    return {
        "taille": len(html),
        "titre": re.sub(r"\s+", " ", "".join(an.titre)).strip()[:80],
        "anti_robot": page_anti_robot(html),
        "liens_resultats": len(an.resultats),
        "liens_uddg": len(an.liens_uddg),
        "classes_liens": an.classes_liens.most_common(12),
        # Chemin seul : les paramètres d'un formulaire anti-robot sont des
        # identifiants de contrôle, inutiles au diagnostic et à ne pas recopier.
        "formulaires": [urllib.parse.urlsplit(f).path for f in an.formulaires[:5]],
    }


class MoteurDuckDuckGo:
    """Interroge DuckDuckGo sans clé, version html. ou lite. Une page de
    contrôle anti-robot lève `anti_robot` : c'est signalé, jamais inventé.
    L'agent reste honnête : Root ne se fait pas passer pour un navigateur."""

    URLS = {"html": "https://html.duckduckgo.com/html/",
            "lite": "https://lite.duckduckgo.com/lite/"}

    def __init__(self, transport: Callable[[str, float], Reponse], region: str = "fr-fr",
                 version: str = "html"):
        if version not in self.URLS:
            raise ValueError("Version DuckDuckGo inconnue.")
        self.transport = transport
        self.region = region
        self.version = version

    accepte_recence = True

    def url(self, requete: str, recence: str | None = None) -> str:
        parametres = {"q": requete, "kl": self.region}
        if recence in RECENCES:
            parametres["df"] = RECENCES[recence]["duckduckgo"]
        return self.URLS[self.version] + "?" + urllib.parse.urlencode(parametres)

    def __call__(self, requete: str, n: int, delai: float,
                 recence: str | None = None) -> list[ResultatMoteur]:
        rep = self.transport(self.url(requete, recence), delai)
        return analyser_duckduckgo(_decoder(rep.corps, rep.charset), n)


def analyser_brave(texte: str, n: int) -> list[ResultatMoteur]:
    """Résultats web de l'API Brave Search (format JSON)."""
    try:
        resultats = json.loads(texte)["web"]["results"]
        if not isinstance(resultats, list):
            raise TypeError
    except (ValueError, KeyError, TypeError):
        raise ErreurRecherche("reponse_illisible")
    sortie, vues = [], set()
    for r in resultats:
        if not isinstance(r, dict) or type(r.get("url")) is not str:
            continue
        cle = normaliser_url(r["url"])
        if not cle or cle in vues:
            continue
        vues.add(cle)
        sortie.append(ResultatMoteur(
            url=r["url"],
            titre=re.sub(r"<[^>]*>", "", str(r.get("title", ""))).strip()[:300],
            extrait=re.sub(r"\s+", " ", re.sub(r"<[^>]*>", "", str(r.get("description", "")))).strip()[:500],
        ))
        if len(sortie) >= n:
            break
    return sortie


class MoteurBrave:
    """API Brave Search, avec une clé de l'utilisateur. Optionnel : la session
    par défaut ne l'ajoute que si BRAVE_SEARCH_API_KEY est définie. La clé ne
    part que vers l'hôte de l'API, jamais vers une redirection, et n'apparaît
    dans aucun message d'erreur."""

    URL = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, transport: Callable, cle: str, pays: str = "fr"):
        if type(cle) is not str or not cle.strip():
            raise ValueError("Clé Brave Search requise.")
        self.transport = transport
        self._cle = cle.strip()
        self.pays = pays

    def __repr__(self):
        return "MoteurBrave(cle=«masquée»)"

    accepte_recence = True

    def __call__(self, requete: str, n: int, delai: float,
                 recence: str | None = None) -> list[ResultatMoteur]:
        parametres = {"q": requete, "count": max(1, min(int(n), 20)), "country": self.pays,
                      "search_lang": "fr", "safesearch": "moderate"}
        if recence in RECENCES:
            parametres["freshness"] = RECENCES[recence]["brave"]
        url = self.URL + "?" + urllib.parse.urlencode(parametres)
        rep = self.transport(url, delai, en_tetes_secrets={
            "X-Subscription-Token": self._cle, "Accept": "application/json"})
        return analyser_brave(_decoder(rep.corps, rep.charset), n)


def analyser_wikipedia(texte: str, langue: str, n: int) -> list[ResultatMoteur]:
    """Résultats de l'API de recherche MediaWiki (format JSON)."""
    try:
        donnees = json.loads(texte)
        trouves = donnees["query"]["search"]
    except (ValueError, KeyError, TypeError):
        raise ErreurRecherche("reponse_illisible")
    sortie = []
    for t in trouves if isinstance(trouves, list) else []:
        titre = t.get("title") if isinstance(t, dict) else None
        if type(titre) is not str or not titre.strip():
            continue
        chemin = urllib.parse.quote(titre.strip().replace(" ", "_"), safe="()_,'-")
        extrait = re.sub(r"<[^>]*>", "", str(t.get("snippet", "")))
        sortie.append(ResultatMoteur(
            url=f"https://{langue}.wikipedia.org/wiki/{chemin}",
            titre=titre.strip()[:300],
            extrait=re.sub(r"\s+", " ", extrait).strip()[:500],
        ))
        if len(sortie) >= n:
            break
    return sortie


class MoteurWikipedia:
    """API publique de recherche de Wikipédia, sans clé et prévue pour les
    programmes identifiés. Sert de secours quand le moteur général bloque."""

    def __init__(self, transport: Callable[[str, float], Reponse], langue: str = "fr"):
        if type(langue) is not str or not re.fullmatch(r"[a-z]{2,3}", langue):
            raise ValueError("Code de langue Wikipédia invalide.")
        self.transport = transport
        self.langue = langue

    def __call__(self, requete: str, n: int, delai: float) -> list[ResultatMoteur]:
        url = f"https://{self.langue}.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
            "action": "query", "list": "search", "srsearch": requete,
            "srlimit": max(1, min(int(n), 20)), "format": "json", "utf8": 1})
        rep = self.transport(url, delai)
        return analyser_wikipedia(_decoder(rep.corps, rep.charset), self.langue, n)


class MoteursCombines:
    """Interroge plusieurs moteurs et entrelace leurs résultats, le premier
    en tête. Un moteur en échec n'empêche pas les autres ; ses échecs sont
    exposés dans `derniers_echecs`. Si tous échouent, l'appel échoue."""

    def __init__(self, moteurs: list[tuple[str, Callable]]):
        if not moteurs or any(type(nom) is not str or not re.fullmatch(r"[a-z0-9_]+", nom)
                              or not callable(m) for nom, m in moteurs):
            raise ValueError("Liste de moteurs nommés requise.")
        self.moteurs = list(moteurs)
        self.derniers_echecs: list[str] = []
        self.suspendus: set[str] = set()

    accepte_recence = True

    def __call__(self, requete: str, n: int, delai: float,
                 recence: str | None = None) -> list[ResultatMoteur]:
        """Un moteur qui renvoie une page anti-robot est suspendu pour la
        session : on n'insiste pas auprès d'un site qui refuse les robots."""
        self.derniers_echecs = []
        listes, reussis = [], 0
        for nom, moteur in self.moteurs:
            if nom in self.suspendus:
                self.derniers_echecs.append(f"{nom}_suspendu_apres_anti_robot")
                continue
            try:
                resultats = appeler_moteur(moteur, requete, n, delai, recence)
            except ErreurRecherche as e:
                self.derniers_echecs.append(f"{nom}_{e.motif}")
                if e.motif == "anti_robot":
                    self.suspendus.add(nom)
                continue
            except Exception:
                self.derniers_echecs.append(f"{nom}_erreur")
                continue
            reussis += 1
            if not resultats:
                self.derniers_echecs.append(f"{nom}_sans_resultat")
            listes.append(list(resultats))
        if reussis == 0:
            raise ErreurRecherche("tous_moteurs_en_echec")
        sortie, vues = [], set()
        for rang in range(max((len(x) for x in listes), default=0)):
            for liste in listes:
                if rang < len(liste):
                    cle = normaliser_url(liste[rang].url)
                    if cle and cle not in vues:
                        vues.add(cle)
                        sortie.append(liste[rang])
        return sortie[: max(n, 0) * len(listes)]


# ─────────────────────────────────────────────────────────────────────────────
# 5 ter. PDF : texte des documents simples, en bibliothèque standard
# ─────────────────────────────────────────────────────────────────────────────

PDF_OCTETS_FLUX = 10_000_000     # plafond décompressé par flux (anti-bombe)
PDF_OCTETS_TOTAL = 40_000_000    # plafond décompressé pour tout le document
PDF_PAGES_MAX = 300
PDF_OBJETS_MAX = 200_000

_PDF_OBJ = re.compile(rb"(\d+)\s+(\d+)\s+obj\b")
_PDF_DELIM = b"()<>[]{}/%"
_PDF_ESPACES = b" \t\r\n\f\x00"


def _pdf_litteral(data: bytes, i: int) -> tuple[bytes, int]:
    """Chaîne littérale « (…) » à partir de la parenthèse ouvrante en i :
    échappements, octal et parenthèses imbriquées. Renvoie (octets, fin)."""
    out = bytearray()
    profondeur, i, n = 1, i + 1, len(data)
    echappes = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12}
    while i < n:
        c = data[i]
        if c == 0x5C and i + 1 < n:          # antislash
            s = data[i + 1]
            if s in echappes:
                out.append(echappes[s]); i += 2
            elif 0x30 <= s <= 0x37:
                j = i + 1
                while j < n and j < i + 4 and 0x30 <= data[j] <= 0x37:
                    j += 1
                out.append(int(data[i + 1:j], 8) & 0xFF); i = j
            elif s in (0x0A, 0x0D):           # continuation de ligne
                i += 2
                if s == 0x0D and i < n and data[i] == 0x0A:
                    i += 1
            else:
                out.append(s); i += 2
            continue
        if c == 0x28:
            profondeur += 1
        elif c == 0x29:
            profondeur -= 1
            if profondeur == 0:
                return bytes(out), i + 1
        out.append(c); i += 1
    return bytes(out), n


def _pdf_jetons(data: bytes):
    """Jetons d'un flux de contenu : (genre, valeur). Les images en ligne
    (BI … ID … EI) sont sautées sans être interprétées."""
    i, n = 0, len(data)
    while i < n:
        c = data[i]
        if c in _PDF_ESPACES:
            i += 1
        elif c == 0x25:                                   # commentaire
            while i < n and data[i] not in (0x0A, 0x0D):
                i += 1
        elif c == 0x28:
            valeur, i = _pdf_litteral(data, i)
            yield "chaine", valeur
        elif c == 0x3C and i + 1 < n and data[i + 1] == 0x3C:
            yield "dico", None; i += 2
        elif c == 0x3E and i + 1 < n and data[i + 1] == 0x3E:
            yield "fin_dico", None; i += 2
        elif c == 0x3C:
            fin = data.find(b">", i)
            fin = n if fin < 0 else fin
            hexa = re.sub(rb"[^0-9A-Fa-f]", b"", data[i + 1:fin])
            if len(hexa) % 2:
                hexa += b"0"
            yield "chaine", bytes.fromhex(hexa.decode("ascii")); i = fin + 1
        elif c == 0x5B:
            yield "[", None; i += 1
        elif c == 0x5D:
            yield "]", None; i += 1
        else:
            j = i + 1 if c == 0x2F else i
            while j < n and data[j] not in _PDF_ESPACES and data[j] not in _PDF_DELIM:
                j += 1
            if j == i:
                i += 1
                continue
            mot = data[i:j].decode("latin-1")
            i = j
            if mot.startswith("/"):
                yield "nom", mot[1:]
            elif re.fullmatch(r"[+-]?(\d+\.?\d*|\.\d+)", mot):
                yield "nombre", float(mot)
            elif mot == "ID":                             # image en ligne
                fin = re.search(rb"\sEI(?=[\s]|$)", data[i:])
                i = n if fin is None else i + fin.end()
            else:
                yield "operateur", mot


def _utf16(hexa: str) -> str:
    try:
        return bytes.fromhex(hexa if len(hexa) % 2 == 0 else hexa + "0").decode("utf-16-be", "replace")
    except ValueError:
        return ""


def lire_cmap(data: bytes) -> tuple[int, dict[int, str]] | None:
    """Table ToUnicode d'une police : (largeur des codes en octets, code → texte)."""
    t = data.decode("latin-1")
    if "begincmap" not in t and "beginbf" not in t:
        return None
    largeur = None
    m = re.search(r"begincodespacerange\s*<([0-9A-Fa-f]+)>", t)
    if m:
        largeur = max(1, len(m.group(1)) // 2)
    table: dict[int, str] = {}
    for bloc in re.finditer(r"beginbfchar(.*?)endbfchar", t, re.S):
        for src, dst in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]*)>", bloc.group(1)):
            largeur = largeur or max(1, len(src) // 2)
            table[int(src, 16)] = _utf16(dst)
    for bloc in re.finditer(r"beginbfrange(.*?)endbfrange", t, re.S):
        for bas, haut, reste in re.findall(
                r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(\[[^\]]*\]|<[0-9A-Fa-f]*>)", bloc.group(1)):
            largeur = largeur or max(1, len(bas) // 2)
            a, b = int(bas, 16), int(haut, 16)
            if b < a or b - a > 65_535:
                continue
            if reste.startswith("["):
                for k, dst in enumerate(re.findall(r"<([0-9A-Fa-f]*)>", reste)):
                    table[a + k] = _utf16(dst)
            else:
                hexa = reste[1:-1]
                if not hexa:
                    continue
                base = int(hexa, 16)
                for k in range(b - a + 1):
                    table[a + k] = _utf16(format(base + k, "0%dx" % len(hexa)))
    if not table:
        return None
    return (largeur or 1), table


def _pdf_decoder_chaine(octets: bytes, cmap) -> str:
    if cmap is not None:
        largeur, table = cmap
        morceaux = []
        for k in range(0, len(octets) - largeur + 1, largeur):
            code = int.from_bytes(octets[k:k + largeur], "big")
            if code in table:
                morceaux.append(table[code])
            elif largeur == 1:
                morceaux.append(bytes([code]).decode("cp1252", "replace"))
        return "".join(morceaux)
    if octets.startswith(b"\xfe\xff"):
        return octets[2:].decode("utf-16-be", "replace")
    return octets.decode("cp1252", "replace")


def _pdf_texte_flux(data: bytes, polices: dict[str, object]) -> str:
    """Texte d'un flux de contenu : opérateurs Tj, TJ, ', " ; retours à la
    ligne sur Td/TD/T*/Tm quand la ligne change, et sur ET."""
    out: list[str] = []
    operandes: list = []
    piles: list[list] = []
    cmap = None
    y_courant = None
    for genre, valeur in _pdf_jetons(data):
        if genre == "[":
            piles.append([])
            continue
        if genre == "]":
            tableau = piles.pop() if piles else []
            (piles[-1] if piles else operandes).append(("tableau", tableau))
            continue
        if genre != "operateur":
            (piles[-1] if piles else operandes).append((genre, valeur))
            continue
        op = valeur
        if op == "Tf" and len(operandes) >= 2 and operandes[-2][0] == "nom":
            cmap = polices.get(operandes[-2][1])
        elif op in ("Tj", "'", '"') and operandes and operandes[-1][0] == "chaine":
            if op != "Tj":
                out.append("\n")
            out.append(_pdf_decoder_chaine(operandes[-1][1], cmap))
        elif op == "TJ" and operandes and operandes[-1][0] == "tableau":
            for g, v in operandes[-1][1]:
                if g == "chaine":
                    out.append(_pdf_decoder_chaine(v, cmap))
                elif g == "nombre" and v < -180:
                    out.append(" ")
        elif op in ("Td", "TD") and len(operandes) >= 2:
            out.append("\n" if abs(operandes[-1][1]) > 0.01 else " ")
        elif op == "Tm" and len(operandes) >= 6:
            y = operandes[-1][1]
            out.append(" " if y_courant is not None and abs(y - y_courant) < 0.01 else "\n")
            y_courant = y
        elif op == "T*":
            out.append("\n")
        elif op == "ET":
            out.append("\n")
        operandes = []
    texte = "".join(out)
    return "\n".join(re.sub(r"[ \t]+", " ", ligne).strip() for ligne in texte.split("\n"))


class _DocumentPDF:
    """Objets d'un PDF, y compris ceux rangés dans des flux d'objets."""

    def __init__(self, corps: bytes):
        self.corps = corps
        self.objets: dict[int, tuple[bytes, bytes | None]] = {}
        self._decodes: dict[int, bytes | None] = {}
        self._budget = PDF_OCTETS_TOTAL
        self._lire_objets()
        self._lire_flux_objets()

    def _lire_objets(self):
        pos, n = 0, len(self.corps)
        while len(self.objets) < PDF_OBJETS_MAX:
            m = _PDF_OBJ.search(self.corps, pos)
            if not m:
                break
            num, debut = int(m.group(1)), m.end()
            fin = self.corps.find(b"endobj", debut)
            fin = n if fin < 0 else fin
            s = self.corps.find(b"stream", debut, fin)
            if s >= 0 and self.corps[s - 3:s] != b"end":
                dico = self.corps[debut:s]
                d0 = s + 6
                if self.corps[d0:d0 + 2] == b"\r\n":
                    d0 += 2
                elif self.corps[d0:d0 + 1] in (b"\n", b"\r"):
                    d0 += 1
                e = self.corps.find(b"endstream", d0)
                e = n if e < 0 else e
                self.objets[num] = (dico, self.corps[d0:e])
                fin = self.corps.find(b"endobj", e)
                fin = n if fin < 0 else fin
            else:
                self.objets[num] = (self.corps[debut:fin], None)
            pos = fin + 6

    def flux(self, num: int) -> bytes | None:
        """Données décodées d'un flux, sous plafonds ; None si filtre inconnu."""
        if num in self._decodes:
            return self._decodes[num]
        dico, data = self.objets.get(num, (b"", None))
        resultat = None
        if data is not None and self._budget > 0:
            filtres = re.findall(rb"/(\w+Decode|Fl|AHx|A85|LZW|DCT|CCF|RL)\b",
                                 dico.split(b"/DecodeParms")[0])
            if not filtres:
                resultat = data[:PDF_OCTETS_FLUX]
            elif filtres in ([b"FlateDecode"], [b"Fl"]):
                try:
                    d = zlib.decompressobj()
                    resultat = d.decompress(data, min(PDF_OCTETS_FLUX, self._budget))
                except zlib.error:
                    resultat = None
            if resultat is not None:
                self._budget -= len(resultat)
        self._decodes[num] = resultat
        return resultat

    def _lire_flux_objets(self):
        for num, (dico, data) in list(self.objets.items()):
            if data is None or not re.search(rb"/Type\s*/ObjStm\b", dico):
                continue
            contenu = self.flux(num)
            premier = re.search(rb"/First\s+(\d+)", dico)
            if not contenu or not premier:
                continue
            premier = int(premier.group(1))
            nombres = [int(x) for x in re.findall(rb"\d+", contenu[:premier])]
            paires = list(zip(nombres[0::2], nombres[1::2]))
            for k, (sous_num, decalage) in enumerate(paires):
                debut = premier + decalage
                fin = premier + paires[k + 1][1] if k + 1 < len(paires) else len(contenu)
                self.objets.setdefault(sous_num, (contenu[debut:fin], None))

    def dico(self, num: int | None) -> bytes:
        return self.objets.get(num, (b"", None))[0] if num is not None else b""

    @staticmethod
    def ref(dico: bytes, cle: bytes) -> int | None:
        m = re.search(rb"/" + cle + rb"\s+(\d+)\s+\d+\s+R", dico)
        return int(m.group(1)) if m else None

    @staticmethod
    def refs(dico: bytes, cle: bytes) -> list[int]:
        m = re.search(rb"/" + cle + rb"\s*\[([^\]]*)\]", dico)
        if m:
            return [int(x) for x in re.findall(rb"(\d+)\s+\d+\s+R", m.group(1))]
        un = _DocumentPDF.ref(dico, cle)
        return [un] if un is not None else []

    def polices(self, ressources: bytes) -> dict[str, object]:
        """Nom de police (/F1) → table ToUnicode, pour un dictionnaire de ressources."""
        m = re.search(rb"/Font\s*(<<(.*?)>>|(\d+)\s+\d+\s+R)", ressources, re.S)
        if not m:
            return {}
        interieur = m.group(2) if m.group(2) is not None else self.dico(int(m.group(3)))
        sortie = {}
        for nom, num in re.findall(rb"/([^\s/<>\[\]()]+)\s+(\d+)\s+\d+\s+R", interieur):
            police = self.dico(int(num))
            cmap_num = self.ref(police, b"ToUnicode")
            cmap = lire_cmap(self.flux(cmap_num) or b"") if cmap_num is not None else None
            sortie[nom.decode("latin-1")] = cmap
        return sortie

    def ressources(self, dico_page: bytes, heritees: bytes) -> bytes:
        num = self.ref(dico_page, b"Resources")
        if num is not None:
            return self.dico(num)
        i = dico_page.find(b"/Resources")
        return dico_page[i:] if i >= 0 else heritees

    def pages(self) -> list[tuple[bytes, bytes]]:
        """(dictionnaire de page, ressources effectives) dans l'ordre du document."""
        racines = re.findall(rb"/Root\s+(\d+)\s+\d+\s+R", self.corps)
        catalogue = self.dico(int(racines[-1])) if racines else b""
        sortie: list[tuple[bytes, bytes]] = []
        vus: set[int] = set()

        def parcourir(num, heritees, profondeur):
            if num in vus or profondeur > 30 or len(sortie) >= PDF_PAGES_MAX:
                return
            vus.add(num)
            d = self.dico(num)
            res = self.ressources(d, heritees)
            if re.search(rb"/Type\s*/Pages\b", d):
                for enfant in self.refs(d, b"Kids"):
                    parcourir(enfant, res, profondeur + 1)
            elif re.search(rb"/Type\s*/Page\b", d):
                sortie.append((d, res))

        racine_pages = self.ref(catalogue, b"Pages")
        if racine_pages is not None:
            parcourir(racine_pages, b"", 0)
        if not sortie:      # arbre introuvable : pages dans l'ordre des objets
            for num in sorted(self.objets):
                d = self.dico(num)
                if re.search(rb"/Type\s*/Page\b", d) and len(sortie) < PDF_PAGES_MAX:
                    sortie.append((d, self.ressources(d, b"")))
        return sortie


def pdf_vers_texte(corps: bytes) -> PageExtraite:
    """Texte d'un PDF simple. Lève `pdf_chiffre` ou `pdf_illisible` : un PDF
    scanné, à polices sans table de caractères ou tronqué n'est jamais
    présenté comme lu. Formulaires XObject et images non lus."""
    if not corps.lstrip()[:5].startswith(b"%PDF"):
        raise ErreurRecherche("pdf_illisible")
    if re.search(rb"/Encrypt\s", corps):
        raise ErreurRecherche("pdf_chiffre")
    doc = _DocumentPDF(corps)
    morceaux = []
    for dico_page, ressources in doc.pages():
        polices = doc.polices(ressources)
        contenu = b"\n".join(filter(None, (doc.flux(n) for n in doc.refs(dico_page, b"Contents"))))
        if contenu:
            morceaux.append(_pdf_texte_flux(contenu, polices))
    texte = _nettoyer_lignes("\n".join(morceaux))
    visibles = [c for c in texte if not c.isspace()]
    lettres = sum(c.isalpha() for c in visibles)
    if len(visibles) < 100 or lettres < 0.6 * len(visibles) or "�" * 3 in texte:
        raise ErreurRecherche("pdf_illisible")
    titre = ""
    m = re.search(rb"/Title\s*\(", corps)
    if m:
        brut, _ = _pdf_litteral(corps, m.end() - 1)
        titre = _pdf_decoder_chaine(brut, None).strip()[:300]
    return PageExtraite(titre=titre, texte=texte)


# ─────────────────────────────────────────────────────────────────────────────
# 5 bis. robots.txt : ne pas lire ce qu'un site interdit aux robots
# ─────────────────────────────────────────────────────────────────────────────

class Robots:
    """Règles robots.txt par site, en cache pour la session (RFC 9309).

    Fichier absent ou refusé (4xx) : tout est permis. Site injoignable,
    erreur 5xx ou adresse refusée par la garde : rien n'est permis.
    Le fichier passe par le même transport, donc par la même garde d'URL.
    """

    AGENT = "Root-recherche"
    OCTETS_MAX = 500_000

    def __init__(self, transport: Callable[[str, float], Reponse]):
        self.transport = transport
        self._regles: dict[str, object] = {}

    def autorise(self, url: str, delai: float) -> tuple[bool, str]:
        try:
            p = urllib.parse.urlsplit(url)
        except ValueError:
            return False, "url_illisible"
        base = f"{p.scheme}://{p.netloc}"
        if base not in self._regles:
            self._regles[base] = self._charger(base, delai)
        regle = self._regles[base]
        if regle is True:
            return True, ""
        if regle is False:
            return False, "robots_injoignable"
        return (True, "") if regle.can_fetch(self.AGENT, url) else (False, "interdit_par_robots")

    def _charger(self, base: str, delai: float):
        try:
            rep = self.transport(base + "/robots.txt", delai)
        except ErreurRecherche as e:
            return e.motif.startswith("http_4")
        except Exception:
            return False
        if rep.statut != 200:
            return 400 <= rep.statut < 500
        regles = urllib.robotparser.RobotFileParser()
        regles.parse(_decoder(rep.corps[: self.OCTETS_MAX], rep.charset).splitlines())
        return regles


# ─────────────────────────────────────────────────────────────────────────────
# 6. Sources, passages et classement BM25
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Source:
    identifiant: str
    url: str
    url_finale: str
    domaine: str
    titre: str
    date_publication: str
    consultee_le: str
    empreinte: str
    texte: str = field(repr=False)
    tronquee: bool = False
    requete: str = field(default="", repr=False)
    via: str = ""                  # identifiant de la source qui la citait


@dataclass(frozen=True)
class Passage:
    source: str
    debut: int
    fin: int
    texte: str = field(repr=False)


_MOTS_VIDES = set("""
a au aux avec ce ces cet cette dans de des du elle en et eux il ils je la le les
leur leurs lui ma mais me meme mes moi mon ne nos notre nous on ou par pas pour
qu que qui sa se ses son sur ta te tes toi ton tu un une vos votre vous est sont
ete etre avoir ont a y d l s c n j m t qu plus comme tout tous toute toutes
the of and to in for on with at by from is are was were be been it its this
that these those as or an not but if then than so such can will would which
who what when where how why do does did has have had into about over also
quel quelle quels quelles comment pourquoi quand combien
""".split())


def _sans_accents(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))


def mots(texte: str) -> list[str]:
    """Mots significatifs, en minuscules et sans accents."""
    t = _sans_accents(texte.casefold())
    return [m for m in re.findall(r"[a-z0-9]+", t)
            if m not in _MOTS_VIDES and (len(m) > 1 or m.isdigit())]


def decouper_passages(source_id: str, texte: str, taille: int = 600) -> list[Passage]:
    """Passages d'au plus `taille` caractères, formés de lignes entières quand
    c'est possible. Invariant : texte[debut:fin] == passage.texte."""
    passages: list[Passage] = []
    debut_bloc = fin_bloc = None

    def emettre(d, f):
        if d is not None and f is not None and f > d and texte[d:f].strip():
            passages.append(Passage(source_id, d, f, texte[d:f]))

    pos = 0
    for ligne in texte.split("\n"):
        d, f = pos, pos + len(ligne)
        pos = f + 1
        if not ligne.strip():
            continue
        if f - d > taille:
            emettre(debut_bloc, fin_bloc)
            debut_bloc = fin_bloc = None
            curseur = d
            while curseur < f:
                limite = min(f, curseur + taille)
                if limite < f:
                    coupe = max(texte.rfind(". ", curseur, limite), texte.rfind(" ", curseur, limite))
                    if coupe > curseur + taille // 3:
                        limite = coupe + 1
                emettre(curseur, limite)
                curseur = limite
                while curseur < f and texte[curseur] == " ":
                    curseur += 1
            continue
        if debut_bloc is not None and f - debut_bloc > taille:
            emettre(debut_bloc, fin_bloc)
            debut_bloc = None
        if debut_bloc is None:
            debut_bloc = d
        fin_bloc = f
    emettre(debut_bloc, fin_bloc)
    return passages


def classer_bm25(requete: str, passages: list[Passage], k1: float = 1.5,
                 b: float = 0.75) -> list[tuple[float, Passage]]:
    """Scores BM25 décroissants ; les passages sans mot commun sont écartés."""
    termes = set(mots(requete))
    if not termes or not passages:
        return []
    docs = [Counter(mots(p.texte)) for p in passages]
    n = len(docs)
    moyenne = sum(sum(d.values()) for d in docs) / n or 1.0
    df = Counter(t for d in docs for t in termes if t in d)
    scores = []
    for p, d in zip(passages, docs):
        longueur = sum(d.values())
        s = 0.0
        for t in termes:
            if t not in d:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * d[t] * (k1 + 1) / (d[t] + k1 * (1 - b + b * longueur / moyenne))
        if s > 0:
            scores.append((s, p))
    scores.sort(key=lambda x: (-x[0], x[1].source, x[1].debut))
    return scores


# ─────────────────────────────────────────────────────────────────────────────
# 7. Vérification des citations et des affirmations
# ─────────────────────────────────────────────────────────────────────────────

_EQUIVALENCES = str.maketrans({
    "‘": "'", "’": "'", "ʼ": "'", "`": "'", "´": "'",
    "“": '"', "”": '"', "«": '"', "»": '"', "„": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
    "−": "-", " ": " ", " ": " ", " ": " ", "­": None,
})
_ELLIPSE = re.compile(r"\s*(?:\[\s*(?:\.\.\.|…)\s*\]|\(\s*(?:\.\.\.|…)\s*\)|\.\.\.|…)\s*")


def _normaliser_citation(t: str) -> str:
    t = unicodedata.normalize("NFKC", t).translate(_EQUIVALENCES)
    return re.sub(r"\s+", " ", t).strip().casefold()


def fragments_citation(extrait: str) -> list[str]:
    """Fragments d'un extrait, coupé aux ellipses ; guillemets d'encadrement retirés."""
    t = _normaliser_citation(extrait).strip(" \"'")
    return [f.strip(" \"'") for f in _ELLIPSE.split(t) if f.strip(" \"'")]


def citation_presente(texte_source: str, extrait: str,
                      source_normalisee: str | None = None) -> tuple[bool, str]:
    """L'extrait figure-t-il mot pour mot dans la source, à la typographie près ?
    Les ellipses sont permises : les fragments doivent apparaître dans l'ordre."""
    if type(extrait) is not str:
        return False, "extrait_non_textuel"
    frags = fragments_citation(extrait)
    utile = sum(len(f) for f in frags)
    if utile < CITATION_MIN:
        return False, "extrait_trop_court"
    if len(_normaliser_citation(extrait)) > CITATION_MAX:
        return False, "extrait_trop_long"
    if any(len(f) < 8 for f in frags):
        return False, "fragment_trop_court"
    source = source_normalisee if source_normalisee is not None else _normaliser_citation(texte_source)
    pos = 0
    for f in frags:
        i = source.find(f, pos)
        if i < 0:
            return False, "extrait_absent_de_la_source"
        pos = i + len(f)
    return True, ""


_NOMBRE = re.compile(
    r"(?<![\d])(?:\d{1,3}(?:[   .,]\d{3})+(?!\d)(?:[.,]\d+)?|\d+(?:[.,]\d+)?)(?!\d)")
_MARQUEUR = re.compile(r"\[\s*S\d+\s*\]", re.IGNORECASE)


def nombres(texte: str) -> set[str]:
    """Chiffres d'un texte, réduits à leurs seuls chiffres (« 1 200 » = « 1,200 »)."""
    t = unicodedata.normalize("NFKC", _MARQUEUR.sub(" ", texte))
    return {re.sub(r"\D", "", m.group()) for m in _NOMBRE.finditer(t)}


@dataclass(frozen=True)
class Citation:
    source: str
    extrait: str


@dataclass(frozen=True)
class CitationRejetee:
    source: str
    extrait: str
    motif: str


@dataclass(frozen=True)
class AffirmationVerifiee:
    texte: str
    statut: str            # corroboree | sourcee | a_verifier | non_sourcee
    motif: str
    citations: tuple[Citation, ...] = ()
    rejetees: tuple[CitationRejetee, ...] = ()
    domaines: tuple[str, ...] = ()


STATUTS = ("corroboree", "sourcee", "a_verifier", "non_sourcee")


# ─────────────────────────────────────────────────────────────────────────────
# 8. Dossier de recherche : sources lues, budgets, vérification, rapport
# ─────────────────────────────────────────────────────────────────────────────

def _heure_murale() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


class DossierRecherche:
    """Une recherche, éventuellement approfondie en plusieurs appels. En
    mémoire seulement ; jamais écrit sur disque ni exporté hors du harness."""

    def __init__(self, question: str, budgets: Budgets | None = None):
        self.question = question
        self.budgets = budgets or Budgets()
        self.sources: dict[str, Source] = {}
        self._par_url: dict[str, str] = {}
        self.requetes: list[str] = []
        self.refus: list[tuple[str, str]] = []      # (requête ou URL, motif)
        self.echecs: list[tuple[str, str]] = []     # (URL normalisée, motif)
        self.pages_tentees = 0
        self._passages: dict[str, list[Passage]] = {}
        self._normalises: dict[str, str] = {}

    # ── état ──
    def connue(self, url_normalisee: str) -> bool:
        return url_normalisee in self._par_url

    def pages_du_domaine(self, domaine: str) -> int:
        return sum(1 for s in self.sources.values() if s.domaine == domaine) + sum(
            1 for u, _ in self.echecs if domaine_racine(u) == domaine)

    def ajouter_source(self, url: str, url_finale: str, page: PageExtraite, *,
                       tronquee: bool, consultee_le: str, requete: str = "",
                       via: str = "") -> Source:
        identifiant = f"S{len(self.sources) + 1}"
        texte = securite.rediger_secrets(page.texte)
        if len(texte) > self.budgets.caracteres_source:
            texte, tronquee = texte[: self.budgets.caracteres_source], True
        source = Source(
            identifiant=identifiant, url=url, url_finale=url_finale,
            domaine=domaine_racine(url_finale), titre=securite.rediger_secrets(page.titre),
            date_publication=page.date_publication, consultee_le=consultee_le,
            empreinte=hashlib.sha256(texte.encode("utf-8")).hexdigest(),
            texte=texte, tronquee=tronquee, requete=requete, via=via,
        )
        self.sources[identifiant] = source
        self._par_url[normaliser_url(url) or url] = identifiant
        cle_finale = normaliser_url(url_finale)
        if cle_finale:
            self._par_url[cle_finale] = identifiant
        self._passages[identifiant] = decouper_passages(
            identifiant, texte, self.budgets.caracteres_passage)
        self._normalises[identifiant] = _normaliser_citation(texte)
        return source

    def passages(self, identifiant: str) -> list[Passage]:
        return list(self._passages.get(identifiant, []))

    def passages_pertinents(self, requete: str, sources: list[str] | None = None) -> list[tuple[float, Passage]]:
        """Meilleurs passages, au plus `passages_par_source` par source."""
        ids = sources if sources is not None else list(self.sources)
        tous = [p for i in ids for p in self._passages.get(i, [])]
        retenus, par_source = [], Counter()
        for score, p in classer_bm25(requete, tous):
            if par_source[p.source] >= self.budgets.passages_par_source:
                continue
            par_source[p.source] += 1
            retenus.append((score, p))
        return retenus

    # ── vérification ──
    def verifier(self, affirmations: list[dict]) -> list[AffirmationVerifiee]:
        """Recontrôle chaque citation dans le texte stocké de sa source.
        Les entrées doivent déjà être validées par `valider_affirmations`."""
        sortie = []
        for a in affirmations:
            texte = a["texte"].strip()
            valides, rejetees = [], []
            for c in a["citations"]:
                sid = c["source"].strip().upper()
                source = self.sources.get(sid)
                if source is None:
                    rejetees.append(CitationRejetee(sid, c["extrait"], "source_inconnue"))
                    continue
                ok, motif = citation_presente(source.texte, c["extrait"],
                                              self._normalises.get(sid))
                if ok:
                    valides.append(Citation(sid, c["extrait"].strip()))
                else:
                    rejetees.append(CitationRejetee(sid, c["extrait"], motif))
            domaines = tuple(sorted({self.sources[c.source].domaine for c in valides}))
            if not valides:
                statut, motif = "non_sourcee", "aucune_citation_retrouvee"
            else:
                texte_citations = " ".join(c.extrait for c in valides)
                manquants = nombres(texte) - nombres(texte_citations)
                if manquants:
                    statut, motif = "a_verifier", "chiffres_absents_des_citations"
                elif not set(mots(texte)) & set(mots(texte_citations)):
                    statut, motif = "a_verifier", "citations_sans_mot_commun"
                elif len(domaines) >= 2:
                    statut, motif = "corroboree", "domaines_independants"
                else:
                    statut, motif = "sourcee", "un_seul_domaine"
            sortie.append(AffirmationVerifiee(texte, statut, motif, tuple(valides),
                                              tuple(rejetees), domaines))
        return sortie

    # ── rapport ──
    def rapport_markdown(self, verifiees: list[AffirmationVerifiee],
                         genere_le: str | None = None) -> str:
        genere_le = genere_le or _heure_murale()
        cites = {c.source for a in verifiees for c in a.citations}
        compte = Counter(a.statut for a in verifiees)
        l = [f"# Recherche : {self.question}", "",
             f"Rapport du {genere_le} · {len(self.sources)} sources lues · "
             f"{len(self.requetes)} requêtes · {len(verifiees)} affirmations", ""]
        l += ["| Statut | Nombre |", "| :--- | ---: |"]
        noms = {"corroboree": "Corroborée (deux domaines ou plus)",
                "sourcee": "Sourcée (un seul domaine)",
                "a_verifier": "À vérifier", "non_sourcee": "Non sourcée"}
        for s in STATUTS:
            l.append(f"| {noms[s]} | {compte.get(s, 0)} |")
        l.append("")

        def bloc(titre, statuts):
            choix = [a for a in verifiees if a.statut in statuts]
            if not choix:
                return
            l.extend([f"## {titre}", ""])
            for a in choix:
                marques = "".join(f"[{s}]" for s in dict.fromkeys(c.source for c in a.citations))
                etiquette = noms[a.statut]
                l.append(f"- **{etiquette}.** {a.texte} {marques}".rstrip())
                if a.statut == "a_verifier":
                    l.append(f"  - Motif : {a.motif.replace('_', ' ')}.")
                for c in a.citations:
                    l.append(f"  > « {c.extrait} » ({c.source})")
                for r in a.rejetees:
                    l.append(f"  - Citation écartée ({r.source}) : {r.motif.replace('_', ' ')}.")
            l.append("")

        bloc("Affirmations retenues", ("corroboree", "sourcee"))
        bloc("À vérifier", ("a_verifier",))
        bloc("Non retenues", ("non_sourcee",))

        l.extend(["## Sources", ""])
        for s in self.sources.values():
            details = [s.domaine]
            if s.date_publication:
                details.append(f"publiée {s.date_publication}")
            details.append(f"consultée {s.consultee_le}")
            if s.tronquee:
                details.append("texte tronqué")
            if s.via:
                details.append(f"trouvée via {s.via}")
            if s.identifiant not in cites:
                details.append("lue, non citée")
            titre = s.titre or s.domaine
            l.append(f"- **[{s.identifiant}]** {titre} · {' · '.join(details)}  ")
            l.append(f"  <{s.url_finale}>")
        l.append("")
        l.extend(["## Limites", "",
                  "- Une citation retrouvée prouve que ce texte figure dans la page "
                  "consultée. Elle ne prouve pas que la page dit vrai, ni qu'elle "
                  "soutient pleinement l'affirmation.",
                  "- Deux domaines différents peuvent reprendre la même source "
                  "d'origine. « Corroborée » ne garantit pas l'indépendance réelle."])
        if self.echecs:
            motifs = Counter(m for _, m in self.echecs)
            l.append("- Pages non lues : " + ", ".join(
                f"{n} × {m.replace('_', ' ')}" for m, n in motifs.most_common()) + ".")
        if self.refus:
            l.append(f"- Requêtes ou adresses refusées localement : {len(self.refus)}.")
        return "\n".join(l) + "\n"


# ─────────────────────────────────────────────────────────────────────────────
# 9. Le chercheur : requêtes, collecte et récupération sous budgets
# ─────────────────────────────────────────────────────────────────────────────

def langue_page(page: PageExtraite) -> str:
    """Langue principale d'une page : l'attribut lang s'il existe, sinon une
    estimation prudente sur les mots les plus fréquents. Chaîne vide si rien
    n'est sûr : une page sans indice clair n'est jamais écartée."""
    attribut = re.split(r"[-_]", page.langue.strip().lower())[0] if page.langue else ""
    if re.fullmatch(r"[a-z]{2,3}", attribut):
        return attribut
    jetons = re.findall(r"[a-zà-ÿ]+", page.texte[:20_000].lower())
    if len(jetons) < 80:
        return ""
    compte = Counter(jetons)
    fr_en = sum(compte[m] for m in _MARQUEURS_FR_EN)
    meilleure, score = "", 0
    for code, marqueurs in _MARQUEURS_LANGUE.items():
        n = sum(compte[m] for m in marqueurs)
        if n > score:
            meilleure, score = code, n
    if score >= 15 and score >= 2 * fr_en:
        return meilleure
    return ""


def references_pertinentes(liens: tuple, termes: set[str], n: int) -> list[str]:
    """Les `n` liens externes dont le texte partage le plus de mots avec la
    recherche. Sans mot commun, un lien n'est jamais suivi."""
    notes = []
    for rang, (url, texte) in enumerate(liens):
        commun = len(set(mots(texte)) & termes)
        if commun and normaliser_url(url):
            notes.append((-commun, rang, url))
    notes.sort()
    return [url for _, _, url in notes[:n]]


class Chercheur:
    """Orchestration sans modèle : le modèle choisit les sous-requêtes et
    rédige les affirmations ; ce code exécute, borne et vérifie."""

    def __init__(self, moteur: Callable, transport: Callable[[str, float], Reponse], *,
                 garde_url: Garde | None = None, horloge: Callable[[], float] = time.monotonic,
                 heure_murale: Callable[[], str] = _heure_murale,
                 robots: Robots | None = None):
        self.moteur = moteur
        self.transport = transport
        self.robots = robots
        self.garde_url = garde_url or securite.url_sure
        self.horloge = horloge
        self.heure_murale = heure_murale

    def explorer(self, dossier: DossierRecherche, question: str,
                 sous_requetes: list[str] | None = None,
                 recence: str | None = None) -> dict:
        """Un appel d'exploration. Renvoie un bilan chiffré ; les sources
        nouvelles sont ajoutées au dossier."""
        b = dossier.budgets
        fin = self.horloge() + b.secondes_par_appel
        bilan = {"requetes": [], "nouvelles_sources": [], "echecs": 0, "refus": 0,
                 "arret": ""}

        # 1. Requêtes : filtrées, dédoublonnées, sous budget.
        candidates = [question] + list(sous_requetes or [])
        requetes = []
        for q in candidates:
            q = q.strip() if type(q) is str else q
            ok, motif = requete_sure(q)
            if not ok:
                dossier.refus.append(("requête", motif))
                bilan["refus"] += 1
                continue
            cle = " ".join(mots(q)) or q.casefold()
            if cle in {" ".join(mots(x)) or x.casefold() for x in dossier.requetes + requetes}:
                continue
            requetes.append(q)
        place = min(b.requetes_par_appel, b.requetes_total - len(dossier.requetes))
        if place <= 0 and requetes:
            bilan["arret"] = "budget_requetes_total"
        requetes = requetes[: max(0, place)]

        # 2. Recherche.
        listes: list[list[tuple[str, ResultatMoteur]]] = []
        for q in requetes:
            reste = fin - self.horloge()
            if reste <= 0:
                bilan["arret"] = "budget_duree"
                break
            dossier.requetes.append(q)
            bilan["requetes"].append(q)
            try:
                resultats = appeler_moteur(self.moteur, q, b.resultats_par_requete,
                                           min(b.delai_requete, reste), recence)
            except ErreurRecherche as e:
                for detail in getattr(self.moteur, "derniers_echecs", []):
                    dossier.echecs.append(("moteur", f"moteur_{detail}"))
                dossier.echecs.append(("moteur", f"moteur_{e.motif}"))
                bilan["echecs"] += 1
                continue
            except Exception:
                dossier.echecs.append(("moteur", "moteur_erreur"))
                bilan["echecs"] += 1
                continue
            for detail in getattr(self.moteur, "derniers_echecs", []):
                dossier.echecs.append(("moteur", f"moteur_{detail}"))
            if not resultats:
                dossier.echecs.append(("moteur", "moteur_sans_resultat"))
            listes.append([(q, r) for r in resultats])

        # 3. Candidats entrelacés entre requêtes, pour varier les angles.
        ordre, vues = [], set()
        for rang in range(max((len(x) for x in listes), default=0)):
            for liste in listes:
                if rang < len(liste):
                    q, r = liste[rang]
                    cle = normaliser_url(r.url)
                    if not cle or cle in vues or dossier.connue(cle):
                        continue
                    vues.add(cle)
                    ordre.append((q, r.url, cle))

        # 4. Récupération. `ordre` peut grandir : les références pertinentes
        # d'une page lue (un article Wikipédia par exemple) y sont ajoutées.
        termes = set(mots(" ".join([question] + requetes)))
        origine: dict[str, str] = {}
        lues, i = 0, 0
        while i < len(ordre):
            q, url, cle = ordre[i]
            i += 1
            if lues >= b.pages_par_appel:
                bilan["arret"] = bilan["arret"] or "budget_pages_appel"
                break
            if dossier.pages_tentees >= b.pages_total:
                bilan["arret"] = "budget_pages_total"
                break
            reste = fin - self.horloge()
            if reste <= 0:
                bilan["arret"] = "budget_duree"
                break
            domaine = domaine_racine(cle)
            if dossier.pages_du_domaine(domaine) >= b.pages_par_domaine:
                continue
            chemin = urllib.parse.urlsplit(cle).path.lower()
            if chemin.endswith(EXTENSIONS_IGNOREES):
                dossier.echecs.append((cle, "format_non_pris_en_charge"))
                bilan["echecs"] += 1
                continue
            url = cle   # adresse nettoyée : sans pistage ni fragment
            ok, _ = self.garde_url(url)
            if not ok:
                dossier.refus.append((cle, "url_refusee_par_la_garde"))
                bilan["refus"] += 1
                continue
            if self.robots is not None:
                permis, motif = self.robots.autorise(url, min(b.delai_requete, reste))
                if not permis:
                    dossier.refus.append((cle, motif))
                    bilan["refus"] += 1
                    continue
                reste = fin - self.horloge()
                if reste <= 0:
                    bilan["arret"] = "budget_duree"
                    break
            dossier.pages_tentees += 1
            lues += 1
            try:
                rep = self.transport(url, min(b.delai_requete, reste))
            except ErreurRecherche as e:
                dossier.echecs.append((cle, e.motif))
                bilan["echecs"] += 1
                continue
            except Exception:
                dossier.echecs.append((cle, "erreur_transport"))
                bilan["echecs"] += 1
                continue
            if rep.statut != 200:
                dossier.echecs.append((cle, f"http_{rep.statut}"))
                bilan["echecs"] += 1
                continue
            est_pdf = (rep.type_contenu == "application/pdf"
                       or rep.corps.lstrip()[:5].startswith(b"%PDF"))
            if rep.type_contenu not in TYPES_ACCEPTES and not est_pdf:
                dossier.echecs.append((cle, "type_non_pris_en_charge"))
                bilan["echecs"] += 1
                continue
            if est_pdf:
                if rep.tronquee:
                    dossier.echecs.append((cle, "pdf_trop_volumineux"))
                    bilan["echecs"] += 1
                    continue
                try:
                    page = pdf_vers_texte(rep.corps)
                except ErreurRecherche as e:
                    dossier.echecs.append((cle, e.motif))
                    bilan["echecs"] += 1
                    continue
                except Exception:
                    dossier.echecs.append((cle, "pdf_illisible"))
                    bilan["echecs"] += 1
                    continue
            elif rep.type_contenu == "text/plain":
                page = PageExtraite(titre="", texte=_nettoyer_lignes(_decoder(rep.corps, rep.charset)))
            else:
                page = html_vers_texte(_decoder(rep.corps, rep.charset))
            if len(page.texte) < TEXTE_MINIMUM:
                dossier.echecs.append((cle, "page_vide_ou_dynamique"))
                bilan["echecs"] += 1
                continue
            langue = langue_page(page)
            if langue and langue not in LANGUES_RETENUES:
                dossier.echecs.append((cle, "langue_non_retenue"))
                bilan["echecs"] += 1
                continue
            cle_finale = normaliser_url(rep.url_finale) or cle
            if cle_finale != cle and dossier.connue(cle_finale):
                continue
            source = dossier.ajouter_source(url, rep.url_finale or url, page,
                                            tronquee=rep.tronquee,
                                            consultee_le=self.heure_murale(), requete=q,
                                            via=origine.get(cle, ""))
            bilan["nouvelles_sources"].append(source.identifiant)
            for ref in references_pertinentes(page.liens_externes, termes,
                                              b.references_par_page):
                cle_ref = normaliser_url(ref)
                if cle_ref and cle_ref not in vues and not dossier.connue(cle_ref):
                    vues.add(cle_ref)
                    origine[cle_ref] = source.identifiant
                    ordre.append((q, ref, cle_ref))
        return bilan


# ─────────────────────────────────────────────────────────────────────────────
# 10. Les outils exposés au modèle (à brancher dans root.py par Claude Code)
# ─────────────────────────────────────────────────────────────────────────────

def _emballer(texte: str) -> str:
    return securite.emballer_non_fiable(securite.rediger_secrets(texte), source="recherche")


def _couper(texte: str, limite: int) -> str:
    return texte if len(texte) <= limite else texte[: limite - 20].rstrip() + "\n… (sortie tronquée)"


def resumer_causes(dossier: DossierRecherche, maximum: int = 8) -> str:
    """Motifs fermés des échecs et refus du dossier, les plus fréquents d'abord."""
    motifs = Counter(m for _, m in dossier.echecs + dossier.refus)
    return ", ".join(f"{n} × {m.replace('_', ' ')}" for m, n in motifs.most_common(maximum))


def valider_affirmations(affirmations: object) -> tuple[list[dict] | None, str]:
    """Contrôle la forme proposée par le modèle, sans rien en déduire."""
    if type(affirmations) is not list or not affirmations:
        return None, "liste d'affirmations vide ou absente"
    if len(affirmations) > 40:
        return None, "au plus 40 affirmations par conclusion"
    propres = []
    for i, a in enumerate(affirmations, 1):
        if type(a) is not dict or type(a.get("texte")) is not str or not a["texte"].strip():
            return None, f"affirmation {i} : champ « texte » manquant"
        cits = a.get("citations")
        if type(cits) is not list or len(cits) > 8:
            return None, f"affirmation {i} : « citations » doit être une liste de 8 éléments au plus"
        propres_c = []
        for c in cits:
            if (type(c) is not dict or type(c.get("source")) is not str
                    or type(c.get("extrait")) is not str):
                return None, f"affirmation {i} : chaque citation veut « source » et « extrait »"
            propres_c.append({"source": c["source"], "extrait": c["extrait"]})
        propres.append({"texte": a["texte"][:1000], "citations": propres_c})
    return propres, ""


class SessionRecherche:
    """État d'une session Root : un dossier courant, approfondi ou remplacé."""

    def __init__(self, chercheur: Chercheur | None = None, budgets: Budgets | None = None):
        self._chercheur = chercheur
        self.budgets = budgets or Budgets()
        self.dossier: DossierRecherche | None = None

    @property
    def chercheur(self) -> Chercheur:
        if self._chercheur is None:
            transport = TransportHTTP(octets_max=self.budgets.octets_page)
            moteurs = []
            cle = os.environ.get("BRAVE_SEARCH_API_KEY", "").strip()
            if cle:
                moteurs.append(("brave", MoteurBrave(transport, cle)))
            moteurs += [("duckduckgo", MoteurDuckDuckGo(transport)),
                        ("wikipedia", MoteurWikipedia(transport, "fr"))]
            moteur = MoteursCombines(moteurs)
            self._chercheur = Chercheur(moteur, transport, robots=Robots(transport))
        return self._chercheur

    def chercher(self, question: object, sous_requetes: object = None,
                 approfondir: object = False, recence: object = None) -> str:
        if type(question) is not str or not question.strip():
            return "ERREUR : « question » doit être un texte non vide."
        if sous_requetes is None:
            sous_requetes = []
        if type(sous_requetes) is not list or len(sous_requetes) > 8:
            return "ERREUR : « sous_requetes » doit être une liste de 8 textes au plus."
        if type(approfondir) is not bool:
            return "ERREUR : « approfondir » doit être vrai ou faux."
        if recence is not None and recence not in RECENCES:
            return "ERREUR : « recence » doit valoir jour, semaine, mois ou annee."
        if not approfondir or self.dossier is None:
            self.dossier = DossierRecherche(question.strip(), self.budgets)
        d = self.dossier
        bilan = self.chercheur.explorer(d, question.strip(), sous_requetes, recence)

        requete_classement = " ".join([question] + [q for q in sous_requetes if type(q) is str])
        retenus = d.passages_pertinents(requete_classement)
        par_source: dict[str, list[Passage]] = {}
        for _, p in retenus:
            par_source.setdefault(p.source, []).append(p)

        entete = [f"Recherche : {d.question}",
                  f"Cet appel : {len(bilan['requetes'])} requêtes, "
                  f"{len(bilan['nouvelles_sources'])} nouvelles sources, "
                  f"{bilan['echecs']} échecs, {bilan['refus']} refus locaux."
                  + (f" Arrêt : {bilan['arret'].replace('_', ' ')}." if bilan["arret"] else ""),
                  f"Dossier : {len(d.sources)} sources, {len(d.requetes)}/{d.budgets.requetes_total} "
                  f"requêtes, {d.pages_tentees}/{d.budgets.pages_total} pages tentées."]
        if recence is not None:
            entete.append(f"Récence demandée : {recence}. Appliquée par Brave et DuckDuckGo "
                          "seulement ; Wikipédia et les références suivies ne sont pas "
                          "filtrées par date : vérifier les dates de publication.")
        causes = resumer_causes(d)
        if causes:
            entete.append("Causes des échecs et refus : " + causes + ".")
        if not d.sources:
            entete.append("Aucune source lisible. Ne rien affirmer comme sourcé ; "
                          "reformuler ou dire que la recherche a échoué, avec ses causes.")
        corps = []
        for sid, source in d.sources.items():
            if sid not in par_source:
                continue
            meta = f"[{sid}] {source.titre or source.domaine} · {source.domaine}"
            if source.date_publication:
                meta += f" · publiée {source.date_publication}"
            corps.append(meta)
            for p in par_source[sid]:
                corps.append("  « " + p.texte.replace("\n", " ") + " »")
        sans_passage = [sid for sid in d.sources if sid not in par_source]
        if sans_passage:
            corps.append("Sources lues sans passage pertinent : " + ", ".join(sans_passage)
                         + ". Utiliser recherche_lire pour les parcourir.")
        consigne = ("Pour conclure, appelle recherche_conclure avec des affirmations "
                    "courtes, chacune avec des extraits copiés mot pour mot (20 à 500 "
                    "caractères) depuis les sources ci-dessus, en citant leur identifiant. "
                    "Ce qui n'est pas cité sera marqué non sourcé.")
        fixe = len("\n".join(entete)) + len(consigne) + 600
        interieur = _couper("\n".join(corps), max(1000, d.budgets.caracteres_sortie - fixe))
        return "\n".join(entete) + "\n\n" + _emballer(interieur) + "\n\n" + consigne

    def lire(self, source: object, page: object = 1) -> str:
        if self.dossier is None:
            return "ERREUR : aucune recherche en cours. Appelle d'abord recherche_web."
        if type(source) is not str or source.strip().upper() not in self.dossier.sources:
            connues = ", ".join(self.dossier.sources) or "aucune"
            return f"ERREUR : source inconnue. Sources disponibles : {connues}."
        if type(page) is not int or page < 1:
            return "ERREUR : « page » doit être un entier à partir de 1."
        s = self.dossier.sources[source.strip().upper()]
        taille = max(1000, self.dossier.budgets.caracteres_sortie - 1500)
        total = max(1, math.ceil(len(s.texte) / taille))
        if page > total:
            return f"ERREUR : {s.identifiant} n'a que {total} page(s)."
        debut = (page - 1) * taille
        morceau = s.texte[debut: debut + taille]
        entete = (f"[{s.identifiant}] {s.titre or s.domaine} · {s.domaine} · page {page}/{total}"
                  + (" · texte tronqué à la récupération" if s.tronquee else ""))
        return entete + "\n\n" + _emballer(morceau)

    def conclure(self, affirmations: object) -> str:
        if self.dossier is None:
            return "ERREUR : aucune recherche en cours. Appelle d'abord recherche_web."
        propres, erreur = valider_affirmations(affirmations)
        if propres is None:
            return f"ERREUR : {erreur}."
        verifiees = self.dossier.verifier(propres)
        rapport = self.dossier.rapport_markdown(verifiees)
        compte = Counter(a.statut for a in verifiees)
        resume = (f"Vérification locale : {compte.get('corroboree', 0)} corroborées, "
                  f"{compte.get('sourcee', 0)} sourcées, {compte.get('a_verifier', 0)} à vérifier, "
                  f"{compte.get('non_sourcee', 0)} non sourcées. Présente à l'utilisateur "
                  "seulement les affirmations retenues comme établies, signale les autres "
                  "comme incertaines, et garde les numéros de sources.")
        # Le rapport peut dépasser la sortie d'exploration : plafond à 1,8 fois,
        # sous la troncature de memoire.py (20 000 caractères), coupé à l'intérieur.
        limite = int(self.dossier.budgets.caracteres_sortie * 1.8) - len(resume) - 600
        return resume + "\n\n" + _emballer(_couper(rapport, max(1000, limite)))


_SESSION: SessionRecherche | None = None


def session() -> SessionRecherche:
    global _SESSION
    if _SESSION is None:
        _SESSION = SessionRecherche()
    return _SESSION


def reinitialiser(nouvelle: SessionRecherche | None = None) -> None:
    """Oublie le dossier courant (fin de session, ou injection en test)."""
    global _SESSION
    _SESSION = nouvelle


def outil_recherche_web(question: str, sous_requetes: list | None = None,
                        approfondir: bool = False, recence: str | None = None) -> str:
    return session().chercher(question, sous_requetes, approfondir, recence)


def outil_recherche_lire(source: str, page: int = 1) -> str:
    return session().lire(source, page)


def outil_recherche_conclure(affirmations: list) -> str:
    return session().conclure(affirmations)


# Table au format de OUTILS dans root.py : `OUTILS.update(recherche.OUTILS_RECHERCHE)`.
OUTILS_RECHERCHE = {
    "recherche_web": {
        "fn": outil_recherche_web, "risque": "web",
        "schema": {
            "description": (
                "Recherche approfondie sur le web public : interroge un moteur, lit "
                "les pages trouvées et renvoie les passages pertinents numérotés par "
                "source (S1, S2…). La question part sur Internet : jamais de donnée "
                "personnelle, de nom, d'adresse, de numéro ni de secret dedans. "
                "Ajoute 1 à 3 sous-requêtes sous d'autres angles. Mets approfondir à "
                "true pour compléter la recherche en cours au lieu d'en commencer une. "
                "Pour l'actualité, des prix ou des règles récentes, donne recence : "
                "jour, semaine, mois ou annee."),
            "parameters": {"type": "object", "properties": {
                "question": {"type": "string"},
                "sous_requetes": {"type": "array", "items": {"type": "string"}},
                "approfondir": {"type": "boolean"},
                "recence": {"type": "string", "enum": ["jour", "semaine", "mois", "annee"]}},
                "required": ["question"]}},
    },
    "recherche_lire": {
        "fn": outil_recherche_lire, "risque": "sûr",
        "schema": {
            "description": "Lire le texte d'une source déjà récupérée (S1, S2…), page par page.",
            "parameters": {"type": "object", "properties": {
                "source": {"type": "string"}, "page": {"type": "integer"}},
                "required": ["source"]}},
    },
    "recherche_conclure": {
        "fn": outil_recherche_conclure, "risque": "sûr",
        "schema": {
            "description": (
                "Faire vérifier localement les affirmations de la recherche en cours. "
                "Chaque affirmation donne ses citations : identifiant de source et "
                "extrait copié mot pour mot (20 à 500 caractères, « … » pour couper). "
                "Renvoie un rapport sourcé avec le statut de chaque affirmation."),
            "parameters": {"type": "object", "properties": {
                "affirmations": {"type": "array", "items": {
                    "type": "object", "properties": {
                        "texte": {"type": "string"},
                        "citations": {"type": "array", "items": {
                            "type": "object", "properties": {
                                "source": {"type": "string"},
                                "extrait": {"type": "string"}},
                            "required": ["source", "extrait"]}}},
                    "required": ["texte", "citations"]}}},
                "required": ["affirmations"]}},
    },
}


def diagnostic(question: str, sortie=print) -> None:
    """Essai réel, à lancer sur la machine de l'utilisateur :
    `python3 -B recherche.py --diagnostic "question publique"`.
    Affiche la structure des réponses des moteurs et les causes d'échec,
    jamais le contenu brut des pages ni une clé."""
    ok, motif = requete_sure(question)
    if not ok:
        sortie(f"Requête refusée localement : {motif}.")
        return
    session_test = SessionRecherche()
    c = session_test.chercheur
    transport = c.transport
    for nom, moteur in c.moteur.moteurs:
        debut = time.monotonic()
        try:
            if isinstance(moteur, MoteurDuckDuckGo):
                rep = transport(moteur.url(question), 20)
                html = _decoder(rep.corps, rep.charset)
                sortie(f"[{nom}] page reçue : {json.dumps(diagnostiquer_duckduckgo(html), ensure_ascii=False)}")
            resultats = moteur(question, 8, 20)
            sortie(f"[{nom}] {len(resultats)} résultats en {time.monotonic() - debut:.1f} s")
            for r in resultats[:5]:
                sortie(f"    {r.url}")
        except ErreurRecherche as e:
            sortie(f"[{nom}] échec : {e.motif}")
        except Exception as e:
            sortie(f"[{nom}] erreur inattendue : {type(e).__name__}")
    sortie("")
    sortie(session_test.chercher(question).split("\n\nAVERTISSEMENT")[0])
    d = session_test.dossier
    for sid, source in d.sources.items():
        sortie(f"  {sid} {source.domaine} · {len(source.texte)} caractères · {source.url_finale}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == "--diagnostic":
        diagnostic(" ".join(sys.argv[2:]))
        raise SystemExit(0)
    # Démonstration locale, sans réseau : `python3 recherche.py`.
    page = ("<html lang='fr'><head><title>Exemple</title></head><body><nav>Menu</nav>"
            "<p>La tour Eiffel mesure 330 mètres depuis l'ajout d'antennes en 2022.</p>"
            + "<p>Texte de remplissage pour atteindre la taille minimale d'une page.</p>" * 5
            + "</body></html>")

    def moteur(q, n, delai):
        return [ResultatMoteur("https://exemple.org/tour", "Exemple")]

    def transport(url, delai):
        return Reponse(url, 200, "text/html", "utf-8", page.encode())

    s = SessionRecherche(Chercheur(moteur, transport, garde_url=lambda u: (True, "")))
    print(s.chercher("hauteur de la tour Eiffel"))
    print(s.conclure([{"texte": "La tour Eiffel mesure 330 mètres.", "citations": [
        {"source": "S1", "extrait": "La tour Eiffel mesure 330 mètres"}]}]))
