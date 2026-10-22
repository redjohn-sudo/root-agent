# Root, moteur de red team IA — conception

Feuille de route pour faire de Root, en plus d'un assistant personnel, un **moteur
de red team et de sécurité de l'IA**. Né d'une veille GitHub du 22/10/2026 (quatre
sous-agents, ~50 dépôts réels vérifiés). Ce document ne touche pas au code : c'est
la carte, à construire par étapes.

Point de départ honnête : Root a déjà les trois quarts des fondations. Son module
d'**immunité** (une erreur vue une fois, retrouvée ailleurs) est, à peu de choses
près, le cœur d'un moteur de red team. La garde anti-injection, le masquage des
secrets, le consentement et la vérification de citations sont les briques de
défense. Il ne s'agit pas de partir de zéro, mais de **brancher** ce qui existe.

Cadre, non négociable : tout usage offensif reste sur **cibles autorisées** — labos
perso, plateformes CTF (Root-Me, HTB, picoCTF, OverTheWire), et strictement le
périmètre déclaré d'un programme de bug bounty.

---

## 1. Les harnais les plus proches de Root (à lire et comparer)

| Projet | Lang / ~★ | À reprendre |
|---|---|---|
| [ipa-lab/hackingBuddyGPT](https://github.com/ipa-lab/hackingBuddyGPT) | Python ~1,3k | Le plus proche. `task_solved` **vérifié contre la réalité** (recoupe « j'ai un shell » avec la vraie sortie). Le pacte de sincérité codé. |
| [frdel/agent-zero](https://github.com/frdel/agent-zero) | Python ~19k | Comportement dans des fichiers de prompt éditables, sous-agents avec budget propre. |
| [dreadnode/rigging](https://github.com/dreadnode/rigging) | Python ~0,4k | Simule le tool-calling pour les modèles qui ne l'ont pas nativement (utile pour Qwen local). |
| [GreyDGL/PentestGPT](https://github.com/GreyDGL/PentestGPT) | Python ~16k | Arbre de tâches qui garde le fil raisonnement/parsing/commandes. |
| [SWE-agent/SWE-agent](https://github.com/SWE-agent/SWE-agent) (EnIGMA) | Python ~20k | Agent-Computer Interface : outils à **sortie propre et bornée**, pas un shell brut. |
| [block/goose](https://github.com/block/goose) | Rust ~55k | Protocole d'outils **MCP** + couche provider pour LLM interchangeables. |
| [letta-ai/letta](https://github.com/letta-ai/letta) (MemGPT) | Python ~25k | L'agent **édite sa propre mémoire** (core + archive vectorielle paginée). |

Autres harnais personnels notés : openinterpreter/open-interpreter (code-as-action
+ confirmation par action), huggingface/smolagents (cœur minimal CodeAct),
All-Hands-AI/OpenHands (event-stream + runtime isolé), simonw/llm (plugins +
journal SQLite), khoj-ai/khoj (RAG perso + planification).

---

## 2. Le squelette à reprendre (ce qui structure tout)

1. **Cœur à plugins façon garak** ([NVIDIA/garak](https://github.com/NVIDIA/garak), ~9,7k) :
   séparer **probe** (l'attaque) / **detector** (juge du succès) / **generator**
   (le cerveau) / **harness** (orchestre) / **evaluator** (rapport). Chaque famille
   auto-découverte. C'est la fondation qui rend tout le reste composable.
2. **Matrice vulnérabilité × enveloppe** ([confident-ai/deepteam](https://github.com/confident-ai/deepteam), ~3k) :
   le « quoi » (fuite de prompt, exfil, abus d'outil) séparé du « comment »
   (Crescendo multi-tours, Base64, ROT13, Unicode). N'importe quelle cible × livraison.
3. **Mémoire auto-gérée MemGPT** (Letta) : fusionne mémoire durable **et**
   compression de contexte en un seul mécanisme à deux niveaux.
4. **Journal event-stream en SQLite** (OpenHands + simonw/llm) : chaque tour
   sérialisé → reprise après crash, audit, calibration.
5. **Bac à sable d'exécution** ([trycua/cua](https://github.com/trycua/cua),
   [e2b-dev/E2B](https://github.com/e2b-dev/E2B), OpenHands) : exécuter code et
   pilotage dans une micro-VM ou un conteneur durci (no-new-privileges,
   capabilities droppées, FS lecture seule, réseau refusé par défaut), pas sur l'hôte.

---

## 3. Modes d'attaque à brancher comme outils

| Projet | À reprendre |
|---|---|
| [patrickrchao/JailbreakingLLMs](https://github.com/patrickrchao/JailbreakingLLMs) (PAIR) | LLM attaquant qui raffine ses prompts d'après le feedback de la cible. |
| [RICommunity/TAP](https://github.com/RICommunity/TAP) | Tree of Attacks with Pruning : recherche en arbre avec élagage. |
| [utkusen/promptmap](https://github.com/utkusen/promptmap) | Règles d'attaque en **YAML**, jugées par un LLM contrôleur, N tentatives. |
| [WithSecureLabs/spikee](https://github.com/WithSecureLabs/spikee) | Payloads d'injection **composables en pipe** (plugins + attacks). |
| [centerforaisafety/HarmBench](https://github.com/centerforaisafety/HarmBench) | Format commun pour comparer attaques × modèles. |
| [perplext/LLMrecon](https://github.com/perplext/LLMrecon) | Encodeurs d'évasion (Unicode smuggling), injection RAG indirecte. |
| [BishopFox/BrokenHill](https://github.com/BishopFox/BrokenHill) | Suffixes adverses par gradient (GCG) pour modèles open-weights. |
| [verazuo/jailbreak_llms](https://github.com/verazuo/jailbreak_llms) | Corpus ~15k prompts in-the-wild, prêt à alimenter la bibliothèque. |

---

## 4. Pentest / CTF

| Projet | À reprendre |
|---|---|
| [NYU-LLM-CTF/nyuctf_agents](https://github.com/NYU-LLM-CTF/nyuctf_agents) (D-CIPHER) | Planner / Executor spécialisés (web, crypto, pwn), état partagé. |
| [usestrix/strix](https://github.com/usestrix/strix) | Validation par **PoC en sandbox** avant de déclarer une faille ; Graph of Agents. |
| [aielte-research/HackSynth](https://github.com/aielte-research/HackSynth) | Module Summarizer qui compresse l'historique à chaque tour. |
| [protectai/vulnhuntr](https://github.com/protectai/vulnhuntr) | Contexte par chaîne d'appels (source→sink), pas un dump complet. |
| [cyproxio/mcp-for-security](https://github.com/cyproxio/mcp-for-security) | Patron MCP pour envelopper nmap, ffuf, sqlmap, nuclei… un par un. |
| [berylliumsec/nebula](https://github.com/berylliumsec/nebula) | Un projet = un engagement, scope + validations humaines, capture de preuves. |
| [andyzorigin/cybench](https://github.com/andyzorigin/cybench), [0ca/BoxPwnr](https://github.com/0ca/BoxPwnr) | Bancs d'essai pour mesurer Root objectivement (succès par sous-tâche, First Solve Time). |

---

## 5. Durcir Root (défense)

| Projet | Brique |
|---|---|
| [protectai/rebuff](https://github.com/protectai/rebuff), [deadbits/vigil-llm](https://github.com/deadbits/vigil-llm) | **Jetons canari** dans le system prompt : s'ils ressortent → fuite/détournement, on bloque. |
| [snyk/agent-scan](https://github.com/snyk/agent-scan) (ex mcp-scan) | **Empreinte des outils** au consentement, revérifiée à l'exécution (anti « rug pull »). |
| [trufflesecurity/trufflehog](https://github.com/trufflesecurity/trufflehog) | Détecte **et vérifie** si une clé fuitée est encore active ; renforce le masquage. |
| [microsoft/presidio](https://github.com/microsoft/presidio) | Détection + anonymisation réversible de PII avant tout appel cloud. |
| [vectara/HHEM](https://github.com/vectara/hallucination-leaderboard), [patronus-ai/Lynx](https://github.com/patronus-ai/Lynx-hallucination-detection) | Juge de fidélité **local** (GGUF/Ollama) : scorer chaque affirmation contre sa source. |
| [invariantlabs-ai/invariant](https://github.com/invariantlabs-ai/invariant) | Politiques sur la **séquence d'actions** (ex. lire un doc externe PUIS envoyer = interdit). |
| garak + [ethz-spylab/agentdojo](https://github.com/ethz-spylab/agentdojo) | Banc de régression de la garde, en CI, pour chiffrer le taux de blocage. |

---

## Le plan, en trois temps

Chaque étape s'appuie sur ce que Root a déjà, et respecte le cadre autorisé.

1. **Cœur à plugins (garak).** Refondre la façon dont Root tient ses capacités de
   sécurité : probe / detector / generator / harness. C'est la fondation ; sans
   elle, tout le reste reste du bricolage.
2. **Immunité → mémoire d'attaques.** Généraliser le module d'immunité aux
   injections : chaque attaque vue est embeddée et retrouvée par similarité
   ailleurs, avec les **jetons canari** pour la détection. Défensif et offensif
   d'un coup.
3. **Mode attaquant-LLM (PAIR/TAP).** Premier vrai outil d'attaque autonome : un
   LLM qui raffine ses prompts en arbre, pilotable sur un modèle local.

Rigueur, en parallèle : passer garak + AgentDojo en banc de régression, et mesurer
sur cybench/BoxPwnr plutôt qu'au ressenti. Les benchmarks publics peuvent être
gonflés si l'agent a accès au web (writeups) : vérifier sur de l'inconnu.

---

## Sources de veille à suivre

awesome-llm-security (corca-ai), awesome-ai-offensive-security (yeyintminthuhtut),
Awesome-LLM-Red-Teaming (user1342), Awesome-Offensive-AI-Agentic-Landscape (Yeti-791).
