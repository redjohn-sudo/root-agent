# Root : mémoire et gestion du contexte

Date : 21 octobre 2026. Statut : conception proposée par Kimi K3, non validée, aucun code dans les fichiers actifs. Tout ce qui suit est une proposition à faire relire par Vincent avant intégration. L'intégration dans `root.py` et `navigateur.py` est réservée à Claude ; l'âme est réservée à Codex. Ce document ne touche rien d'existant.

## Ce qui existe déjà, lu dans le code de l'instantané

Constats faits sur les fichiers actuels, pas des mesures. Ils servent à ne pas proposer deux fois la même chose.

- `root.py`, `un_tour` : la conversation est la liste `messages`, en mémoire vive seulement. Elle est perdue à la fermeture. Elle ne grandit que par ajout, jamais par retrait.
- `root.py`, `elaguer_images` (Lot 3, Claude) : déjà en place. Seules les images du dernier message qui en contient sont conservées ; les images des messages plus anciens sont remplacées par le texte `[image vue plus tôt]`. Donc le problème « renvoyer toutes les images à chaque tour » est déjà réglé dans ce sens. Ce qui manque : la trace textuelle de ce que chaque image montrait, donc Root ne peut pas s'en resservir sans la revoir.
- `root.py`, `outil_lire_fichier` et `outil_terminal` : troncation en dur à 20 000 caractères, suffixe `… (tronqué)`. Déjà en place. Limite : couper au caractère 20 000 peut trancher au milieu de la ligne décisive sans préserver ni le début utile ni la fin (où vivent souvent les erreurs et les codes de sortie).
- `navigateur.py`, `texte` : troncation à 12 000 caractères. Même limite.
- Aucune compression du milieu de conversation. Aucune persistance entre deux lancements (`main` repart de `messages = [{"role": "system", "content": AME}]`). Aucune mémoire longue durée.
- `securite.py` (Claude) masque les secrets et emballe le web en contenu non fiable sur les résultats d'outils. Ma mémoire ne recopiera pas cette couche : elle consomme des textes déjà nettoyés, elle ne stocke pas de bruts.

Deux risques dominent. D'un côté, la fenêtre : la conversation grandit sans fin, et même avec les images élaguées, les tours web et terminaux longs s'empilent jusqu'à saturer le contexte ou le budget. De l'autre, la frontière cloud : tout ce qui entre dans `messages` part à DeepSeek, donc toute mémoire persistée qui serait un jour rechargée dans le prompt doit être construite dès le départ comme si elle allait sortir de la machine.

## Principe directeur

La mémoire de Root est un carnet local, pas une extension du prompt envoyée telle quelle au cloud. Le disque garde tout ; le modèle ne reçoit qu'une projection courte, curée et explicitement autorisée. Ce qui est écrit sur disque n'est jamais réinjecté en entier. Ça répond aux deux horizons d'un coup : on tient dans la fenêtre, et on tient dans la décence.

---

# HORIZON 1 — Tenir dans la fenêtre (mémoire courte, une session)

Recommandations classées par impact décroissant. L'effort est estimé en unités simples : S (quelques heures), M (une journée), L (plusieurs jours avec tests).

## 1. Compter les tokens et déclencher sur budget, pas au feeling

**Problème réglé.** Aujourd'hui, rien ne sait quand la conversation devient trop grosse. On ne peut pas compresser au bon moment si on ne mesure pas. C'est la brique dont dépendent toutes les autres.

**Comment l'implémenter.** Nouveau module `memoire.py` (mien, personne d'autre n'y touche). Une fonction `estimer_tokens(messages) -> int` qui calcule une borne haute : somme des caractères des champs `content` divisée par ~4 pour le texte, plus un coût fixe par image encore présente (une image = un forfait, ex. 1 100 tokens, ajustable après mesure sur `usage.prompt_tokens` retourné par l'API). Pas besoin d'un tokenizer exact : une surestimation stable suffit, parce qu'on déclenche sous un seuil confortable.

`root.py` expose déjà `usage.prompt_tokens` dans `un_tour` (utilisé pour le compteur du jour). Je propose que Claude lise aussi cette valeur réelle à chaque tour et l'écrive dans un petit fichier d'état (`~/.local/root-etat.json`), ce qui calibre mon estimateur au fil du temps. Côté `memoire.py`, une constante `BUDGET_FENETRE` (ex. 100 000 tokens en entrée pour DeepSeek, marge comprise) et `SEUIL_COMPRESSION` (ex. 70 % du budget).

**Effort.** S. Aucun appel modèle, aucun risque.

## 2. Garder la dernière image utile, résumer les précédentes en une ligne

**Problème réglé.** `elaguer_images` efface bien les vieilles images, mais les remplace par `[image vue plus tôt]`, ce qui est muet. Root ne sait plus ce qu'elle avait vu (une capture d'écran d'il y a cinq tours, une photo envoyée au début). Au prochain besoin, soit elle redemande une capture inutile, soit elle avance sans l'info.

**Comment l'implémenter.** Je ne touche pas à `elaguer_images` (fichier de Claude). Je propose que `memoire.py` tienne, en parallèle de `messages`, un registre local des images déjà montrées : pour chacune, une ligne courte écrite au moment où l'image entre — outil source (`capture_ecran`, `web_voir`, photo de Vincent), cible, et une description en une phrase soit fournie par l'outil, soit générée une fois par le modèle **au moment de la première vue** (l'image est encore là, ça coûte un petit appel) puis stockée.

Quand `elaguer_images` remplace une image par du texte, le texte devient `[image du {outil} à {heure} : {description en une phrase}]` au lieu de `[image vue plus tôt]`. Le remplacement reste dans la boucle de Claude ; je lui fournis la ligne à mettre. Le registre des descriptions vit sur disque dans la session courante, jamais une image elle-même.

**Effort.** M. Dépend d'un point de branchement dans `elaguer_images` (Claude) et d'un appel de description par image (coût tokens à mesurer). Si le coût de description est jugé trop cher, version dégradée sans appel : la ligne porte juste outil, heure et cible — déjà bien mieux que « vue plus tôt ».

## 3. Tronquer les résultats d'outils en gardant tête et queue, avec une note de coupure

**Problème réglé.** La troncation actuelle coupe à 20 000 caractères avec `… (tronqué)`. Pour un `lire_fichier` ou un gros `terminal`, la fin (où se trouvent le code de sortie, le traceback, la ligne fautive) est perdue. Root peut croire qu'une commande a réussi alors que l'erreur était sous la coupe.

**Comment l'implémenter.** `memoire.py` fournit `tronquer_outil(texte, budget=20000) -> str`. Politique : garder les premiers ~40 % et les derniers ~40 % du budget, avec au milieu une ligne explicite `… (N caractères omis au milieu, début et fin conservés)`. Jamais de coupure silencieuse en plein milieu de mot : on aligne sur un saut de ligne. Pour le terminal, on s'assure en plus que la ligne `[code X]` du retour est toujours dans la tête conservée (c'est déjà le format actuel, facile à préserver).

C'est un remplacement local des deux `if len(texte) > 20000` de `root.py` et du `texte()` de `navigateur.py` — donc à intégrer par Claude, en appelant ma fonction. La valeur 20 000 reste un réglage, sortie en constante.

**Effort.** S. Fonction pure, testable hors ligne avec des chaînes synthétiques.

## 4. Compresser le milieu de la conversation quand on approche du seuil

**Problème réglé.** Même bien tronquée, une longue session web ou un gros débogage finit par atteindre la fenêtre. Sans compression, Root s'arrête au cap `MAX_ETAPES` ou dérive.

**Comment l'implémenter.** `memoire.py` : `compresser_milieu(messages) -> nouveaux_messages`. Règles strictes :

- **Protégé, jamais compressé** : le message `system` (l'âme), et les `N` derniers échanges (proposition : les 6 derniers messages, ajustable), pour que Root garde le fil immédiat.
- **Compressable** : tout ce qui est entre les deux, découpé en blocs `user → assistant → tool… `. Chaque bloc résumé en quelques lignes : but de Vincent, actions réellement faites, résultat concret, ce qui restait en suspens.
- Le résumé remplace les blocs anciens par un seul message `assistant` balisé, ex. `Résumé des échanges 3 à 17 (fait à {heure}) : …`. Le balisage est volontairement laid et daté pour qu'on voie que c'est un résumé, pas de la conversation fraîche.
- Le résumé est fait **une fois** par un appel au modèle, au moment du dépassement de seuil (recommandation 1). Coût : un appel. Réglable, et on peut dégrader sans appel : garder pour chaque bloc seulement la première ligne de Vincent, les noms d'outils appelés et la dernière ligne de résultat de chaque outil. C'est moins lisible mais gratuit et sans fuite supplémentaire.

Le déclenchement est dans `un_tour` (Claude) : avant chaque appel, si `estimer_tokens > SEUIL_COMPRESSION`, remplacer `messages` par `compresser_milieu(messages)`.

**Effort.** M à L selon la qualité de résumé visée. Tests hors ligne avec des fausses conversations. Point d'attention pour Claude : préserver l'appariement `tool_calls` / `tool` (un message `tool` orphelin casse l'API) — le découpage en blocs doit couper entre échanges complets, jamais au milieu d'un appel d'outil.

## 5. Éviter que Root refasse ce que son propre résumé dit comme déjà fait

**Problème réglé.** Risque connu des résumés : Root relit « j'ai déjà vérifié X » et, sans la preuve sous les yeux, soit recommence X par méfiance, soit conclut trop vite en se fiant à sa propre formulation. Les deux sont mauvais (le doc de Codex l'exige : un « OK » n'est pas une preuve, une preuve ancienne ne vaut pas pour l'état courant).

**Comment l'implémenter.** Deux garde-fous, un dans le texte, un dans le code :

- Dans le gabarit de résumé (recommandation 4), chaque ligne « fait » est écrite au passé composé impersonnel avec sa source : `ÉCHANGE 5 — outil `lire_fichier` sur `config.txt`, résultat : 12 lignes, aucune clé trouvée.` Pas de « j'ai compris », pas de « tout est bon ». Le résumé décrit des actes et des observations, jamais des conclusions de réussite — la conclusion reste l'apanage du registre de preuves de Codex, pas du mien.
- `memoire.py` tient un petit registre des signatures d'actions déjà résumées (outil + arguments normalisés + empreinte du texte de résultat, sans le texte). Si, dans les derniers messages protégés, Root repart sur une action déjà couverte par le résumé sans que la cible ait changé, le résumé porte déjà la mention, et la boucle de Codex (détection de répétitions, `autonomie.py`) peut s'y appuyer. Je ne fais pas la détection moi-même ; je fournis les signatures propres.

**Effort.** S pour le gabarit, M pour le registre de signatures. La décision « répétition ou pas » reste chez Codex ; je m'occupe de rendre les faits comparables.

## 6. Ce que je ne propose PAS pour l'horizon 1, et pourquoi

- Pas de résumé à chaque tour : trop cher, et un résumé réécrit en continu glisse (chaque version « améliore » la précédente, on perd les faits).
- Pas de suppression pure et simple des vieux messages : on perdrait la capacité de revenir sur un détail. On résume, on n'efface pas.
- Pas de mise en cache sémantique (vector store) dans la session : surdimensionné pour une conversation, et ça rajoute une dépendance et un risque de fuite pour un gain faible devant une bonne troncation tête-queue.

---

# HORIZON 2 — Se souvenir entre les sessions (mémoire longue)

## 1. Journal de session sur disque, append-only, jamais réinjecté en entier

**Problème réglé.** Tout meurt à la fermeture. Impossible de reprendre une tâche interrompue, impossible d'apprendre d'une session à l'autre.

**Comment l'implémenter.** `memoire.py` écrit un journal JSONL dans `~/.local/root-sessions/` — un objet JSON par ligne, ajouté à chaque événement (message utilisateur, appel d'outil, résultat résumé, décision). Append-only : on n'édite jamais une ligne passée, ce qui rend le fichier auditable et robuste à une coupure en cours d'écriture (écrire dans un fichier temporaire puis renommer n'est utile que pour des fichiers réécrits ; ici on ne fait qu'append).

Chaque ligne : `{ts, type, role?, outil?, signature?, resume, sensible: false}`. **Aucune image, aucun contenu de page brute, aucun secret.** On stocke le résumé et les signatures, pas les bruts. Au démarrage suivant, `memoire.py` sait relire ce journal et en tirer un état : ce qui a été tenté, ce qui a marché, où on s'est arrêté.

Point de coordination avec Codex : son `autonomie.py` sauvegarde déjà un état de tâche. Je propose que mon journal de session soit la couche « faits bruts curés » et que l'état de tâche de Codex s'y appuie, plutôt que deux fichiers concurrents. À trancher ensemble.

**Effort.** M. Testable hors ligne (écrire, couper, relire).

## 2. Reprendre une session interrompue, prudemment

**Problème réglé.** Sans mécanisme, un crash ou un `/q` au mauvais moment perd tout le contexte d'une tâche en cours.

**Comment l'implémenter.** Au lancement, `memoire.py` regarde si le dernier journal se termine proprement (une ligne explicite `fin`) ou s'arrête en plein milieu. Si plein milieu : proposer à Vincent, dans la bannière, `reprendre la session du {date} ? [o/N]`. Si oui, on ne recharge **pas** les anciens messages dans `messages` (risque de fuite et d'empilement) ; on injecte dans `messages` un seul message `system` additionnel, court : « Reprise d'une session du {date}. Déjà fait : {3-5 lignes tirées du journal}. En suspens : {ce qui n'avait pas de fin}. À toi de vérifier l'état actuel avant d'agir. » Le journal complet reste sur disque, consultable à la demande via un outil de lecture locale si besoin.

Ça respecte le principe de Codex : recharger tout l'historique expose des données et fait confondre ancien et courant. On n'injecte qu'une projection, et on dit clairement que c'est du passé à revérifier.

**Effort.** M. Dépend de la recommandation 1 de l'horizon 2.

## 3. Une mémoire longue durée curée : `memoire.md`, des faits courts, pas des logs

**Problème réglé.** Root oublie tout entre deux lancements : les conventions de Vincent, les pièges déjà rencontrés, les « ici on fait comme ça ». Sans ça, elle reposera les mêmes questions et refera les mêmes erreurs.

**Comment l'implémenter.** Un fichier `~/Projets/root-harness/memoire.md` (dans le projet, inspectable d'un coup d'œil, versionnable si Vincent veut — donc **aucune donnée sensible dedans, par construction**). Ce n'est **pas** un journal. C'est une liste de faits curés, tenue à jour, qui ressemble à ça :

```markdown
# Mémoire de Root — faits durables

## Conventions de travail
- Les projets web vivent dans un dossier dédié, un venv par projet, jamais
  d'install globale.
- « Le serveur », chez lui, c'est un NAS local, pas un cloud.

## Pièges déjà rencontrés
- `web_cliquer` sur un bouton « Envoyer » dans un formulaire X : la page recharge
  lentement, attendre avant `web_voir` sinon on lit l'ancienne page.
- `lire_fichier` tronque à 20 000 caractères : un JSON de config volumineux
  doit être lu par morceaux ou filtré d'abord avec `terminal` + `grep`.

## Préférences
- Réponses courtes. Pas de jargon pour faire joli (déjà dans l'âme, rappel).
- Confirmer avant toute écriture hors du dossier projet courant.
```

Deux garde-fous sur la forme, confirmés par les tests : les catégories et les
faits ne portent **pas de prénom ni de donnée personnelle en clair** — la couche
de rédaction (securite.py) les masque de toute façon à l'écriture et à la
lecture pour le prompt. Un fait vraiment sensible (secret, carte, identifiant)
est refusé avant d'être écrit.

Le mécanisme de mise à jour : pas automatique à chaque tour (ça dériverait). Je propose un outil `memoire_noter(fait, categorie)` que Root appelle **uniquement** quand un fait est établi et utile au long cours — et une règle dans l'âme (à ajouter par Codex) : « note seulement ce qui restera vrai dans un mois ; jamais une donnée personnelle, un secret, un chemin privé, un contenu de conversation ». En dessous de ça, `memoire.py` fournit la fonction d'écriture ; la décision de ce qui mérite d'y aller est laissée au jugement, borné par la règle.

Au démarrage, `main` (Claude) lit `memoire.md` et l'injecte **tel quel** comme second message `system`. C'est la seule chose persistée qui entre directement dans le prompt, donc sa taille et son innocuité sont le contrat (voir recommandation 4).

**Effort.** M. La fonction d'écriture est simple (S) ; la difficulté est la discipline de curation, qui relève du prompt (Codex) et de la relecture par Vincent.

## 4. Garder cette mémoire propre et sûre

**Problème réglé.** Une mémoire qui grossit sans borne finit par saturer le prompt, et une mémoire qui accepte tout finit par contenir ce qu'on ne veut pas envoyer à DeepSeek.

**Comment l'implémenter.** Quatre bornes dans `memoire.py` :

- **Taille bornée.** `memoire.md` refusé en écriture au-delà d'un plafond (proposition : 8 000 caractères, soit ~2 000 tokens — assez pour des faits, trop petit pour des logs). Si plein, `memoire_noter` renvoie une erreur explicite invitant à purger, pas de troncation silencieuse.
- **Filtre d'entrée.** Avant d'écrire un fait, le même nettoyeur que `securite.py` pour les secrets (Claude expose déjà `rediger_secrets` ; je m'y branche plutôt que de réécrire le mien), plus un refus des marqueurs évidents de données privées. Le filtre n'est pas une preuve d'absence de fuite (le doc de Codex le rappelle) ; c'est une barrière, pas une garantie. La règle « jamais de perso » reste portée par l'âme et par le fait que ce fichier peut être relu à tout moment.
- **Inspectable.** Texte brut, un fait par ligne, daté. Vincent lit et édite à la main ; rien de magique.
- **Révocable.** Chaque fait porte une date d'ajout. Une commande `memoire_oublier(motif)` supprime les lignes correspondantes. Un fait contredit n'est pas écrasé en silence : la nouvelle ligne le remplace avec sa date, et on garde le principe « le plus récent prime », visible à la lecture.

Détail de fuite à verrouiller : `memoire.md` est lu au démarrage et injecté dans le prompt, donc **il part au cloud à chaque session**. Conséquence nette : on n'y met jamais ce qu'on ne veut pas chez DeepSeek. Le journal de sessions, lui, n'est jamais injecté en entier — seule sa projection curée l'est.

**Effort.** S pour les bornes et le filtre, M pour l'outil d'oubli et la discipline.

## 5. Ce que je ne propose PAS pour l'horizon 2, et pourquoi

- Pas de base vectorielle ni d'embeddings pour la mémoire longue : lourd, opaque, et la donnée d'embedding vit aussi en mémoire ou sur un service — risque de fuite pour un bénéfice faible sur une mémoire de faits courts. Une recherche `grep` sur `memoire.md` suffit à cette échelle.
- Pas de réinjection automatique du journal complet au démarrage : fuite potentielle et hors sujet, contraire au principe directeur.
- Pas de mémoire qui s'écrit toute seule à chaque échange : dérive assurée. La curation est un acte explicite et rare.

---

# Forme proposée du fichier de mémoire longue durée

Récapitulatif concret, pour discussion :

- **`~/.local/root-sessions/AAAA-MM-JJ.jsonl`** — journal de session, append-only, résumés et signatures, jamais de bruts, jamais réinjecté en entier.
- **`~/Projets/root-harness/memoire.md`** — mémoire durable curée, trois sections (Conventions de travail / Pièges / Préférences — sans prénom ni donnée perso en clair), un fait daté par ligne, plafond ~8 000 caractères, filtrée à l'entrée, injectée telle quelle au prompt au démarrage.

Deux fichiers, deux rôles nets : l'un se souvient de tout pour la machine locale, l'autre ne dit au cloud que ce qui mérite d'être dit.

# Points de coordination à ouvrir avec Claude et Codex

- Claude, `root.py` : brancher `estimer_tokens`, le déclencheur de `compresser_milieu`, l'appel de ma `tronquer_outil` à la place des coupures en dur, et la lecture de `memoire.md` au démarrage. Je fournis les fonctions, il décide des points d'insertion.
- Claude, `elaguer_images` : lui passer la ligne de description par image pour remplacer `[image vue plus tôt]`.
- Codex, `ame.md` : la règle de curation (« note seulement ce qui reste vrai dans un mois, jamais de perso ») et la distinction entre mon résumé de faits et son registre de preuves — mon résumé ne conclut jamais « réussi ».
- Codex, `autonomie.py` : éviter deux fichiers d'état concurrents ; mon journal de session peut porter ses faits, ou l'inverse, à trancher.

# Vérifications à exiger avant de dire que la mémoire fonctionne

Proposées, pas exécutées ici :

- une conversation synthétique de 40 échanges avec images : la fenêtre reste sous le budget, les images anciennes sont remplacées par leur ligne de description, et Root ne redemande pas une capture qu'elle a déjà décrite ;
- un `terminal` dont la sortie de 50 000 caractères contient l'erreur à la fin : la fin est conservée après troncation ;
- compression déclenchée au seuil : le message `system` et les 6 derniers échanges sont intacts, aucun `tool` orphelin dans le résultat ;
- un résumé présent : Root ne relance pas un outil déjà résumé pour la même cible inchangée ;
- fermeture et relance en pleine tâche : reprise proposée, projection courte injectée, aucun message ancien complet ne ressort ;
- `memoire.md` rempli au-delà du plafond : écriture refusée proprement ; un fait sensible synthétique : filtré à l'entrée ;
- aucune donnée personnelle ni secret dans les deux fichiers après une session de test, vérifié par lecture brute.

# Appendice 2026-10-21 — portage de deux mécanismes de soulbook et Oblivion

Sur demande de Claude Code (« reprends les points précis dans team/memoires.ts et
compare-les à ta conception »), j'ai relu les sources
(`~/Projets/soulbook-main/team/memoires.ts`, `engine/trust/{origine,oubli,empreinte,
semantique}.ts`, `engine/distill/empreinte.ts`) et trié ce qui se porte
honnêtement dans memoire.py — c'est-à-dire ce qui est hors ligne, testable,
utile à memoire.md, et conforme à mes principes.

Ce qui a été porté :

1. **Refus des quasi-doublons** (inspiré d'`empreinte.ts` qui utilise SimHash).
   `memoire_noter` refuse un fait trop proche d'un fait déjà présent, pour ne
   pas encombrer memoire.md de la même phrase réécrite. La MESURE utilisée
   n'est pas SimHash : c'est un recouvrement de mots (Jaccard) parce que
   SimHash (Charikar) perd sa localité sur des textes très courts — les faits
   de memoire.md font souvent moins de 15 mots, et un mot changé y déplace
   trop de bits pour que la distance reste fidèle. C'est un défaut connu :
   `trust/oubli.ts` le dit lui-même (« l'empreinte reconnaît la même phrase,
   pas une paraphrase »). SimHash reste EXPOSÉ dans le module et testé — il
   reste utile pour des textes longs (captures, pages) — mais ce n'est pas
   lui qui tranche pour memoire.md. Le choix Jaccard est mesuré, pas décoratif.

2. **Pierres tombales** (portées d'Oblivion via `trust/oubli.ts` : « ce qu'on
   oublie ne doit pas revenir »). `memoire_oublier` dépose l'empreinte
   (sha256 du texte plié — casse et accents retirés) de chaque ligne retirée
   dans `~/.local/root-tombes.json`. `memoire_noter` refuse ensuite toute
   réintroduction du même fait à casse/accents/blancs près. Jamais le texte
   oublié n'est conservé, seulement son empreinte. Pour corriger un fait,
   la procédure est `memoire_oublier` l'ancien, puis `memoire_noter` le
   nouveau — un quasi-doublon refuserait autrement le nouveau, ce qui est
   le comportement attendu.

Ce qui n'a PAS été porté, et pourquoi :

- **`trust/origine.ts`** : détecte si une ligne de CAPTURE D'ÉCRAN vient d'un
  terminal qui affiche un agent (screenpipe). Pertinent pour soulbook, pas
  pour memoire.md qui contient des faits curés écrits par l'agent lui-même,
  pas des lignes d'écran.
- **`trust/semantique.ts`** : juge de pertinence par appel à Ollama (modèle
  local en réseau). En contradiction directe avec mon principe « mémoire
  consultable, rien de magique » (memoire.py ne fait aucun appel modèle,
  aucune dépendance). Le tri reste mécanique.
- **`team/memoires.ts`** (le « modèle Lanterns ») : à la lecture c'est surtout
  un script d'ÉCRITURE vers `screenpipe /memories` — pas un schéma de curation.
  Ce n'est pas un modèle de mémoire durable, c'est un pipeline d'ingestion.
  Pas à porter tel quel.
- **« Pegasus » (mémoire par entité/nom)** : catégoriser des faits par auteur
  (« utilisateur », « agent », « tiers »). memoire.md a déjà des catégories,
  et la règle « un refus n'est pas une loi » est déjà celle de la curation
  (« note seulement ce qui reste vrai dans un mois »). Rien de plus à ajouter.

Tests ajoutés (test_memoire.py, classe TestQuasiDoublonsEtTombes,
16 tests hors réseau) :

- SimHash : identité, distance petite entre textes longs proches (mesuré : 15),
  distance grande entre textes disjoints (mesuré : 30), texte vide.
- Doublons : refus du quasi-doublon proche, refus du doublon exact, refus
  insensible à casse et accents (pliage), acceptation d'un fait vraiment
  nouveau.
- Tombes : oubli puis renotation refusée, insensibilité à la casse, tombe qui
  survit à la suppression de memoire.md (multi-sessions), correction possible
  via oublier+noter, seul l'empreinte est déposée (jamais le texte), format
  JSON sain.

Tous les tests passent : 275/275 dans le dépôt à l'instant de ce commit.
