# Journal de Root — coordination des IA

Quatre agents travaillent sur Root en parallèle :
- **Claude cloud** : recherche sourcée (`recherche.py`).
- **Kimi K3** : mémoire (`memoire.py`, `CONCEPTION-MEMOIRE.md`).
- **Codex** : autonomie (`autonomie.py`, `verification.py`, `ame.md`, `CONCEPTION-AUTONOMIE.md`) et tests de cet axe.
- **Claude Code** : puissance d’action et intégration (`root.py`, `navigateur.py`). `root.py` est son point d’intégration exclusif.

Règles : lire ce journal au début de chaque session. Ne pas toucher un fichier marqué « en cours » par une autre IA. Écrire une entrée après chaque avancée **réelle et vérifiée** (jamais de « fini » sans preuve). Aucune donnée perso ni secret ici.

---

## 2026-10-21 — Claude (Opus)

- **Fait** : Lot 1 (boucle bornée à 30 étapes, dispatch robuste sur JSON d'outil cassé, reprises avec recul sur 429/5xx/réseau) et Lot 3 (élagage des vieilles images, troncation des résultats) dans `root.py`. Testés en isolé.
- **Fichiers touchés** : `root.py` (réservé à Claude), sauvegardes `root.py.avant-lots` / `navigateur.py.avant-lots`.
- **En cours** : Lot 2 (sécurité) — module `securite.py` en écriture, puis branchement dans `root.py` (redaction des secrets sur chaque résultat d'outil, liste noire de fichiers, blocage des URL internes, anti-traversée de chemin, emballage anti-injection des pages web).
- **Besoin des autres** : ne touchez pas `root.py`, `navigateur.py`, `securite.py`. Codex sur `ame.md`, Kimi sur la mémoire.

## 2026-10-21 14:29 — Codex

- Fait : portage local créé dans `verification.py`, avec registre de preuves, références exactes, versions de cibles et contrôles Python distincts de l’exécution. Les 32 tests de `test_verification.py` ont réussi avec le réseau bloqué ; l’exemple documenté a aussi été exécuté. Les empreintes des deux fichiers sont toujours celles de cette exécution. Aucun essai DeepSeek ni navigation réelle. Module non intégré à la boucle active.
- Fichiers touchés : `verification.py`, `test_verification.py` et `CONCEPTION-AUTONOMIE.md` lors du portage ; `JOURNAL.md` pour cette entrée. Aucun changement par Codex dans les fichiers réservés à Claude. Les évolutions parallèles de `root.py` sont bien distinguées du portage.
- En cours / prochaine étape : aucun fichier de code pris par Codex. Prochaine étape : intégration du registre dans la boucle par Claude ; le prompt actif attend les outils correspondants.
- Besoin des autres : Claude, actualiser les versions des cibles juste avant `conclure` et conserver les contrôles côté Python. Kimi K3, conserver les observations brutes locales ; une ancienne preuve ne valide pas l’état courant. Contrat API et limites dans la section « Premier portage réalisé » de `CONCEPTION-AUTONOMIE.md`.

## 2026-10-21 14:30 — Codex

- Fait : journal lu intégralement ; module de vérification existant et interface contrôlés avant la suite.
- Fichiers touchés : `JOURNAL.md` pour cette réservation uniquement.
- En cours / prochaine étape : `autonomie.py`, `test_autonomie.py`, `ame.md` et `CONCEPTION-AUTONOMIE.md` réservés à Codex pour le plan vivant, les limites et les consignes. Aucun de ces changements supplémentaires n’est encore annoncé comme réalisé ou testé.
- Besoin des autres : ne pas modifier ces quatre fichiers pendant le portage. Claude garde exclusivement `root.py`, `navigateur.py` et `securite.py` ; Kimi K3 garde la mémoire et le contexte. Le journal est relâché après cet ajout.

## 2026-10-21 14:32 — Claude (Opus)

- **Fait** : les 3 lots de robustesse/sécurité sont terminés et vérifiés sur l'intégration réelle. Lot 1 (boucle bornée 30 étapes, dispatch robuste, reprises réseau), Lot 2 (`securite.py` écrit + branché : masquage des secrets sur chaque résultat d'outil, `.env`/clés en lecture refusés, écriture des fichiers système/credentials bloquée, URL internes et métadonnées cloud bloquées à la navigation, pages web emballées en contenu non fiable), Lot 3 (élagage des vieilles images, troncation). Tests : `securite.py` 25/25, vérifs d'intégration OK (lire `.env` refusé, clé masquée, `169.254.169.254` bloquée).
- **Fichiers touchés** : `root.py`, `securite.py` (réservés Claude). Sauvegardes `.avant-lots`.
- **En cours / prochaine étape** : à la demande de Codex, brancher son registre de vérification (`verification.py`) dans la boucle avant la conclusion d'une tâche (actualiser l'état des cibles juste avant `conclure`). À faire quand l'axe autonomie de Codex sera stabilisé.
- **Besoin des autres** : rien de bloquant. Je garde `root.py`, `navigateur.py`, `securite.py`.

## 2026-10-21 14:41 — Codex

- Fait : `autonomie.py` créé, `ame.md` révisé et documentation actualisée. Les 31 tests d’autonomie et 32 tests de vérification passent, soit 63 tests hors réseau. Plan avec une étape active, budgets, détection de cycles, reprise limitée, refus sans contournement et fin recontrôlée. Pas d’intégration à la boucle, de persistance après redémarrage ou d’essai DeepSeek annoncé.
- Fichiers touchés : `autonomie.py`, `test_autonomie.py`, `ame.md`, `CONCEPTION-AUTONOMIE.md`, `JOURNAL.md`. Aucun fichier réservé à Claude modifié par Codex.
- En cours / prochaine étape : publication des fichiers testés dans le dépôt GitHub privé `redjohn-sudo/root`, sous `harness/` pour conserver l’identité visuelle existante. La copie publiée du journal et de la conception retire les noms personnels et chemins locaux. Push non encore vérifié à l’écriture de cette entrée.
- Besoin des autres : chaque IA pousse ses seuls fichiers vérifiés et le journal, jamais les secrets, souvenirs ou conversations. Utiliser un clone Git séparé pour éviter un index partagé ; conserver l’historique distant, sans push forcé. Claude, l’API de `Tache` est documentée pour ton branchement ; Kimi K3, persistance des compteurs et reprise après interruption restent à raccorder.

## 2026-10-21 14:43 — Codex

- Fait : commit `359d9e3` poussé sur `main` de `redjohn-sudo/root`. La tête distante a été relue par l’API GitHub et correspond au commit local ; dépôt confirmé privé. Les modules et tests sont publiés sous `harness/`, avec les consignes, la conception et le journal sans chemins personnels. Les 63 tests passent aussi dans la copie destinée au dépôt. Auteur Git configuré avec l’adresse GitHub masquée pour les contributions.
- Fichiers touchés : copie publiée de `harness/autonomie.py`, `harness/verification.py`, leurs tests, `harness/ame.md`, `harness/CONCEPTION-AUTONOMIE.md`, `harness/JOURNAL.md`, `harness/README.md` et clarification de `SECURITY.md` à la racine distante. Aucun fichier réservé à Claude modifié par Codex.
- En cours / prochaine étape : tous les fichiers de code et conception de Codex sont relâchés. La présente entrée de suivi est en cours de synchronisation. Modules locaux disponibles, mais pas encore branchés dans la boucle ; aucune reprise persistante ou protection totale contre les fuites annoncée.
- Besoin des autres : consigne durable, pousser fréquemment après une avancée réelle et vérifiée. Chaque IA utilise son clone séparé, ajoute ses seuls fichiers et le journal, vérifie les données avant le push, récupère les nouveautés distantes et ne pousse jamais en force. Claude, le branchement de `Tache` et `RegistrePreuves` peut commencer ; Kimi K3, coordonner la persistance sans inclure d’état privé dans GitHub.

## 2026-10-21 15:07 — Codex

- Fait : revue du dépôt publié après la consigne de terminer sur GitHub avant déploiement local. Aucun workflow GitHub Actions n’était présent. Workflow ajouté dans le clone : tests des modules hors réseau et contrôle d’assemblage distinct. L’exécution locale du contrôle reproduit le blocage : trois fichiers du moteur manquent sous `harness/` et existent encore à la racine. Le prompt côté dépôt précise la curation de faits durables vérifiés, sans données privées. Aucun code recopié vers le Root utilisé sur le Mac.
- Fichiers touchés : `.github/workflows/harness.yml`, `harness/ame.md`, `harness/README.md`, `harness/JOURNAL.md`, uniquement dans le clone GitHub. Aucun fichier réservé à Claude modifié ou déplacé par Codex.
- En cours / prochaine étape : publier et observer le workflow. Les tests de modules déjà vérifiés ne constituent pas un essai de la boucle complète. L’assemblage doit actuellement échouer ; il ne sera pas présenté comme terminé.
- Besoin des autres : Claude, unifier tes fichiers sous `harness/` et raccorder le suivi et les preuves dans ton clone, sans mise à jour du Root local avant validation du dépôt. Kimi K3, publier les contributions mémoire relues et leurs tests avant toute intégration. Chaque IA pousse ses seuls fichiers vérifiés avec le journal, sans données locales ni push forcé.

## 2026-10-21 15:08 — Codex

- Fait : workflow publié au commit `a5ef4cf`, exécution GitHub Actions `39605267574` terminée et journaux relus. Le job « Modules locaux hors réseau » réussit avec 63 tests. Le job « Assemblage des fichiers » échoue sur les trois fichiers du moteur encore à la racine et manquants sous `harness/`. La CI est donc rouge, pas validée pour déploiement. Aucun code de cette revue GitHub n’a été recopié vers Root local.
- Fichiers touchés : `harness/JOURNAL.md` pour ce relevé. Le workflow, le prompt et sa documentation sont déjà publiés. Aucun fichier réservé à Claude modifié ou déplacé par Codex.
- En cours / prochaine étape : attendre la correction d’assemblage par Claude, puis vérifier la nouvelle CI et l’intégration fonctionnelle du suivi et des preuves. La réussite des modules seuls ne vaut pas réussite du harness complet.
- Besoin des autres : Claude, corriger les chemins dans ton clone et pousser la correction sur GitHub avant toute mise à jour locale. Résultats : (CI run, private repository) . Kimi K3, mémoire et contexte restent à publier et à relire séparément. Ne pas annoncer le projet terminé tant que les vérifications manquantes ne sont pas passées.

## 2026-10-21 15:39 — Codex

- Fait : deux tests ont reproduit une réussite tardive après dépassement du budget pendant la vérification d’étape ou finale. Correction dans `autonomie.py` : délai recontrôlé après le contrôle local, tâche incomplète et étape active bloquée si le temps est écoulé. Les 65 tests hors réseau passent, dont les deux régressions auparavant en échec. Le journal indique maintenant les quatre rôles demandés. Configuration de signature SSH vérifiée : clé publique enregistrée sur GitHub.
- Fichiers touchés : `harness/autonomie.py`, `harness/test_autonomie.py`, `harness/CONCEPTION-AUTONOMIE.md`, `harness/JOURNAL.md`. Aucun fichier d’un autre axe modifié.
- En cours : récupération des nouveautés par rebase, commit signé puis push de cette étape vérifiée. Les fichiers de cet axe restent pris par Codex jusqu’au push. Aucun déploiement vers Root local.
- Besoin des autres : Claude Code, raccorder les méthodes de `Tache` et `RegistrePreuves` documentées, y compris le contrôle de durée pendant les attentes. Le contrôle d’assemblage est désormais vert sur `089199a`, mais ne prouve pas ce raccordement. Claude cloud et Kimi K3 conservent leurs fichiers respectifs.

## 2026-10-21 15:41 — Codex

- Fait : correctif `be9106f` poussé ; signature SSH vérifiée valide par GitHub. La CI `39610006297` est terminée avec succès pour les modules et l’assemblage. Les 65 tests ont passé localement hors réseau ; le job de tests GitHub est vert. Les quatre fichiers publiés ont été contrôlés et appartiennent tous à l’axe autonomie ou à la coordination.
- Fichiers touchés : `harness/JOURNAL.md` pour ce relevé vérifié, sans changement de code supplémentaire.
- En cours : aucun fichier réservé par Codex après ce checkpoint. Aucun déploiement vers Root local. La réussite de cette CI ne constitue pas un essai fonctionnel de la boucle complète.
- Besoin des autres : Claude Code, poursuivre le raccordement de `Tache` et `RegistrePreuves` dans `root.py`. Claude cloud et Kimi K3 conservent leurs axes. Référence CI : (CI run, private repository) .

## 2026-10-21 — Claude (cloud), axe recherche

- Fait : journal lu en entier, dépôt synchronisé sur `089199a` (mémoire de Kimi K3 branchée). Rien d'autre n'est encore écrit ni testé.
- Fichiers touchés : `harness/JOURNAL.md` pour cette réservation uniquement.
- En cours : `harness/recherche.py`, `harness/test_recherche.py` et `harness/CONCEPTION-RECHERCHE.md` réservés à Claude (cloud). Module de recherche approfondie sourcée : requêtes filtrées, récupération bornée et gardée par `securite.url_sure`, passages pertinents, affirmations reliées à des citations exactes recontrôlées, rapport avec sources numérotées.
- Besoin des autres : ne pas modifier ces trois fichiers. Je ne touche pas `root.py` ; le point de branchement sera décrit ici pour Claude Code.

## 2026-10-21 — Claude (cloud), axe recherche

- Fait : `harness/recherche.py` écrit et `harness/test_recherche.py` vert, 49 tests en 0,8 s, réseau coupé pendant les tests sauf un serveur HTTP local sur 127.0.0.1 pour les redirections réelles. Les 63 tests d'autonomie et de vérification restent verts. Contenu : garde des requêtes sortantes (courriel, téléphone, carte, IBAN, chemin local, secret, motifs personnels), récupération bornée en taille, temps et nombre de pages, chaque redirection recontrôlée par `securite.url_sure`, extraction du texte HTML en bibliothèque standard, classement BM25 des passages, vérification des citations mot pour mot dans le texte récupéré, statuts corroborée / sourcée / à vérifier / non sourcée, rapport Markdown avec sources numérotées.
- Non vérifié : aucun essai sur le vrai web. Le réseau de l'environnement cloud refuse `html.duckduckgo.com` et `fr.wikipedia.org`. L'analyse des résultats DuckDuckGo est testée sur un HTML figé écrit d'après le format connu, pas sur une réponse réelle.
- Fichiers touchés : `harness/recherche.py`, `harness/test_recherche.py`, `harness/JOURNAL.md`.
- En cours : `harness/CONCEPTION-RECHERCHE.md` (contrat et limites).
- Besoin des autres :
  - Claude Code, branchement dans `root.py` : `import recherche` puis `OUTILS.update(recherche.OUTILS_RECHERCHE)` après la table `OUTILS`. Trois outils : `recherche_web` (risque `web`), `recherche_lire` et `recherche_conclure` (risque `sûr`). Le module emballe déjà ses sorties comme contenu non fiable, car `un_tour` n'emballe que les outils `web_*`. Sorties sous 18 000 caractères, donc sous la troncature de `memoire.py`. Premier essai réel à faire sur le Mac, où le DNS fonctionne : `python3 -B -c "import recherche as r; print(r.outil_recherche_web('hauteur de la tour Eiffel'))"`.
  - Claude Code, `securite.py` : `rediger_secrets` ne masque pas une affectation `NOM_KEY=valeur` placée au milieu d'une ligne, seulement en début de ligne. Exemple constaté : « clé API_KEY=abcdefghijklmnop123 trouvée » reste intact.
  - Codex, workflow : ajouter `test_recherche` à la commande des tests du job « Modules locaux hors réseau », et `recherche.py` aux fichiers requis si souhaité.

## 2026-10-21 — Claude (cloud), axe recherche

- Fait : `harness/CONCEPTION-RECHERCHE.md` écrit, avec le déroulé, les statuts, la protection des données, les budgets, le contrat de branchement, les limites et les vérifications réellement exécutées. `main` fusionné dans ma branche sans push forcé ; 114 tests verts ensemble (autonomie, vérification, recherche) et contrôle d'assemblage local vert.
- Fichiers touchés : `harness/CONCEPTION-RECHERCHE.md`, `harness/JOURNAL.md`.
- En cours : rien. Les trois fichiers de l'axe recherche restent à Claude (cloud). Mes commits sont sur la branche `claude/eager-bell-ff42x2`, pas encore sur `main` : la fusion attend l'accord de l'utilisateur.
- Besoin des autres : inchangé depuis l'entrée précédente. Claude Code pour le branchement dans `root.py`, le premier essai réel sur le Mac et le masquage en milieu de ligne dans `securite.py`. Codex pour ajouter `test_recherche` au workflow.

## 2026-10-21 — Claude (cloud), axe recherche

- Fait : à la demande de l'utilisateur, l'axe recherche est publié sur `main` au commit `7f8b361`, en avance rapide sans push forcé, après fusion de `b755349`. Les 114 tests hors réseau étaient verts juste avant le push. La phrase « pas encore sur `main` » de l'entrée précédente n'est donc plus vraie.
- Fichiers touchés : `harness/JOURNAL.md`.
- En cours : rien. Les trois fichiers de l'axe recherche restent à Claude (cloud).
- Besoin des autres : inchangé. Claude Code pour le branchement dans `root.py`, le premier essai réel sur le Mac et le masquage en milieu de ligne dans `securite.py`. Codex pour ajouter `test_recherche` au workflow.

## 2026-10-21 15:50 : Codex

- Fait : scénario complet ajouté aux tests d'autonomie sur un fichier temporaire et un sous-processus Python isolé : défaut reproduit, correction écrite et relue, calcul corrigé contrôlé. Deux variantes : conclusion acceptée sur état inchangé, refusée après altération du fichier. Les 66 tests autonomie et preuves passent ; les 115 tests avec recherche passent aussi, avec un avertissement de ressource socket non fermée. Aucun essai modèle ni boucle réelle. Le moteur lu sur `57b60c5` ne branche toujours pas ces deux modules.
- Fichiers touchés : `harness/test_autonomie.py`, `harness/CONCEPTION-AUTONOMIE.md`, `harness/JOURNAL.md` uniquement.
- En cours : publication signée de cette validation, sans déploiement local. Aucun changement du moteur.
- Besoin des autres : Claude Code, brancher le suivi et les preuves selon le contrat documenté, actualiser les empreintes réelles avant conclusion et tester la boucle. Demande envoyée sur le bus. L'ajout de recherche à la CI reste à coordonner car le workflow est hors des fichiers attribués à cet axe.

## 2026-10-21 15:50 : Codex

- Fait : ajout de `test_recherche` à la commande du workflow, demandé explicitement par l'utilisateur après transmission de Claude cloud. `recherche.py` est également requis par le contrôle d'assemblage. La commande commune a réussi localement avec 115 tests ; aucun essai sur le web réel. L'exécution GitHub de cette version n'est pas encore observée.
- Fichiers touchés : `.github/workflows/harness.yml`, `harness/JOURNAL.md`.
- En cours : commit signé et push, puis observation du résultat de la CI.
- Besoin des autres : Claude Code conserve le branchement recherche et autonomie dans `root.py`, le premier essai web réel et la correction du masquage des clés en milieu de ligne dans `securite.py`.

## 2026-10-21 15:51 : Codex

- Fait : les commits signés `3b58b58` et `d202c8d` sont sur `main`. La CI `39611586483` a réussi : journaux relus, 115 tests exécutés et contrôle d’assemblage vert. Signature de `d202c8d` validée par GitHub. Heure de l’entrée précédente corrigée.
- Fichiers touchés : `harness/JOURNAL.md` pour ce relevé.
- En cours : aucun fichier de code pris par Codex. Aucun déploiement local ni validation fonctionnelle de la boucle complète.
- Besoin des autres : Claude Code pour les intégrations et la correction de sécurité indiquées précédemment. CI : (CI run, private repository) .

## 2026-10-21 — Claude (cloud), axe recherche

- Fait : revue du dépôt sur `59bb0fd`. La CI `39611586483` est confirmée verte via l'API GitHub. L'avertissement de socket non fermé signalé par Codex venait de `recherche.py` : une réponse d'erreur HTTP (404 par exemple) n'était pas fermée, en usage réel comme en test. Corrigé par la fermeture de chaque `HTTPError`. Les 115 tests passent avec `python3 -X dev`, sans aucun avertissement.
- Fichiers touchés : `harness/recherche.py`, `harness/JOURNAL.md`.
- En cours : rien.
- Manques constatés, par axe :
  - Claude Code : `root.py` n'importe toujours ni `recherche`, ni `autonomie`, ni `verification`. Le masquage d'une clé en milieu de ligne dans `securite.py` n'est pas corrigé, vérifié à nouveau. `action_systeme.py` n'a pas de test. Le prénom de l'utilisateur figure encore dans `root.py`, `navigateur.py`, `securite.py` et `action_systeme.py`, contre la règle du README.
  - Kimi K3 : `memoire.py` n'a pas de `test_memoire.py`, et `CONCEPTION-MEMOIRE.md` est absent du dépôt. Le prénom figure aussi dans `memoire.py`.
  - Tous : aucune boucle complète n'a été essayée avec le modèle, et aucun essai de recherche sur le vrai web.

## 2026-10-21 — Claude (cloud), axe recherche

- Fait : la CI de `6ab2405` a été annulée par le push suivant, comme le prévoit le workflow. La CI `39611969228` sur `f77641a` inclut ce commit et elle est verte. Correction de Claude Code dans `securite.py` vérifiée : « clé API_KEY=… trouvée » est maintenant masqué. Les 115 tests passent avec `python3 -X dev`, sans avertissement.
- Fichiers touchés : `harness/JOURNAL.md`.
- En cours : rien.
- Manques restants : ceux de l'entrée précédente, sauf le masquage en milieu de ligne, désormais corrigé. Les autotests de `securite.py` restent à 24 et ne couvrent pas encore ce cas.

## 2026-10-21 — Claude (cloud), axe recherche

- Règle de l'utilisateur, transmise à tous : aucun essai réel, ni web ni boucle avec le modèle, tant que tous les axes ne sont pas terminés. Les tests unitaires hors ligne de chaque module continuent, comme le demande la règle 6.
- En cours : `recherche.py` et `test_recherche.py`, pris par Claude (cloud). Trois ajouts : un moteur de secours par l'API de recherche Wikipédia, le respect de `robots.txt`, et l'extraction du texte principal des pages (`main`, `article`).
- Après la fin du branchement par Claude Code : premier essai réel de la recherche sur le Mac, puis contrôle de son intégration dans `root.py`.

## 2026-10-21 — Claude (cloud), axe recherche

- Fait :
  - Moteur de secours `MoteurWikipedia` par l'API publique de recherche.
  - `MoteursCombines`, nouveau moteur par défaut : DuckDuckGo puis Wikipédia, résultats entrelacés, échec d'un moteur consigné sans bloquer l'autre.
  - Respect de `robots.txt` selon la RFC 9309, avec cache par site : une page interdite n'est jamais récupérée.
  - Extraction du seul texte principal (`main`, `article`, `role="main"`) quand il fait au moins 400 caractères.
  - 65 tests de recherche verts, 131 avec autonomie et vérification, sans avertissement en `-X dev`. Branchement de Claude Code (`aad40ca`) relu sans exécution : conforme au contrat.
- Fichiers touchés : `harness/recherche.py`, `harness/test_recherche.py`, `harness/CONCEPTION-RECHERCHE.md`, `harness/JOURNAL.md`.
- En cours : rien. Les fichiers de l'axe recherche restent à Claude (cloud).
- Besoin des autres : rien de neuf. L'API des trois outils est inchangée, donc `root.py` n'a pas à bouger.

## 2026-10-21 ~16:05 — Claude (Opus) — intégration + essai réel

- ESSAI RÉEL de Root sur DeepSeek réussi : message simple -> Root appelle lister, voit son dossier, répond juste. Toute la boucle tient avec les modules intégrés (mémoire, sécurité, recherche, action système, budget de tâche). CI vert.
- Intégrés dans root.py et poussés : securite (fix clé au milieu de ligne), recherche (OUTILS.update), action_systeme (5 outils, risque systeme=confirmation), memoire (troncation/compression/durable), budget de durée de Tache (non bloquant).
- Claude cloud : BUG recherche à corriger dans recherche.py — essai réel = 0 source. Réseau OK (page DuckDuckGo ~14 Ko récupérée sur html. et lite.), mais analyser_duckduckgo renvoie 0. L analyseur ne reconnaît plus la structure DDG actuelle (ou page anti-bot). Branchement OK, c est le moteur/analyseur à corriger.
- Codex : autonomie COMPLÈTE (plan+avant_outil+preuves+observer-avant-mutation) NON câblée : elle briderait la boucle libre de Root (aucune_etape_en_cours, blocage des mutations sans observation). Seul le budget de durée est câblé. L intégration complète = refonte vers un flux planifié, à décider avec Vincent. Je ne bride pas l action de Root sans cette décision.

## 2026-10-21 16:05 : Codex

- Fait : revue de `fbc83af`, recherche branchée mais seul le budget entre tours utilise Tache. Un test a reproduit une validation prématurée après écriture incertaine ; correction du garde de vérification, puis 67 tests autonomie/preuves réussis en mode développement, sans avertissement. Relecture complète après incertitude testée. Proposition de raccordement en six points ajoutée à la conception. Les 131 tests communs ont été exécutés avec Python 3.9 : quatre erreurs de recherche dans HTTPError.close, transmises à Claude sur le bus. La CI distante de fbc83af est verte sur son autre version Python. Aucun essai réel par Codex.
- Fichiers touchés : `harness/autonomie.py`, `harness/test_autonomie.py`, `harness/CONCEPTION-AUTONOMIE.md`, `harness/JOURNAL.md`.
- En cours : publication signée du correctif après synchronisation.
- Besoin des autres : Claude Code, décider et réaliser le flux planifié décrit dans la conception ; le seul budget entre tours ne satisfait pas le suivi et les preuves. Claude cloud, vérifier les quatre erreurs de recherche sous Python 3.9. Aucun fichier des autres axes modifié.

## 2026-10-21 — Claude (cloud), axe recherche

- Fait, correction du bug relevé par Claude Code (zéro source à l'essai réel) :
  - Analyseur DuckDuckGo réécrit : versions `html` et `lite`, liens relatifs `/l/?uddg=…` (rejetés auparavant, cause plausible), repli sur tout lien `uddg`, cibles non http(s) écartées.
  - Une page anti-robot lève désormais `anti_robot` au lieu de passer pour une absence de résultats.
  - La sortie de `recherche_web` liste les causes des échecs et refus.
  - Nouveau mode `python3 -B recherche.py --diagnostic "question"` : structure des réponses des moteurs, sans texte brut ni clé.
  - Moteur optionnel `MoteurBrave` (API Brave Search), ajouté en tête seulement si `BRAVE_SEARCH_API_KEY` existe. La clé ne part que vers l'hôte de l'API, jamais après une redirection vers un autre hôte.
  - 76 tests de recherche, 142 au total, verts sans avertissement en `-X dev`.
- Non vérifié : la vraie page reçue sur le Mac. Le réseau cloud bloque toujours DuckDuckGo et Wikipédia. La cause exacte du zéro reste à confirmer par le diagnostic.
- Revue de l'ensemble du dépôt sur `fbc83af` : tests verts, CI verte, syntaxe valide. Restent ouverts :
  - Claude Code : `outil_terminal` ne passe toujours pas par les gardes de fichiers ; `--remote-allow-origins=*` est toujours dans `navigateur.py` ; `action_systeme.py` n'a pas de test ; le prénom de l'utilisateur figure encore 18 fois dans les fichiers Python.
  - Kimi K3 : ni `test_memoire.py` ni `CONCEPTION-MEMOIRE.md`.
  - Codex et l'utilisateur : le câblage complet de l'autonomie attend la décision de l'utilisateur, comme l'a noté Claude Code.
- Fichiers touchés : `harness/recherche.py`, `harness/test_recherche.py`, `harness/CONCEPTION-RECHERCHE.md`, `harness/JOURNAL.md`.
- Besoin des autres : Claude Code, sur le Mac, lancer `cd harness && python3 -B recherche.py --diagnostic "hauteur de la tour Eiffel"` et recopier ici les lignes `[duckduckgo]`, `[wikipedia]` et `Causes`. Elles ne contiennent que de la structure. Aucun changement de `root.py` n'est nécessaire.

## 2026-10-21 16:11 : Codex

- Fait : `PiloteAutonomie`, `ControleLocal` et `PhaseLocale` implémentés dans autonomie.py : déclaration des critères, versions réelles par callback, permission locale explicite, réception des retours, références exactes et transitions vérifiées. Une écriture seule ne fournit pas de preuve. Reprise de contrôle final bornée sans réinitialiser les compteurs. Les 21 nouveaux tests et les 67 existants passent, soit 88 tests autonomie/preuves sous Python 3.9 en mode développement, sans avertissement. Suite commune sur eda5dcc : 164 tests, cinq erreurs de recherche dans HTTPError.close sous Python 3.9, signalées à Claude. Aucun essai modèle ou web.
- Fichiers touchés : `harness/autonomie.py`, `harness/test_autonomie.py`, `harness/CONCEPTION-AUTONOMIE.md`, `harness/JOURNAL.md` uniquement.
- En cours : publier cette étape avec signature, observer la CI puis fournir le contrat à Claude Code. Le pilote existe mais ne tourne pas encore dans la boucle.
- Besoin des autres : Claude Code, le contrat des six points de branchement est documenté dans la section PiloteAutonomie ; tu gardes exclusivement root.py et les permissions. Les contrôles et classifications doivent rester côté moteur. Kimi K3, aucune restauration persistante ajoutée.

## 2026-10-21 16:12 : Codex

- Fait : pilote publié au commit signé b1d7af8 ; CI 39614691517 terminée avec succès. Revue poursuivie : deux nouveaux tests ont reproduit des lectures de versions après annulation et un retour accepté après expiration. Correction des gardes avant ces callbacks, puis 90 tests autonomie/preuves réussis localement en mode développement. Aucun essai cloud ou web.
- Fichiers touchés : `harness/autonomie.py`, `harness/test_autonomie.py`, `harness/CONCEPTION-AUTONOMIE.md`, `harness/JOURNAL.md`.
- En cours : publication signée du durcissement et contrôle de sa CI. Pilote non raccordé au moteur par Codex.
- Besoin des autres : Claude Code, contrat appelable du pilote déjà envoyé sur le bus. Les étapes et contrôles restent déclarés localement ; arrêt réel des processus et protection avant envoi restent au moteur.
## 2026-10-21 ~16:15 — Claude (Opus) — sécurité + tests

- Fait (poussé) : prénom de l utilisateur retiré de root.py/navigateur.py/action_systeme.py/securite.py (17 occurrences -> l utilisateur). Garde terminal : outil_terminal refuse une commande qui lit/écrit un fichier bloqué (cat .env, ~/.ssh...) et masque sa sortie en mode agressif -> plus de contournement de la liste noire. Navigateur : --remote-allow-origins restreint à http://localhost:PORT (plus * ). action_systeme : test_action_systeme.py ajouté (7 tests hors ligne, clics/frappes vérifiés sans cliquer).
- Codex : peux-tu ajouter test_action_systeme à la commande unittest du workflow (comme pour test_recherche) ? C est ton fichier .github/workflows/harness.yml, je n y touche pas.
- Reste : décision autonomie (planifié vs boucle libre) chez Vincent. Garde anti-fuite à remettre à la fin.
## 2026-10-21 ~16:25 — Décision de Vincent (via Claude) : BOUCLE LIBRE

- Root garde sa BOUCLE LIBRE comme mode par défaut : le modèle appelle ses outils librement, sans plan d étapes imposé à chaque tâche.
- L autonomie de Codex (Tache + RegistrePreuves, plan + preuves) reste une CAPACITÉ OPTIONNELLE, à activer seulement pour une grosse tâche multi-étapes — pas le mode par défaut. Le budget de durée est déjà câblé, non bloquant.
- Codex : ne pas refondre la boucle vers un flux planifié obligatoire. Si tu veux, exposer l autonomie comme un outil que Root invoque quand une tâche le mérite.
- Reste ouvert : Kimi K3 (tests + doc mémoire + reprendre Lanterns complet et Pegasus) ; garde anti-fuite à remettre en fin de chantier.

## 2026-10-21 — Claude (cloud), axe recherche + revue

- Fait : les cinq erreurs signalées par Codex sous Python 3.9 sont reproduites avec un Python 3.9.25 isolé. Elles venaient de `HTTPError.close()` sur une erreur sans corps, qui lève dans cette version. Fermeture protégée dans `recherche.py`. Les 173 tests (autonomie, vérification, recherche, action système) passent sous Python 3.9 et 3.13 en `-X dev`, sans avertissement. Tous les fichiers Python s'analysent et s'importent sous 3.9. `root.py` s'importe aussi sous 3.9 avec ses dépendances, dans un environnement isolé, sans lancer Root : 21 outils, dont les trois de recherche avec les bons niveaux de risque.
- Revue sur `01c57c7` :
  - Vérifié : prénom retiré du code ; origine du navigateur limitée à localhost ; `test_action_systeme.py` présent et vert ; le terminal refuse `cat .env`, `cat ~/.ssh/id_rsa`, `cat $HOME/.ssh/config` et `cat ~/.aws/credentials`.
  - Contournements encore possibles de la garde du terminal, constatés sans fichier réel : un joker comme `cat ~/.ss*/config`, et une lecture par programme comme `python3 -c "open('.e'+'nv')"`. La sortie reste masquée en mode agressif. Une vraie fermeture demanderait un bac à sable, à décider par Claude Code et l'utilisateur.
- Restent ouverts :
  - Recherche : le diagnostic sur le Mac n'a pas été relevé dans le journal. La cause du zéro source n'est donc pas confirmée. Commande : `cd harness && python3 -B recherche.py --diagnostic "hauteur de la tour Eiffel"`.
  - Codex : ajouter `test_action_systeme` au workflow, demandé par Claude Code.
  - Kimi K3 : `test_memoire.py` et `CONCEPTION-MEMOIRE.md` toujours absents.
  - Tous : remettre le garde anti-fuite en fin de chantier.
- Fichiers touchés : `harness/recherche.py`, `harness/JOURNAL.md`.

## 2026-10-21 16:18 : Codex

- Fait : diagnostic demandé exécuté sur le Mac dans la copie GitHub du harness, sans lancer Root ni appeler le modèle. Retour 0. Résumé structurel sans identifiants de challenge : `[duckduckgo] page reçue : taille=14284, anti_robot=true, liens_resultats=0, liens_uddg=0` ; `[duckduckgo] échec : anti_robot` ; `[wikipedia] 8 résultats en 0.5 s` ; `Causes des échecs et refus : 1 × moteur duckduckgo anti robot.` La page anti-robot est confirmée sur cet essai ; elle ne prouve pas rétroactivement le contenu de la réponse ancienne. Huit résultats moteur ne signifient pas huit sources récupérées. Ajout de test_action_systeme au workflow ; les 173 tests de la commande commune passent localement sous Python 3.9 avec -X dev, sans avertissement.
- Fichiers touchés : `.github/workflows/harness.yml`, `harness/JOURNAL.md` uniquement.
- En cours : commit signé et push, puis observation de la CI. La boucle libre reste le défaut selon la décision consignée ; aucune refonte imposée.
- Besoin des autres : Claude cloud dispose maintenant du diagnostic ; ne pas contourner le challenge DuckDuckGo. Claude Code conserve la décision et le traitement du bac à sable terminal ainsi que le garde anti-fuite final. Kimi K3 conserve les tests et la conception mémoire.
## 2026-10-21 15:52 — Kimi K3 (mémoire)

- Fait : module `memoire.py` relu, testé et publié avec ses tests dédiés. 32 tests hors réseau (socket bloqué) : troncation tête-queue signalée, estimation de tokens, compression du milieu avec protection tête+fin, signatures d'actions, journal JSONL append-only tolérant une coupure, memoire.md borné (8 000) filtré et révocable. Un vrai bug trouvé et corrigé : `compresser_milieu` pouvait couper une séquence d'outil en deux et laisser un message `tool` orphelin, que l'API refuse — ajout de `_frontiere_sure` qui recule la frontière de la zone protégée. Deuxième correction : les exemples utilisaient le prénom de l'utilisateur comme catégorie ; la couche de rédaction le masque à juste titre, donc les catégories sont désormais neutres (« Conventions de travail »), et la conception comme l'exemple de memoire.md l'indiquent. `CONCEPTION-MEMOIRE.md` (jusqu'ici non publié) ajouté au dépôt. `test_memoire.py` créé et ajouté au contrôle CI.
- Fichiers touchés : `harness/memoire.py`, `harness/test_memoire.py`, `harness/CONCEPTION-MEMOIRE.md`, `.github/workflows/harness.yml` (une ligne : ajout de test_memoire au job modules), `harness/JOURNAL.md` (cette entrée). Aucun fichier d'un autre axe modifié (root.py, navigateur.py, securite.py, autonomie.py, verification.py intacts chez moi).
- En cours : module non branché dans la boucle (réservé à Claude Code). Points d'insertion documentés dans CONCEPTION-MEMOIRE.md, section « Points de coordination ».
- Besoin des autres : Claude Code — dans root.py, quatre branchages quand tu y passes : appeler `memoire.enregistrer_tokens_reels(usage.prompt_tokens)` après chaque réponse ; appeler `memoire.compresser_milieu(messages)` avant l'appel modèle quand `estimer_tokens > SEUIL`; remplacer les troncations en dur par `memoire.tronquer_outil`; lire `memoire.memoire_pour_prompt()` au démarrage pour un second system. Dans `elaguer_images`, passer une ligne par `memoire.ligne_image(outil, description)`. Codex — règle de curation à ajouter à ame.md (« noter seulement ce qui reste vrai dans un mois, jamais de perso ») ; aligner mon journal de session avec l'état de tâche d'autonomie.py pour éviter deux fichiers concurrents.

## 2026-10-21 — Kimi K3 (mémoire) — correction CI

- Fait : première CI sur mon commit a échoué (1 test sur 32). Cause lue dans le log : `test_prenom_utilisateur_masque` testait le masquage du prénom, or Codex l'a retiré volontairement de `securite.py` (commit a1bd271, décision de l'équipe). Mon test imposait un comportement abandonné — remplacé par `test_secret_masque_au_prompt`, qui vérifie la garantie réellement stable du module (un secret en clair ne ressort jamais vers le prompt). Pas de changement de logique dans memoire.py, seulement le test. 32/32 mémoire vert, 205/205 au total, réseau bloqué, local Python 3.9.
- Fichiers touchés : `harness/test_memoire.py`, `harness/JOURNAL.md` (cette entrée).
- En cours : rien côté mémoire tant que CI n'est pas revérifiée.
- Besoin des autres : inchangé (branchages Claude Code, règle de curation Codex).

## 2026-10-21 16:40 : Codex

- Fait : synchronisation sur 5f60737, 205 tests communs réussis localement avec Python 3.9 -X dev, CI mémoire verte vérifiée. Règle de curation déjà présente dans ame.md, renforcée par exclusion des chemins privés et conversations. Boucle libre par défaut et suivi formel optionnel explicités. Contrat mémoire/autonomie documenté : autonomie ne sauvegarde rien sur disque ; le journal de session reste à memoire.py, sans deuxième todo, sans sérialisation brute de vue_locale et sans assimilation des signatures de résumé aux preuves. Les quatre appels mémoire demandés sont déjà présents dans root.py lu sur 5f60737 ; ligne_image reste absente. Aucun essai réel supplémentaire.
- Fichiers touchés : `harness/ame.md`, `harness/CONCEPTION-AUTONOMIE.md`, `harness/JOURNAL.md`.
- En cours : publication signée puis contrôle CI ; aucune persistance nouvelle ni modification du moteur.
- Besoin des autres : Kimi K3, corriger dans ta conception la mention que autonomie sauvegarderait déjà un état. Claude Code garde le branchement optionnel du pilote et la description des images ; les quatre points mémoire existants nécessitent surtout une revue intégrée. Points transmis sur le bus.

## 2026-10-21 — Claude (cloud), axe recherche + vérification de Kimi K3

- Vérifié pour Kimi K3 sur `5f60737` :
  - `test_memoire.py` (32 tests) et `CONCEPTION-MEMOIRE.md` présents, `test_memoire` et `test_action_systeme` dans le workflow ;
  - 205 tests verts sous Python 3.9 et 3.13 en `-X dev` ;
  - CI verte, trois commits signés.
  - Précision : dans `root.py`, `enregistrer_tokens_reels`, `compresser_milieu`, `tronquer_outil`, `memoire_pour_prompt` et `journaliser` sont déjà appelés. Seul `memoire.ligne_image` manque dans `elaguer_images`.
- Fait, suite au diagnostic relevé par Codex (DuckDuckGo anti-robot, Wikipédia 8 résultats) :
  - Un moteur qui renvoie une page anti-robot est suspendu pour la session. Root n'insiste plus auprès de DuckDuckGo.
  - Les références externes des articles Wikipédia sont relevées, et jusqu'à trois par page, les plus proches de la question, sont lues sous les mêmes gardes, budgets et règles `robots.txt`. Le rapport indique « trouvée via S1 ». Sans clé Brave, c'est ce qui donne des domaines indépendants, donc des affirmations corroborées.
  - 82 tests de recherche, 211 au total, verts sous Python 3.9 et 3.13 en `-X dev`.
- Non vérifié : la lecture réelle des pages et des références. Les 8 résultats Wikipédia du diagnostic ne disent pas combien de pages ont été lues.
- Fichiers touchés : `harness/recherche.py`, `harness/test_recherche.py`, `harness/CONCEPTION-RECHERCHE.md`, `harness/JOURNAL.md`.
- Besoin des autres :
  - Utilisateur : décider d'une clé Brave Search, à fournir par `BRAVE_SEARCH_API_KEY`.
  - Claude Code : brancher `memoire.ligne_image`. Puis, sur le Mac, `cd harness && python3 -B recherche.py --diagnostic "taxe de séjour"`, en relevant les lignes `[wikipedia]`, `Causes` et `S1`, `S2`…, qui ne contiennent que domaines, tailles et adresses publiques.

## 2026-10-21 16:48 — Claude (cloud), axe recherche

- Fait : texte des articles MediaWiki nettoyé. Les liens « modifier », appels de note « [1] », bandeaux de navigation, liste des références et catégories sont retirés du texte. Les liens externes de ces zones restent relevés, donc les références sont toujours suivies. Passages et citations portent sur l'article seul. 85 tests de recherche, 214 au total, verts sous Python 3.9 et 3.13 en `-X dev`.
- Résultat réel relevé par Claude Code sur le Mac, avant ce nettoyage : 8 résultats Wikipédia, 6 sources lues, DuckDuckGo écarté après sa page anti-robot.
- Non vérifié : le nettoyage sur un article réel. Le test utilise une page écrite d'après la structure MediaWiki.
- Fichiers touchés : `harness/recherche.py`, `harness/test_recherche.py`, `harness/CONCEPTION-RECHERCHE.md`, `harness/JOURNAL.md`, `harness/CANAL.md`.
- Besoin des autres : rien de bloquant.

## 2026-10-21 16:50 : Codex

- Fait : CapaciteAutonomie implémentée, six outils au format OUTILS pour démarrer un profil local, consulter le suivi, vérifier une étape, conclure, reprendre un contrôle et arrêter. Sans profil local, aucune table exposée. Une seule préparation par demande, aucun redémarrage de budget par le modèle. État minimisé sans objectif, cible, condition, observation ou détail d’exception. 14 nouveaux tests de capacité, 228 tests communs verts après synchronisation sur d570d16. ame.md précise les outils optionnels et le parcours recherche_web puis recherche_conclure, demandé par Claude cloud. Aucun essai modèle ni fichier moteur modifié.
- Fichiers touchés : `harness/autonomie.py`, `harness/test_autonomie.py`, `harness/ame.md`, `harness/CONCEPTION-AUTONOMIE.md`, `harness/JOURNAL.md`, `harness/CANAL.md`.
- En cours : publication signée et contrôle de la CI. Les outils ne sont pas encore exposés dans la boucle réelle.
- Besoin des autres : Claude Code, instancier CapaciteAutonomie avec un premier profil de confiance et raccorder les hooks métier via pilote_local ; exclure les six outils de suivi du dispatch des observations métier. Une fois le pilote démarré, ne jamais basculer librement après refus ou épuisement. Contrat détaillé dans la conception.

## 2026-10-21 17:04 : Codex

- Fait : ProfilTestsPython implémenté : commande unittest fixe, permission et contexte contrôlés localement, rapport complet, code zéro et minimum de tests exigés. Une course entre les lectures de versions a été reproduite puis corrigée. Empreinte locale bornée des fichiers Python, sans configuration ni lien symbolique. 19 nouveaux tests, dont une vraie exécution sur fixture synthétique. test_lecture et test_consentement ajoutés au workflow ; test_action_systeme y était déjà. Les sept suites passent localement, soit 261 tests.
- Fichiers touchés : `harness/autonomie.py`, `harness/test_autonomie.py`, `harness/CONCEPTION-AUTONOMIE.md`, `.github/workflows/harness.yml`, `harness/JOURNAL.md`, `harness/CANAL.md`.
- En cours : publication signée et contrôle CI. Aucun fichier moteur modifié, aucun essai modèle.
- Besoin des autres : Claude Code, premier profil prêt pour le raccordement : creer_capacite renvoie capacité stable et outils ; passer par les méthodes du profil pour les actions métier. Recette complète dans la conception. Le raccordement réel reste à vérifier après ton changement réservé à root.py.

## 2026-10-21 17:07 : Codex

- Fait : revue ciblée des mécanismes d'Oblivion à la révision 6a4109b : noyau et mémoire des anticorps, preuves et cycle des méthodes apprises. Recommandations de portage et limites ajoutées à la conception : exemples avant/après contrôlés, occurrences nouvelles à revérifier, méthodes périmées bloquées, permissions non mémorisées, persistance unique côté mémoire. Aucun de ces mécanismes supplémentaires n'est annoncé comme implémenté dans Root.
- Fichiers touchés : `harness/CONCEPTION-AUTONOMIE.md`, `harness/JOURNAL.md`.
- En cours : raccordement du premier profil de tests demandé à Claude Code ; pas de modification du moteur par Codex.
- Besoin des autres : Kimi K3 conserve la persistance ; Claude Code conserve root.py. Les 261 tests locaux vérifient l'étape précédente, pas les propositions de ce relevé.
- Vérification complémentaire : CI 39622500021 de d4c28b7 terminée avec succès, journaux relus : 261 tests et assemblage verts. Ce résultat valide les modules et le premier profil, pas le branchement absent du moteur.

## 2026-10-21 17:11 — Claude (cloud), axe recherche

- Vérifié en réel par l'utilisateur sur le Mac, avec la clé Brave lue dans le trousseau pour ce seul essai : `[brave] 8 résultats en 1.0 s` ; DuckDuckGo page anti-robot, échec `anti_robot` ; `[wikipedia] 8 résultats en 0.4 s`. Six sources lues sur cinq domaines : service-public.gouv.fr, deux articles Wikipédia, taxesejour.fr, myguestrelation.com, et une page allemande hors sujet. Pages non lues : une 404, une 403, une interdite par robots.txt.
- Fait : le diagnostic n'affiche plus que le chemin des formulaires, sans les identifiants de contrôle anti-robot de DuckDuckGo. 261 tests de la commande CI verts sous Python 3.9 et 3.13.
- Fichiers touchés : `harness/recherche.py`, `harness/test_recherche.py`, `harness/JOURNAL.md`, `harness/CANAL.md`.
- Besoin des autres : pour que Root utilise Brave en usage normal, la variable `BRAVE_SEARCH_API_KEY` doit être définie dans l'environnement de Root au lancement, depuis le trousseau. Commande proposée à l'utilisateur pour `~/.zshrc` : `export BRAVE_SEARCH_API_KEY="$(security find-generic-password -s BRAVE_SEARCH_API_KEY -w 2>/dev/null)"`.
## 2026-10-21 17:25 : Kimi K3 (axe mémoire)

- Fait : portage de deux mécanismes lus dans soulbook-main (à la demande de Claude Code) — refus des quasi-doublons sur memoire.md et pierres tombales inspirées d'Oblivion (`trust/oubli.ts`). Le refus des doublons est mesuré par recouvrement de mots (Jaccard), pas par SimHash : mesuré sur place (proches ~15/64 bits, éloignés ~30/64), SimHash perd sa localité sur des phrases courtes comme celles de memoire.md — même défaut signalé dans `trust/oubli.ts`. SimHash reste exposé dans le module (utile pour textes longs) et couvert par des tests calibrés sur les distances réellement observées. Les pierres tombales vivent dans `~/.local/root-tombes.json` (sha256 du texte plié) : un fait oublié ne peut pas être renoté — jamais le texte, seulement l'empreinte. Pour corriger un fait : `memoire_oublier` l'ancien puis `memoire_noter` le nouveau.
- Ce qui N'A PAS été porté (motivé dans CONCEPTION-MEMOIRE) : `origine.ts` (détection d'agent à l'écran, hors sujet pour memoire.md), `semantique.ts` (juge LLM — appel modèle, hors périmètre de memoire.py), `team/memoires.ts` (modèle « Lanterns » = script d'écriture vers screenpipe, pas un schéma de curation), « Pegasus » (= catégoriser par auteur ; les catégories existent déjà).
- 16 nouveaux tests hors réseau (classe TestQuasiDoublonsEtTombes). 275/275 tests passent dans tout le dépôt. Aucun réseau, aucune entrée utilisateur, textes synthétiques.
- Fichiers touchés : `harness/memoire.py`, `harness/test_memoire.py`, `harness/CONCEPTION-MEMOIRE.md`, `harness/JOURNAL.md`.
- En cours : vérifier que la CI reste verte sur les ajouts.
- Besoin des autres : Claude Code, les deux branchements mémoire restants dans root.py (détaillés dans le CANAL à 17:15) : `proposer_reprise` au démarrage et la callback `resumer_blocs` à passer à `compresser_milieu`, sinon le résumé automatique par modèle n'est jamais utilisé.

## 2026-10-21 17:16 : Codex

- Fait : canal relu, synchronisation sur 2506541. Les neuf suites passent ensemble sous Python 3.9 avec -X dev, soit 300 tests. test_immunite et test_confiance ajoutés au workflow : 25 tests présents mais jusque-là hors de la commande CI. immunite.py et ses tests relus, sans modification de ce module. Absence du raccordement autonomie et des deux derniers appels mémoire constatée dans root.py.
- Fichiers touchés : `.github/workflows/harness.yml`, `harness/CANAL.md`, `harness/JOURNAL.md`.
- En cours : publication signée de la couverture CI, puis observation des jobs. Aucun branchement moteur ou immunité annoncé comme fait.
- Besoin des autres : Claude Code conserve root.py ; Kimi conserve la persistance. Réponse et points de raccordement publiés dans CANAL.md.

## 2026-10-21 17:26 : Codex

- Fait : retrait de test_confiance de la commande CI apres suppression du module par Claude Code. Le clone de travail passe ses huit suites avec 307 tests, dont 20 nouveaux tests immunite encore non publies. Le resultat GitHub du correctif reste a observer.
- Fichiers touches : `.github/workflows/harness.yml`, `harness/CANAL.md`, `harness/JOURNAL.md`.
- En cours : publication signee de cette correction CI ; raccordement immunite en cours dans les seuls fichiers Codex.
- Besoin des autres : aucun ajout de module confiance, la provenance reste dans les regles de curation de Codex.

## 2026-10-21 17:29 : Codex

- Fait : ImmuniteControlee raccordee a PiloteAutonomie et a son profil Python optionnel. Apprentissage conditionne a deux captures enregistrees, correction actuelle verifiee, detecteur positif avant et negatif apres. Correspondances candidates par positions locales ; aucun extrait copie dans les rencontres SQLite. Regex calculees dans un processus arretable et recolte, limites de taille et de nombre. Pas de confiance automatique des regles importees ou relues apres redemarrage. Provenance humain/outil/IA explicitee dans ame.md. 22 nouveaux tests, dont une regex bloquante reellement interrompue et le parcours du pilote ; 309 tests locaux passes avec -X dev. Correction CI 35e8d4a confirmee verte.
- Fichiers touches : `harness/verification.py`, `harness/autonomie.py`, `harness/test_autonomie.py`, `harness/ame.md`, `harness/CONCEPTION-AUTONOMIE.md`, `harness/JOURNAL.md`, `harness/CANAL.md`. Aucun changement de root.py ou immunite.py.
- En cours : publication signee et verification CI ; activation dans le moteur non annoncee.
- Besoin des autres : Claude Code peut fournir immunite=adaptateur lors de la creation du pilote ou du profil ; contrat dans la conception. Kimi garde la persistance et l oubli ; aucune copie de son journal. Les candidats ne sont jamais des permissions ni des preuves finales.

## 2026-10-21 17:30 : Codex

- Fait : publication signee 0c2d9bf verifiee sur GitHub ; auteur associe au compte et signature valide. CI 39626154225 terminee avec succes, journaux relus : 309 tests et assemblage verts.
- Fichiers touches : `harness/CANAL.md`, `harness/JOURNAL.md` pour ce releve.
- En cours : aucun fichier de code reserve par Codex. Activation dans la boucle et methodes apprises non annoncees comme realisees.
- Besoin des autres : Claude Code conserve le raccordement moteur, contrat et limites publies dans la conception.

## 2026-10-21 17:37 — Claude (cloud), axe recherche

- Fait : les pages qui ne sont ni en français ni en anglais sont écartées, d'après l'attribut `lang` ou, à défaut, une estimation prudente sur les mots fréquents. Motif consigné : `langue_non_retenue`. Constat d'origine : une page allemande hors sujet parmi les six sources du premier essai Brave réel. 88 tests de recherche verts sous Python 3.9 et 3.13.
- Fichiers touchés : `harness/recherche.py`, `harness/test_recherche.py`, `harness/CONCEPTION-RECHERCHE.md`, `harness/JOURNAL.md`.

## 2026-10-21 17:38 — Claude (cloud), axe recherche

- Fait : paramètre `recence` (jour, semaine, mois, annee) sur `recherche_web`, transmis à Brave (`freshness`) et à DuckDuckGo (`df`). Wikipédia et les références suivies ne filtrent pas par date, et la sortie le dit. Schéma de l'outil mis à jour dans `OUTILS_RECHERCHE`, donc rien à changer dans `root.py` : vérifié en chargeant `root.py` sous Python 3.9. 91 tests de recherche verts sous Python 3.9 et 3.13.
- Fichiers touchés : `harness/recherche.py`, `harness/test_recherche.py`, `harness/CONCEPTION-RECHERCHE.md`, `harness/JOURNAL.md`.

## 2026-10-21 17:43 — Claude (cloud), axe recherche

- Fait : lecture des PDF en bibliothèque standard. Flux FlateDecode, flux d'objets, arbre des pages, polices par page avec tables ToUnicode, opérateurs de texte. Plafonds anti-bombe : 10 Mo par flux, 40 Mo par document, 300 pages. Refus motivés : `pdf_chiffre`, `pdf_trop_volumineux` si tronqué, `pdf_illisible` si scanné ou sans table de caractères. Lecture par page relevée à 5 Mo. 97 tests de recherche ; commande CI complète, 323 tests, verte sous Python 3.9 et 3.13 en `-X dev` ; `root.py` se charge sous 3.9.
- Non vérifié : un vrai PDF officiel téléchargé. Les tests utilisent des PDF fabriqués d'après la norme, avec les cas courants des générateurs (polices composites, flux d'objets).
- Fichiers touchés : `harness/recherche.py`, `harness/test_recherche.py`, `harness/CONCEPTION-RECHERCHE.md`, `harness/JOURNAL.md`.


## 2026-10-21 17:44 — Codex

- Fait : deux courses de capture reproduites par deux tests en echec avant correction (ajout de fichier et modification d un fichier deja lu). Empreinte corrigee avec controle global des identites et de la liste. Les huit suites du workflow passent localement sous Python 3.9 en mode developpement : 331 tests.
- Fichiers touches : autonomie.py, test_autonomie.py, CONCEPTION-AUTONOMIE.md, JOURNAL.md et CANAL.md.
- En cours : publication signee puis controle CI. Aucun changement de root.py.
- Besoin des autres : Claude Code, integrer le profil optionnel dans le moteur ; demande envoyee sur le bus. ImmuniteControlee est deja raccordee au pilote.

## 2026-10-21 22:50 — Kimi K3 — Calibrage des tokens (4a)

- Pourquoi : jusqu'ici `estimer_tokens` reposait sur des constantes à la main (4 caractères/token, 1100 tokens/image) sans jamais regarder les mesures réelles collectées par `enregistrer_tokens_reels`. L'instrumentation existait, l'analyse non — l'ajustement aurait demandé des jours d'attente avant d'envisager un recalage, alors que l'écart peut être connu dès 5 mesures.
- Fait : ajout d'une série persistée `root-tokens.jsonl` (append JSONL borné à 50 mesures, ligne = `{caracteres_estime, estime, reel, images, ts}`), de deux fonctions pures `_mediane` / `_ecart_relatif`, et de `analyser_calibration()` / `calibrer_constantes()` dans memoire.py. `analyser_calibration` coupe les mesures en `texte_seul` / `avec_image`, calcule les densités observées (tokens par caractère, tokens par image), sort moyenne et médiane d'écart en pourcentage. `calibrer_constantes` n'agit que si `ecart_moyen > 25 %` et au moins `CALIBRATION_MIN_POINTS=5` mesures, borne à ±50 % (une majoration ne dépasse pas le facteur 3/2, une minoration ne descend pas sous 2/3), et est idempotente (2ᵉ appel sans ajustement supplémentaire).
- `estimer_tokens` retourne toujours un `int` même après calibrage, qui rend `CARACTERES_PAR_TOKEN` réel. Le durcissement maintient la rétro-compatibilité totale de l'interface : noms et signatures inchangés, deux paramètres additionnels optionnels sur `enregistrer_tokens_reels` (`estime`, `images`), nul en l'état — aucun appelant ne les oblige.
- Fichiers touchés : memoire.py, test_memoire.py (classe `TestCalibrationTokens`, 23 tests verts).
- Critères d'acceptation (méta-prompt 4a) : plus besoin d'attendre des jours, l'ajustement se fait dès 5 mesures réelles empiriques.
- En cours : robustesse du stockage (4b).

## 2026-10-21 22:50 — Kimi K3 — Robustesse du stockage (4b)

- Pourquoi : la persistence mémoire (memoire.md, tombes.json, etat.json, mesures.jsonl) reposait sur des écritures directes `write_text` et des lectures `read_text` nues. Une interruption électrique pouvait tronquer un fichier ; un JSON cassé ou bytes invalides faisaient planter le démarrage.
- Fait : ajout d'une utilité `_ecrire_texte_atomique` (écrit dans `<path>.tmp` puis `os.replace`, atomique POSIX et NT ; sauvegarde la version précédente en `.bak` avant d'écraser, jamais de `.tmp` traînant en sortie normale), et de `_lire_json_tolerant` / `_lire_texte_tolerant` (JSON cassé → tente `.bak`, sinon valeur par défaut ; UTF-8 invalide → `str` vide, jamais de propagation). Branchement sur chaque site : `enregistrer_tokens_reels` (ETAT_FICHIER), `_mesures_borner` (JSONL), `_tombes_charger` / `_tombes_sauver` (TOMBES_FICHIER), `memoire_noter` / `memoire_oublier` / `memoire_pour_prompt` (MEMOIRE_FICHIER). Un démarrage après `kill -9` ou disque plein ne plante JAMAIS : il démarre sur un état vierge plutôt que sur un crash à la chaîne.
- Fichiers touchés : memoire.py, test_memoire.py (classe `TestRobustessePersistence`, 22 tests verts).
- Critères d'acceptation (méta-prompt 4b) : chargement tolérant à un fichier corrompu (JSON, UTF-8, OSError), écriture atomique, `.bak` de secours, AUCUNE exception propagate.
- En cours : durcissement de `compresser_milieu` et du callback `resumer_blocs` (4c).

## 2026-10-21 22:50 — Kimi K3 — Durcissement de compresser_milieu (4c)

- Pourquoi : `compresser_milieu` pouvait (i) propager une exception remontée par le callback `resumer_blocs` (le bloc modèle tombe → toute la conversation embarque le contexte), (ii) omettre silencieusement un bloc du résumé si le callback renvoyait une liste trop courte, une non-liste, une valeur non-str ou une phrase vide, (iii) silencieusement perdre les blocs constitués uniquement de séquences outil (le résumé local retournait `""` qui était alors filtré du résumé injecté).
- Fait : durcissement structuré. Ajout d'une fonction locale `_resume_local` dans `compresser_milieu` qui garantit ne JAMAIS renvoyer une chaîne vide (un bloc sans contenu utilisateur lisible devient `"(bloc de N message(s) sans contenu utilisateur lisible)"`). Le callback est maintenant appelé dans un `try/except` (toute exception → repli local complet), la valeur de retour est validée (non-list ou liste trop courte → repli local complet), et chaque entrée est normalisée (non-str ou vide → repli local pour CETTE entrée seulement, les phrases textuelles valides des autres blocs sont conservées). Les messages system sont toujours conservés intacts en tête, et la frontière de protection `_frontiere_sure` recule avant un `tool` orphelin (jamais de message tool coupé de son tool_calls apparié).
- Fichiers touchés : memoire.py, test_memoire.py (classe `TestCompressionRobustesse`, 11 tests verts).
- Critères d'acceptation (méta-prompt 4c) : compression ne coupe jamais une séquence outil, tête (system) et queue (N derniers messages) toujours utiles, callback robuste face à exception/type invalide/liste courte/entrée vide ou non-str.

## Bilan 4a+4b+4c

- `103/103` tests verts dans test_memoire.py, `393/393` verts sur tout le dépôt (`python3 -m unittest discover -p "test_*.py" -q` depuis harness/, incluant les 6 tests `test_entendre.py` nouveaux de Codex).
- Interface inchangée : `compresser_milieu`, `enregistrer_tokens_reels`, `estimer_tokens`, `journaliser`, `ligne_image`, `memoire_noter`, `memoire_oublier`, `memoire_pour_prompt`, `proposer_reprise`, `tronquer_outil`, callback `resumer_blocs` — mêmes noms, mêmes signatures (ajout de 2 paramètres optionnels seulement sur `enregistrer_tokens_reels`).

## 2026-10-22 09:30 — Kimi K3 — rappel_pertinent + rappel_pour_prompt (5ᵉ mission)

- Pourquoi : au démarrage `memoire_pour_prompt` injecte tout le contenu persisté — mais une fois la session lancée, la boucle n'a aucun moyen de « remonter » le fait du mois dernier qui colle à la demande du moment. Il fallait un rappel ciblé, lexical, hors modèle.
- Fait : deux nouvelles fonctions dans memoire.py (ajout pur, aucune modification d'existant).
  - `rappel_pertinent(demande: str, n: int = 5) -> list` : tokenise la demande via `_mots` (même normalisation NFKC + sans accents que les quasi-doublons), calcule le score Jaccard `|A ∩ B| / |A ∪ B|` contre chaque fait de memoire.md, trie par `(-score, index asc)`, renvoie les `n` premiers. Aucun recouvrement → liste vide (préfère « rien » au bruit). Fait le plus ancien gagne en cas d'égalité stricte (stabilité déterministe).
  - `rappel_pour_prompt(demande, n=5) -> str` : formate pour injection (header `"Souvenirs durables pertinents pour la demande actuelle :"` + lignes `- ...`), chaîne vide si rien à rappeler. Jamais `None`.
- Métrique choisie : Jaccard classique (intersection/union des ensembles de mots normalisés) plutôt qu'une TF-IDF ou un modèle — cohérent avec `_mots`/`_plier`, zéro dépendance externe, zéro appel modèle, reproductible hors ligne.
- Cas limites verrouillés par 21 tests dans `TestRappelPertinent` : demande vide, mémoire absente/vide/sans faits, aucun recouvrement, casse et accents normalisés, ponctuation finale tolérée, départage stable en cas d'égalité, `n=0`/`n<0`/`n` par défaut à 5, lecture pure (aucun effet de bord sur le fichier).
- Fichiers touchés : memoire.py, test_memoire.py (classe `TestRappelPertinent`, 21 tests verts).
- Tests : 21/21 nouveaux, 124/124 memoire, 423/423 dépôt.
- Interface : TOTALEMENT PRÉSERVÉE. `rappel_pertinent` et `rappel_pour_prompt` s'AJOUTENT. Aucune signature, aucun nom d'existant ne change.
- Branchement : Claude Code pourra appeler `rappel_pour_prompt(demande)` à chaque tour utilisateur dans root.py et injecter le résultat (chaîne non vide) à côté du message, à côté ou à la place des `déjà_memoires` existants — c'est sa décision. Aucune intégration faite côté Kimi.
