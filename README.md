# Root Terminal

La fenêtre de Root : un terminal qui n'en est pas un. Une vraie app macOS, peinte en
HTML/CSS/JS et personnalisable de A à Z, branchée sur le harness Python de Root
(même boucle, mêmes 36 outils, même mémoire, mêmes gardes de sécurité).

## Lancer

```sh
~/.local/root-venv/bin/python fenetre.py     # la fenêtre
~/.local/root-venv/bin/python root.py        # le même Root, dans le terminal
```

Installation des dépendances : voir `INSTALL.md` (plus `pywebview` pour la fenêtre).

## Ce qu'il y a

- `fenetre.py` : la fenêtre (pywebview / WebKit) et le pont vers le moteur.
  `root.un_tour` passe par un objet « écran » : `EcranTerminal` ou `EcranFenetre`.
- `ui/` : l'interface (`index.html`, `style.css`, `app.js`), le fond (`fond.jpg`,
  Unsplash, licence libre) et les actions (`actions.json`, `actions.exemple.json`).
- `cerveaux.json` + `cerveaux.py` : les LLM interchangeables (DeepSeek, Nebius :
  Kimi K3, GLM-5.3, Qwen3.8, gpt-oss). Aucune clé dans le fichier, seulement le
  nom de la variable qui la contient. Outils et vision mesurés le 21/10/2026.
- `root.py` et ses modules : le harness (mémoire de Kimi K3, autonomie et
  vérification de Codex, recherche de Claude cloud, action, sécurité, lecture,
  immunité, consentement, entendre de Claude Code).
- `pentest_journal.py` + panneau Pentest (⌘6) : lancer une campagne d'attaques
  contre un cerveau depuis la fenêtre, répéter N fois, et garder la trace durable
  (cible, attaques, méthode, résultats) dans `~/.local/root-pentest.db`. Onglets
  Lancer / Historique / Failles (taux de réussite d'attaque par type). Un
  « mandat de test » (system prompt, modifiable) cadre le modèle attaquant pour
  qu'il sache travailler dans un test autorisé ; il n'est jamais envoyé à la cible.
- `redteam.py` : le cœur de red team IA (probe / detector / generator / harnais,
  façon garak). Probes de base (fuite de prompt, injection directe et indirecte,
  encodage, jeu de rôle), detectors (canari, chaîne, refus, juge LLM), et chargeurs
  de règles YAML (promptmap) et de corpus (jailbreak_llms). Attaque un vrai cerveau
  de Root et sort un rapport chiffré. Usage sur cibles autorisées seulement.
  Feuille de route complète : `CONCEPTION-REDTEAM.md`.
- `README-MOTEUR.md`, `CONCEPTION-*.md`, `JOURNAL.md`, `CANAL.md` : la conception et
  la coordination des agents.

## Le dock

Une icône = un panneau. Faits : **Cerveaux** (⌘1), **Conversations** (⌘2), **Mémoire** (⌘3), **Outils**
(⌘4), **Terminal** (⌘5) et **Pentest** (⌘6). À venir : Âme, Actions, Réglages, Comparer.

**Terminal** (`terminal_shell.py` + `ui/vendor/xterm.js`) : un vrai shell (PTY)
dans la fenêtre, où Vincent tape ses commandes, comme dans Ghostty. Rien à voir
avec l'outil `terminal` du cerveau : ici le harness ne lit pas l'entrée et ne
l'envoie nulle part, ça reste entre le PTY et l'affichage.

**Outils** (`outils_reglages.py`) : les outils par famille (repliées par défaut,
avec une recherche), chacun avec son risque. On coupe un outil (il n'est plus
proposé au cerveau), on le rend plus strict (toujours demander), on choisit
l'autonomie et des préréglages. Option éteinte par défaut, « commandes sans
confirmation » : Vincent liste les préfixes de commandes terminal qui tournent
sans accord en autonomie large, pour ses labos et ses CTF.

**Mes outils** : Vincent déclare ses propres outils (une commande locale, ou un
dépôt GitHub qu'il a installé). Il colle un lien, Root lit le README pour préparer
une fiche, Vincent complète et valide ; rien ne s'installe ni ne s'exécute tout
seul. L'outil passe ensuite par les mêmes autorisations que les autres. Les règles
de sécurité du moteur ne sont jamais affaiblies : on n'ajoute ou ne retire que des
demandes, sur décision explicite.

**Conversations** rassemble celles de Root, Claude Code, Codex et Hermes
(`conversations.py`), rangées par projet, cherchables dans tout leur texte. Les
fichiers des autres outils sont seulement lus ; titres, projets et épingles vivent
dans `~/.local/root-conversations/meta.json`. Une conversation d'un autre outil
s'ouvre en lecture : « Continuer avec Root » ou « Rouvrir » dans son outil.

**Mémoire** montre les faits durables de Root par catégorie (`memoire_edition.py`
par-dessus les règles de `memoire.py`) : ajouter, modifier, oublier, avec la jauge
du plafond et celle de la conversation en cours. Quand Root retient un fait seul,
une notification propose d'annuler. `memoire.md` reste hors de GitHub.

Raccourcis : ⌘1 cerveaux, ⌘2 conversations, ⌘3 mémoire, ⌘4 outils, ⌘5 terminal, ⌘6 pentest, ⌘K palette, ⌘N nouvelle conversation, ⌘⏎ / esc pour
autoriser ou refuser une action de Root.

## En faire une app (Root.app)

```sh
python3 paquet/faire_icone.py paquet/icone.png   # l'icône (Pillow)
bash paquet/faire_app.sh                          # monte paquet/Root.app
```

`Root.app` est une vraie app macOS : double-clic, icône, Dock, Applications.
Son lanceur appelle le venv et le code en place (`~/.local/root-venv`,
`~/Projets/root-harness`), donc tes mises à jour de code sont prises sans
reconstruire. `Root.icns` est versionné ; refaire l'icône demande Pillow.
Les logs de l'app vont dans `~/.local/root-app.log`.

## Tests

```sh
~/.local/root-venv/bin/python -m unittest discover -p "test_*.py"
```

503 tests au 22/10/2026, hors réseau.
