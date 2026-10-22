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
- `README-MOTEUR.md`, `CONCEPTION-*.md`, `JOURNAL.md`, `CANAL.md` : la conception et
  la coordination des agents.

## Le dock

Une icône = un panneau. Faits : **Cerveaux** (⌘1), **Conversations** (⌘2) et **Mémoire** (⌘3).
À venir, un par un : Outils, Âme, Actions, Réglages, et Comparer.

**Conversations** rassemble celles de Root, Claude Code, Codex et Hermes
(`conversations.py`), rangées par projet, cherchables dans tout leur texte. Les
fichiers des autres outils sont seulement lus ; titres, projets et épingles vivent
dans `~/.local/root-conversations/meta.json`. Une conversation d'un autre outil
s'ouvre en lecture : « Continuer avec Root » ou « Rouvrir » dans son outil.

**Mémoire** montre les faits durables de Root par catégorie (`memoire_edition.py`
par-dessus les règles de `memoire.py`) : ajouter, modifier, oublier, avec la jauge
du plafond et celle de la conversation en cours. Quand Root retient un fait seul,
une notification propose d'annuler. `memoire.md` reste hors de GitHub.

Raccourcis : ⌘1 cerveaux, ⌘2 conversations, ⌘3 mémoire, ⌘K palette, ⌘N nouvelle conversation, ⌘⏎ / esc pour
autoriser ou refuser une action de Root.

## Tests

```sh
~/.local/root-venv/bin/python -m unittest discover -p "test_*.py"
```

457 tests au 22/10/2026, hors réseau.
