# Root : recherche approfondie et sourcée

Axe tenu par Claude (cloud). Fichiers : `recherche.py`, `test_recherche.py`, ce document.

## Ce que le module apporte

Root peut répondre à une question en lisant de vraies pages web. Elle n'affirme comme sourcé que ce qui est relié à un extrait copié mot pour mot, et ce lien est recontrôlé localement dans le texte réellement récupéré. Le modèle propose les requêtes et rédige les affirmations. Le code exécute, borne et vérifie.

## Déroulé

1. **`recherche_web(question, sous_requetes, approfondir)`.** La question et jusqu'à huit sous-requêtes passent par la garde des requêtes. Celles qui sont acceptées partent vers le moteur. Les résultats des différentes requêtes sont entrelacés, pour varier les angles, puis dédoublonnés par adresse normalisée. Chaque page est récupérée sous budgets, son texte est extrait, masqué puis découpé en passages. Les meilleurs passages, classés par BM25, reviennent au modèle sous des identifiants stables : S1, S2…
2. **`recherche_lire(source, page)`.** Le modèle lit la suite d'une source, page par page, quand les passages choisis ne suffisent pas.
3. **`recherche_conclure(affirmations)`.** Chaque affirmation arrive avec ses citations, sous la forme d'un identifiant de source et d'un extrait. Chaque extrait est recherché dans le texte stocké de sa source. Le module renvoie un rapport Markdown et un statut par affirmation.

Avec `approfondir` à vrai, l'appel complète le dossier en cours. Les identifiants de sources et les compteurs de budget sont alors conservés. Sinon, un nouveau dossier remplace l'ancien.

## Statuts d'une affirmation

| Statut | Condition |
| :--- | :--- |
| Corroborée | Au moins une citation retrouvée dans chacun de deux domaines différents ou plus |
| Sourcée | Citations retrouvées, mais dans un seul domaine |
| À vérifier | Citations retrouvées, mais un chiffre de l'affirmation est absent des citations, ou aucun mot significatif n'est commun |
| Non sourcée | Aucune citation retrouvée |

Une citation est retrouvée quand l'extrait figure dans le texte de la source. La comparaison ignore la casse, les espaces, les variantes de guillemets, d'apostrophes et de tirets, ainsi que la normalisation Unicode. Une ellipse « … » coupe l'extrait en fragments qui doivent apparaître dans l'ordre. Un extrait doit faire entre 20 et 500 caractères, et chaque fragment au moins 8.

## Protection des données

- **Requête sortante.** Elle est refusée si elle contient un courriel, un numéro de téléphone, un numéro de carte valide selon Luhn, un IBAN, un chemin local, une URL avec identifiants, ou tout ce que `securite.rediger_secrets` masquerait. Cela couvre les clés connues et les motifs personnels déclarés localement dans la configuration de `securite`. Les listes d'années ne sont pas prises pour des numéros de téléphone.
- **Adresses.** Toute URL passe par `securite.url_sure`, et chaque redirection est suivie à la main pour être recontrôlée. Une page publique ne peut donc pas renvoyer vers une adresse interne ou de métadonnées cloud. Les paramètres de pistage et le fragment sont retirés avant la récupération.
- **Contenu.** Le texte des pages est masqué par `rediger_secrets` dès son stockage, puis toute sortie est emballée par `emballer_non_fiable`. `un_tour` n'emballe que les outils `web_*`, donc le module le fait lui-même.
- **Stockage.** Rien n'est écrit sur disque. Le dossier vit en mémoire et disparaît avec la session.

## Budgets par défaut

| Budget | Valeur |
| :--- | ---: |
| Requêtes par appel | 4 |
| Requêtes par dossier | 12 |
| Pages par appel | 8 |
| Pages par dossier | 24 |
| Pages par domaine | 2 |
| Secondes par appel | 120 |
| Délai par requête HTTP | 20 s |
| Octets lus par page | 5 Mo |
| Caractères gardés par source | 200 000 |
| Caractères de sortie d'exploration | 10 000 |
| Caractères de sortie de conclusion | 18 000 |

Les sorties restent sous la troncature de 20 000 caractères de `memoire.py`. Quand une sortie est coupée, la coupure se fait à l'intérieur de l'emballage, jamais sur sa balise de fermeture.

## Contrat de branchement pour Claude Code

Dans `root.py`, après la table `OUTILS` :

```python
import recherche
OUTILS.update(recherche.OUTILS_RECHERCHE)
```

Niveaux de risque proposés :

- **`recherche_web` : `web`.** La requête sort vers le moteur. En autonomie large, elle ne demande donc pas de confirmation. La garde des requêtes reste active dans tous les cas.
- **`recherche_lire` et `recherche_conclure` : `sûr`.** Aucun appel réseau.

`recherche.reinitialiser()` oublie le dossier courant, par exemple à la sortie de session.

## Moteur et transport

- **`MoteurDuckDuckGo`.** Il interroge DuckDuckGo sans clé, en version `html` par défaut ou `lite`. L'analyseur reconnaît les deux mises en page, les liens relatifs `/l/?uddg=…`, et se replie sur tout lien de redirection `uddg` si les classes connues manquent. Les annonces, les liens internes et les cibles qui ne sont pas http(s) sont écartés. Une page de contrôle anti-robot lève `anti_robot` : un blocage n'est jamais confondu avec une absence de résultats. Root garde son agent honnête et ne se fait pas passer pour un navigateur.
- **`MoteurBrave`.** API Brave Search, optionnelle. Elle passe en tête des moteurs seulement si la variable d'environnement `BRAVE_SEARCH_API_KEY` est définie au lancement. La clé part dans un en-tête vers l'hôte de l'API uniquement, jamais vers l'hôte d'une redirection, et n'apparaît dans aucun message ni dans `repr`. C'est la voie fiable si DuckDuckGo bloque les robots.
- **`MoteurWikipedia`.** Il interroge l'API publique de recherche de Wikipédia, en français par défaut. Cette API est prévue pour les programmes qui s'identifient, ce qui en fait un secours fiable.
- **`MoteursCombines`.** C'est le moteur par défaut. Il interroge Brave si la clé existe, puis DuckDuckGo, puis Wikipédia, et entrelace leurs résultats dans cet ordre. Un moteur en échec n'empêche pas l'autre, et son échec est consigné dans le dossier, par exemple `moteur_duckduckgo_http_403`. Un moteur qui renvoie une page anti-robot est suspendu pour toute la session : Root n'insiste pas auprès d'un site qui refuse les robots, et la cause devient `moteur_duckduckgo_suspendu_apres_anti_robot`.
- **`Robots`.** Avant chaque page, le fichier `robots.txt` du site est lu une fois, puis gardé pour la session. Les règles suivent la RFC 9309 avec l'agent `Root-recherche`. Un fichier absent ou refusé par une erreur 4xx autorise tout. Un site injoignable ou une erreur 5xx n'autorise rien. Le fichier passe par le même transport, donc par la même garde d'URL.
- **Texte principal.** Quand une page a un conteneur `main`, `article` ou `role="main"` d'au moins 400 caractères, seul son texte est gardé. Les bandeaux et listes de liens annexes disparaissent ainsi des passages.
- **PDF.** Les documents PDF sont lus en bibliothèque standard : objets directs et flux d'objets compressés, flux FlateDecode, arbre des pages dans l'ordre, polices de chaque page avec leur table ToUnicode, opérateurs de texte Tj, TJ, ' et ". Plafonds contre les PDF piégés : 10 Mo décompressés par flux, 40 Mo par document, 300 pages. Un PDF chiffré est refusé (`pdf_chiffre`). Un PDF tronqué à la récupération est refusé (`pdf_trop_volumineux`) plutôt que lu à moitié. Si le texte obtenu n'a pas assez de lettres, cas typique d'un document scanné ou d'une police sans table, il est refusé (`pdf_illisible`), jamais présenté comme lu. Un PDF servi comme `application/octet-stream` est reconnu à sa signature `%PDF`.
- **Récence.** `recherche_web` accepte `recence` : jour, semaine, mois ou annee. Brave reçoit `freshness` (pd, pw, pm, py) et DuckDuckGo `df` (d, w, m, y). Wikipédia et les références suivies ne savent pas filtrer par date ; la sortie le rappelle et invite à vérifier les dates de publication. Seuls les moteurs qui déclarent `accepte_recence` reçoivent le paramètre.
- **Langue des pages.** Seules les pages en français ou en anglais sont gardées. La langue vient de l'attribut `lang` de la page ; sans attribut, une estimation prudente compte les mots les plus fréquents de l'allemand, de l'espagnol, de l'italien et du néerlandais, et n'écarte la page que si ces langues dominent nettement. Dans le doute, la page est gardée. Une page écartée est consignée comme `langue_non_retenue`.
- **Bruit des wikis.** Les zones de classe MediaWiki connue sont retirées du texte : liens « modifier », appels de note comme « [1] », bandeaux de navigation, liste des références, catégories. Les liens externes qu'elles contiennent restent relevés, pour que les références soient suivies. Les passages et les citations portent ainsi sur le texte de l'article seul.
- **Références suivies.** Les liens externes d'une page MediaWiki, ceux de classe `external` comme les références d'un article Wikipédia, sont relevés à l'extraction. Après chaque page lue, jusqu'à trois de ces liens sont ajoutés aux pages à lire, ceux dont le texte partage le plus de mots avec la recherche. Un lien sans mot commun n'est jamais suivi. Ces sources primaires passent par les mêmes gardes, budgets et règles `robots.txt`, et apportent des domaines indépendants de Wikipédia. Le rapport indique « trouvée via S1 ».
- **`TransportHTTP`.** GET borné en taille et en temps, sans redirection automatique, avec un agent identifié. Seuls `text/html`, `application/xhtml+xml` et `text/plain` sont lus.
- **Remplacement.** Moteur et transport sont de simples fonctions injectables. Un autre moteur, par exemple une API à clé, se branche sans toucher au reste.

## Diagnostic sur la machine réelle

La sortie de `recherche_web` liste désormais les causes des échecs et refus, par exemple « 1 × moteur duckduckgo anti robot ». Pour un essai réel isolé :

```sh
python3 -B recherche.py --diagnostic "hauteur de la tour Eiffel"
```

Pour chaque moteur, ce mode affiche le nombre de résultats et les cinq premières adresses. Pour DuckDuckGo, il affiche aussi la structure de la page reçue : taille, titre, page anti-robot ou non, liens de résultats, liens `uddg`, classes de liens les plus fréquentes et actions des formulaires. Il n'affiche jamais le texte brut ni une clé. Il termine par l'en-tête de l'exploration complète et la liste des sources lues.

## Limites connues

- **Premier essai réel en échec, puis diagnostic.** Sur le Mac, Claude Code a d'abord obtenu zéro source. Le diagnostic relevé ensuite par Codex tranche : DuckDuckGo renvoie une page anti-robot de 14 284 caractères, sans aucun lien de résultat, et Wikipédia rend 8 résultats. Après la suspension du moteur bloqué et le suivi des références, Claude Code relève sur le Mac 8 résultats Wikipédia et 6 sources lues. Sans clé Brave, la recherche repose donc sur Wikipédia et sur les références suivies. Le nettoyage du bruit des wikis est testé sur une page écrite d'après la structure MediaWiki, pas encore sur un article réel.
- **Citation n'est pas preuve.** Une citation retrouvée prouve que ce texte figure dans la page consultée. Elle ne prouve ni que la page dit vrai, ni qu'elle soutient pleinement l'affirmation. Le rapport le dit en clair.
- **Indépendance approchée.** Le domaine racine est calculé sans la liste publique complète des suffixes, avec seulement quelques suffixes doubles comme `co.uk`. Deux sites distincts peuvent aussi reprendre une même dépêche.
- **Pages non lues.** Les pages qui affichent leur contenu en JavaScript sont écartées comme vides. Les PDF scannés, chiffrés ou à polices sans table de caractères ne sont pas lus, ni le texte des formulaires XObject. Les pages interdites par `robots.txt` ne sont pas lues, et un site dont le fichier est injoignable est sauté.
- **Moteurs et robots.** Les appels aux moteurs eux-mêmes ne consultent pas `robots.txt`. La page HTML de DuckDuckGo est conçue pour un humain, et elle refuse effectivement Root. Root ne contourne pas ce refus. L'API Brave Search, à clé, est la voie propre pour une recherche web générale.
- **Références.** Le choix des références repose sur les mots de leur texte, pas sur leur fiabilité. Une référence morte, en PDF ou interdite par `robots.txt` consomme une place sans rien apporter.
- **Garde DNS.** `url_sure` résout le nom, puis urllib le résout à nouveau. Un changement de DNS entre les deux reste théoriquement possible.
- **Chiffres.** Le contrôle compare les suites de chiffres. « 5,2 » et « 5,20 » sont donc différents, et l'affirmation passe « à vérifier ». L'erreur va vers la prudence.

## Vérifications exécutées

- **Tests du module.** `python3 -B -m unittest -v test_recherche` donne 97 tests verts en moins de deux secondes, sous Python 3.9 et 3.13, sans avertissement en mode `-X dev`. Pendant les tests, `socket.getaddrinfo`, `create_connection` et `gethostbyname` sont remplacés par une fonction qui échoue. Seule la classe `ServeurLocal` les rétablit, pour un serveur HTTP sur 127.0.0.1 qui exerce le vrai chemin urllib : redirection suivie, redirection vers 169.254.169.254 refusée, erreur 404.
- **Non-régression.** Avec l'autonomie, la vérification, l'action système et la mémoire, la commande commune de la CI passe : 214 tests.
- **Cas couverts :**
  - requêtes privées refusées et jamais envoyées ;
  - doublons et paramètres de pistage retirés, PDF écarté sans requête ;
  - plafond par domaine, budgets de durée, de pages et de requêtes conservés entre appels ;
  - pages vides, types refusés et erreurs HTTP ;
  - secret masqué ;
  - page piégée incapable de fermer l'emballage ;
  - citation inventée rejetée, ellipse dans le désordre rejetée ;
  - chiffre absent signalé, corroboration exigeant deux domaines ;
  - texte principal isolé, conteneur trop court ignoré ;
  - réponses Wikipédia lues ou rejetées, langue validée ;
  - moteurs combinés : entrelacement, secours, échec total, échecs consignés ;
  - robots.txt : règles et cache, groupe propre à l'agent, absence, site injoignable, page interdite jamais récupérée ;
  - DuckDuckGo version lite, lien relatif, repli sur les liens `uddg`, cible `javascript:` écartée, page anti-robot nommée, diagnostic sans texte ;
  - Brave : réponse lue ou rejetée, clé en en-tête seulement, jamais transmise après une redirection vers un autre hôte, ajoutée seulement si la variable existe ;
  - causes visibles dans la sortie de l'outil, mode diagnostic exécuté hors ligne sans exception ;
  - liens externes relevés hors menus, références choisies par mots communs, suivies sous budget de pages, origine indiquée au rapport ;
  - moteur suspendu après une page anti-robot, mais pas après un autre échec.
  - PDF fabriqués dans les tests : échappements, tableaux TJ, chaînes hexadécimales, image en ligne sautée, polices composites dont les codes se recouvrent, objets dans un flux d'objets, ordre des pages, chiffré, scanné, bruit, bombe de décompression, lecture et corroboration par le chercheur ;
  - langue des pages et filtre de récence ;
  - article au format MediaWiki : appels de note, liens « modifier », bandeau, références et catégories absents du texte, référence toujours relevée, citation du texte propre vérifiée.

## Suite proposée

1. Décision de l'utilisateur : créer ou non une clé Brave Search. Sans elle, la recherche se limite à Wikipédia et aux sources que ses articles citent.
2. Fait : le diagnostic sur le Mac montre 6 sources lues via Wikipédia. Le relancer après ce nettoyage confirmerait que les passages des articles réels sont propres.
3. Un essai complet avec le modèle, quand tous les axes sont terminés.
