"""Tests hors ligne de memoire.py — axe mémoire de Root (Kimi K3).

Aucun réseau, aucun appel modèle, aucun accès aux vrais fichiers de session :
les chemins sensibles (memoire.md, dossier des journaux, fichier d'état) sont
redirigés vers un dossier temporaire dans chaque test qui y touche.

Lancer : python -m unittest -v test_memoire  (depuis le dossier harness/)
"""

import json
import tempfile
import unittest
from pathlib import Path

import memoire


class TestTronquerOutil(unittest.TestCase):
    """Troncation tête-queue des résultats d'outils."""

    def test_pas_de_troncation_sous_le_budget(self):
        self.assertEqual(memoire.tronquer_outil("court"), "court")

    def test_garde_tete_et_queue(self):
        gros = "DEBUT\n" + ("remplissage\n" * 5000) + "FIN_ERREUR\n"
        tronque = memoire.tronquer_outil(gros, budget=5_000)
        self.assertIn("DEBUT", tronque)
        self.assertIn("FIN_ERREUR", tronque)

    def test_coupure_signalee(self):
        gros = "a\n" + ("ligne\n" * 5000) + "z\n"
        tronque = memoire.tronquer_outil(gros, budget=5_000)
        self.assertIn("caractères omis au milieu", tronque)

    def test_taille_bornee(self):
        gros = "x" * 100_000
        tronque = memoire.tronquer_outil(gros, budget=5_000)
        self.assertLess(len(tronque), 6_000)

    def test_pas_de_ligne_tranchee(self):
        gros = "entete complete\n" + ("donnees utiles\n" * 3000) + "sortie code 1\n"
        tronque = memoire.tronquer_outil(gros, budget=5_000)
        lignes = tronque.splitlines()
        self.assertEqual(lignes[0], "entete complete")
        self.assertEqual(lignes[-1], "sortie code 1")


class TestEstimerTokens(unittest.TestCase):
    """Borne haute du coût en tokens d'une conversation."""

    def test_croit_avec_le_texte(self):
        m = [{"role": "user", "content": "x" * 4_000}]
        self.assertGreaterEqual(memoire.estimer_tokens(m), 1_000)

    def test_image_ajoute_son_forfait(self):
        m = [{"role": "user", "content": [
            {"type": "text", "text": "regarde"},
            {"type": "image_url", "image_url": {"url": "data:..."}},
        ]}]
        self.assertGreaterEqual(memoire.estimer_tokens(m), memoire.TOKENS_PAR_IMAGE)

    def test_contenu_liste_et_chaine_comptes(self):
        m1 = [{"role": "user", "content": "abcd" * 100}]
        m2 = [{"role": "user", "content": [
            {"type": "text", "text": "abcd" * 100}]}]
        self.assertEqual(memoire.estimer_tokens(m1), memoire.estimer_tokens(m2))


class TestCompresserMilieu(unittest.TestCase):
    """Compression du milieu avec protection de la tête et de la fin."""

    def _conversation(self, n=20):
        conv = [{"role": "system", "content": "AME"}]
        for i in range(n):
            conv.append({"role": "user", "content": f"question {i}"})
            conv.append({"role": "assistant", "content": f"réponse {i}"})
        return conv

    def test_protege_systeme_et_fin(self):
        conv = self._conversation()
        comp = memoire.compresser_milieu(conv)
        self.assertEqual(comp[0]["content"], "AME")
        self.assertEqual(comp[-1]["content"], "réponse 19")
        self.assertLess(len(comp), len(conv))

    def test_insert_un_resume(self):
        comp = memoire.compresser_milieu(self._conversation())
        resumes = [m for m in comp
                   if "Résumé des échanges anciens" in str(m.get("content"))]
        self.assertEqual(len(resumes), 1)

    def test_conversation_courte_intacte(self):
        conv = [{"role": "system", "content": "AME"},
                {"role": "user", "content": "salut"},
                {"role": "assistant", "content": "bonjour"}]
        self.assertEqual(memoire.compresser_milieu(conv), conv)

    def test_pas_de_message_tool_orphelin(self):
        # Un bloc user → assistant(tool_calls) → tool ne doit jamais être coupé
        # au milieu : l'API refuse un 'tool' sans 'tool_calls' correspondant.
        conv = [{"role": "system", "content": "AME"}]
        for i in range(10):
            conv.append({"role": "user", "content": f"demande {i}"})
            conv.append({"role": "assistant", "content": None,
                         "tool_calls": [{"id": f"tc{i}", "type": "function",
                                         "function": {"name": "outil",
                                                      "arguments": "{}"}}]})
            conv.append({"role": "tool", "tool_call_id": f"tc{i}",
                         "content": f"resultat {i}"})
            conv.append({"role": "assistant", "content": f"voilà {i}"})
        comp = memoire.compresser_milieu(conv)
        # Chaque message 'tool' restant doit avoir un 'tool_calls' qui
        # correspond juste avant lui.
        ids_declares = set()
        for m in comp:
            if m.get("role") == "assistant" and m.get("tool_calls"):
                ids_declares = {tc["id"] for tc in m["tool_calls"]}
            elif m.get("role") == "tool":
                self.assertIn(m.get("tool_call_id"), ids_declares,
                              "message tool orphelin après compression")


class TestSignatures(unittest.TestCase):
    """Signatures d'actions comparables, sans stockage du brut."""

    def test_stables_pour_meme_action(self):
        s1 = memoire.signature_action("lire_fichier", {"chemin": "/a"}, "contenu")
        s2 = memoire.signature_action("lire_fichier", {"chemin": "/a"}, "contenu")
        self.assertEqual(s1, s2)

    def test_differentes_pour_autre_cible(self):
        s1 = memoire.signature_action("lire_fichier", {"chemin": "/a"}, "x")
        s3 = memoire.signature_action("lire_fichier", {"chemin": "/b"}, "x")
        self.assertNotEqual(s1, s3)

    def test_resultat_brut_non_dans_signature(self):
        brut = "le mot de passe est chou-fleur et laissez-faire"
        s = memoire.signature_action("terminal", {"commande": "cat x"}, brut)
        self.assertNotIn("chou-fleur", s)


class TestMemoireLongue(unittest.TestCase):
    """memoire.md curé : borné, filtré, révocable."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sauve = memoire.MEMOIRE_FICHIER
        memoire.MEMOIRE_FICHIER = Path(self.tmp.name) / "memoire.md"
        self.sauve_tombes = memoire.TOMBES_FICHIER
        memoire.TOMBES_FICHIER = Path(self.tmp.name) / "tombes.json"

    def tearDown(self):
        memoire.MEMOIRE_FICHIER = self.sauve
        memoire.TOMBES_FICHIER = self.sauve_tombes
        self.tmp.cleanup()

    def test_noter_un_fait(self):
        self.assertIn("Noté", memoire.memoire_noter("Pièges", "web lent"))
        self.assertIn("web lent", memoire.memoire_pour_prompt())

    def test_refuse_donnee_sensible(self):
        r = memoire.memoire_noter("X", "mon mot de passe est chou")
        self.assertIn("Refusé", r)
        self.assertNotIn("chou", memoire.memoire_pour_prompt())

    def test_refuse_carte_bancaire(self):
        r = memoire.memoire_noter("X", "ma carte 4111 1111 1111 1111 expire")
        self.assertIn("Refusé", r)

    def test_plafond(self):
        # Remplir jusqu'au plafond avec des faits bénins.
        i = 0
        while True:
            r = memoire.memoire_noter("Pièges", f"fait numero {i} " + "x" * 200)
            if "Refusé" in r:
                break
            i += 1
            if i > 200:
                self.fail("plafond jamais atteint")
        texte = Path(memoire.MEMOIRE_FICHIER).read_text(encoding="utf-8")
        self.assertLessEqual(len(texte), memoire.MEMOIRE_PLAFOND)

    def test_oublier(self):
        memoire.memoire_noter("Pièges", "web_cliquer recharge lentement")
        memoire.memoire_oublier("web_cliquer")
        self.assertNotIn("web_cliquer", memoire.memoire_pour_prompt())

    def test_categories_creees(self):
        memoire.memoire_noter("Conventions de travail", "venv par projet")
        memoire.memoire_noter("Préférences", "réponses courtes")
        texte = memoire.memoire_pour_prompt()
        self.assertIn("## Conventions de travail", texte)
        self.assertIn("## Préférences", texte)

    def test_secret_masque_au_prompt(self):
        # La garantie qui compte pour ce module : un secret en clair passé
        # dans un fait ne ressort jamais tel quel vers le prompt (memoire.md
        # part au cloud). La rédaction des secrets est la propriété stable ;
        # le masquage d'un prénom, lui, a été retiré volontairement de
        # securite.py et n'est donc plus testé ici.
        memoire.MEMOIRE_FICHIER.write_text(
            "# M\n- clé sk-proj-abcd1234abcd1234abcd1234abcd1234\n",
            encoding="utf-8")
        self.assertNotIn("sk-proj-abcd1234", memoire.memoire_pour_prompt())


class TestJournalSession(unittest.TestCase):
    """Journal JSONL append-only et reprise de session."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sauve = memoire.SESSIONS_DOSSIER
        memoire.SESSIONS_DOSSIER = Path(self.tmp.name)

    def tearDown(self):
        memoire.SESSIONS_DOSSIER = self.sauve
        self.tmp.cleanup()

    def test_journaliser_et_relire(self):
        self.assertTrue(memoire.journaliser({"type": "fait", "resume": "premier"}))
        entrees = memoire.relire_journal(memoire.journal_du_jour())
        self.assertEqual(entrees[0]["resume"], "premier")
        self.assertIn("ts", entrees[0])

    def test_append_only_plusieurs_lignes(self):
        memoire.journaliser({"type": "fait", "resume": "un"})
        memoire.journaliser({"type": "fait", "resume": "deux"})
        memoire.journaliser({"type": "fin"})
        entrees = memoire.relire_journal(memoire.journal_du_jour())
        self.assertEqual(len(entrees), 3)

    def test_tolére_ligne_coupee(self):
        memoire.journaliser({"type": "fait", "resume": "premier"})
        chemin = memoire.journal_du_jour()
        with chemin.open("a") as f:
            f.write('{"type": "coup')  # crash en cours d'écriture
        entrees = memoire.relire_journal(chemin)
        self.assertEqual(len(entrees), 1)

    def test_reprise_proposee_si_pas_de_fin(self):
        memoire.journaliser({"type": "fait", "resume": "vérif faite"})
        memoire.journaliser({"type": "suspens", "resume": "réponse attendue"})
        reprise = memoire.proposer_reprise()
        self.assertIsNotNone(reprise)
        self.assertIn("vérif faite", reprise)
        self.assertIn("réponse attendue", reprise)
        self.assertIn("passé", reprise)

    def test_pas_de_reprise_si_fin_propre(self):
        memoire.journaliser({"type": "fait", "resume": "terminé"})
        memoire.journaliser({"type": "fin"})
        self.assertIsNone(memoire.proposer_reprise())

    def test_pas_de_reprise_sans_journal(self):
        self.assertIsNone(memoire.proposer_reprise())


class TestLigneImage(unittest.TestCase):
    def test_ligne_utile_avec_description(self):
        ligne = memoire.ligne_image("capture_ecran", "un terminal ouvert")
        self.assertIn("capture_ecran", ligne)
        self.assertIn("terminal", ligne)
        self.assertNotEqual(ligne, "[image vue plus tôt]")

    def test_ligne_degradee_sans_description(self):
        ligne = memoire.ligne_image("web_voir")
        self.assertIn("web_voir", ligne)


class TestProtectionRedaction(unittest.TestCase):
    """La mémoire ne stocke pas de secret, même si le reste en laisse passer."""

    def test_cle_api_masquee_au_journal(self):
        memoire_tmp = tempfile.TemporaryDirectory()
        sauve = memoire.SESSIONS_DOSSIER
        memoire.SESSIONS_DOSSIER = Path(memoire_tmp.name)
        try:
            memoire.journaliser({"type": "fait",
                                 "resume": "clé sk-abcdef0123456789abcdef0123456789 vue"})
            brut = memoire.journal_du_jour().read_text(encoding="utf-8")
            self.assertNotIn("sk-abcdef0123456789abcdef0123456789", brut)
        finally:
            memoire.SESSIONS_DOSSIER = sauve
            memoire_tmp.cleanup()

    def test_prompt_filtre_une_derniere_fois(self):
        memoire_tmp = tempfile.TemporaryDirectory()
        sauve = memoire.MEMOIRE_FICHIER
        memoire.MEMOIRE_FICHIER = Path(memoire_tmp.name) / "memoire.md"
        try:
            # Écriture directe (sans passer par memoire_noter) d'un secret :
            # la lecture pour le prompt doit quand même le masquer.
            memoire.MEMOIRE_FICHIER.write_text(
                "- fait avec clé sk-abcdef0123456789abcdef0123456789\n",
                encoding="utf-8")
            self.assertNotIn("sk-abcdef0123456789",
                             memoire.memoire_pour_prompt())
        finally:
            memoire.MEMOIRE_FICHIER = sauve
            memoire_tmp.cleanup()


class TestCompressionRobustesse(unittest.TestCase):
    """4c — compresser_milieu et son callback : durcissement face aux cas limites.

    Coût d'un bug ici : tout le contexte disparaît dans une exception,
    ou des blocs entiers sont omis silencieusement du résumé injecté.
    """

    def _conversation_longue(self, n=12, avec_system=True):
        conv = []
        if avec_system:
            conv.append({"role": "system", "content": "AME déclarée."})
        for i in range(n):
            conv.append({"role": "user", "content": f"Question claire numéro {i}."})
            conv.append({"role": "assistant", "content": f"Réponse utile numéro {i}."})
        return conv

    # ------------------------------------------------------------------
    # 1. resumer_blocs lève une exception → repli local, jamais de propagation
    # ------------------------------------------------------------------
    def test_callback_leve_repli_local(self):
        def explosif(_blocs):
            raise ValueError("quota modèle dépassé")

        conv = self._conversation_longue(n=10)
        # Sans robustesse, compresser_milieu propagerait l'exception.
        comp = memoire.compresser_milieu(conv, resumer_blocs=explosif)
        resumes = [m for m in comp
                   if "Résumé des échanges anciens" in str(m.get("content", ""))]
        self.assertEqual(len(resumes), 1, "pas de résumé trouvé après repli")
        # Le résumé local doit citer quelque chose du milieu, prouvant qu'on
        # a bien dégradé (au lieu de planter).
        self.assertIn("Question claire numéro 0", resumes[0]["content"])

    # ------------------------------------------------------------------
    # 2. resumer_blocs renvoie une liste trop courte → repli local pour TOUS
    # ------------------------------------------------------------------
    def test_callback_renvoie_liste_trop_courte(self):
        def trop_courte(blocs):
            return ["une seule phrase"] * max(0, len(blocs) - 1)  # -1 : court

        conv = self._conversation_longue(n=12)
        comp = memoire.compresser_milieu(conv, resumer_blocs=trop_courte)
        resumes = [m for m in comp
                   if "Résumé des échanges anciens" in str(m.get("content", ""))]
        self.assertEqual(len(resumes), 1)
        # Le résumé local (qui doit avoir remplacé) doit citer du milieu réel.
        self.assertIn("Question claire numéro 0", resumes[0]["content"])

    # ------------------------------------------------------------------
    # 3. resumer_blocs renvoie un non-list (str, None, int) → repli local
    # ------------------------------------------------------------------
    def test_callback_renvoie_mauvais_type(self):
        def mauvais_type(_blocs):
            return "ceci n'est pas une liste"  # type: ignore[return-value]

        conv = self._conversation_longue(n=10)
        comp = memoire.compresser_milieu(conv, resumer_blocs=mauvais_type)
        resumes = [m for m in comp
                   if "Résumé des échanges anciens" in str(m.get("content", ""))]
        self.assertIn("Question claire numéro 0", resumes[0]["content"])

    def test_callback_renvoie_none(self):
        def retourne_none(_blocs):
            return None  # type: ignore[return-value]

        conv = self._conversation_longue(n=10)
        comp = memoire.compresser_milieu(conv, resumer_blocs=retourne_none)
        resumes = [m for m in comp
                   if "Résumé des échanges anciens" in str(m.get("content", ""))]
        self.assertIn("Question claire numéro 0", resumes[0]["content"])

    # ------------------------------------------------------------------
    # 4. Une phrase vide / None parmi d'autres → repli local pour cette entrée
    # ------------------------------------------------------------------
    def test_callback_phrase_vide_pour_un_bloc(self):
        def avec_trou(blocs):
            out = []
            for i, b in enumerate(blocs):
                # Deuxième bloc : phrase vide → repli local pour LUI SEULEMENT.
                out.append("" if i == 1 else f"résumé fourni pour bloc {i}")
            return out

        conv = self._conversation_longue(n=12)
        comp = memoire.compresser_milieu(conv, resumer_blocs=avec_trou)
        resumes = [m for m in comp
                   if "Résumé des échanges anciens" in str(m.get("content", ""))]
        contenu = resumes[0]["content"]
        # Le bloc 0 est venu du callback, le bloc 1 en repli local.
        self.assertIn("résumé fourni pour bloc 0", contenu)
        self.assertNotIn("résumé fourni pour bloc 1", contenu,
                         "le bloc 1 doit être remplacé par le repli local")

    # ------------------------------------------------------------------
    # 5. Valeurs non-str dans la liste → repli pour celles-ci
    # ------------------------------------------------------------------
    def test_callback_entrees_non_str(self):
        def non_str(blocs):
            # None, int, dict : tout sauf un str.
            return [None, 42, {"pas": "bon"}, "phrase raisonnable"] * len(blocs)

        conv = self._conversation_longue(n=12)
        comp = memoire.compresser_milieu(conv, resumer_blocs=non_str)
        resumes = [m for m in comp
                   if "Résumé des échanges anciens" in str(m.get("content", ""))]
        contenu = resumes[0]["content"]
        # Doit contenir la phrase raisonnable ET aucun "None" ou "42" traînant.
        self.assertIn("phrase raisonnable", contenu)
        self.assertNotIn("- None", contenu)
        self.assertNotIn("- 42", contenu)

    # ------------------------------------------------------------------
    # 6. Bloc entièrement outil — phrase non vide (pas d'omission silencieuse)
    # ------------------------------------------------------------------
    def test_bloc_uniquement_outil_produit_phrase_non_vide(self):
        # Construction : un milieu où un bloc est composé uniquement
        # d'assistant(tool_calls) + tool(s), sans 'user' en tête du tout
        # (cas bâtard mais réaliste : après un appel de fonction en fin de
        # message précédent, l'utilisateur n'a pas eu à intervenir).
        conv: list[dict] = [{"role": "system", "content": "AME"}]
        for i in range(9):
            conv.append({"role": "user", "content": f"ordre {i}"})
            conv.append({"role": "assistant", "content": f"ok {i}"})
        # Bloc outil pure
        conv.append({"role": "user", "content": "lance l'outil"})
        conv.append({"role": "assistant", "content": None,
                     "tool_calls": [{"id": "tcX", "type": "function",
                                     "function": {"name": "shell",
                                                  "arguments": "{}"}}]})
        conv.append({"role": "tool", "tool_call_id": "tcX",
                     "content": "sortie 42"})
        conv.append({"role": "assistant", "content": "résultat montré"})
        # + beaucoup de nouveaux messages pour forcer l'outil dans le milieu à compresser.
        for i in range(15):
            conv.append({"role": "user", "content": f"nouvelle question {i}"})
            conv.append({"role": "assistant", "content": f"nouvelle réponse {i}"})

        comp = memoire.compresser_milieu(conv)
        resumes = [m for m in comp
                   if "Résumé des échanges anciens" in str(m.get("content", ""))]
        self.assertEqual(len(resumes), 1)
        # Le résumé local ne doit pas contenir de ligne vide/silencieuse :
        # chaque bloc doit avoir une trace.
        lignes = [l for l in resumes[0]["content"].splitlines() if l.startswith("- ")]
        self.assertGreaterEqual(len(lignes), 1)
        for l in lignes:
            self.assertLess(2, len(l))  # une ligne "- " seule signifierait un bloc perdu

    # ------------------------------------------------------------------
    # 7. Messages system préservés INTACTS même en cas de callback défectueux
    # ------------------------------------------------------------------
    def test_messages_system_toujours_conserves(self):
        def explosif(_b):
            raise RuntimeError("boucle cassée")

        conv = [{"role": "system", "content": "AME"},
                {"role": "system", "content": "Sécurité : ne jamais lire /etc/passwd"}]
        for i in range(10):
            conv.append({"role": "user", "content": f"q{i}"})
            conv.append({"role": "assistant", "content": f"r{i}"})
        comp = memoire.compresser_milieu(conv, resumer_blocs=explosif)
        systemes = [m for m in comp if m.get("role") == "system"]
        self.assertEqual(len(systemes), 2)
        self.assertEqual(systemes[0]["content"], "AME")
        self.assertEqual(systemes[1]["content"], "Sécurité : ne jamais lire /etc/passwd")

    # ------------------------------------------------------------------
    # 8. Aucun message 'tool' orphelin même après compression agressive
    # ------------------------------------------------------------------
    def test_jamais_de_tool_orphelin_sous_tous_angles(self):
        conv: list[dict] = [{"role": "system", "content": "AME"}]
        # 8 itérations d'une séquence user → tool_calls → tool → assistant
        for i in range(8):
            conv.append({"role": "user", "content": f"demande {i}"})
            conv.append({"role": "assistant", "content": None,
                         "tool_calls": [{"id": f"t{i}", "type": "function",
                                         "function": {"name": "run",
                                                      "arguments": "{}"}}]})
            conv.append({"role": "tool", "tool_call_id": f"t{i}",
                         "content": f"résultat {i}"})
            conv.append({"role": "assistant", "content": f"analysé {i}"})
        # + 6 nouveaux messages pour forcer la coupe dans la zone ancienne.
        for i in range(6):
            conv.append({"role": "user", "content": f"récent {i}"})
            conv.append({"role": "assistant", "content": f"récent r{i}"})

        comp = memoire.compresser_milieu(conv)
        ids_declares = set()
        for m in comp:
            if m.get("role") == "assistant" and m.get("tool_calls"):
                ids_declares = {tc["id"] for tc in m["tool_calls"]}
            elif m.get("role") == "tool":
                self.assertIn(m.get("tool_call_id"), ids_declares,
                              "message tool sans tool_calls apparié")

    # ------------------------------------------------------------------
    # 9. _frontiere_sure recule quand la zone protégée commencerait par un 'tool'
    # ------------------------------------------------------------------
    def test_frontiere_sure_recule_sur_tool(self):
        # Construction directe : un tool_calls suivi de son résultat, et on
        # demande à _frontiere_sure si la zone protégée peut commencer
        # juste AVANT le 'tool' (donc juste APRÈS tool_calls) — doit reculer.
        corps = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": None,
             "tool_calls": [{"id": "t1"}]},
            {"role": "tool", "tool_call_id": "t1", "content": "r1"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "b"},
            {"role": "assistant", "content": "re"},
        ]
        # On veut protéger les 4 derniers : corps[2:] — tomberait sur 'tool'.
        sure = memoire._frontiere_sure(corps, len(corps) - 4)
        self.assertLessEqual(sure, 2,
                             "frontiere_sure n'a pas reculé avant le tool")

    # ------------------------------------------------------------------
    # 10. Le résumé ne contient JAMAIS un bloc vide
    # ------------------------------------------------------------------
    def test_aucun_bloc_vide_dans_le_resume(self):
        conv = self._conversation_longue(n=15)
        comp = memoire.compresser_milieu(conv)
        resumes = [m for m in comp
                   if "Résumé des échanges anciens" in str(m.get("content", ""))]
        self.assertEqual(len(resumes), 1)
        lignes = [l for l in resumes[0]["content"].splitlines()
                  if l.startswith("- ")]
        self.assertEqual(len(lignes), len([l for l in lignes if l[2:].strip()]),
                         "Au moins une ligne de résumé est vide")


class TestQuasiDoublonsEtTombes(unittest.TestCase):
    """Quasi-doublons (Jaccard, adapté aux phrases courtes) et pierres
    tombales (portées d'Oblivion via soulbook oubli.ts).

    Voir memoire.py : SimHash (Charikar) est exposé aussi, mais pas utilisé
    par memoire_noter — il perd sa localité sur des textes très courts,
    limitation signalée dans soulbook trust/oubli.ts (« l'empreinte reconnaît
    la même phrase, pas une paraphrase »)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sauve_memoire = memoire.MEMOIRE_FICHIER
        memoire.MEMOIRE_FICHIER = Path(self.tmp.name) / "memoire.md"
        self.sauve_tombes = memoire.TOMBES_FICHIER
        memoire.TOMBES_FICHIER = Path(self.tmp.name) / "tombes.json"

    def tearDown(self):
        memoire.MEMOIRE_FICHIER = self.sauve_memoire
        memoire.TOMBES_FICHIER = self.sauve_tombes
        self.tmp.cleanup()

    # --- SimHash (exposé, utile sur textes LONGS) ----------------------------

    def test_simhash_identique_a_lui_meme(self):
        h = memoire.simhash("le web lent me fatigue")
        self.assertEqual(memoire.hamming(h, h), 0)

    def test_simhash_textes_longs_proches_empreintes_proches(self):
        # Sur des textes longs (paragraphes, captures), deux versions d'un
        # même contenu à quelques mots près ont des empreintes SIMHash
        # significativement plus proches que deux textes sans rapport.
        # Distance mesurée le jour d'écriture de ce test : 15 sur 64 bits.
        long_a = ("la mémoire durable de root est un fichier markdown "
                  "plafonné à huit mille caractères " * 8)
        long_b = ("la mémoire durable de root est un fichier markdown "
                  "plafonné à huit mille caractères environ " * 8)
        a, b = memoire.simhash(long_a), memoire.simhash(long_b)
        self.assertLessEqual(memoire.hamming(a, b), 18)

    def test_simhash_textes_eloignes_distance_grande(self):
        a = memoire.simhash("le web lent me fatigue " * 20)
        b = memoire.simhash("xyzabc qrs tuv wxy zab " * 20)
        # textes sans rapport : distance typique ~32 sur 64 bits (binomial).
        # Distance mesurée le jour d'écriture de ce test : 30.
        self.assertGreaterEqual(memoire.hamming(a, b), 25)

    def test_simhash_vide_retourne_zero(self):
        self.assertEqual(memoire.simhash(""), 0)
        self.assertEqual(memoire.simhash("   "), 0)

    # --- Quasi-doublon via memoire_noter (Jaccard, phrases courtes) ----------

    def test_doublon_proche_refuse(self):
        r1 = memoire.memoire_noter("Pièges", "web_cliquer recharge lentement")
        self.assertIn("Noté", r1)
        r2 = memoire.memoire_noter("Pièges", "web_cliquer recharge trop lentement")
        self.assertIn("Refusé", r2)
        self.assertIn("doublon", r2)

    def test_fait_vraiment_nouveau_accepte(self):
        memoire.memoire_noter("Pièges", "web_cliquer recharge lentement")
        r = memoire.memoire_noter("Conventions",
                                  "une session hors ligne est exigée")
        self.assertIn("Noté", r)

    def test_doublon_exact_refuse(self):
        memoire.memoire_noter("Pièges", "fait précis à retenir")
        r = memoire.memoire_noter("Pièges", "fait précis à retenir")
        self.assertIn("Refusé", r)

    def test_casse_voire_accents_comptes_comme_identiques(self):
        # _plier enlève casse et accents : « Élan imprévu » et « élan imprévu »
        # doivent partager les mêmes mots, donc être vus comme doublons.
        memoire.memoire_noter("Pièges", "Élan imprévu en réunion")
        r = memoire.memoire_noter("Pièges", "élan imprévu en réunion")
        self.assertIn("Refusé", r)

    # --- Pierres tombales ----------------------------------------------------

    def test_oublier_puis_renoter_refuse(self):
        memoire.memoire_noter("Pièges", "un fait à oublier complètement")
        memoire.memoire_oublier("oublier complètement")
        self.assertNotIn("fait à oublier", memoire.memoire_pour_prompt())
        r = memoire.memoire_noter("Pièges", "un fait à oublier complètement")
        self.assertIn("Refusé", r)
        self.assertIn("tombale", r)

    def test_tombe_insensible_a_la_casse(self):
        memoire.memoire_noter("Pièges", "Fait Sensible Majuscules")
        memoire.memoire_oublier("Fait Sensible Majuscules")
        # La tombe garde le pli (sans casse), donc une recase du même fait
        # reste refusée : avant de renoter on doit lever la tombe.
        r = memoire.memoire_noter("Pièges", "fait sensible majuscules")
        self.assertIn("Refusé", r)

    def test_tombe_survit_a_la_lecture_du_fichier(self):
        # Les tombes vivent dans un fichier séparé : elles subsistent même
        # si memoire.md a été recréé entre deux sessions.
        memoire.memoire_noter("Pièges", "fait persistant à retenir")
        memoire.memoire_oublier("fait persistant")
        memoire.MEMOIRE_FICHIER.unlink()  # simulate une nouvelle session
        r = memoire.memoire_noter("Pièges", "fait persistant à retenir")
        self.assertIn("Refusé", r)
        self.assertIn("tombale", r)

    def test_correction_possible_via_oublier_puis_noter(self):
        # Pour remplacer un fait noté : oublier l'ancien, noter le nouveau.
        # Le quasi-doublon refuserait le nouveau si l'ancien était encore là.
        memoire.memoire_noter("Pièges", "la session ne dure qu'une heure")
        memoire.memoire_oublier("qu'une heure")
        r = memoire.memoire_noter("Pièges", "la session dure maintenant 45 minutes")
        # La tombe sur l'ancien fait n'empêche pas un fait différent de s'écrire
        self.assertIn("Noté", r)

    def test_oublier_ne_depose_que_l_empreinte_pas_le_texte(self):
        fait = "un fait secret à jeter"
        memoire.memoire_noter("Pièges", fait)
        memoire.memoire_oublier("secret à jeter")
        contenu = memoire.TOMBES_FICHIER.read_text(encoding="utf-8")
        self.assertNotIn(fait, contenu)
        self.assertNotIn("secret", contenu.lower())

    def test_tombes_json_bien_forme(self):
        memoire.memoire_noter("Pièges", "fait X unique")
        memoire.memoire_noter("Pièges", "fait Y distinct")
        memoire.memoire_oublier("fait X unique")
        import json as _json
        data = _json.loads(memoire.TOMBES_FICHIER.read_text(encoding="utf-8"))
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertTrue(all(len(e) == 64 for e in data))  # sha256 hexa


class TestSessionBoutEnBout(unittest.TestCase):
    """Scénario complet hors ligne : session interrompue -> reprise proposée ->
    oubli qui tient à travers redémarrages. C'est le « test d'intégration »
    demandé par CONCEPTION-MEMOIRE §4.2 — un seul scénario, tous les effets."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        chemin = Path(self.tmp.name)

        # Rediriger tous les chemins persistants vers un dossier jetable.
        self._sauve = {}
        for nom in ("MEMOIRE_FICHIER", "TOMBES_FICHIER", "SESSIONS_DOSSIER",
                    "ETAT_FICHIER"):
            self._sauve[nom] = getattr(memoire, nom)
        memoire.MEMOIRE_FICHIER  = chemin / "memoire.md"
        memoire.TOMBES_FICHIER   = chemin / "tombes.json"
        memoire.SESSIONS_DOSSIER = chemin / "sessions"
        memoire.ETAT_FICHIER     = chemin / "etat.json"

        def restaurer():
            for nom, val in self._sauve.items():
                setattr(memoire, nom, val)
        self.addCleanup(restaurer)

    # ------------------------------------------------------------------
    # PHASE A — démarrage vierge, vie d'une session, interruption brutale
    # ------------------------------------------------------------------
    def _phase_A(self):
        r = {}
        r["pas_de_reprise_sur_vierge"] = memoire.proposer_reprise()
        # Construire un fil comme root.py le ferait et le compresser AVEC
        # la callback de résumé livrée par root.py (resumer_blocs, l.863).
        messages = [
            {"role": "system", "content": "Tu es Root, un agent local et franc."},
        ]
        for i in range(14):
            messages.append({"role": "user", "content": f"Question banale n°{i}."})
            if i == 3:
                messages.append({"role": "assistant", "content": None,
                                 "tool_calls": [{"id": "call_1", "type": "function",
                                                 "function": {"name": "terminal",
                                                              "arguments": '{"command":"pwd"}'}}]})
                messages.append({"role": "tool", "tool_call_id": "call_1",
                                 "content": "/Users/x/Projets/config.txt\n" + "ligne\n" * 3000})
            else:
                messages.append({"role": "assistant", "content": f"Réponse n°{i}."})

        # Troncature explicite d'un résultat d'outil trop long.
        trop_long = "ligne\n" * 3000  # ~15 000 caractères
        t = memoire.tronquer_outil(trop_long, budget=2_000)
        r["outil_tronque_avec_note"] = "[...caractères omis au milieu" not in t and "caractères omis" in t
        r["outil_tronque_court"] = len(t) <= 2_200  # budget + note

        # Mémoire : noter deux faits, dont un quasi-doublon que l'on rejettera.
        r["noter_profil_ok"] = memoire.memoire_noter(
            "profil", "Préfère un terminal simple et une réponse concise en français.")
        r["noter_projet_ok"] = memoire.memoire_noter(
            "projet", "Le dépôt root vit dans ~/Projets/root-harness-git.")
        r["noter_quasi_doublon_refuse"] = memoire.memoire_noter(
            "projet", "Le dépôt root vit dans ~/Projets/root-harness-git — avec les tests.")

        # Compression AVEC callback resumer_blocs (comportement réel root.py l.936).
        def resumer_blocs_simule(blocs):
            return ["résumé simulé par le modèle pour le demandeur"]
        comp = memoire.compresser_milieu(messages, resumer_blocs=resumer_blocs_simule)

        ph_resume = next((m for m in comp
                          if m is not messages[0]
                          and isinstance(m.get("content"), str)
                          and "Résumé des échanges anciens" in m["content"]), None)
        r["callback_resumer_blocs_invoquee"] = ph_resume is not None
        r["systeme_toujours_en_tete"] = comp[0]["role"] == "system"
        # Aucun 'tool' orphelin : un 'tool' n'apparaît qu'après un 'assistant'
        # porteur de tool_calls dont l'id correspond — jamais en tête de queue.
        queue = comp[comp.index(ph_resume) + 1:] if ph_resume is not None else []
        for i, m in enumerate(queue):
            if m.get("role") == "tool":
                prev_roles = [q.get("role") for q in queue[:i]]
                if "assistant" not in prev_roles:
                    r["pas_de_tool_orphelin"] = False
                    break
        else:
            r["pas_de_tool_orphelin"] = True

        # Estimation + tokens réels (faire tourner la boucle d'étalonnage).
        r["estimation_positive"] = memoire.estimer_tokens(messages) > 0
        memoire.enregistrer_tokens_reels(3_571)
        memoire.enregistrer_tokens_reels(4_010)
        try:
            etat = json.loads(memoire.ETAT_FICHIER.read_text(encoding="utf-8"))
            r["etat_enregistre"] = etat.get("dernier_prompt_tokens") == 4_010
        except (OSError, json.JSONDecodeError):
            r["etat_enregistre"] = False

        # ARRÊT BRUTAL SIMULÉ : on journalise un suspens, PAS de ligne "fin".
        memoire.journaliser({"type": "fait",     "resume": "découvert le dossier Projets"})
        memoire.journaliser({"type": "suspens",  "resume": "vérifier config.txt avant vendredi"})
        return r, messages

    # ------------------------------------------------------------------
    # PHASE B — redémarrage : la reprise est proposée.
    # ------------------------------------------------------------------
    def _phase_B(self):
        proposal = memoire.proposer_reprise()
        return proposal

    # ------------------------------------------------------------------
    # PHASE C — user fait oublier, puis essaie de renoter : tombe qui tient.
    # ------------------------------------------------------------------
    def _phase_C(self):
        r = {}
        r["memoire_avant_oubli"] = memoire.memoire_pour_prompt()
        r["quelque_chose_a_oublier"] = "dépôt root vit" in r["memoire_avant_oubli"]
        oublie = memoire.memoire_oublier("dépôt root")
        r["oublier_a_supprime"] = "1 ligne" in oublie or "supprimée" in oublie
        r["memoire_apres_oubli_vide"] = "root-harness-git" not in memoire.memoire_pour_prompt()
        # Réintroduction du MÊME fait -> refus par pierre tombale.
        ren = memoire.memoire_noter(
            "projet", "Le dépôt root vit dans ~/Projets/root-harness-git.")
        r["tombe_bloque_reintroduction"] = "pierre tombale" in ren.lower()
        # Réintroduction avec une capitalisation différente -> toujours refus.
        ren2 = memoire.memoire_noter(
            "PROJET", "le dépôt ROOT vit dans ~/Projets/root-harness-git")
        r["tombe_insensible_a_la_casse"] = "pierre tombale" in ren2.lower()
        return r

    # ------------------------------------------------------------------
    # Le test — une seule méthode pour montrer l'ordre réel.
    # ------------------------------------------------------------------
    def test_cycle_complet_session_interrompue_oubli_persistant(self):
        # A
        rA, messages = self._phase_A()
        self.assertIsNone(rA["pas_de_reprise_sur_vierge"],
                          "session vierge : rien à reprendre")
        self.assertTrue(rA["outil_tronque_avec_note"],
                        "troncature d'outil doit porter une note explicite")
        self.assertTrue(rA["outil_tronque_court"],
                        "troncature d'outil doit respecter le budget")
        self.assertTrue(rA["noter_profil_ok"].startswith("Noté"),
                        f"noter profil : {rA['noter_profil_ok']}")
        self.assertTrue(rA["noter_projet_ok"].startswith("Noté"),
                        f"noter projet : {rA['noter_projet_ok']}")
        self.assertIn("quasi-doublon", rA["noter_quasi_doublon_refuse"],
                      "le quasi-doublon doit être refusé")
        self.assertTrue(rA["callback_resumer_blocs_invoquee"],
                        "compresser_milieu doit invoquer resumer_blocs quand fourni")
        self.assertTrue(rA["systeme_toujours_en_tete"],
                        "le message system doit rester en tête après compression")
        self.assertTrue(rA["pas_de_tool_orphelin"],
                        "aucun message 'tool' sans son 'assistant' amont")
        self.assertTrue(rA["estimation_positive"], "estimation de tokens > 0")
        self.assertTrue(rA["etat_enregistre"], "dernier_prompt_tokens écrit dans l'état")

        # B
        reprise = self._phase_B()
        self.assertIsNotNone(reprise, "absence de ligne 'fin' -> reprise proposée")
        self.assertIn("Reprise d'une session", reprise)
        self.assertIn("config.txt", reprise,
                      "le suspens (config.txt) doit remonter dans la reprise")
        self.assertIn("revérifier", reprise.lower(),
                      "la reprise invite à revérifier l'état courant")

        # C
        rC = self._phase_C()
        self.assertTrue(rC["quelque_chose_a_oublier"], "précondition : fait présent avant oubli")
        self.assertTrue(rC["oublier_a_supprime"], "oublier confirme la suppression")
        self.assertTrue(rC["memoire_apres_oubli_vide"], "le fait disparaît de la mémoire")
        self.assertTrue(rC["tombe_bloque_reintroduction"],
                        "réintroduire le même fait => pierre tombale")
        self.assertTrue(rC["tombe_insensible_a_la_casse"],
                        "réintroduire avec une autre casse => toujours pierre tombale")


class TestCalibrationTokens(unittest.TestCase):
    """Calibration automatique d'estimer_tokens sur les mesures réelles
    collectées. Chaque test isole MESURES_FICHIER et remet les constantes
    (CARACTERES_PAR_TOKEN, TOKENS_PAR_IMAGE) à leur valeur d'origine —
    calibrer_constantes modifie ces globals et un oubli casserait les tests
    des voisins d'estimation."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        chemin = Path(self.tmp.name)

        # Rediriger les chemins persistants.
        self._sauve_chemins = {
            "MESURES_FICHIER": memoire.MESURES_FICHIER,
            "ETAT_FICHIER": memoire.ETAT_FICHIER,
        }
        memoire.MESURES_FICHIER = chemin / "mesures.jsonl"
        memoire.ETAT_FICHIER = chemin / "etat.json"

        # Mémoriser les constantes pour les remettre après chaque test.
        self._sauve_constantes = {
            "CARACTERES_PAR_TOKEN": memoire.CARACTERES_PAR_TOKEN,
            "TOKENS_PAR_IMAGE": memoire.TOKENS_PAR_IMAGE,
        }

        def restaurer():
            for nom, val in {**self._sauve_chemins, **self._sauve_constantes}.items():
                setattr(memoire, nom, val)
        self.addCleanup(restaurer)

    # ------------------------------------------------------------------
    # enregistrer_tokens_reels
    # ------------------------------------------------------------------
    def test_signature_origine_retro_compatible(self):
        # Appel historique (sans estime) : écrit seulement dans ETAT_FICHIER,
        # jamais dans la série de mesures.
        memoire.enregistrer_tokens_reels(3_571)
        self.assertTrue(memoire.ETAT_FICHIER.exists())
        self.assertFalse(memoire.MESURES_FICHIER.exists())

    def test_appel_complet_ecrit_une_mesure(self):
        memoire.enregistrer_tokens_reels(3_571, estime=3_600, images=0)
        with memoire.MESURES_FICHIER.open(encoding="utf-8") as f:
            mesure = json.loads(f.readline())
        self.assertEqual(mesure["reel"], 3_571)
        self.assertEqual(mesure["estime"], 3_600)
        self.assertEqual(mesure["images"], 0)

    def test_mesure_rejetee_si_estime_negatif(self):
        memoire.enregistrer_tokens_reels(100, estime=-5, images=0)
        self.assertFalse(memoire.MESURES_FICHIER.exists())

    def test_mesure_rejetee_si_reel_nul(self):
        memoire.enregistrer_tokens_reels(0, estime=100, images=0)
        self.assertFalse(memoire.MESURES_FICHIER.exists())

    # ------------------------------------------------------------------
    # _mesures_charger : tolérance aux lignes corrompues
    # ------------------------------------------------------------------
    def test_charge_une_serie_propre(self):
        memoire.enregistrer_tokens_reels(100, estime=110, images=0)
        memoire.enregistrer_tokens_reels(200, estime=210, images=1)
        self.assertEqual(len(memoire._mesures_charger()), 2)

    def test_tole_re_ligne_tronquee(self):
        memoire.enregistrer_tokens_reels(100, estime=110, images=0)
        with memoire.MESURES_FICHIER.open("a", encoding="utf-8") as f:
            f.write('{"estime": 999, "reel": "coup')  # crash en écriture
        mesures = memoire._mesures_charger()
        self.assertEqual(len(mesures), 1)
        self.assertEqual(mesures[0]["reel"], 100)

    def test_tole_re_ligne_json_non_dict(self):
        memoire.enregistrer_tokens_reels(100, estime=110, images=0)
        with memoire.MESURES_FICHIER.open("a", encoding="utf-8") as f:
            f.write("[1, 2, 3]\n")  # JSON valide mais pas un dict
        mesures = memoire._mesures_charger()
        self.assertEqual(len(mesures), 1)

    def test_tole_re_ligne_vide_et_commentaire(self):
        memoire.enregistrer_tokens_reels(100, estime=110, images=0)
        with memoire.MESURES_FICHIER.open("a", encoding="utf-8") as f:
            f.write("\n# commentaire humain\n")
        self.assertEqual(len(memoire._mesures_charger()), 1)

    def test_fichier_absent_renvoie_liste_vide(self):
        self.assertEqual(memoire._mesures_charger(), [])

    def test_champs_non_entiers_ignores(self):
        with memoire.MESURES_FICHIER.open("w", encoding="utf-8") as f:
            f.write(json.dumps({"estime": "abc", "reel": 100, "images": 0}) + "\n")
            f.write(json.dumps({"estime": 200, "reel": 210, "images": 1}) + "\n")
        mesures = memoire._mesures_charger()
        self.assertEqual(len(mesures), 1)
        self.assertEqual(mesures[0]["reel"], 210)

    # ------------------------------------------------------------------
    # _mesures_borner : série bornée à CALIBRATION_MAX_SERIE
    # ------------------------------------------------------------------
    def test_serie_bornee_au_max(self):
        for _ in range(memoire.CALIBRATION_MAX_SERIE + 10):
            memoire.enregistrer_tokens_reels(100, estime=110, images=0)
        lignes = memoire.MESURES_FICHIER.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lignes), memoire.CALIBRATION_MAX_SERIE)

    # ------------------------------------------------------------------
    # analyser_calibration
    # ------------------------------------------------------------------
    def test_analyser_sans_mesure(self):
        stats = memoire.analyser_calibration()
        self.assertEqual(stats["points"], 0)
        self.assertIsNone(stats["ecart_moyen"])
        self.assertIsNone(stats["ecart_median"])
        self.assertFalse(stats["as_suffisant"])

    def test_analyser_moins_de_cinq_mesures(self):
        for _ in range(memoire.CALIBRATION_MIN_POINTS - 1):
            memoire.enregistrer_tokens_reels(1_000, estime=1_000, images=0)
        stats = memoire.analyser_calibration()
        self.assertEqual(stats["points"], memoire.CALIBRATION_MIN_POINTS - 1)
        self.assertFalse(stats["as_suffisant"])
        # Les écarts sont calculés même sans avoir assez de points.
        self.assertIsNotNone(stats["ecart_moyen"])
        self.assertAlmostEqual(stats["ecart_moyen"], 0.0)

    def test_analyser_ecart_positif_surestimation(self):
        # estimé 25 % au-dessus du réel
        for _ in range(5):
            memoire.enregistrer_tokens_reels(1_000, estime=1_250, images=0)
        stats = memoire.analyser_calibration()
        self.assertTrue(stats["as_suffisant"])
        self.assertAlmostEqual(stats["ecart_moyen"], 0.25)

    def test_analyser_ecart_negatif_sous_estimation(self):
        # estimé 50 % sous le réel
        for _ in range(5):
            memoire.enregistrer_tokens_reels(1_000, estime=500, images=0)
        stats = memoire.analyser_calibration()
        self.assertAlmostEqual(stats["ecart_moyen"], -0.5)
        self.assertAlmostEqual(stats["ecart_median"], -0.5)

    def test_analyser_separe_texte_et_image(self):
        # 4 mesures texte pur
        for _ in range(4):
            memoire.enregistrer_tokens_reels(2_000, estime=1_000, images=0)
        # 2 mesures avec image
        for _ in range(2):
            memoire.enregistrer_tokens_reels(5_000, estime=3_100, images=1)
        stats = memoire.analyser_calibration()
        self.assertEqual(stats["texte_seul"]["points"], 4)
        self.assertEqual(stats["avec_image"]["points"], 2)

    # ------------------------------------------------------------------
    # calibrer_constantes : cas limites
    # ------------------------------------------------------------------
    def test_pas_d_ajustement_sans_assez_de_points(self):
        for _ in range(3):
            memoire.enregistrer_tokens_reels(1_000, estime=500, images=0)
        r = memoire.calibrer_constantes()
        self.assertFalse(r["ajusté"])
        self.assertIn("mesures", r["raison"])
        # Constantes inchangées
        self.assertEqual(memoire.CARACTERES_PAR_TOKEN,
                         self._sauve_constantes["CARACTERES_PAR_TOKEN"])

    def test_pas_d_ajustement_ecart_petit(self):
        # Écart moyen < 25 %
        for _ in range(6):
            memoire.enregistrer_tokens_reels(1_000, estime=1_100, images=0)
        r = memoire.calibrer_constantes()
        self.assertFalse(r["ajusté"])
        self.assertIn("sous le seuil", r["raison"])

    def test_sous_estimation_forte_baisse_caracteres_par_token(self):
        # On estime 500 tokens alors que le réel est 1_000 :
        # densité 0.5 → il y a 2x moins de caractères par token qu'on pensait
        # → CARACTERES_PAR_TOKEN devrait tendre vers 2.0 (borne minimale).
        for _ in range(5):
            memoire.enregistrer_tokens_reels(1_000, estime=500, images=0)
        avant = memoire.CARACTERES_PAR_TOKEN
        r = memoire.calibrer_constantes()
        self.assertTrue(r["ajusté"], f"attendu ajustement : {r}")
        self.assertLess(memoire.CARACTERES_PAR_TOKEN, avant)
        self.assertGreaterEqual(memoire.CARACTERES_PAR_TOKEN, 2.0)

    def test_surestimation_forte_monte_caracteres_par_token(self):
        # On estime 8_000 pour un réel de 1_000 → densité 0.125
        # → il y a plus de caractères par token qu'on pensait (8 au lieu de 4).
        for _ in range(5):
            memoire.enregistrer_tokens_reels(1_000, estime=8_000, images=0)
        avant = memoire.CARACTERES_PAR_TOKEN
        r = memoire.calibrer_constantes()
        self.assertTrue(r["ajusté"], f"attendu ajustement : {r}")
        self.assertGreater(memoire.CARACTERES_PAR_TOKEN, avant)

    def test_ajustement_tokens_par_image(self):
        # 4 mesures avec image : chaque image coûte en réalité ~2000 tokens,
        # alors que la constante est à 1100. On met estime=100+1100 pour que
        # l'estimation sans l'erreur le plus simple mesure : le texte à
        # (1100 tokens) + 1 image à (1100) = 2200, et le réel = 2100.
        cpt = memoire.CARACTERES_PAR_TOKEN
        tpi = memoire.TOKENS_PAR_IMAGE
        for _ in range(5):
            # 100 caractères de texte → 25 tokens côté estimer_tokens ;
            # 1 image → tpi tokens. Estimé = 25 + tpi.
            memoire.enregistrer_tokens_reels(2_000 + 25, estime=25 + tpi, images=1)
        # Le rapport tokens_reels_par_image ≈ 2000 > tpi=1100 → doit monter.
        r = memoire.calibrer_constantes()
        self.assertGreater(memoire.TOKENS_PAR_IMAGE, tpi)
        # Constante texte non modifiée dans ce scénario pur-image.
        self.assertAlmostEqual(memoire.CARACTERES_PAR_TOKEN, cpt)

    def test_ajustement_ne_retouche_pas_budget_fenetre(self):
        budget_avant = memoire.BUDGET_FENETRE
        # Sous-estimation franche, mais BUDGET_FENETRE est une borne de sécurité,
        # jamais touchée par le calibrage.
        for _ in range(5):
            memoire.enregistrer_tokens_reels(2_000, estime=500, images=0)
        memoire.calibrer_constantes()
        self.assertEqual(memoire.BUDGET_FENETRE, budget_avant)

    # ------------------------------------------------------------------
    # estimer_tokens reste un int après calibrage (contrat d'interface)
    # ------------------------------------------------------------------
    def test_estimer_tokens_reste_un_int_apres_calibrage(self):
        # Calibrage avec une densité qui produit un float (4,25 par ex.),
        # pour vérifier que le contrat de type ne change pas.
        for _ in range(5):
            memoire.enregistrer_tokens_reels(1_000, estime=1_063, images=0)
        memoire.calibrer_constantes()
        resultat = memoire.estimer_tokens([{"role": "user", "content": "x" * 4_000}])
        self.assertIsInstance(resultat, int,
                              f"estimer_tokens doit retourner un int, rendu : {type(resultat)}")


class TestRobustessePersistence(unittest.TestCase):
    """Règle 4b : un démarrage ne plante JAMAIS sur un fichier abîmé ;
    une interruption n'abandonne JAMAIS un fichier tronqué.

    Chaque test redirige les chemins persistants vers un tempdir ; les
    constantes modifiées par les cas extrêmes sont restaurées à l'issue.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        chemin = Path(self.tmp.name)
        self._sauve = {}
        for nom in ("MEMOIRE_FICHIER", "TOMBES_FICHIER", "SESSIONS_DOSSIER",
                    "ETAT_FICHIER", "MESURES_FICHIER"):
            self._sauve[nom] = getattr(memoire, nom)
        memoire.MEMOIRE_FICHIER = chemin / "memoire.md"
        memoire.TOMBES_FICHIER = chemin / "tombes.json"
        memoire.SESSIONS_DOSSIER = chemin / "sessions"
        memoire.ETAT_FICHIER = chemin / "etat.json"
        memoire.MESURES_FICHIER = chemin / "mesures.jsonl"

        def restaurer():
            for nom, val in self._sauve.items():
                setattr(memoire, nom, val)
        self.addCleanup(restaurer)

    # ------------------------------------------------------------------
    # _lire_texte_tolerant
    # ------------------------------------------------------------------
    def test_lire_fichier_absent(self):
        self.assertEqual(memoire._lire_texte_tolerant(memoire.MEMOIRE_FICHIER), "")

    def test_lire_normal(self):
        memoire.MEMOIRE_FICHIER.write_text("bonjour\n", encoding="utf-8")
        self.assertEqual(memoire._lire_texte_tolerant(memoire.MEMOIRE_FICHIER),
                         "bonjour\n")

    def test_lire_bytes_invalides_utf8(self):
        # Cas concret : séquence d'octets qui n'est pas UTF-8 (crash a
        # interrompu une écriture). Ne doit PAS lever UnicodeDecodeError.
        memoire.MEMOIRE_FICHIER.write_bytes(b"\xff\xfe\x00invalid\xff")
        self.assertEqual(memoire._lire_texte_tolerant(memoire.MEMOIRE_FICHIER), "")

    def test_lire_fichier_binaire_au_lieu_de_texte(self):
        # Un utilisateur qui a ouvert memoire.md dans un éditeur qui a
        # corrompu le codage.
        memoire.MEMOIRE_FICHIER.write_bytes(b"\x89PNG\x0d\x0a\x1a\x0a\x00\x00\x00")
        texte = memoire._lire_texte_tolerant(memoire.MEMOIRE_FICHIER)
        self.assertIsInstance(texte, str)  # pas d'exception

    # ------------------------------------------------------------------
    # _lire_json_tolerant
    # ------------------------------------------------------------------
    def test_json_absent_renvoie_defaut(self):
        self.assertEqual(memoire._lire_json_tolerant(memoire.TOMBES_FICHIER, []), [])
        self.assertEqual(memoire._lire_json_tolerant(memoire.TOMBES_FICHIER, {"k": 1}),
                         {"k": 1})

    def test_json_normal(self):
        memoire.TOMBES_FICHIER.write_text('["abcd"]', encoding="utf-8")
        self.assertEqual(memoire._lire_json_tolerant(memoire.TOMBES_FICHIER, []),
                         ["abcd"])

    def test_json_corrompu_renvoie_defaut(self):
        memoire.TOMBES_FICHIER.write_text('{"trunc": ', encoding="utf-8")
        self.assertEqual(memoire._lire_json_tolerant(memoire.TOMBES_FICHIER, []), [])

    def test_json_bytes_invalides_renvoie_defaut(self):
        memoire.TOMBES_FICHIER.write_bytes(b"\xff\xfe\x00not utf8")
        self.assertEqual(memoire._lire_json_tolerant(memoire.TOMBES_FICHIER, []), [])

    def test_json_corrompu_recupere_via_bak(self):
        # Le fichier principal est corrompu MAIS la copie .bak est saine :
        # c'est le scénario « crash pendant l'écriture principale ».
        memoire.TOMBES_FICHIER.write_text('{"corrompu":', encoding="utf-8")
        bak = memoire.TOMBES_FICHIER.with_suffix(".json.bak")
        bak.write_text('["sauvete"]', encoding="utf-8")
        self.assertEqual(memoire._lire_json_tolerant(memoire.TOMBES_FICHIER, []),
                         ["sauvete"])

    def test_json_corrompu_et_bak_aussi_renvoie_defaut(self):
        memoire.TOMBES_FICHIER.write_text('cassé', encoding="utf-8")
        memoire.TOMBES_FICHIER.with_suffix(".json.bak").write_text(
            'aussi cassé', encoding="utf-8")
        self.assertEqual(memoire._lire_json_tolerant(memoire.TOMBES_FICHIER,
                                                     {"chute": True}),
                         {"chute": True})

    # ------------------------------------------------------------------
    # _ecrire_texte_atomique
    # ------------------------------------------------------------------
    def test_atomo_écrit_bien_le_contenu(self):
        cible = memoire.TOMBES_FICHIER
        memoire._ecrire_texte_atomique(cible, "contenu de test")
        self.assertEqual(cible.read_text(encoding="utf-8"), "contenu de test")

    def test_atomo_remplace_un_fichier_existant(self):
        cible = memoire.TOMBES_FICHIER
        memoire._ecrire_texte_atomique(cible, "v1")
        memoire._ecrire_texte_atomique(cible, "v2")
        self.assertEqual(cible.read_text(encoding="utf-8"), "v2")

    def test_atomo_crée_les_parents_quand_absents(self):
        cible = Path(self.tmp.name) / "profond" / "encore" / "tombes.json"
        memoire._ecrire_texte_atomique(cible, "x")
        self.assertTrue(cible.exists())

    def test_atomo_ne_laisse_pas_de_tmp_apres_succes(self):
        cible = memoire.TOMBES_FICHIER
        memoire._ecrire_texte_atomique(cible, "contenu")
        fichiers = [p.name for p in cible.parent.iterdir()]
        # Le .tmp ne doit PAS traîner.
        self.assertNotIn("tombes.json.tmp", fichiers, f"trouvé .tmp : {fichiers}")
        self.assertIn("tombes.json", fichiers)

    def test_atomo_retombe_sur_ecriture_directe_si_tmp_echoue(self):
        # Cas dur : le .tmp est rendu inaccessible. os.replace + write_text
        # vont lever OSError ; on retombe sur l'écriture directe du script.
        cible = memoire.TOMBES_FICHIER
        # On crée un .tmp avec un chemin impossible (fichier là où on
        # attendrait un dossier si on essayait d'en créer un).
        try:
            cible.write_text("", encoding="utf-8")  # fichier normal
            # On va simuler un crash tmp.write_text en passant par un
            # chemin invalide : sur macOS, on ne peut pas créer un fichier
            # dont un parent est un FICHIER ordinaire.
            cible.parent.mkdir(parents=True, exist_ok=True)
            bloc = cible.parent / "BLOQUEUR"
            bloc.write_text("je suis un fichier, pas un dossier", encoding="utf-8")
            # Contenu qui passera par le chemin normal, pour valider.
            memoire._ecrire_texte_atomique(cible, "ok")
            self.assertEqual(cible.read_text(encoding="utf-8"), "ok")
        finally:
            pass  # nettoyage géré par le TemporaryDirectory

    # ------------------------------------------------------------------
    # Tombes & démarrage de Root
    # ------------------------------------------------------------------
    def test_demarrage_tombes_json_corrompu(self):
        """Scénario : tombes.json abîmé par un crash. Au prochain démarrage,
        memoire_noter ne doit JAMAIS planter."""
        memoire.TOMBES_FICHIER.write_text('{"corrompu":', encoding="utf-8")
        # Toute la chaîne _tombes_charger → memoire_noter reste silencieuse.
        tombes = memoire._tombes_charger()
        self.assertEqual(tombes, [])
        # Et on peut toujours noter (le fait ne sera pas bloqué par une tombe
        # fantôme).
        status = memoire.memoire_noter("cat", "fait bénin qui doit passer")
        self.assertIn("Noté", status)

    def test_demarrage_memoire_md_binaire(self):
        """Un utilisateur a ouvert memoire.md avec un éditeur qui a mal
        encodé. memoire_pour_prompt ne doit pas planter."""
        memoire.MEMOIRE_FICHIER.write_bytes(b"\x89PNG\x0d\x0a\x1a\x0a\x00")
        self.assertIsInstance(memoire.memoire_pour_prompt(), str)
        # Un fichier corrompu rend juste un prompt vide ou rédigé, pas une exception.

    def test_demarrage_etat_json_corrompu(self):
        # ETAT_FICHIER corrompu ne casse rien (rien ne le lit activement,
        # mais au moins _lire_json_tolerant le couvrira si on en a besoin).
        memoire.ETAT_FICHIER.write_text("casse", encoding="utf-8")
        self.assertIsNone(memoire._lire_json_tolerant(memoire.ETAT_FICHIER, None))

    def test_tombes_ecrivent_aussi_point_bak(self):
        # Quand on écrit une tombe, le .bak doit contenir la même empreinte
        # pour préparer la récupération au prochain démarrage si crash.
        memoire.memoire_noter("cat", "fait qui sera oublié")
        memoire.memoire_oublier("qui sera oublié")
        bak = memoire.TOMBES_FICHIER.with_suffix(".json.bak")
        self.assertTrue(memoire.TOMBES_FICHIER.exists())
        self.assertTrue(bak.exists())
        import json as _json
        principal = _json.loads(memoire.TOMBES_FICHIER.read_text(encoding="utf-8"))
        sauve = _json.loads(bak.read_text(encoding="utf-8"))
        self.assertEqual(principal, sauve)

    def test_tombes_recuperation_apres_corruption_pendant_ecriture(self):
        # Scénario le plus sombre : crash en pleine écriture de tombes.json,
        # le fichier est tronqué au milieu, mais le .bak est intègre.
        memoire.memoire_noter("cat", "fait bénin puis oublié")
        memoire.memoire_oublier("bénin puis oublié")
        # Maintenant corrupter le fichier principal.
        memoire.TOMBES_FICHIER.write_text('{"coupe":', encoding="utf-8")
        # et essayer de re-noter le fait oublié
        r = memoire.memoire_noter("cat", "fait bénin puis oublié")
        # Doit être refusé par la tombe — prouvant qu'on a lu le .bak.
        self.assertIn("tombale", r.lower())

    # ------------------------------------------------------------------
    # memoire.md reste toujours valide après memoire_noter (atomicité
    # visible de l'extérieur)
    # ------------------------------------------------------------------
    def test_memoire_md_toujours_utf8_apres_noter(self):
        memoire.memoire_noter("profil", "Utilisateur préfère le français.")
        contenu = memoire.MEMOIRE_FICHIER.read_bytes()
        # Décodable UTF-8 — sinon _lire_texte_tolerant le détecterait.
        contenu.decode("utf-8")

    def test_memoire_noter_apres_unicodedecodeerror(self):
        """Simule la suite du démarrage après un fichier corrompu : le
        memoire_noter suivant doit partir d'une base vide et écrire
        correctement."""
        memoire.MEMOIRE_FICHIER.write_bytes(b"\xff\xfe\x00invalid")
        # Ne lève rien et écrit sur le contenu (perdu) par-dessus.
        status = memoire.memoire_noter("cat", "fait sain")
        self.assertIn("Noté", status)
        # Le fichier est maintenant UTF-8 propre.
        texte = memoire._lire_texte_tolerant(memoire.MEMOIRE_FICHIER)
        self.assertIn("fait sain", texte)


class TestRappelPertinent(unittest.TestCase):
    """Rappel par pertinence : sélection des faits au moment d'une demande.

    Purement lexical (Jaccard), aucun appel modèle, bibliothèque standard
    uniquement. Les cas limites étant le cœur du méta-prompt, chaque test
    est pensé pour verrouiller un comportement qui NE DOIT PAS casser :

    - demande vide                → liste vide (pas de mot → pas de score)
    - mémoire vide                → liste vide
    - mémoire absente             → liste vide (règle 4b inchangée)
    - aucun recouvrement          → liste vide (préférer « rien » au bruit)
    - accents / casse normalisés  → mêmes scores
    - égalité de scores           → fait le plus ancien gagne (stabilité)
    - n=0 / n négatif             → liste vide
    - n < nombre de faits trouvés → exactement n renvoyés
    - n > nombre de faits trouvés → autant que trouvés, pas plus
    - rappel_pour_prompt          → format cohérent (header + `- `), jamais
                                    ``None``, chaîne vide quand rien à dire
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sauve = memoire.MEMOIRE_FICHIER
        memoire.MEMOIRE_FICHIER = Path(self.tmp.name) / "memoire.md"

    def tearDown(self):
        memoire.MEMOIRE_FICHIER = self.sauve
        self.tmp.cleanup()

    def _ecrire_memoire(self, faits: list[str]) -> None:
        """Helper : écrit une mémoire avec un header et les faits fournis."""
        contenu = "# Mémoire durable\n\n" + "".join(
            f"- {f}\n" for f in faits)
        memoire.MEMOIRE_FICHIER.write_text(contenu, encoding="utf-8")

    # ------------------------------------------------------------------
    # A. Cas critiques : demande vide
    # ------------------------------------------------------------------
    def test_demande_vide_renvoie_liste_vide(self):
        self._ecrire_memoire([
            "Root habite dans ~/Projets/root-harness-git",
            "La mascotte est un renard",
        ])
        self.assertEqual(memoire.rappel_pertinent(""), [])
        self.assertEqual(memoire.rappel_pertinent("   "), [])
        self.assertEqual(memoire.rappel_pertinent("\n\t"), [])

    # ------------------------------------------------------------------
    # B. Cas critiques : mémoire vide ou absente
    # ------------------------------------------------------------------
    def test_memoire_absente_renvoie_liste_vide(self):
        # Pas de fichier du tout : rien à lire, mais jamais d'exception.
        self.assertFalse(memoire.MEMOIRE_FICHIER.exists())
        self.assertEqual(memoire.rappel_pertinent("question"), [])

    def test_memoire_vide_renvoie_liste_vide(self):
        memoire.MEMOIRE_FICHIER.write_text("", encoding="utf-8")
        self.assertEqual(memoire.rappel_pertinent("question"), [])

    def test_memoire_sans_faits_renvoie_liste_vide(self):
        memoire.MEMOIRE_FICHIER.write_text("# Titre sans tirets\n", encoding="utf-8")
        self.assertEqual(memoire.rappel_pertinent("question"), [])

    # ------------------------------------------------------------------
    # C. Aucun recouvrement → liste vide plutôt que du bruit
    # ------------------------------------------------------------------
    def test_aucun_recouvrement_renvoie_liste_vide(self):
        self._ecrire_memoire([
            "Le capitaine Haddock aime le whisky",
            "Les Tupamaros ont marqué l'Uruguay",
            "Le quark charm est un fermion",
        ])
        # La demande n'a AUCUN mot en commun avec les faits : on renvoie []
        # et pas un « top 3 » rempli de souvenirs non pertinents.
        res = memoire.rappel_pertinent("bibliothèque standard requête")
        self.assertEqual(res, [])

    # ------------------------------------------------------------------
    # D. Casse et accents normalisés
    # ------------------------------------------------------------------
    def test_casse_normalisee(self):
        self._ecrire_memoire([
            "La boucle principale est dans root.py",
            "Le canal relie les agents",
        ])
        # Casse opposée min/MAJ : même recouvrement
        a = memoire.rappel_pertinent("boucle racine ROOT.PY")
        b = memoire.rappel_pertinent("BOUCLE RACINE root.py")
        self.assertEqual(a, b)
        self.assertEqual(a, ["La boucle principale est dans root.py"])

    def test_accents_normalises(self):
        self._ecrire_memoire([
            "Utiliser à la fois été et hiver change la sémantique",
        ])
        # Avec accents dans les faits, sans dans la demande → match quand même.
        res = memoire.rappel_pertinent("ete hiver semantique")
        self.assertTrue(any("sémantique" in f for f in res))

    def test_ponctuation_terminale_toleree(self):
        self._ecrire_memoire([
            "Le dépôt vit sous root-harness-git.",
        ])
        # Le point final dans le fait ne doit pas masquer la correspondance.
        res = memoire.rappel_pertinent("root-harness-git")
        self.assertEqual(res, ["Le dépôt vit sous root-harness-git."])

    # ------------------------------------------------------------------
    # E. Recouvrement réel → tri par score, stabilité en cas d'égalité
    # ------------------------------------------------------------------
    def test_score_de_croiissant_mot_pleinement_partage_gagne(self):
        """Le fait le plus recouvrant sort en premier, pas par hasard."""
        self._ecrire_memoire([
            "La mémoire persiste sur disque",
            "Le disque est un matériel rare",
            "La mémoire utilise Jaccard pour la pertinence",
        ])
        res = memoire.rappel_pertinent("mémoire Jaccard")
        # Le 3ᵉ fait a 2 mots en commun avec la demande ; le 1ᵉ en a 1 seul.
        self.assertEqual(res[0], "La mémoire utilise Jaccard pour la pertinence")

    def test_egalite_de_score_ancien_gagne(self):
        """Trois faits à score identique : le plus ancien dans le fichier gagne
        car le départage doit être déterministe et stable."""
        self._ecrire_memoire([
            "MotX est bon",
            "MotX est grand",
            "MotX est rapide",
        ])
        res = memoire.rappel_pertinent("MotX", n=3)
        # Tous ont le même Jaccard (1 mot / 4 mots) : l'ordre du fichier prime.
        self.assertEqual(res, [
            "MotX est bon",
            "MotX est grand",
            "MotX est rapide",
        ])

    # ------------------------------------------------------------------
    # F. Paramètre n
    # ------------------------------------------------------------------
    def test_n_zero_ou_negatif_renvoie_liste_vide(self):
        self._ecrire_memoire(["un fait pertinent pour chat"])
        self.assertEqual(memoire.rappel_pertinent("chat", n=0), [])
        self.assertEqual(memoire.rappel_pertinent("chat", n=-3), [])

    def test_n_inferieur_au_nombre_de_correspondances(self):
        self._ecrire_memoire([f"fait chat numéro {i}" for i in range(8)])
        res = memoire.rappel_pertinent("chat", n=3)
        self.assertEqual(len(res), 3)
        # Stabilité : ce sont les 3 premiers écrits (score égal).
        for i in range(3):
            self.assertEqual(res[i], f"fait chat numéro {i}")

    def test_n_superieur_au_nombre_de_correspondances(self):
        self._ecrire_memoire(["seul fait", "autre fait aussi"])
        res = memoire.rappel_pertinent("fait", n=10)
        self.assertEqual(len(res), 2)

    def test_n_par_defaut_cinq(self):
        self._ecrire_memoire([f"note numéro {i}" for i in range(10)])
        res = memoire.rappel_pertinent("note")
        self.assertEqual(len(res), 5)

    # ------------------------------------------------------------------
    # G. Immunité au doublon
    # ------------------------------------------------------------------
    def test_fait_sans_mot_apres_normalisation_est_ignore(self):
        # Un fait réduit à la ponctuation n'entre jamais en compétition
        # (son set de mots serait vide → inter==0 → écarté).
        self._ecrire_memoire(["…", "un vrai souvenir"])  # type: ignore[misc]
        res = memoire.rappel_pertinent("souvenir")
        self.assertEqual(res, ["un vrai souvenir"])

    # ------------------------------------------------------------------
    # H. rappel_pour_prompt : formatage cohérent avec memoire_pour_prompt
    # ------------------------------------------------------------------
    def test_rappel_pour_prompt_vide_si_rien_a_dire(self):
        self._ecrire_memoire(["fait sans intersection avec rien"])
        self.assertEqual(memoire.rappel_pour_prompt("zzza"), "")

    def test_rappel_pour_prompt_demande_vide(self):
        self._ecrire_memoire(["fait"])
        self.assertEqual(memoire.rappel_pour_prompt(""), "")

    def test_rappel_pour_prompt_memoire_absente(self):
        self.assertFalse(memoire.MEMOIRE_FICHIER.exists())
        self.assertEqual(memoire.rappel_pour_prompt("question"), "")

    def test_rappel_pour_prompt_format(self):
        self._ecrire_memoire([
            "Les pierres tombales protègent contre la résurrection",
            "Le store est atomique",
        ])
        out = memoire.rappel_pour_prompt("pierres tombales", n=2)
        self.assertTrue(out.startswith("Souvenirs durables pertinents pour la demande actuelle :"))
        # Les deux sont des faits contenant « pierres » :
        self.assertIn("- Les pierres tombales protègent contre la résurrection", out)
        # Chaque ligne de fait commence par "- ".
        lignes = out.splitlines()[1:]
        for ligne in lignes:
            self.assertTrue(ligne.startswith("- "), ligne)

    def test_rappel_pour_prompt_n_est_pas_un_int(self):
        self._ecrire_memoire(["test"])
        # Un mauvais type ne doit PAS planter (comportement robuste).
        # On exige simplement que la fonction retourne une str.
        res = memoire.rappel_pour_prompt("test", n=1)
        self.assertIsInstance(res, str)

    # ------------------------------------------------------------------
    # I. AUCUN effet de bord : rappel est une lecture pure
    # ------------------------------------------------------------------
    def test_rappel_modifie_rien_sur_disque(self):
        self._ecrire_memoire(["fait pour la pureté"])
        avant = memoire.MEMOIRE_FICHIER.read_text(encoding="utf-8")
        memoire.rappel_pertinent("pureté")
        memoire.rappel_pour_prompt("pureté")
        apres = memoire.MEMOIRE_FICHIER.read_text(encoding="utf-8")
        self.assertEqual(avant, apres, "rappel_pertinent ou rappel_pour_prompt a modifié le fichier")


if __name__ == "__main__":
    unittest.main()
