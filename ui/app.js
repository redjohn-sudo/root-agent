// Root — vie de l'interface : le dock (une icône = un panneau), le fil, les
// autorisations, et le pont vers le moteur Python (window.pywebview.api / window.rootEvent).
"use strict";

const api = () => (window.pywebview && window.pywebview.api) || null;
const $ = s => document.querySelector(s);

// ── Icônes (traits 1.6, dessinées pour Root) ─────────────────────────────────
const ICONES = {
  cerveau: '<path d="M9 4.5a3 3 0 0 0-3 3v.3a3 3 0 0 0-1.5 5.2A3 3 0 0 0 9 17.6V19.5h1.5V4.5zM15 4.5a3 3 0 0 1 3 3v.3a3 3 0 0 1 1.5 5.2 3 3 0 0 1-4.5 4.6v1.9h-1.5V4.5z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  bulle: '<path d="M20 11.5a7.5 7.5 0 0 1-11 6.6L4.5 19.5l1.4-4.1A7.5 7.5 0 1 1 20 11.5z"/>',
  epingle: '<path d="M9 4h6M10 4v5.5L7 13h10l-3-3.5V4M12 13v7"/>',
  dossier: '<path d="M3.5 7.5A1.5 1.5 0 0 1 5 6h4l2 2h8a1.5 1.5 0 0 1 1.5 1.5v8A1.5 1.5 0 0 1 19 19H5a1.5 1.5 0 0 1-1.5-1.5z"/>',
  croix: '<path d="M7 7l10 10M17 7 7 17"/>',
  chevron: '<path d="m7 10 5 5 5-5"/>',
  crayon: '<path d="M14.5 5.5l4 4L9 19H5v-4z"/>',
  carnet: '<path d="M6.5 4.5h10A1.5 1.5 0 0 1 18 6v13.5H8a1.5 1.5 0 0 1-1.5-1.5zM6.5 18A1.5 1.5 0 0 1 8 16.5h10M10 8.5h4.5"/>',
  outils: '<path d="M10 6.5a3.5 3.5 0 0 0-4.8 4.3l-1.7 1.7 2 2 1.7-1.7A3.5 3.5 0 0 0 11.5 8M13.5 13l4.5 4.5a1.4 1.4 0 0 0 2-2L15.5 11"/>',
  terminal: '<path d="M4.5 5.5h15a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1h-15a1 1 0 0 1-1-1v-11a1 1 0 0 1 1-1zM7 10l2.5 2L7 14M12.5 14.5h4"/>',
};
const svg = (nom, classe = "") => `<svg${classe ? ` class="${classe}"` : ""} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${ICONES[nom]}</svg>`;
const echap = s => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const normal = s => String(s || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

// ── Le sceau : l'oreillette pixel par pixel ──────────────────────────────────
const OREILLETTE = [
  "................", "...oooo....L....", "..owwhho....L...", ".ouuwwwwo.L..L..",
  ".ouuwwLLo..L..L.", ".owwwwLLo..L..L.", "..owwwwso.L..L..", "...owwwso...L...",
  "....owso........", "....owso........", "....owso........", "....owso........",
  "....owso........", "....owso........", ".....oo.........", "................",
];
const TEINTES = { o: "#8a8a96", w: "#d8d8de", h: "#ffffff", s: "#aeaeb8", u: "#3e3e48", L: "#6fd4b6" };
function dessinerSceau() {
  const g = $("#oreillette").getContext("2d"), p = 4;
  for (let y = 0; y < 16; y++) for (let x = 0; x < 16; x++) {
    const c = TEINTES[OREILLETTE[y][x]];
    if (c) { g.fillStyle = c; g.fillRect(x * p, y * p, p, p); }
  }
}

// ── L'onde, plus ample quand Root réfléchit ─────────────────────────────────
function animerOnde() {
  const cv = $("#onde"), g = cv.getContext("2d"), W = cv.width, H = cv.height, n = 24;
  let t = 0, ampli = .3;
  (function tic() {
    requestAnimationFrame(tic);
    if (document.hidden) return;
    const cible = document.body.classList.contains("reflechit") ? 1 : .3;
    ampli += (cible - ampli) * .06;
    g.clearRect(0, 0, W, H);
    for (let i = 0; i < n; i++) {
      const v = (Math.sin(t + i * .55) + Math.sin(t * 1.7 + i * .23)) / 4 + .5;
      const h = 6 + v * (H - 10) * ampli, w = W / n;
      g.fillStyle = `rgba(111,212,182,${.3 + v * .55})`;
      g.beginPath(); g.roundRect(i * w + 1, (H - h) / 2, w - 4, h, 3); g.fill();
    }
    t += .06 + ampli * .05;
  })();
}

// ── Profondeur : le fond suit doucement la souris ───────────────────────────
addEventListener("mousemove", e => {
  const r = document.documentElement.style;
  r.setProperty("--mx", (e.clientX / innerWidth - .5).toFixed(3));
  r.setProperty("--my", (e.clientY / innerHeight - .5).toFixed(3));
});

// ── Mini-rendu Markdown : blocs de code, `code`, **gras**, listes, liens ─────
function enRiche(texte) {
  const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const blocs = [];
  texte = texte.replace(/```[\w-]*\n?([\s\S]*?)```/g, (_, c) => `\u0000${blocs.push(c) - 1}\u0000`);
  const ligne = s => esc(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2">$1</a>');
  return texte.split(/\n{2,}/).map(par => {
    const m = par.match(/^\u0000(\d+)\u0000$/);
    if (m) return `<pre>${esc(blocs[+m[1]])}</pre>`;
    const lignes = par.split("\n");
    if (lignes.every(l => /^\s*[-•*]\s+/.test(l)))
      return "<p>" + lignes.map(l => "• " + ligne(l.replace(/^\s*[-•*]\s+/, ""))).join("<br>") + "</p>";
    return "<p>" + lignes.map(ligne).join("<br>") + "</p>";
  }).join("");
}
const fr = (n, d = 0) => n.toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d });

// ── Le fil ───────────────────────────────────────────────────────────────────
const fil = $("#fil"), interieur = $("#fil-inner");
function poser(el) {
  el.classList.add("entre");
  interieur.appendChild(el);
  requestAnimationFrame(() => fil.scrollTo({ top: fil.scrollHeight, behavior: "smooth" }));
  return el;
}
function bloc(classe, html) { const d = document.createElement("div"); d.className = classe; d.innerHTML = html; return poser(d); }
const ajouterToi = t => { const d = document.createElement("div"); d.className = "msg toi"; d.textContent = t; poser(d); };
const ajouterRoot = (t, alerte) => bloc(`msg root verre${alerte ? " alerte" : ""}`, `<div class="liseré"></div><div class="corps">${enRiche(t)}</div>`);
const conversationEntamee = () => interieur.querySelector(".msg.toi") !== null;

const enCours = [];   // puces d'outils qui attendent leur résultat
function ajouterOutil(nom, args) {
  const el = bloc("outil verre", `<div class="outil-tete"><span class="rond"></span><span class="nom"></span><span class="args"></span></div><div class="outil-detail"><pre></pre></div>`);
  el.querySelector(".nom").textContent = nom;
  el.querySelector(".args").textContent = args && args !== "{}" ? args : "";
  el.querySelector(".outil-tete").onclick = () => el.classList.toggle("ouvert");
  enCours.push({ nom, el });
}
function resultatOutil(nom, texte) {
  const i = enCours.map(x => x.nom).lastIndexOf(nom);
  if (i < 0) return;
  const { el } = enCours.splice(i, 1)[0];
  el.classList.add(texte === "refusé" ? "refuse" : "fait");
  el.querySelector("pre").textContent = texte;
}

let demandeOuverte = null;
function demande(id, nom, args) {
  const el = bloc("demande verre", `<div class="titre">Root veut utiliser <b></b></div><pre></pre>
    <div class="gestes"><button class="oui">Autoriser<kbd>⌘⏎</kbd></button><button class="non">Refuser<kbd>esc</kbd></button></div>`);
  el.querySelector(".titre b").textContent = nom;
  el.querySelector("pre").textContent = args;
  const trancher = ok => {
    if (!demandeOuverte || demandeOuverte.id !== id) return;
    demandeOuverte = null;
    el.classList.add("tranchee");
    el.querySelector(".titre").append(ok ? " · autorisé" : " · refusé");
    api() && api().repondre(id, ok);
  };
  el.querySelector(".oui").onclick = () => trancher(true);
  el.querySelector(".non").onclick = () => trancher(false);
  demandeOuverte = { id, trancher };
}

function fin(ev) {
  const heure = new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  let txt = `✻ ${ev.secondes} s · <span class="cerv">${ev.cerveau}</span>`;
  if (ev.tokens) txt += ` · ${ev.tokens >= 1000 ? fr(ev.tokens / 1000, 1) + "k" : ev.tokens} tokens`;
  if (ev.cout != null) txt += ` · ${fr(ev.cout * 100, ev.cout * 100 < 1 ? 2 : 1)} ct`;
  bloc("duree", `${txt} · ${heure}`);
  if (ev.lies && ev.lies.length) {                 // souvenirs liés à la demande (rappel)
    const n = ev.lies.length, el = bloc("lies", `${svg("carnet")}${n} souvenir${n > 1 ? "s" : ""} lié${n > 1 ? "s" : ""}`);
    el.title = ev.lies.map(f => "• " + f).join("\n");
    el.setAttribute("role", "button");
    el.onclick = () => ouvrirPanneau("memoire");
  }
}

function toast(texte, ok = true, geste = null) {
  const t = document.createElement("div");
  const partir = () => { if (t._parti) return; t._parti = true; t.classList.add("sort"); setTimeout(() => t.remove(), 450); };
  t.className = "toast verre" + (ok ? "" : " ko") + (geste ? " geste" : "");
  if (geste) {                                     // un toast qui propose un geste (Annuler…)
    t.innerHTML = '<span class="t-txt"></span><button></button>';
    t.querySelector(".t-txt").textContent = texte;
    t.querySelector("button").textContent = geste.label;
    t.querySelector("button").onclick = () => { geste.faire(); partir(); };
  } else t.textContent = texte;
  $("#toasts").appendChild(t);
  setTimeout(partir, geste ? 7000 : 2600);
}

function etat(valeur) {
  const reflechit = valeur === "reflechit";
  document.body.classList.toggle("reflechit", reflechit);
  $("#etat-texte").textContent = reflechit ? "écoute la Machine…" : "à l'écoute";
}

// ── Les événements poussés par le moteur Python ─────────────────────────────
window.rootEvent = function (ev) {
  switch (ev.type) {
    case "root": ajouterRoot(ev.texte); break;
    case "toi": ajouterToi(ev.texte); break;
    case "outil": ajouterOutil(ev.nom, ev.args); break;
    case "resultat": resultatOutil(ev.nom, ev.texte); break;
    case "image": bloc("capture", `<img alt="capture d'écran vue par Root" src="${ev.src}">`); break;
    case "demande": demande(ev.id, ev.nom, ev.args); break;
    case "fin": fin(ev); break;
    case "arret": ajouterRoot(ev.texte, true); break;
    case "etat": etat(ev.valeur); break;
    case "toast": toast(ev.texte, ev.ok); break;
    case "cerveau": cerveauActif(ev.id, ev.nom); break;
    case "conversations": chargerConversations(); break;
    case "memoire": if (PANNEAU === "memoire") chargerMemoire(); break;
    case "term": termEcrire(ev.data); break;
    case "term_fin": termFin(); break;
    case "retenu":
      toast(`Root a retenu : ${ev.fait}`, true, { label: "Annuler", faire: async () => {
        await api().memoire_retirer(ev.fait); toast("Retiré de sa mémoire"); } });
      break;
  }
};


// ── Le dock : une icône = un panneau ─────────────────────────────────────────
const lueur = $("#dock-lueur"), bulle = $("#bulle");
const ICONES_DOCK = [
  { id: "cerveaux", label: "Cerveaux", icone: "cerveau", kbd: "⌘1", ouvrir: () => basculer("cerveaux") },
  { id: "conversations", label: "Conversations", icone: "bulle", kbd: "⌘2", ouvrir: () => basculer("conversations") },
  { id: "memoire", label: "Mémoire", icone: "carnet", kbd: "⌘3", ouvrir: () => basculer("memoire") },
  { id: "outils", label: "Outils", icone: "outils", kbd: "⌘4", ouvrir: () => basculer("outils") },
  { id: "terminal", label: "Terminal", icone: "terminal", kbd: "⌘5", ouvrir: ouvrirTerminal },
];
function survol(btn, label, kbd) {
  const r = btn.getBoundingClientRect(), d = $("#dock").getBoundingClientRect();
  lueur.style.transform = `translateY(${r.top - d.top + r.height / 2 - 11}px)`;
  lueur.classList.add("on");
  $("#bulle-label").textContent = label; $("#bulle-kbd").textContent = kbd || "";
  $("#bulle-kbd").style.display = kbd ? "" : "none";
  bulle.style.top = `${r.top + r.height / 2 - bulle.offsetHeight / 2}px`;
  bulle.classList.add("on");
}
function quitter() {
  bulle.classList.remove("on");
  const ouvert = document.querySelector(".dock-btn.ouvert");
  ouvert ? survolLueur(ouvert) : lueur.classList.remove("on");
}
function survolLueur(btn) {
  const r = btn.getBoundingClientRect(), d = $("#dock").getBoundingClientRect();
  lueur.style.transform = `translateY(${r.top - d.top + r.height / 2 - 11}px)`; lueur.classList.add("on");
}
function frapper(b) { b.classList.remove("frappe"); void b.offsetWidth; b.classList.add("frappe"); }
function construireDock() {
  const zone = $("#dock-icones"); zone.innerHTML = "";
  for (const ic of ICONES_DOCK) {
    const b = document.createElement("button");
    b.className = "dock-btn"; b.id = "ic-" + ic.id;
    b.innerHTML = svg(ic.icone) + '<span class="onde-clic"></span>';
    b.setAttribute("aria-label", ic.label);
    b.onmouseenter = () => survol(b, ic.label, ic.kbd);
    b.onmouseleave = quitter;
    b.onclick = () => { frapper(b); ic.ouvrir(); };
    zone.appendChild(b);
  }
}

// ── Les panneaux : un seul ouvert à la fois, soudé au dock ──────────────────
const PANNEAUX = {
  cerveaux: { el: $("#panneau-cerveaux"), ouvrir: () => { rendreCerveaux(); sonderTout(); } },
  conversations: { el: $("#panneau-conv"), ouvrir: () => { rendreConversations(); chargerConversations(); setTimeout(() => cherche.focus(), 80); } },
  memoire: { el: $("#panneau-memoire"), ouvrir: () => { rendreMemoire(); chargerMemoire(); setTimeout(() => champFait.focus(), 80); } },
  outils: { el: $("#panneau-outils"), ouvrir: chargerOutils },
};
let PANNEAU = null;
function ouvrirPanneau(nom) {
  if (PANNEAU === nom) return;
  if (PANNEAU) fermerPanneau(false);
  const p = PANNEAUX[nom]; PANNEAU = nom;
  p.el.classList.add("ouvert"); p.el.setAttribute("aria-hidden", "false");
  const b = $("#ic-" + nom); b.classList.add("ouvert"); survolLueur(b);
  p.ouvrir();
}
function fermerPanneau(rendreFocus = true) {
  fermerMenu();
  if (!PANNEAU) return;
  const p = PANNEAUX[PANNEAU];
  $("#ic-" + PANNEAU).classList.remove("ouvert"); PANNEAU = null;
  p.el.classList.remove("ouvert"); p.el.setAttribute("aria-hidden", "true");
  lueur.classList.remove("on");
  if (rendreFocus) saisie.focus();
}
const basculer = nom => PANNEAU === nom ? fermerPanneau() : ouvrirPanneau(nom);
document.querySelectorAll("[data-fermer]").forEach(b => { b.onclick = () => fermerPanneau(); });
document.addEventListener("mousedown", e => {
  if (!menu.hidden && !menu.contains(e.target)) fermerMenu();
  if (!PANNEAU || PANNEAUX[PANNEAU].el.contains(e.target) || $("#dock").contains(e.target)
      || menu.contains(e.target) || e.target.closest("#puce-cerveau")) return;
  fermerPanneau();
});

// ── Panneau « Cerveaux » ─────────────────────────────────────────────────────
const liste = $("#cerveaux-liste");
let CERVEAUX = [], ACTIF = null, SONDES = {};

function cerveauActif(id, nom) {
  ACTIF = id;
  const p = $("#puce-cerveau");
  p.textContent = nom; p.classList.remove("change"); void p.offsetWidth; p.classList.add("change");
  liste.querySelectorAll(".cerveau").forEach(c => { c.classList.toggle("actif", c.dataset.id === id); c.classList.remove("choix"); });
}

function prix(c) {
  if (!c.prix) return "prix à confirmer";
  const f = x => fr(x, x < 1 ? 2 : 1).replace(/,?0+$/, "") || "0";
  return `${f(c.prix[0])} $ / ${f(c.prix[1])} $ le M`;
}
function sonde(id) {
  const s = SONDES[id];
  if (!s) return '<span class="c-point attente"></span>';
  if (!s.ok) return `<span class="c-point ko"></span>${s.raison === "clé absente" ? "clé absente" : "injoignable"}`;
  return `<span class="c-point ok"></span>${s.ms} ms`;
}
function rendreCerveaux() {
  let html = "", i = 0, groupe = null;
  for (const c of CERVEAUX) {
    if (c.fournisseur !== groupe) { groupe = c.fournisseur; html += `<div class="groupe">${groupe}</div>`; }
    const badges = [
      c.outils ? '<span class="badge">outils</span>' : '<span class="badge sans">outils</span>',
      c.vision ? '<span class="badge">vision</span>' : '<span class="badge sans">vision</span>',
      c.raisonnement ? '<span class="badge">réflexion</span>' : "",
    ].join("");
    html += `<div class="cerveau${c.id === ACTIF ? " actif" : ""}" role="button" tabindex="0" data-id="${c.id}" style="--i:${i++}">
      <div class="c-ligne"><span class="c-nom">${c.nom}</span><span class="c-actif">● actif</span><span class="c-sonde">${sonde(c.id)}</span></div>
      <div class="c-note">${c.note || ""}</div>
      <div class="c-pied">${badges}<span class="c-prix">${prix(c)}</span></div>
      <div class="c-choix"><div><button class="continuer">Continuer ici</button><button class="repartir">Repartir à zéro</button></div></div>
    </div>`;
  }
  liste.innerHTML = html;
  liste.querySelectorAll(".cerveau").forEach(el => {
    const id = el.dataset.id;
    el.onclick = e => {
      if (e.target.closest(".continuer")) return choisir(id, false);
      if (e.target.closest(".repartir")) return choisir(id, true);
      if (id === ACTIF) return;
      if (!conversationEntamee()) return choisir(id, false);     // rien à garder : on bascule
      const deja = el.classList.contains("choix");
      liste.querySelectorAll(".cerveau.choix").forEach(x => x.classList.remove("choix"));
      if (!deja) el.classList.add("choix");                     // sinon : continuer ou repartir ?
    };
    el.onkeydown = e => { if (e.key === "Enter") el.click(); };
  });
}
async function choisir(id, repartir) {
  if (!api()) return;
  const ok = await api().choisir_cerveau(id, repartir);
  if (!ok) return;
  if (repartir) repartirDeZero();
  fermerPanneau();
}
async function sonderTout() {
  SONDES = {}; rendreCerveaux();
  if (!api()) return;
  SONDES = await api().sonder_cerveaux();
  liste.querySelectorAll(".cerveau").forEach(el => { el.querySelector(".c-sonde").innerHTML = sonde(el.dataset.id); });
}
function ouvrirCerveaux(choixId) {
  ouvrirPanneau("cerveaux");
  if (choixId && choixId !== ACTIF) {
    const el = liste.querySelector(`.cerveau[data-id="${choixId}"]`);
    if (el) { conversationEntamee() ? el.classList.add("choix") : choisir(choixId, false); el.scrollIntoView({ block: "nearest" }); }
  }
}
$("#puce-cerveau").onclick = () => ouvrirCerveaux();

// ── Panneau « Conversations » : toutes, de tous les LLM, rangées par projet ──
const NOMS_SOURCES = { root: "Root", claude: "Claude Code", codex: "Codex", hermes: "Hermes" };
const listeC = $("#conv-liste"), cherche = $("#conv-cherche"), menu = $("#menu-ranger");
let CONV = { projets: [], liste: [], actuelle: null }, FILTRE = "tout", TROUVEES = null, LECTURE = null, iRang = 0;
const plies = new Set((() => { try { return JSON.parse(localStorage.getItem("root.plies") || "[]"); } catch { return []; } })());
const memoriserPlies = () => { try { localStorage.setItem("root.plies", JSON.stringify([...plies])); } catch { /* sans stockage */ } };

async function chargerConversations() {
  if (!api()) return;
  CONV = await api().conversations();
  if (PANNEAU === "conversations") rendreConversations();
}

const debutJour = d => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
const joursDepuis = ts => Math.round((debutJour(new Date()) - debutJour(new Date(ts * 1000))) / 864e5);
function quand(ts) {
  const d = new Date(ts * 1000), j = joursDepuis(ts);
  if (j <= 0) return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  if (j === 1) return "hier";
  if (j < 7) return d.toLocaleDateString("fr-FR", { weekday: "long" });
  const autreAnnee = d.getFullYear() !== new Date().getFullYear();
  return d.toLocaleDateString("fr-FR", { day: "numeric", month: "short", ...(autreAnnee ? { year: "numeric" } : {}) });
}
function periode(ts) {
  const j = joursDepuis(ts);
  return j <= 0 ? "Aujourd'hui" : j === 1 ? "Hier" : j < 7 ? "Cette semaine" : j < 31 ? "Ce mois-ci" : "Plus ancien";
}
function nomCerveau(c) {
  if (!c.cerveau) return "";
  if (c.source === "root") return (CERVEAUX.find(x => x.id === c.cerveau) || {}).nom || c.cerveau;
  const m = c.cerveau.match(/^claude-([a-z]+)-(\d+)(?:-(\d+))?/);
  if (m) return `${m[1][0].toUpperCase() + m[1].slice(1)} ${m[2]}${m[3] ? "." + m[3] : ""}`;
  return c.cerveau.split("/").pop();
}

function rendreFiltres() {
  const n = s => CONV.liste.filter(c => s === "tout" || c.source === s).length;
  const zone = $("#conv-filtres");
  zone.innerHTML = ["tout", "root", "claude", "codex", "hermes"].filter(s => s === "tout" || n(s)).map(s =>
    `<button class="filtre${FILTRE === s ? " on" : ""}" data-f="${s}"${s !== "tout" ? ` data-src="${s}"` : ""}>${s !== "tout" ? '<span class="src"></span>' : ""}${s === "tout" ? "Tout" : NOMS_SOURCES[s]}<span class="n">${n(s)}</span></button>`).join("");
  zone.querySelectorAll(".filtre").forEach(b => { b.onclick = () => { FILTRE = b.dataset.f; rendreConversations(); }; });
}

function ligne(c) {
  const sous = [NOMS_SOURCES[c.source], nomCerveau(c), quand(c.date)].filter(Boolean).map(echap).join(" · ")
    + (c.auto ? ' · <span class="auto">proposé</span>' : "");
  return `<div class="conv${c.cle === CONV.actuelle ? " actuelle" : ""}${c.epingle ? " epinglee" : ""}" draggable="true" data-cle="${echap(c.cle)}" data-src="${c.source}" style="--i:${Math.min(iRang++, 30)}" role="button" tabindex="0">
    <span class="src"></span>
    <div class="conv-txt"><div class="conv-titre">${echap(c.titre)}</div><div class="conv-sous">${sous}</div></div>
    <div class="conv-gestes">
      <button class="epingle${c.epingle ? " on" : ""}" title="${c.epingle ? "Désépingler" : "Épingler"}">${svg("epingle")}</button>
      <button class="renommer" title="Renommer (double-clic sur le titre)">${svg("crayon")}</button>
      <button class="ranger" title="Ranger dans un projet">${svg("dossier")}</button>
      <button class="suppr" title="${c.source === "root" ? "Supprimer" : "Masquer d'ici (rien n'est effacé)"}">${svg("croix")}</button>
    </div></div>`;
}

function groupe(g) {
  const cle = "g:" + (g.id || "libres"), plie = !g.fixe && plies.has(cle);
  let corps = "";
  if (g.periodes) {
    let courante = null;
    for (const c of g.items) {
      const p = periode(c.date);
      if (p !== courante) { courante = p; corps += `<div class="sous-grp">${p}</div>`; }
      corps += ligne(c);
    }
  } else corps = g.items.map(ligne).join("");
  if (!g.items.length) corps = `<div class="grp-vide">${g.projet ? "Glisse une conversation ici." : "Aucune."}</div>`;
  const icone = g.projet ? svg("dossier", "dossier") : g.icone ? svg(g.icone, "dossier") : "";
  return `<section class="grp${g.projet ? " projet" : ""}${plie ? " plie" : ""}" data-g="${echap(g.id)}" data-cle="${cle}"${g.projet || g.cible ? ' data-cible="1"' : ""}>
    <button class="grp-tete">${svg("chevron", "chevron")}${icone}<span class="grp-nom">${echap(g.nom)}</span><span class="grp-n">${g.items.length}</span>${g.projet ? `<span class="grp-suppr" title="Supprimer le projet (ses conversations restent)">${svg("croix")}</span>` : ""}</button>
    <div class="grp-corps"><div>${corps}</div></div></section>`;
}

function rendreConversations() {
  rendreFiltres();
  iRang = 0;
  let items = CONV.liste.filter(c => FILTRE === "tout" || c.source === FILTRE);
  const q = cherche.value.trim();
  if (q) {
    const qn = normal(q);
    items = items.filter(c => (TROUVEES && TROUVEES.has(c.cle)) || normal(c.titre).includes(qn));
    $("#conv-sous").textContent = `${items.length} résultat${items.length > 1 ? "s" : ""}${TROUVEES ? "" : " dans les titres…"}`;
    listeC.innerHTML = items.length ? groupe({ id: "res", nom: "Résultats", items, fixe: true }) : '<div class="conv-vide">Rien trouvé.</div>';
  } else {
    $("#conv-sous").textContent = CONV.liste.length ? `${CONV.liste.length} conversations, de tous tes LLM.` : "Je rassemble tes conversations…";
    const epinglees = items.filter(c => c.epingle);
    let html = epinglees.length ? groupe({ id: "epinglees", nom: "Épinglées", items: epinglees, icone: "epingle" }) : "";
    for (const p of CONV.projets) html += groupe({ id: p.id, nom: p.nom, items: items.filter(c => c.projet === p.id && !c.epingle), projet: true });
    html += groupe({ id: "", nom: "Non classées", items: items.filter(c => !c.projet && !c.epingle), periodes: true, cible: true });
    listeC.innerHTML = html;
  }
  brancherConversations();
}

function armer(btn, label, action) {          // deux clics pour un geste qui efface
  if (btn.classList.contains("arme")) { clearTimeout(btn._t); return action(); }
  const avant = btn.innerHTML; btn.classList.add("arme"); btn.textContent = label;
  btn._t = setTimeout(() => { btn.classList.remove("arme"); btn.innerHTML = avant; }, 3000);
}
function editer(el, valider) {                  // renommer sur place : Entrée garde, Échap annule
  const avant = el.textContent, rangee = el.closest(".conv");
  if (rangee) rangee.draggable = false;
  el.contentEditable = "true"; el.focus();
  getSelection().selectAllChildren(el);
  const fin = ok => {
    el.contentEditable = "false"; el.onkeydown = el.onblur = null;
    if (rangee) rangee.draggable = true;
    const t = el.textContent.trim();
    if (ok && t && t !== avant) valider(t); else el.textContent = avant;
  };
  el.onkeydown = e => {
    e.stopPropagation();
    if (e.key === "Enter") { e.preventDefault(); fin(true); } else if (e.key === "Escape") { e.preventDefault(); fin(false); }
  };
  el.onblur = () => fin(true);
}
function renommerConv(el, cle) {
  editer(el, async t => {
    await api().renommer_conversation(cle, t);
    if (cle === CONV.actuelle) titreConv(t);
    chargerConversations();
  });
}

function brancherConversations() {
  listeC.querySelectorAll(".grp").forEach(g => {
    const tete = g.querySelector(".grp-tete");
    tete.onclick = e => {
      const s = e.target.closest(".grp-suppr");
      if (s) {
        e.stopPropagation();
        return armer(s, "Supprimer ?", async () => {
          await api().supprimer_projet(g.dataset.g); await chargerConversations();
          toast("Projet supprimé, ses conversations sont dans Non classées");
        });
      }
      if (g.dataset.cle === "g:res" || e.target.closest('[contenteditable="true"]')) return;
      g.classList.toggle("plie");
      g.classList.contains("plie") ? plies.add(g.dataset.cle) : plies.delete(g.dataset.cle);
      memoriserPlies();
    };
    if (g.classList.contains("projet"))
      tete.ondblclick = e => {
        e.preventDefault(); g.classList.remove("plie");
        editer(tete.querySelector(".grp-nom"), async nom => { await api().renommer_projet(g.dataset.g, nom); chargerConversations(); });
      };
    if (g.dataset.cible) {
      g.ondragover = e => { e.preventDefault(); g.classList.add("survol"); };
      g.ondragleave = e => { if (!g.contains(e.relatedTarget)) g.classList.remove("survol"); };
      g.ondrop = async e => {
        e.preventDefault(); g.classList.remove("survol");
        const cle = e.dataTransfer.getData("text/plain");
        if (cle) { await api().ranger_conversation(cle, g.dataset.g); chargerConversations(); }
      };
    }
  });
  listeC.querySelectorAll(".conv").forEach(el => {
    const cle = el.dataset.cle, c = CONV.liste.find(x => x.cle === cle), titre = el.querySelector(".conv-titre");
    el.onclick = e => {
      if (e.target.closest(".epingle")) return api().epingler_conversation(cle, !c.epingle).then(chargerConversations);
      if (e.target.closest(".renommer")) return renommerConv(titre, cle);
      if (e.target.closest(".ranger")) return menuRanger(e.target.closest(".ranger"), c);
      const s = e.target.closest(".suppr");
      if (s) return armer(s, c.source === "root" ? "Supprimer ?" : "Masquer ?", async () => {
        await api().supprimer_conversation(cle);
        if (cle === CONV.actuelle) repartirDeZero();
        chargerConversations();
      });
      if (titre.isContentEditable) return;
      // un clic sur le titre attend un éventuel double-clic (renommer)
      if (e.target.closest(".conv-titre")) { clearTimeout(el._t); el._t = setTimeout(() => ouvrirConversation(cle), 230); return; }
      ouvrirConversation(cle);
    };
    titre.ondblclick = e => { e.stopPropagation(); clearTimeout(el._t); renommerConv(titre, cle); };
    el.onkeydown = e => { if (e.key === "Enter" && e.target === el) ouvrirConversation(cle); };
    el.ondragstart = e => { e.dataTransfer.setData("text/plain", cle); e.dataTransfer.effectAllowed = "move"; el.classList.add("glisse"); };
    el.ondragend = () => el.classList.remove("glisse");
  });
}

function menuRanger(btn, c) {
  const r = btn.getBoundingClientRect();
  menu.innerHTML = '<div class="m-titre">Ranger dans</div>'
    + CONV.projets.map(p => `<button data-p="${echap(p.id)}"${c.projet === p.id ? ' class="on"' : ""}>${svg("dossier")}${echap(p.nom)}</button>`).join("")
    + `<button data-p=""${!c.projet ? ' class="on"' : ""}>${svg("croix")}Non classées</button><hr><button data-nouveau>${svg("plus")}Nouveau projet…</button>`;
  menu.hidden = false;
  menu.style.left = `${Math.min(r.left - 8, innerWidth - menu.offsetWidth - 10)}px`;
  menu.style.top = `${Math.min(r.bottom + 6, innerHeight - menu.offsetHeight - 10)}px`;
  menu.querySelectorAll("button").forEach(b => {
    b.onclick = async () => {
      fermerMenu();
      if (b.hasAttribute("data-nouveau")) return nouveauProjet(c.cle);
      await api().ranger_conversation(c.cle, b.dataset.p); chargerConversations();
    };
  });
}
function fermerMenu() { menu.hidden = true; }

function nouveauProjet(cleARanger) {
  const pied = $(".conv-pied"), bouton = $("#projet-nouveau");
  const champ = document.createElement("input");
  champ.className = "projet-saisie"; champ.placeholder = "Nom du projet, puis Entrée";
  bouton.hidden = true; pied.appendChild(champ); champ.focus();
  const fin = async ok => {
    if (champ._fini) return;
    champ._fini = true;
    const nom = champ.value.trim();
    champ.remove(); bouton.hidden = false;
    if (!ok || !nom) return;
    const p = await api().creer_projet(nom);
    if (cleARanger) await api().ranger_conversation(cleARanger, p.id);
    await chargerConversations();
    toast(`Projet « ${nom} » créé`);
  };
  champ.onkeydown = e => { e.stopPropagation(); if (e.key === "Enter") fin(true); else if (e.key === "Escape") fin(false); };
  champ.onblur = () => fin(true);
}
$("#projet-nouveau").onclick = () => nouveauProjet(null);
$("#conv-nouvelle").onclick = () => { nouvelleConversation(); fermerPanneau(); };

let minuterie;
cherche.addEventListener("input", () => {
  clearTimeout(minuterie); TROUVEES = null;
  const q = cherche.value.trim();
  rendreConversations();                       // les titres tout de suite, le texte entier juste après
  if (!q) return;
  minuterie = setTimeout(async () => {
    const cles = await api().chercher_conversations(q);
    if (cherche.value.trim() === q) { TROUVEES = new Set(cles); rendreConversations(); }
  }, 220);
});
cherche.addEventListener("keydown", e => {
  if (e.key === "Enter") { const premiere = listeC.querySelector(".conv"); if (premiere) ouvrirConversation(premiere.dataset.cle); }
  if (e.key === "Escape") {
    e.stopPropagation(); e.preventDefault();
    if (cherche.value) { cherche.value = ""; TROUVEES = null; rendreConversations(); } else fermerPanneau();
  }
});

// ── Panneau « Outils » : ce que Root a le droit de faire ─────────────────────
let OU = null;
async function chargerOutils() {
  if (!api()) return;
  OU = await api().outils();
  rendreOutils();
}
function rendreOutils() {
  if (!OU) return;
  const seg = $("#ou-mode-choix");
  seg.innerHTML = [["prudente", "Prudente"], ["large", "Large"]].map(([id, n]) =>
    `<button data-m="${id}"${OU.autonomie === id ? ' class="on"' : ""}>${n}</button>`).join("");
  seg.querySelectorAll("button").forEach(b => b.onclick = async () => { await api().outils_autonomie(b.dataset.m); chargerOutils(); });
  $("#ou-mode-aide").textContent = OU.autonomie === "large"
    ? "Root agit seule, demande avant ce qui casse ou sort" : "Root demande avant chaque action";
  $("#ou-pre").innerHTML = OU.prereglages.map(p =>
    `<button data-p="${p.id}"${OU.actif === p.id ? ' class="on"' : ""} title="${echap(p.aide)}">${echap(p.nom)}</button>`).join("");
  $("#ou-pre").querySelectorAll("button").forEach(b => b.onclick = async () => { await api().outils_prereglage(b.dataset.p); chargerOutils(); });

  const q = normal(($("#ou-cherche") || {}).value || "");
  let i = 0;
  $("#ou-familles").innerHTML = OU.familles.filter(f => !f.perso).map(f => {
    const cle = "o:" + f.titre;
    const outils = q ? f.outils.filter(o => normal(o.id + " " + o.description).includes(q)) : f.outils;
    if (!outils.length) return "";
    // replié par défaut : on n'ouvre que si Vincent l'a ouvert, ou si on cherche
    const plie = !q && !ouvertsOutils.has(cle);
    const actifs = f.outils.filter(o => !o.coupe).length;
    return `<section class="grp projet${plie ? " plie" : ""}" data-cle="${echap(cle)}">
      <button class="grp-tete">${svg("chevron", "chevron")}<span class="grp-nom">${echap(f.titre)}</span><span class="grp-n">${actifs}/${f.outils.length}</span></button>
      <div class="grp-corps"><div>${outils.map(o => outilLigne(o, i++)).join("")}</div></div></section>`;
  }).join("") || '<div class="conv-vide">Aucun outil pour cette recherche.</div>';
  rendreMesOutils();
  brancherOutils();

  const av = $("#ou-avance"), ta = OU.terminal_auto;
  av.classList.toggle("actif", ta.actif);
  av.classList.toggle("plie", !plies.has("o:avance") ? !ta.actif && !av.classList.contains("force-ouvert") : true);
  av.toggleAttribute("data-eteint", !ta.actif);
  $("#ou-auto-etat").textContent = ta.actif ? `${ta.prefixes.length} autorisée${ta.prefixes.length > 1 ? "s" : ""}` : "éteint";
  $("#ou-auto-actif").checked = ta.actif;
  $("#ou-prefixes").innerHTML = ta.prefixes.map((p, k) =>
    `<div class="ou-prefixe"><code>${echap(p)}</code><button data-k="${k}" title="Retirer">${svg("croix")}</button></div>`).join("");
  $("#ou-prefixes").querySelectorAll("button").forEach(b => b.onclick = async () => {
    const reste = ta.prefixes.filter((_, k) => k !== +b.dataset.k);
    await api().terminal_auto_prefixes(reste); chargerOutils();
  });
}
function outilLigne(o, i) {
  const fige = o.verrouille_demande;
  const retrait = o.perso ? `<button class="ou-perso-x" title="Retirer cet outil">${svg("croix")}</button>` : "";
  return `<div class="ou-outil${o.coupe ? " coupe" : ""}" style="--i:${i}" data-id="${o.id}">
    <button class="ou-dep" title="Détails">${svg("chevron", "chevron")}</button>
    <div class="ou-txt">
      <div class="ou-nom">${echap(o.id)}<span class="ou-risque${o.perso ? " mien" : ""}" data-r="${o.risque}" title="${echap(o.risque_aide)}">${echap(o.risque_nom)}</span></div>
      <div class="ou-desc">${echap(o.description)}</div>
      <div class="ou-detail">
        ${o.source ? `<a class="ou-src" href="#" data-url="${echap(o.source)}">${echap(o.source.replace(/^https?:\/\//, ""))}</a>` : ""}
        ${o.commande ? `<code class="ou-cmd">${echap(o.commande)}</code>` : ""}
        <div class="ou-reglages">
          <label class="${fige ? "fige" : ""}" title="${fige ? "Cet outil demande toujours, c'est un garde-fou" : "Demander mon accord à chaque fois"}">
            <input type="checkbox" class="strict"${o.strict || fige ? " checked" : ""}${fige ? " disabled" : ""}><span class="mini-interr"></span>Demander mon accord</label>
          ${retrait}
        </div>
      </div>
    </div>
    <label class="ou-bascule-c" title="${o.coupe ? "Activer" : "Couper : Root ne pourra plus l'utiliser"}"><input type="checkbox" class="actif"${o.coupe ? "" : " checked"}><span class="interr"></span></label>
  </div>`;
}
function rendreMesOutils() {
  const f = OU.familles.find(x => x.perso), liste = $("#ou-mes-liste");
  $("#ou-mes-n").textContent = f ? f.outils.length : 0;
  let i = 0;
  liste.innerHTML = f ? f.outils.map(o => outilLigne(o, i++)).join("") : '<div class="grp-vide">Aucun outil à toi pour l\'instant.</div>';
}
function brancherOutils() {
  document.querySelectorAll("#ou-familles .grp").forEach(g => {
    g.querySelector(".grp-tete").onclick = () => { g.classList.toggle("plie"); basculerFamilleOutil(g.dataset.cle); };
  });
  ["#ou-avance", "#ou-mes"].forEach(id => {
    const g = $(id); if (!g) return;
    g.querySelector(".grp-tete").onclick = () => {
      g.classList.toggle("plie");
      g.classList.contains("plie") ? plies.add(g.dataset.cle) : plies.delete(g.dataset.cle);
      memoriserPlies();
    };
  });
  document.querySelectorAll(".ou-outil").forEach(el => {
    const id = el.dataset.id;
    el.querySelector(".actif").onchange = async e => { await api().outil_basculer(id, !e.target.checked); chargerOutils(); };
    const st = el.querySelector(".strict:not(:disabled)");
    if (st) st.onchange = async e => { await api().outil_strict(id, e.target.checked); };
    const dep = el.querySelector(".ou-dep");
    if (dep) dep.onclick = () => el.classList.toggle("ouvert");
    const x = el.querySelector(".ou-perso-x");
    if (x) x.onclick = () => armer(x, "Retirer ?", async () => { await api().outil_perso_retirer(id); chargerOutils(); });
    const src = el.querySelector(".ou-src");
    if (src) src.onclick = e => { e.preventDefault(); ouvrirLien(src.dataset.url); };
  });
}
$("#ou-auto-actif").onchange = async e => {
  if (e.target.checked) $("#ou-avance").classList.add("force-ouvert");
  await api().terminal_auto_activer(e.target.checked); chargerOutils();
};
$("#ou-prefixe-ajout").addEventListener("submit", async e => {
  e.preventDefault();
  const champ = $("#ou-prefixe-champ"), v = champ.value.trim();
  if (!v || !OU) return;
  await api().terminal_auto_prefixes([...OU.terminal_auto.prefixes, v]);
  champ.value = ""; chargerOutils();
});
$("#ou-prefixe-champ").addEventListener("keydown", e => e.stopPropagation());

// familles d'outils : repliées par défaut, Vincent ouvre celles qu'il veut
const ouvertsOutils = new Set((() => { try { return JSON.parse(localStorage.getItem("root.ouvertsOutils") || "[]"); } catch { return []; } })());
function basculerFamilleOutil(cle) {
  ouvertsOutils.has(cle) ? ouvertsOutils.delete(cle) : ouvertsOutils.add(cle);
  try { localStorage.setItem("root.ouvertsOutils", JSON.stringify([...ouvertsOutils])); } catch { /* sans stockage */ }
}
function ouvrirLien(url) { if (api() && api().ouvrir_lien) api().ouvrir_lien(url); }

const chercheOutil = $("#ou-cherche");
let minuterieOutil;
chercheOutil.addEventListener("input", () => { clearTimeout(minuterieOutil); minuterieOutil = setTimeout(rendreOutils, 120); });
chercheOutil.addEventListener("keydown", e => { e.stopPropagation(); if (e.key === "Escape") { chercheOutil.value = ""; rendreOutils(); } });

// Mes outils : lire un README GitHub pour préremplir, puis Vincent valide
const ghChamp = $("#ou-gh"), form = $("#ou-perso-form"), opRetour = $("#op-retour");
$("#ou-gh-lire").onclick = async () => {
  const url = ghChamp.value.trim();
  if (!url || !api()) return;
  $("#ou-gh-lire").textContent = "…";
  const r = await api().outil_depuis_github(url);
  $("#ou-gh-lire").textContent = "Lire";
  if (!r.ok) return toast(r.message, false);
  ouvrirFormOutil(r);
};
function ouvrirFormOutil(pre) {
  form.hidden = false;
  $("#op-nom").value = pre?.nom || "";
  $("#op-desc").value = pre?.readme ? resumeReadme(pre.readme) : "";
  $("#op-cmd").value = pre?.nom ? pre.nom.toLowerCase() : "";
  form.dataset.source = pre?.source || "";
  opRetour.textContent = pre?.readme_manquant ? "README introuvable : décris l'outil toi-même." : "Vérifie et complète, puis ajoute.";
  opRetour.className = "mem-retour";
  $("#op-nom").focus();
}
function resumeReadme(txt) {
  const lignes = txt.split("\n").map(l => l.replace(/^#+\s*/, "").trim())
    .filter(l => l && !l.startsWith("![") && !l.startsWith("[!") && !/^[-=*_]{3,}$/.test(l));
  return lignes.slice(0, 3).join(" ").slice(0, 240);
}
$("#op-annuler").onclick = () => { form.hidden = true; ghChamp.value = ""; };
form.addEventListener("submit", async e => {
  e.preventDefault();
  const nom = $("#op-nom").value.trim(), desc = $("#op-desc").value.trim(), cmd = $("#op-cmd").value.trim();
  if (!nom || !desc || !cmd) { opRetour.className = "mem-retour ko"; opRetour.textContent = "Nom, description et commande sont nécessaires."; return; }
  const r = await api().outil_perso_ajouter(nom, desc, cmd, $("#op-arg").checked, "", $("#op-demande").checked, form.dataset.source || "");
  if (!r.ok) { opRetour.className = "mem-retour ko"; opRetour.textContent = r.message; return; }
  form.hidden = true; ghChamp.value = "";
  plies.delete("o:mes"); memoriserPlies();
  await chargerOutils();
  toast(`« ${nom} » ajouté à tes outils`);
});
[ "#op-nom", "#op-desc", "#op-cmd", "#ou-gh" ].forEach(s => $(s).addEventListener("keydown", e => e.stopPropagation()));

// ── Panneau « Mémoire » : ce que Root sait de toi ────────────────────────────
const listeM = $("#mem-liste"), champFait = $("#mem-fait"), retourM = $("#mem-retour");
let MEM = { categories: [], taille: 0, plafond: 8000, proposees: [] }, CAT = null, NEUF = null;

async function chargerMemoire() {
  if (!api()) return;
  MEM = await api().memoire();
  if (PANNEAU === "memoire") rendreMemoire();
}
const kilo = n => n >= 1000 ? fr(n / 1000, n < 10000 ? 1 : 0) + "k" : String(n);
const dateCourte = iso => { const d = new Date(iso + "T12:00:00"); return isNaN(d) ? iso : d.toLocaleDateString("fr-FR", { day: "numeric", month: "short" }); };
function jauge(id, val, max, texte, repere) {
  const j = $(id), part = Math.min(1, val / max);
  j.querySelector(".j-val").textContent = texte;
  j.querySelector("i").style.width = (part * 100).toFixed(1) + "%";
  j.classList.toggle("haute", repere ? val > repere : part > .85);
  const b = j.querySelector("b");
  if (b) b.style.left = (repere / max * 100).toFixed(1) + "%";
}
function rendreMemoire() {
  jauge("#jauge-durable", MEM.taille, MEM.plafond, `${fr(MEM.taille)} / ${fr(MEM.plafond)} caractères`);
  const c = MEM.contexte || { tokens: 0, budget: 100000, seuil: 70000 };
  jauge("#jauge-contexte", c.tokens, c.budget, `≈ ${kilo(c.tokens)} / ${kilo(c.budget)} tokens`, c.seuil);
  $("#jauge-contexte").title = `Au-delà de ${kilo(c.seuil)} tokens (le repère ambre), Root résume le milieu de la conversation.`;
  rendreCats();
  if (!MEM.categories.length) {
    listeM.innerHTML = '<div class="mem-vide">Root ne sait encore rien de toi.<br>Écris un premier fait au-dessus.</div>';
    return;
  }
  let i = 0;
  listeM.innerHTML = MEM.categories.map(cat => {
    const cle = "m:" + cat.nom;
    return `<section class="grp projet${plies.has(cle) ? " plie" : ""}" data-cle="${echap(cle)}" data-cat="${echap(cat.nom)}">
      <button class="grp-tete">${svg("chevron", "chevron")}<span class="grp-nom">${echap(cat.nom)}</span><span class="grp-n">${cat.faits.length}</span></button>
      <div class="grp-corps"><div>${cat.faits.map(f => `<div class="fait${f.texte === NEUF ? " neuf" : ""}" style="--i:${Math.min(i++, 30)}" data-texte="${echap(f.texte)}">
        <div class="fait-txt"><div class="fait-texte">${echap(f.texte)}</div>${f.date ? `<div class="fait-date">noté le ${dateCourte(f.date)}</div>` : ""}</div>
        <div class="conv-gestes"><button class="modifier" title="Modifier (double-clic)">${svg("crayon")}</button><button class="suppr" title="Oublier : Root ne pourra plus le réapprendre seul">${svg("croix")}</button></div>
      </div>`).join("")}</div></div></section>`;
  }).join("");
  brancherMemoire();
}
function rendreCats() {
  const noms = [...new Set([...MEM.categories.map(c => c.nom), ...MEM.proposees])];
  if (!CAT) CAT = noms[0] || "Profil";
  if (!noms.includes(CAT)) noms.push(CAT);
  const zone = $("#mem-cats");
  zone.innerHTML = noms.map(n => `<button type="button"${n === CAT ? ' class="on"' : ""} data-n="${echap(n)}">${echap(n)}</button>`).join("")
    + '<input placeholder="+ catégorie" aria-label="Nouvelle catégorie">';
  zone.querySelectorAll("button").forEach(b => { b.onclick = () => { CAT = b.dataset.n; rendreCats(); champFait.focus(); }; });
  const entree = zone.querySelector("input");
  entree.onkeydown = e => {
    e.stopPropagation();
    if (e.key === "Enter") { e.preventDefault(); const v = entree.value.trim(); if (v) { CAT = v; rendreCats(); champFait.focus(); } }
    else if (e.key === "Escape") entree.blur();
  };
}
function brancherMemoire() {
  listeM.querySelectorAll(".grp").forEach(g => {
    const tete = g.querySelector(".grp-tete");
    tete.onclick = e => {
      if (e.target.closest('[contenteditable="true"]')) return;
      g.classList.toggle("plie");
      g.classList.contains("plie") ? plies.add(g.dataset.cle) : plies.delete(g.dataset.cle);
      memoriserPlies();
    };
    tete.ondblclick = e => {
      e.preventDefault(); g.classList.remove("plie");
      editer(tete.querySelector(".grp-nom"), async nom => {
        if (await api().memoire_renommer_categorie(g.dataset.cat, nom)) { if (CAT === g.dataset.cat) CAT = nom; }
        else toast("Cette catégorie existe déjà", false);
        chargerMemoire();
      });
    };
  });
  listeM.querySelectorAll(".fait").forEach(el => {
    const texte = el.dataset.texte, zone = el.querySelector(".fait-texte");
    const modifier = () => editer(zone, async nouveau => {
      const r = await api().memoire_modifier(texte, nouveau);
      if (!r.ok) toast(r.message, false);
      chargerMemoire();
    });
    el.querySelector(".modifier").onclick = modifier;
    zone.ondblclick = modifier;
    const s = el.querySelector(".suppr");
    s.onclick = () => armer(s, "Oublier ?", async () => {
      await api().memoire_oublier(texte);
      toast("Oublié. Root ne le réapprendra pas seul.");
    });
  });
}
async function retenir(lever = false) {
  const fait = champFait.value.trim();
  if (!fait || !api()) return;
  const r = await api().memoire_ajouter(CAT || "Profil", fait, lever);
  retourM.className = "mem-retour" + (r.ok ? "" : " ko");
  if (r.ok) {
    NEUF = fait; champFait.value = ""; retourM.textContent = `Retenu dans « ${CAT} ».`;
    await chargerMemoire();
    setTimeout(() => { NEUF = null; }, 2500);
  } else if (r.tombe) {
    retourM.innerHTML = 'Tu lui avais fait oublier ce fait. <button type="button">Le remettre quand même</button>';
    retourM.querySelector("button").onclick = () => retenir(true);
  } else {
    const doublon = r.message.match(/ressemble trop à « (.+?) » déjà noté/);
    retourM.textContent = doublon ? `Déjà retenu presque mot pour mot : « ${doublon[1]} ». Modifie l'ancien plutôt.`
                                  : r.message.replace(/^Refusé\s*:\s*/, "Refusé : ");
  }
}
$("#mem-ajout").addEventListener("submit", e => { e.preventDefault(); retenir(); });
champFait.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey && !e.metaKey) { e.preventDefault(); retenir(); }
});
champFait.addEventListener("input", () => { retourM.textContent = ""; retourM.className = "mem-retour"; });

// ── Ouvrir une conversation : le fil change d'un coup ───────────────────────
const PAR_PAGE = 120;
function titreConv(t) { $("#titre-conv").textContent = t || ""; }
function element(x, src) {
  const d = document.createElement("div");
  if (x.r === "toi") { d.className = "msg toi"; d.textContent = x.t; }
  else if (x.r === "root") {
    d.className = "msg root verre";
    if (src && src !== "root") d.dataset.src = src;
    d.innerHTML = `<div class="liseré"></div><div class="corps">${enRiche(x.t)}</div>`;
  } else {
    const uniques = [...new Set(x.noms)];
    d.className = "outil verre fait groupe";
    d.innerHTML = '<div class="outil-tete"><span class="rond"></span><span class="nom"></span><span class="args"></span></div>';
    d.querySelector(".nom").textContent = x.noms.length > 1 ? `${x.noms.length} actions` : x.noms[0];
    if (x.noms.length > 1) d.querySelector(".args").textContent = uniques.slice(0, 4).join(", ") + (uniques.length > 4 ? "…" : "");
  }
  return d;
}
function bandeauLecture(r) {
  const d = document.createElement("div"), nom = NOMS_SOURCES[r.source];
  d.className = "lecture verre"; d.dataset.src = r.source;
  d.innerHTML = `<div class="l-txt"><div class="l-titre"><span class="src"></span><span class="l-nom"></span></div><div class="l-sous"></div></div>
    <div class="l-gestes"><button class="continuer">Continuer avec Root</button>${r.rouvrir ? `<button class="rouvrir">Rouvrir dans ${nom}</button>` : ""}</div>`;
  d.querySelector(".l-nom").textContent = `Conversation ${nom}, en lecture`;
  d.querySelector(".l-sous").textContent = [nomCerveau(r), r.date ? new Date(r.date * 1000).toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" }) : "",
    r.cwd ? r.cwd.replace(/^\/Users\/[^/]+/, "~") : ""].filter(Boolean).join(" · ");
  d.querySelector(".continuer").onclick = async () => { if (await api().continuer_conversation()) passerEnReprise(); };
  const ro = d.querySelector(".rouvrir");
  if (ro) ro.onclick = () => api().rouvrir_conversation(r.cle);
  return d;
}
function passerEnReprise() {
  if (!LECTURE) return;
  const b = interieur.querySelector(".lecture");
  if (b) { b.classList.add("reprise"); b.querySelector(".l-nom").textContent = `Reprise par Root, depuis ${NOMS_SOURCES[LECTURE.source]}`; }
  bloc("separation", `Root reprend ici, avec ${echap((CERVEAUX.find(c => c.id === ACTIF) || {}).nom || "son cerveau")}`);
  LECTURE = null; CONV.actuelle = null;
  saisie.placeholder = "Parle à Root…"; saisie.focus();
}
function peindreFil(r) {
  interieur.style.transition = "opacity .22s, filter .22s"; interieur.style.opacity = 0; interieur.style.filter = "blur(6px)";
  setTimeout(() => {
    interieur.innerHTML = "";
    enCours.length = 0;
    if (r.lecture) interieur.appendChild(bandeauLecture(r));
    let debut = Math.max(0, r.fil.length - PAR_PAGE);
    const plus = document.createElement("button");
    plus.className = "precedents";
    const majPlus = () => { plus.hidden = debut === 0; plus.textContent = `Afficher ${Math.min(PAR_PAGE, debut)} messages plus anciens`; };
    plus.onclick = () => {
      const h = fil.scrollHeight, avant = Math.max(0, debut - PAR_PAGE), morceau = document.createDocumentFragment();
      r.fil.slice(avant, debut).forEach(x => morceau.appendChild(element(x, r.source)));
      plus.after(morceau); debut = avant; majPlus();
      fil.scrollTop += fil.scrollHeight - h;
    };
    interieur.appendChild(plus); majPlus();
    const morceau = document.createDocumentFragment();
    r.fil.slice(debut).forEach(x => morceau.appendChild(element(x, r.source)));
    interieur.appendChild(morceau);
    if (!r.fil.length) bloc("separation", "conversation vide");
    interieur.style.opacity = 1; interieur.style.filter = "none";
    fil.scrollTop = fil.scrollHeight;
  }, 230);
}
async function ouvrirConversation(cle) {
  if (!api()) return;
  fermerPanneau();
  if (cle === CONV.actuelle && !LECTURE) return;
  const r = await api().ouvrir_conversation(cle);
  if (!r) return;
  CONV.actuelle = cle; LECTURE = r.lecture ? r : null;
  peindreFil(r);
  titreConv(r.titre);
  saisie.placeholder = r.lecture ? "Écris pour continuer avec Root…" : "Parle à Root…";
}

function viderFil() {
  interieur.style.transition = "opacity .35s, filter .35s"; interieur.style.opacity = 0; interieur.style.filter = "blur(8px)";
  setTimeout(() => { interieur.innerHTML = ""; interieur.style.opacity = 1; interieur.style.filter = "none"; }, 360);
}
function repartirDeZero() {
  viderFil(); LECTURE = null; CONV.actuelle = null; titreConv("");
  saisie.placeholder = "Parle à Root…";
}
function nouvelleConversation() { api() && api().nouvelle(); repartirDeZero(); toast("Nouvelle conversation"); }

// ── La palette ⌘K : cerveaux, conversations, actions, au clavier ─────────────
const voile = $("#palette-voile"), champ = $("#palette-champ"), listeP = $("#palette-liste");
let choixP = 0, visibles = [];
function entreesPalette(q) {
  const convs = (q ? CONV.liste : CONV.liste.slice(0, 5)).map(c => ({
    label: c.titre, aide: `${NOMS_SOURCES[c.source]} · ${quand(c.date)}`, icone: "bulle", faire: () => ouvrirConversation(c.cle) }));
  return [
    ...CERVEAUX.map(c => ({ label: `Penser avec ${c.nom}`, aide: c.fournisseur + (c.id === ACTIF ? " · actif" : ""), icone: "cerveau", faire: () => ouvrirCerveaux(c.id) })),
    { label: "Nouvelle conversation", aide: "Repartir de zéro", icone: "plus", kbd: "⌘N", faire: nouvelleConversation },
    { label: "Toutes les conversations", aide: "Par projet, de tous tes LLM", icone: "bulle", kbd: "⌘2", faire: () => ouvrirPanneau("conversations") },
    { label: "Mémoire", aide: "Ce que Root sait de toi", icone: "carnet", kbd: "⌘3", faire: () => ouvrirPanneau("memoire") },
    { label: "Outils", aide: "Ce que Root a le droit de faire", icone: "outils", kbd: "⌘4", faire: () => ouvrirPanneau("outils") },
    { label: "Terminal", aide: "Un vrai shell, tu tapes dedans", icone: "terminal", kbd: "⌘5", faire: ouvrirTerminal },
    ...convs,
  ];
}
function rendrePalette() {
  const q = normal(champ.value.trim());
  visibles = entreesPalette(q).filter(a => !q || normal(a.label + " " + a.aide).includes(q)).slice(0, 40);
  choixP = Math.min(choixP, Math.max(0, visibles.length - 1));
  listeP.innerHTML = visibles.map((a, i) =>
    `<button class="p-item${i === choixP ? " choisi" : ""}" data-i="${i}">${svg(a.icone)}<span>${echap(a.label)}</span><span class="p-aide">${echap(a.aide)}</span>${a.kbd ? `<kbd>${a.kbd}</kbd>` : ""}</button>`).join("");
  listeP.querySelectorAll(".p-item").forEach(el => {
    el.onmouseenter = () => { choixP = +el.dataset.i; rendrePalette(); };
    el.onclick = () => { const a = visibles[+el.dataset.i]; fermerPalette(); a.faire(); };
  });
}
function ouvrirPalette() { voile.hidden = false; champ.value = ""; choixP = 0; rendrePalette(); champ.focus(); }
function fermerPalette() { voile.hidden = true; saisie.focus(); }
voile.addEventListener("mousedown", e => { if (e.target === voile) fermerPalette(); });
champ.addEventListener("input", () => { choixP = 0; rendrePalette(); });
champ.addEventListener("keydown", e => {
  const n = Math.max(1, visibles.length);
  if (e.key === "ArrowDown") { choixP = (choixP + 1) % n; rendrePalette(); e.preventDefault(); }
  else if (e.key === "ArrowUp") { choixP = (choixP - 1 + n) % n; rendrePalette(); e.preventDefault(); }
  else if (e.key === "Enter" && visibles[choixP]) { e.preventDefault(); const a = visibles[choixP]; fermerPalette(); a.faire(); }
  else if (e.key === "Escape") { e.preventDefault(); fermerPalette(); }
});

// ── Clavier global : ⌘1 cerveaux, ⌘2 conversations, ⌘K palette, ⌘N nouvelle,
//    ⌘⏎ / esc autorisation ──────────────────────────────────────────────────
addEventListener("keydown", e => {
  const cmd = e.metaKey || e.ctrlKey;
  if (cmd && e.key.toLowerCase() === "k") { e.preventDefault(); voile.hidden ? ouvrirPalette() : fermerPalette(); return; }
  if (!voile.hidden) return;
  if (demandeOuverte && cmd && e.key === "Enter") { e.preventDefault(); demandeOuverte.trancher(true); return; }
  if (e.key === "Escape") {
    if (!menu.hidden) { e.preventDefault(); fermerMenu(); return; }
    if (demandeOuverte) { e.preventDefault(); demandeOuverte.trancher(false); return; }
    if (PANNEAU) { e.preventDefault(); fermerPanneau(); return; }
    if (TERM_OUVERT) { e.preventDefault(); fermerTerminal(); return; }
  }
  if (cmd && e.key === "1") { e.preventDefault(); frapper($("#ic-cerveaux")); basculer("cerveaux"); return; }
  if (cmd && e.key === "2") { e.preventDefault(); frapper($("#ic-conversations")); basculer("conversations"); return; }
  if (cmd && e.key === "3") { e.preventDefault(); frapper($("#ic-memoire")); basculer("memoire"); return; }
  if (cmd && e.key === "4") { e.preventDefault(); frapper($("#ic-outils")); basculer("outils"); return; }
  if (cmd && e.key === "5") { e.preventDefault(); frapper($("#ic-terminal")); basculerTerminal(); return; }
  if (cmd && e.key.toLowerCase() === "n") { e.preventDefault(); nouvelleConversation(); }
});

// ── Le vrai terminal (xterm + shell PTY) ─────────────────────────────────────
let TERM = null, FIT = null, TERM_OUVERT = false, termPret = false;
const vueTerm = $("#terminal"), hoteTerm = $("#terminal-hote");

function construireTerminal() {
  TERM = new Terminal({
    fontFamily: 'ui-monospace, "SF Mono", Menlo, monospace', fontSize: 13, lineHeight: 1.25,
    cursorBlink: true, allowProposedApi: true, scrollback: 5000,
    theme: {
      background: "rgba(0,0,0,0)", foreground: "#e7efec", cursor: "#6fd4b6", cursorAccent: "#0b0f0e",
      selectionBackground: "rgba(111,212,182,.3)",
      black: "#0b0f0e", red: "#f0866a", green: "#6fd4b6", yellow: "#f0b35a", blue: "#7fb8e6",
      magenta: "#a990f2", cyan: "#5fd6c6", white: "#cdd6d2",
      brightBlack: "#5a6460", brightGreen: "#8ff0d2", brightYellow: "#ffcf8f", brightWhite: "#ffffff",
    },
  });
  FIT = new FitAddon.FitAddon();
  TERM.loadAddon(FIT);
  try { TERM.loadAddon(new WebLinksAddon.WebLinksAddon()); } catch { /* lien web optionnel */ }
  TERM.open(hoteTerm);
  TERM.onData(d => api() && api().terminal_entree(btoa(unescape(encodeURIComponent(d)))));
  TERM.onResize(({ cols, rows }) => api() && api().terminal_taille(cols, rows));
  new ResizeObserver(() => { if (TERM_OUVERT) ajusterTerminal(); }).observe(hoteTerm);
}
function ajusterTerminal() {
  try { FIT.fit(); } catch { /* pas encore mesurable */ }
}
function termEcrire(b64) {
  if (!TERM) return;
  const octets = atob(b64), tab = new Uint8Array(octets.length);
  for (let i = 0; i < octets.length; i++) tab[i] = octets.charCodeAt(i);
  TERM.write(tab);
}
function termFin() { if (TERM) TERM.write("\r\n\x1b[2m[shell terminé — ↻ pour relancer]\x1b[0m\r\n"); termPret = false; }

async function ouvrirTerminal() {
  if (PANNEAU) fermerPanneau(false);
  if (!TERM) construireTerminal();
  vueTerm.hidden = false; TERM_OUVERT = true;
  document.body.classList.add("terminal");
  $("#ic-terminal").classList.add("ouvert");
  requestAnimationFrame(async () => {
    ajusterTerminal();
    if (!termPret && api()) {
      termPret = true;
      await api().terminal_demarrer(TERM.cols, TERM.rows);
    }
    TERM.focus();
  });
}
function fermerTerminal() {
  vueTerm.hidden = true; TERM_OUVERT = false;
  document.body.classList.remove("terminal");
  $("#ic-terminal").classList.remove("ouvert");
  lueur.classList.remove("on");
  saisie.focus();
}
const basculerTerminal = () => TERM_OUVERT ? fermerTerminal() : ouvrirTerminal();
$("#terminal-fermer").onclick = fermerTerminal;
$("#terminal-neuf").onclick = async () => {
  if (!api()) return;
  await api().terminal_arreter();
  TERM.reset();
  termPret = true;
  await api().terminal_demarrer(TERM.cols, TERM.rows);
  TERM.focus();
};

// ── Saisie ───────────────────────────────────────────────────────────────────
const saisie = $("#saisie");
function ajuster() { saisie.style.height = "auto"; saisie.style.height = Math.min(saisie.scrollHeight, 140) + "px"; }
saisie.addEventListener("input", ajuster);
function envoyer() {
  const texte = saisie.value.trim();
  if (!texte) return;
  if (LECTURE) passerEnReprise();                // écrire sous une conversation d'un autre outil = la reprendre
  if (!$("#titre-conv").textContent) titreConv(texte.length > 60 ? texte.slice(0, 59) + "…" : texte);
  ajouterToi(texte);
  saisie.value = ""; ajuster();
  api() && api().envoyer(texte);
}
$("#barre").addEventListener("submit", e => { e.preventDefault(); envoyer(); });
saisie.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey && !e.metaKey) { e.preventDefault(); envoyer(); }
});

// ── Démarrage ────────────────────────────────────────────────────────────────
dessinerSceau();
animerOnde();
construireDock();
window.addEventListener("pywebviewready", async () => {
  const d = await api().cerveaux();
  CERVEAUX = d.liste; ACTIF = d.actif;
  api().pret();
  chargerConversations();
});
saisie.focus();
