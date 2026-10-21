# Moteur de Root

Ce dossier contient les contributions vérifiées au harness Python de Root.
L’identité visuelle existante est conservée à la racine du dépôt.

## État réel

- `verification.py` : registre local des observations et contrôles de preuves.
- `autonomie.py` : plan vivant, budgets, reprises et critères de fin.
- `ame.md` : consignes révisées, sans dépendre d’outils encore absents.
- `test_verification.py` et `test_autonomie.py` : 63 tests passés hors réseau.
- `CONCEPTION-AUTONOMIE.md` : conception, réemploi, API et limites.
- `JOURNAL.md` : coordination et résultats, copie sans chemins personnels.

Les modules ne sont pas encore branchés à la boucle active. Le harness, le
navigateur et la sécurité restent sous la responsabilité de Claude ; la mémoire
et le contexte sous celle de Kimi K3. Les fichiers de ces axes seront ajoutés par
leurs auteurs après vérification. Aucun état privé ni conversation n’est inclus.

## Vérifier les modules

Depuis ce dossier, avec Python 3.14 (version utilisée pour les essais) :

```sh
python3 -B -m unittest test_autonomie test_verification
```

## Contrôles GitHub avant déploiement

Le workflow `Contrôles du moteur Root` vérifie séparément les tests locaux et
l’assemblage des fichiers sous `harness/`. Il ne lance ni Root, ni modèle cloud,
ni navigateur. Il ne charge aucun secret GitHub.

Le contrôle d’assemblage échoue si `root.py`, `navigateur.py` ou `securite.py`
restent à la racine, ou si les fichiers nécessaires manquent sous `harness/`.
Le passage des tests de modules ne démontre pas que le suivi des tâches et les
preuves sont raccordés à la boucle. Un essai fonctionnel isolé de cette intégration
reste nécessaire avant toute mise à jour du Root utilisé sur le Mac.

## Synchronisation entre IA

Pousser après chaque avancée réelle et testée. Chaque IA utilise son clone Git,
met le journal à jour et ajoute uniquement ses fichiers. Relire et intégrer les
nouveaux commits distants avant de pousser ; jamais de push forcé. Ne pas copier
le dossier de travail entier : exclure clés, fichiers d’environnement, données,
conversations, bases locales et sauvegardes. Les documents publiés ne contiennent
pas de noms personnels ni de chemins de compte local.
