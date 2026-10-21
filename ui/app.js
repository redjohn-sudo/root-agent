// Root — vie de l'interface : le dock (une icône = un panneau), le fil, les
// autorisations, et le pont vers le moteur Python (window.pywebview.api / window.rootEvent).
"use strict";

const api = () => (window.pywebview && window.pywebview.api) || null;
const $ = s => document.querySelector(s);

// ── Icônes (traits 1.6, dessinées pour Root) ─────────────────────────────────
const ICONES = {
  cerveau: '<path d="M9 4.5a3 3 0 0 0-3 3v.3a3 3 0 0 0-1.5 5.2A3 3 0 0 0 9 17.6V19.5h1.5V4.5zM15 4.5a3 3 0 0 1 3 3v.3a3 3 0 0 1 1.5 5.2 3 3 0 0 1-4.5 4.6v1.9h-1.5V4.5z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
};
const svg = nom => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${ICONES[nom]}</svg>`;

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
}

function toast(texte, ok = true) {
  const t = document.createElement("div");
  t.className = "toast verre" + (ok ? "" : " ko"); t.textContent = texte;
  $("#toasts").appendChild(t);
  setTimeout(() => { t.classList.add("sort"); setTimeout(() => t.remove(), 450); }, 2600);
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
  }
};

// ── Le dock : une icône = un panneau ─────────────────────────────────────────
const lueur = $("#dock-lueur"), bulle = $("#bulle");
const ICONES_DOCK = [
  { id: "cerveaux", label: "Cerveaux", icone: "cerveau", kbd: "⌘1", ouvrir: () => basculerPanneau() },
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

// ── Panneau « Cerveaux » ─────────────────────────────────────────────────────
const panneau = $("#panneau"), liste = $("#cerveaux-liste");
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
  if (repartir) viderFil();
  fermerPanneau();
}
async function sonderTout() {
  SONDES = {}; rendreCerveaux();
  if (!api()) return;
  SONDES = await api().sonder_cerveaux();
  liste.querySelectorAll(".cerveau").forEach(el => { el.querySelector(".c-sonde").innerHTML = sonde(el.dataset.id); });
}
function ouvrirPanneau(choixId) {
  panneau.classList.add("ouvert"); panneau.setAttribute("aria-hidden", "false");
  const b = $("#ic-cerveaux"); b.classList.add("ouvert"); survolLueur(b);
  rendreCerveaux(); sonderTout();
  if (choixId && choixId !== ACTIF) {
    const el = liste.querySelector(`.cerveau[data-id="${choixId}"]`);
    if (el) { conversationEntamee() ? el.classList.add("choix") : choisir(choixId, false); el.scrollIntoView({ block: "nearest" }); }
  }
}
function fermerPanneau() {
  panneau.classList.remove("ouvert"); panneau.setAttribute("aria-hidden", "true");
  $("#ic-cerveaux").classList.remove("ouvert"); lueur.classList.remove("on");
  saisie.focus();
}
function basculerPanneau() { panneau.classList.contains("ouvert") ? fermerPanneau() : ouvrirPanneau(); }
$("#pan-fermer").onclick = fermerPanneau;
$("#puce-cerveau").onclick = () => ouvrirPanneau();
document.addEventListener("mousedown", e => {
  if (panneau.classList.contains("ouvert") && !panneau.contains(e.target) && !$("#dock").contains(e.target)
      && !e.target.closest("#puce-cerveau")) fermerPanneau();
});

function viderFil() {
  interieur.style.transition = "opacity .35s, filter .35s"; interieur.style.opacity = 0; interieur.style.filter = "blur(8px)";
  setTimeout(() => { interieur.innerHTML = ""; interieur.style.opacity = 1; interieur.style.filter = "none"; }, 360);
}
function nouvelleConversation() { api() && api().nouvelle(); viderFil(); toast("Nouvelle conversation"); }

// ── La palette ⌘K : changer de cerveau au clavier ───────────────────────────
const voile = $("#palette-voile"), champ = $("#palette-champ"), listeP = $("#palette-liste");
let choixP = 0, visibles = [];
function entreesPalette() {
  return [...CERVEAUX.map(c => ({ label: `Penser avec ${c.nom}`, aide: c.fournisseur + (c.id === ACTIF ? " · actif" : ""), icone: "cerveau", faire: () => ouvrirPanneau(c.id) })),
          { label: "Nouvelle conversation", aide: "Repartir de zéro", icone: "plus", kbd: "⌘N", faire: nouvelleConversation }];
}
function rendrePalette() {
  const q = champ.value.trim().toLowerCase();
  visibles = entreesPalette().filter(a => !q || (a.label + " " + a.aide).toLowerCase().includes(q));
  choixP = Math.min(choixP, Math.max(0, visibles.length - 1));
  listeP.innerHTML = visibles.map((a, i) =>
    `<button class="p-item${i === choixP ? " choisi" : ""}" data-i="${i}">${svg(a.icone)}<span>${a.label}</span><span class="p-aide">${a.aide}</span>${a.kbd ? `<kbd>${a.kbd}</kbd>` : ""}</button>`).join("");
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

// ── Clavier global : ⌘1 cerveaux, ⌘K palette, ⌘N nouvelle, ⌘⏎ / esc autorisation ──
addEventListener("keydown", e => {
  const cmd = e.metaKey || e.ctrlKey;
  if (cmd && e.key.toLowerCase() === "k") { e.preventDefault(); voile.hidden ? ouvrirPalette() : fermerPalette(); return; }
  if (!voile.hidden) return;
  if (demandeOuverte && cmd && e.key === "Enter") { e.preventDefault(); demandeOuverte.trancher(true); return; }
  if (e.key === "Escape") {
    if (demandeOuverte) { e.preventDefault(); demandeOuverte.trancher(false); return; }
    if (panneau.classList.contains("ouvert")) { e.preventDefault(); fermerPanneau(); return; }
  }
  if (cmd && e.key === "1") { e.preventDefault(); frapper($("#ic-cerveaux")); basculerPanneau(); return; }
  if (cmd && e.key.toLowerCase() === "n") { e.preventDefault(); nouvelleConversation(); }
});

// ── Saisie ───────────────────────────────────────────────────────────────────
const saisie = $("#saisie");
function ajuster() { saisie.style.height = "auto"; saisie.style.height = Math.min(saisie.scrollHeight, 140) + "px"; }
saisie.addEventListener("input", ajuster);
function envoyer() {
  const texte = saisie.value.trim();
  if (!texte) return;
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
});
saisie.focus();
