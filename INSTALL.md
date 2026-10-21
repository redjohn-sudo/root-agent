# Installer Root

Root est un harness d'agent en Python, pour macOS. Rien de personnel ni de secret
ne vit dans ce dépôt : les clés se posent en local (voir plus bas).

## 1. Dépendances système (Homebrew)

- Python 3.14 : `brew install python@3.14`
- cliclick (clics/frappes système, action hors navigateur) : `brew install cliclick`
- ffmpeg (capture d'écran réduite, images de vidéo) : `brew install ffmpeg`
- Brave Browser (pilotage web via CDP) : installer depuis brave.com

## 2. Environnement Python

```sh
python3.14 -m venv ~/.local/root-venv
~/.local/root-venv/bin/pip install -r harness/requirements.txt
```

## 3. Clés — jamais dans le dépôt

Dans `~/.hermes/profiles/racine/.env` (une ligne par clé) :

- `DEEPSEEK_API_KEY=...`  — cerveau par défaut (DeepSeek, API OpenAI-compatible)
- `ANTHROPIC_API_KEY=...` — optionnel, pour faire tourner Root sur Claude (`CERVEAU = "claude"` dans root.py)
- `BRAVE_SEARCH_API_KEY=...` — optionnel, recherche web générale ; sans elle, Root cherche via Wikipédia et ses références

## 4. Lancer

```sh
~/.local/root-venv/bin/python harness/root.py
```

Au premier usage, macOS demande d'autoriser le terminal (Ghostty) pour
« Enregistrement de l'écran » (capture) et « Accessibilité » (clics/frappes),
dans Réglages Système > Confidentialité et sécurité. Sans ces autorisations,
la capture et l'action système restent sans effet.

## Dépendances facultatives selon les axes

- La recherche (`recherche.py`) et la mémoire (`memoire.py`) n'utilisent que la
  bibliothèque standard.
- Le pilotage navigateur a besoin de `websocket-client` (dans requirements) et de
  Brave installé.
