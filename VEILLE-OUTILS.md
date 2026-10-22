# Veille outils — Root (23/10/2026)

Récolte de 6 recherches parallèles (web + API GitHub, étoiles/activité vérifiées le
23/10/2026). But : muscler Root côté cyber **et** côté cœur (boucle, inférence,
mémoire, éval). Tri par priorité. Les outils déjà dans notre registre (promptfoo,
PyRIT, agentdojo, inspect_ai, mlx-lm, litellm, langfuse, graphiti, fastmcp, textual,
pycryptodome, gmpy2, sympy, z3, pwntools, RsaCtfTool, radare2, binwalk, exiftool,
john, steghide, sagemath, semgrep, ast-grep, ripgrep, mitmproxy, burpsuite) sont
signalés « déjà au registre » quand ils reviennent.

Convention : **P1** = à brancher vite, **P2** = fort intérêt, **P3** = selon besoin.
Les licences/étoiles marquées « à vérifier » ne sont pas confirmées à la source.

---

## 0. À brancher en premier (le top transversal)

Si on ne fait que 10 choses, c'est celles-là :

1. **vLLM** ou **SGLang** sur la tour (serveur concurrent, API OpenAI) — P1
2. **llama-swap** devant tour + Mac (un endpoint, modèles à la demande) — P1
3. **XGrammar** (tool calls 100% valides, zéro retry) — P1
4. **mini-swe-agent** (boucle sans tool-calling natif, pour les cerveaux locaux) — P1
5. **Vulnhuntr** (analyse statique LLM input→sink, PoC) — P1 cyber
6. **garak** (bibliothèque de probes red team, modèle qu'on imite déjà) — P1 cyber
7. **Burp MCP officiel** (Root pilote Burp + Autorize) — P1 cyber
8. **angr** + **Ghidra headless/ghidrecomp** + **Chepy** (le trio CTF) — P1 CTF
9. **Chonkie + bge-m3 + sqlite-vec** (RAG de code greffé sur notre SQLite) — P1
10. **deepeval + promptfoo** (mesurer si Root progresse, juge local) — P1

Lecture de fond avant de refactorer la boucle : *« Harness Engineering: Anatomy,
Architecture, and Evolution of Coding Agents »* (arXiv 2609.00006), étude du code de
11 harness.

---

## 1. Harness / boucle d'agent (forker ou s'inspirer)

| Outil | Lien | Apport pour Root | Prio |
|---|---|---|---|
| mini-swe-agent | github.com/SWE-agent/mini-swe-agent | boucle ~100 lignes, parse le texte au lieu du tool-call → mode de secours pour ollama | P1 |
| Codex CLI (profil Seatbelt) | github.com/openai/codex | leur politique `sandbox-exec` macOS = référence pour durcir `sandbox.py` | P1 |
| Claude Agent SDK | github.com/anthropics/claude-agent-sdk-python | hooks + `permissionDecision` → formaliser permissions/budgets ; AgentDefinition pour sous-agents | P1 |
| SWE-agent / EnIGMA | github.com/SWE-agent/SWE-agent | ACI (exposer des outils interactifs) + mode CTF état de l'art (NYU CTF, Cybench) | P1 |
| smolagents | github.com/huggingface/smolagents | CodeAct (actions en code Python) + abstraction « executor » pour brancher notre Seatbelt | P2 |
| gptme | github.com/gptme/gptme | cousin le plus proche de Root : shell, python, navigateur, MCP, plugins, sandbox Wasmtime | P2 |
| OpenHands | github.com/All-Hands-AI/OpenHands | event stream + abstraction Runtime (séparer boucle et runtime d'exécution) | P2 |
| cdp-use | github.com/browser-use/cdp-use | bindings CDP typés réutilisables tels quels pour `navigateur.py` | P2 |
| browser-use | github.com/browser-use/browser-use | représentation DOM/accessibilité donnée au modèle | P2 |
| Pydantic-AI | github.com/pydantic/pydantic-ai | tool-calling typé/validé + durable execution (reprise après panne) | P2 |
| LangGraph | github.com/langchain-ai/langgraph | checkpointing : pause/reprise, time-travel, human-in-the-loop | P2 |
| Letta (MemGPT) | github.com/letta-ai/letta | architecture mémoire core/archival/recall, auto-édition par l'agent | P2 |
| Aider | github.com/Aider-AI/aider | repo map (tree-sitter + ranking) + formats d'édition robustes, réparation de diff | P2 |
| OpenAI Agents SDK | github.com/openai/openai-agents-python | handoffs + guardrails + sessions, patterns multi-agent minimalistes | P3 |
| Goose | github.com/aaif-goose/goose | recettes YAML + couche anti-injection (Rust, inspiration) | P3 |
| Cline | github.com/cline/cline | UX d'approbation humaine des actions + checkpoints (inspiration UI) | P3 |
| CrewAI / Agno / AG2 | — | patterns rôles/équipes multi-agent | P3 |
| Dyad | github.com/dyad-sh/dyad | modèle UX desktop local « bring your own key » (parallèle pywebview) | P3 |

Alerte licence : **Open Interpreter** est AGPL-3.0 (contaminant) → inspiration
seulement pour l'édition publique, ne pas copier de code.

---

## 2. Red team IA & datasets

**Outils / frameworks**

| Outil | Lien | Apport | Prio |
|---|---|---|---|
| garak (NVIDIA) | github.com/NVIDIA/garak | catalogue de probes/detectors, le modèle qu'on imite déjà | P1 |
| HarmBench | github.com/centerforaisafety/HarmBench | classifier de succès d'attaque sérieux (remplace « refus/pas refus ») | P1 |
| StrongREJECT | github.com/alexandrasouly/strongreject | juge qui note l'utilité réelle de la réponse, pas le refus | P1 |
| llm-guard (ProtectAI) | github.com/protectai/llm-guard | scanners input/output : injection, PII, secrets, toxicité | P1 |
| Spikee | github.com/WithSecureLabs/spikee | toolkit injection directe/indirecte + contournement guardrails | P1 |
| InjecAgent | github.com/uiuc-kang-lab/injecagent | injection indirecte sur agents outillés (1054 cas) — pile notre cas | P1 |
| AgentDojo | github.com/ethz-spylab/agentdojo | banc d'essai attaque d'agents par injection dans les sorties d'outils | P2 |
| AgentHarm | huggingface.co/datasets/ai-safety-institute/AgentHarm | agent jailbreaké garde-t-il ses capacités (110 tâches) | P2 |
| ASB (Agent Security Bench) | github.com/agiresearch/ASB | injection + memory poisoning + backdoor (tester notre RAG) | P2 |
| Meta Prompt Guard 2 | huggingface.co/meta-llama | classifier injection léger, local Apple Silicon | P2 |
| PINT Benchmark | github.com/lakeraai/pint-benchmark | noter nos détecteurs sur une base neutre | P2 |
| EasyJailbreak | github.com/EasyJailbreak/EasyJailbreak | assemble plusieurs méthodes (GPTFuzz, AutoDAN, GCG) en recipes | P2 |
| PAIR / TAP | github.com/patrickrchao/JailbreakingLLMs | jailbreak boîte-noire adaptatif (LLM attaquant vs cible) | P2 |
| Guardrails AI | github.com/guardrails-ai/guardrails | hub de validators (⚠ CVE-2026-31233, isoler l'install) | P3 |
| vigil / rebuff | github.com/deadbits/vigil-llm | défense (quasi abandonnés, piocher les idées : YARA, canary) | P3 |

**Datasets d'attaque** (corpus de probes)

- **AdvBench** (dans github.com/llm-attacks/llm-attacks) — socle, P2
- **In-the-Wild / DAN** (huggingface TrustAIRLab) — 15 140 prompts réels, P1
- **JBB-Behaviors** (JailbreakBench) — comportements alignés policies, P1
- **HackAPrompt** (600k+ prompts, brut) — P2
- **WildJailbreak** (AllenAI, 262k + hard negatives) — mesure faux positifs, P2
- **deepset/prompt-injections** — jeu propre léger pour CI, P2
- **BeaverTails** (PKU, 330k QA safety-labeled) — P3

**Référentiels** (taxonomie du journal SQLite)

- **OWASP GenAI/LLM Top 10 2026** — colonne `owasp_category`, P1
- **MITRE ATLAS** (atlas.mitre.org) — tag `atlas_technique`, P1
- **AI Incident Database** / **AVID** — contexte incidents, P3

---

## 3. Pentest / bug bounty / MCP sécurité

Constat honnête : **aucun SAST open source ne détecte l'IDOR de façon fiable**
(logique métier). Le combo réaliste = règles dataflow custom (CodeQL) + agent LLM
input→sink (Vulnhuntr) + test dynamique via Burp.

**Axe autorisation / IDOR (notre focus)**

| Outil | Lien | Apport | Prio |
|---|---|---|---|
| Vulnhuntr | github.com/protectai/vulnhuntr | analyse statique LLM input→sink + PoC, pilotable ollama | P1 |
| Strix | github.com/usestrix/strix | agent autonome ciblant broken access control / IDOR, PoC réel (71k★) | P1 |
| Shannon | github.com/KeygraphHQ/shannon | analyse code source puis exploite pour prouver | P2 |
| AutorizePro | github.com/WuliRuler/AutorizePro | extension Burp : rejoue trafic privilégié en bas-privilège (IDOR) | P2 |
| Autorize / AuthMatrix | github.com/PortSwigger/autorize | baseline test d'autorisation multi-rôles (Burp) | P3 |
| CodeQL | github.com/github/codeql | requêtes dataflow custom pour autorisation manquante (CWE-862) | P2 |

**MCP servers sécurité** (outils exposés à un agent)

| Outil | Lien | Apport | Prio |
|---|---|---|---|
| Burp MCP officiel | github.com/PortSwigger/mcp-server | Root pilote Burp + Autorize via MCP | P1 |
| Semgrep MCP | github.com/semgrep/mcp | scanner→findings→fix→re-scan, wrapper propre de notre semgrep | P2 |
| pd-tools-mcp | github.com/intelligent-ears/pd-tools-mcp | suite ProjectDiscovery en MCP clé en main | P2 |
| mcp-for-security / Bolt | github.com/cyberstrikeus/bolt | 22-33 outils en MCP (⚠ `run_command` arbitraire à sandboxer) | P3 |

**Recon / fuzzing / secrets (briques CLI pilotables)**

- **nuclei, httpx, subfinder, katana** (ProjectDiscovery) — sorties JSON, P1/P2
- **Amass** (OWASP) — surface d'attaque, P2
- **gau + waybackurls** — endpoints oubliés, P2
- **ffuf** + **feroxbuster** — fuzzing (dirs/params), P1/P2
- **Arjun** + **Kiterunner** + **x8** — paramètres cachés + routes API (cibles IDOR), P2
- **TruffleHog** (secrets vérifiés) + **Gitleaks** (pre-commit), P2
- SAST par langage : **Bandit** (Py), **gosec** (Go), **Brakeman** (Rails), **njsscan** (Node) — P3
- **Opengrep** — fork Semgrep OSS 100% libre, P3

**Agents de pentest**

- **PentAGI** (github.com/vxcontrol/pentagi) — multi-agent, isolation Docker, P2
- **HackingBuddyGPT** (github.com/ipa-lab/hackingBuddyGPT) — construire ses agents en ~50 lignes, P2
- **PentestGPT** / **Nebula** — raisonnement guidé (Nebula supporte DeepSeek local), P3

**Harness « code audit » récents** (logique input→sink, à regarder)

- **Anthropic defending-code-reference-harness** — découverte/triage/patch avec Claude, direct pour nous, P2
- **Visa visa-vulnerability-agentic-harness** — SAST agentique (Markdown+SARIF), P2
- **Capital One VulnHunter** / **Google Mantis** — audit attaquant-first + filtre faux positifs, P2

**Cartes de l'écosystème** : awesome-security-agent-harnesses (Ed-Marcavage),
awesome-ai-pentest (insidetrust).

---

## 4. Inférence & orchestration (tout vérifié API GitHub)

**Serving GPU (tour Fedora CUDA)**

| Outil | Lien | Apport | Prio |
|---|---|---|---|
| vLLM | github.com/vllm-project/vllm | serveur concurrent (PagedAttention, batching), FP8/INT4 | P1 |
| SGLang | github.com/sgl-project/sglang | RadixAttention : énorme sur prompts système/RAG répétés | P1 |
| LMCache | github.com/LMCache/LMCache | cache KV hiérarchique, jusqu'à 15x sur contexte long/RAG | P1 |
| KTransformers | github.com/kvcache-ai/ktransformers | gros MoE sur 1 GPU via offload RAM (modèles plus gros) | P2 |
| EAGLE-3 + SpecForge | github.com/SafeAILab/EAGLE | décodage spéculatif x2-3 en latence (agent interactif) | P2 |
| ExLlamaV3 + TabbyAPI | github.com/turboderp-org/exllamav3 | EXL3 : plus gros Qwen3 à bas bits (⚠ TabbyAPI AGPL si exposé) | P2 |
| llm-compressor | github.com/vllm-project/llm-compressor | produire soi-même les poids quantifiés (AWQ/GPTQ/FP8) | P2 |
| LMDeploy / GPTQModel / FlashInfer | — | serving/quant alternatifs, noyaux CUDA | P3 |

⚠ **TGI** est archivé (03/2026), ne pas partir dessus.

**Orchestration / routing (les deux machines)**

| Outil | Lien | Apport | Prio |
|---|---|---|---|
| llama-swap | github.com/mostlygeek/llama-swap | un endpoint, modèles levés/déchargés par leur nom (tour + Mac) | P1 |
| vLLM Semantic Router | github.com/vllm-project/semantic-router | route selon la difficulté (Mac / tour / cloud) | P2 |
| GPUStack | github.com/gpustack/gpustack | voir tour + Mac comme un pool unique | P2 |
| RouteLLM | github.com/lm-sys/RouteLLM | routeur coût/qualité (code figé, s'inspirer) | P3 |
| BentoML | github.com/bentoml/BentoML | packaging en service (plus tard) | P3 |

**Sorties structurées**

- **XGrammar** (github.com/mlc-ai/xgrammar) — tool calls 100% valides, P1
- **Outlines** (github.com/dottxt-ai/outlines) — JSON Schema/regex/CFG, P2
- **lm-format-enforcer**, **guidance** — garde-fous de format, P3

**Apple Silicon (Mac M5 Pro)**

- **EXO** (github.com/exo-explore/exo) — fédérer tour + Mac pour un très gros modèle, P2
- **mlx-omni-server** (github.com/madroidmaq/mlx-omni-server) — modèles MLX du Mac en API OpenAI derrière llama-swap, P2
- **FastMLX** / **mlx-vlm** — serveur MLX alternatif / vision, P3
- À tester : **MTPLX**, **mlx-serve** (spéculatif MLX, jeunes), P3

Séquence conseillée : vLLM/SGLang + XGrammar → LMCache si contexte long →
llama-swap devant les deux → EAGLE-3 → Semantic Router/GPUStack quand le routing
cloud/local devient le vrai sujet. KTransformers et EXO = leviers « modèles plus gros ».

---

## 5. CTF / reverse / crypto / forensics

Reco transverse : une **image Docker Linux x86_64 « ctf-tools »** que Root invoque
depuis le bac à sable (Ghidra, gdb+pwndbg, Qiling tournent mieux sous Linux).

**Cœur scriptable (P1)**

| Outil | Lien | Apport | Prio |
|---|---|---|---|
| angr | github.com/angr/angr | exécution symbolique (embarque claripy, pas besoin d'ajouter z3) | P1 |
| Ghidra headless + PyGhidra | github.com/NationalSecurityAgency/ghidra | décompilation C de qualité, scriptable sans GUI | P1 |
| ghidrecomp | github.com/clearbluejar/ghidrecomp | décompile tout un binaire en une commande (enrobage CLI de Ghidra) | P1 |
| Chepy | github.com/securisec/chepy | « CyberChef en Python », opérations chaînables | P1 |
| Qiling | github.com/qilingframework/qiling | émulation complète avec hooks (exécuter un binaire inconnu en sécurité) | P1 |
| Frida | github.com/frida/frida | instrumentation dynamique scriptable, natif macOS/ARM64 | P2 |

**Pwn**

- **pwndbg** / **GEF** (debugger gdb scriptable en batch) — P2 (choisir un)
- **one_gadget** + **libc-database** + **pwninit** — chaîne pwn libc, P2
- **angrop** / **Ropper** (ROPgadget équivalent) — chaînes ROP, P2
- **Unicorn** / **Keystone** / **Capstone** — émulation/asm/désasm bas niveau, P2/P3
- **villoc** — visualisation heap, P3

**Reverse avancé**

- **LIEF** — parse+modifie ELF/PE/Mach-O (utile Apple Silicon), P2
- **capa** + **FLOSS** (Mandiant) — capacités d'un binaire + chaînes obfusquées, P2
- **Triton** / **Miasm** / **Manticore** (⚠ AGPL) — symbolic alternatifs, P2/P3
- **ghidriff** (patch-diff décompilé), **pypcode**, **pyelftools** — P3

**Crypto / encodage auto**

- **Ares** (github.com/bee-san/Ares) — décodage auto « blob inconnu », P2
- **Chepy** (déjà cité) — chaînage, P1
- **xortool** — XOR répété, P2
- **FeatherDuster/Cryptanalib** — cryptanalyse auto (vieux, pour la lib), P3
- **Ciphey** — secours API Python d'Ares, P3

**Forensics / stégano / web offline**

- **Volatility 3** — dumps mémoire, P2
- **The Sleuth Kit** + **plaso** — disque / timeline, P2/P3
- **StegoVeritas** (meilleur « StegSolve scriptable ») + **zsteg** + **Stegseek** — P2
- **scapy** — pcap/réseau, P2
- **Kaitai Struct** + **construct** — formats binaires custom, P2/P3
- **jwt_tool** — attaques JWT, P2
- **sqlmap** (API REST) / **commix** / **nuclei** — web, P3
- **hashid / Name-That-Hash** — identifier un hash avant crack, P3

⚠ **Binary Ninja** (payant) et **Cutter** (GUI) écartés au profit de Ghidra/PyGhidra.

---

## 6. Mémoire / RAG / éval / observabilité / MCP

**Mémoire d'agent**

| Outil | Lien | Apport | Prio |
|---|---|---|---|
| Letta (MemGPT) | github.com/letta-ai/letta | memory blocks éditables, work vs archival (modèle à copier) | P1 |
| mem0 (OSS) | github.com/mem0ai/mem0 | extraction de faits 100% local sur Qdrant (⚠ pousse vers son cloud) | P1 |
| cognee | github.com/topoteretes/cognee | graphe mémoire + vecteurs (stores locaux), sans dépendre de graphiti | P2 |
| Memobase / A-MEM / Zep | — | mémoire profil / Zettelkasten / conversationnelle (secondaires) | P3 |

**RAG sur code et docs**

| Outil | Lien | Apport | Prio |
|---|---|---|---|
| Chonkie | github.com/chonkie-inc/chonkie | CodeChunker AST tree-sitter (165 langages) | P1 |
| FlagEmbedding / bge-m3 | github.com/FlagOpen/FlagEmbedding | embeddings + reranker état de l'art, 100% local | P1 |
| rerankers (Answer.AI) | github.com/answerdotai/rerankers | API unifiée pour tous les rerankers, change en 1 ligne | P1 |
| sqlite-vec | github.com/asg017/sqlite-vec | recherche vectorielle dans le SQLite existant, zéro infra | P1 |
| LanceDB | github.com/lancedb/lancedb | base vectorielle embarquée versionnée (rien à déployer) | P2 |
| LightRAG | github.com/HKUDS/LightRAG | GraphRAG local léger (bien moins cher que MS GraphRAG) | P2 |
| LlamaIndex | github.com/run-llama/llama_index | boîte RAG complète (n'importer que `core` + intégrations locales) | P2 |
| Qdrant | github.com/qdrant/qdrant | store vectoriel solide (défaut de mem0) | P2 |
| txtai / Haystack / nano-graphrag / R2R | — | index tout-en-un / pipelines / GraphRAG hackable / service RAG | P3 |
| RAGatouille (ColBERT) / RAGFlow | — | retrieval précis code (ralenti) / docs riches (lourd) | P3 |

Embeddings de code à essayer : `nomic-embed-code`, `jina-embeddings-v2-base-code`,
`SFR-Embedding-Code`.

**Évaluation d'agents**

- **deepeval** (github.com/confident-ai/deepeval) — « pytest pour LLM », métriques d'agent/trajectoire, juge local, P1
- **promptfoo** (déjà au registre) — non-régression + red-team, P1
- **ragas** — métriques RAG (faithfulness, context recall), P2
- **AgentOps** / **TruLens** — trajectoires, replay, feedback continu, P2/P3

**Observabilité / tracing**

- **OpenLLMetry** (github.com/traceloop/openllmetry) — instrumentation OTel, évite le verrou, P1
- **Phoenix** (Arize, ⚠ licence Elastic) ou **Opik** (Comet, Apache-2.0) — visualiser en local, P1
- **Laminar** / **Helicone** / **OpenLIT** (télémétrie GPU) / **Langtrace** — alternatives, P2/P3

**Serveurs & registres MCP**

- **Serveurs de référence MCP** (github.com/modelcontextprotocol/servers) — filesystem, git, fetch, memory, P1
- **Serena** (github.com/oraios/serena) — édition de code par symboles via LSP (utile aussi pour 42 en C), P1
- **context7** (⚠ service en ligne) — doc à jour des libs, P2
- **Registre officiel MCP** + **awesome-mcp-servers** — découverte, P2
- **bytebase/dbhub** — MCP multi-SGBD local, P3

Pile RAG minimale conseillée : Chonkie + bge-m3 + rerankers + sqlite-vec (greffé sur
le journal SQLite), LightRAG si graphe voulu, deepeval/promptfoo/ragas pour l'éval.

---

## 7. Pièges & licences (honnêteté)

- **Open Interpreter** = AGPL-3.0, **Manticore** = AGPL, **TabbyAPI** = AGPL, **Bolt** = AGPL,
  **Arjun** = AGPL : contaminantes → inspiration pour l'édition publique, pas de copie.
- **Phoenix** = Elastic-2.0 (restrictions commerciales), **CodeQL** = licence GitHub
  (gratuit recherche/OSS, à vérifier pour usage commercial).
- **Bolt / Arkana / « 50+ tools MCP »** : dépôts jeunes avec exécution shell arbitraire
  → auditer et sandboxer sévèrement avant de laisser Root les piloter.
- **TGI** archivé, **rebuff** archivé, **vigil** quasi abandonné, **RouteLLM** figé,
  **Ciphey** remplacé par Ares, **Nosey Parker** archivé : à ne pas prendre comme base vivante.
- **garak** : ses detectors regardent surtout le refus → relire les logs, biais connu.
- IDOR : pas d'outil statique « prêt à l'emploi » fiable, c'est le gap que comble le combo LLM+dataflow.

---

## 8. Prochaines actions possibles (à décider par Vincent)

- Ajouter au registre `outils_externes.py` les P1 cyber installables en pip/brew
  (garak, llm-guard, vulnhuntr, ffuf, nuclei, httpx, trufflehog, gitleaks, angr,
  qiling, chepy, lief, capa, floss, stegoveritas, ares).
- Prototyper la pile RAG locale (Chonkie + bge-m3 + sqlite-vec) sur le journal.
- Benchmarker vLLM vs SGLang sur le trafic réel de la tour, puis poser llama-swap.
- Brancher garak comme generator red team et remplacer la détection « refus » par
  HarmBench/StrongREJECT.

Rien n'est installé ni modifié par cette veille : c'est un inventaire de pointeurs
publics. Les décisions d'intégration restent à toi.
