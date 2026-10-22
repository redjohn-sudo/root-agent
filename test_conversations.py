"""Conversations : chaque source est lue correctement, rien n'est jamais écrit
chez les autres outils, et le choix de Vincent (titres, projets) tient.
Tout se passe dans un dossier temporaire : aucun vrai fichier n'est lu."""

import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import conversations as cv


def _jsonl(chemin, lignes):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text("\n".join(json.dumps(l) for l in lignes) + "\n", encoding="utf-8")


def _claude(texte_user, entree="cli", titre="Mon titre"):
    base = {"parentUuid": None, "isSidechain": False, "cwd": "/Users/x/Projets/root-harness",
            "entrypoint": entree, "timestamp": "2026-10-22T10:00:00Z"}
    return [
        {"type": "ai-title", "aiTitle": "Ancien titre", "sessionId": "s"},
        base | {"type": "user", "message": {"role": "user", "content": texte_user}},
        base | {"type": "user", "message": {"role": "user", "content": "<system-reminder>bruit</system-reminder>"}},
        base | {"type": "assistant", "message": {"model": "claude-opus-5-5", "content": [
            {"type": "thinking", "thinking": "…"}, {"type": "tool_use", "name": "Bash", "input": {}}]}},
        base | {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "x"}]}},
        base | {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "input": {}}]}},
        base | {"type": "assistant", "message": {"content": [{"type": "text", "text": "Voilà la réponse."}]}},
        base | {"type": "user", "isSidechain": True, "message": {"role": "user", "content": "d'un sous-agent"}},
        {"type": "ai-title", "aiTitle": titre, "sessionId": "s"},
        {"type": "api-request-blob", "message": {"content": "énorme"}},
    ]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="test-conv-"))
        for nom, val in (("DOSSIER", self.tmp / "root-conv"), ("CLAUDE_PROJETS", self.tmp / "claude"),
                         ("CODEX_DB", self.tmp / "codex" / "state.sqlite"), ("HERMES", self.tmp / "hermes")):
            p = mock.patch.object(cv, nom, val)
            p.start()
            self.addCleanup(p.stop)

    def codex(self):
        db = cv.CODEX_DB
        db.parent.mkdir(parents=True)
        rollout = self.tmp / "codex" / "r1.jsonl"
        _jsonl(rollout, [
            {"type": "session_meta", "payload": {}},
            {"type": "response_item", "payload": {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "consignes"}]}},
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "# AGENTS.md instructions"}]}},
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "regarde contingency"}]}},
            {"type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec"}},
            {"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "C'est fait."}]}},
        ])
        cx = sqlite3.connect(db)
        cx.execute("create table threads (id, rollout_path, title, name, cwd, model, updated_at, "
                   "first_user_message, archived, thread_source, source)")
        cx.execute("insert into threads values ('c1', ?, 'titre auto', null, '/Users/x', 'gpt-6', 1792000000, 'regarde', 0, 'user', 'cli')", (str(rollout),))
        cx.execute("insert into threads values ('c2', ?, 'sous-agent', null, '', 'gpt-6', 1, '', 0, 'subagent', '{\"subagent\":1}')", (str(rollout),))
        cx.execute("insert into threads values ('c3', ?, 'exec', null, '', 'gpt-6', 1, '', 0, 'user', 'exec')", (str(rollout),))
        cx.commit(); cx.close()

    def hermes(self):
        db = cv.HERMES / "state.db"
        db.parent.mkdir(parents=True)
        cx = sqlite3.connect(db)
        cx.execute("create table sessions (id, source, title, model, cwd, started_at, last_activity_at, "
                   "message_count, hidden, archived)")
        cx.execute("create table messages (id integer primary key, session_id, role, content, tool_calls, tool_name)")
        cx.execute("insert into sessions values ('h1', 'cli', '', 'moonshotai/Kimi-K3', '/Users/x', 1, 1792000500, 4, 0, 0)")
        cx.execute("insert into sessions values ('h2', 'cron', 'tâche', 'm', '', 1, 2, 2, 0, 0)")
        for role, contenu, appels in (("user", "Prépare le hackathon de Munich", None), ("user", "Prépare le hackathon de Munich", None),
                                      ("assistant", "Je regarde.", json.dumps([{"function": {"name": "web_search"}}])),
                                      ("tool", "résultat", None), ("assistant", "Voilà le plan.", None)):
            cx.execute("insert into messages (session_id, role, content, tool_calls) values ('h1', ?, ?, ?)", (role, contenu, appels))
        cx.commit(); cx.close()


class TestSources(Base):
    def test_claude_titre_bruit_outils_et_sous_agents(self):
        _jsonl(cv.CLAUDE_PROJETS / "-Users-x" / "aaa.jsonl", _claude("Salut Claude"))
        _jsonl(cv.CLAUDE_PROJETS / "-Users-x" / "aaa" / "subagents" / "sub.jsonl", _claude("sous-agent"))
        _jsonl(cv.CLAUDE_PROJETS / "-tmp" / "auto.jsonl", _claude("claude -p", entree="sdk-cli"))
        liste = cv.lister()["liste"]
        self.assertEqual([c["cle"] for c in liste], ["claude:aaa"])     # ni sous-agent ni appel automatique
        c = liste[0]
        self.assertEqual(c["titre"], "Mon titre")                       # le dernier titre gagne
        self.assertEqual(c["cerveau"], "claude-opus-5-5")
        fil = cv.ouvrir("claude:aaa")["fil"]
        self.assertEqual(fil, [{"r": "toi", "t": "Salut Claude"}, {"r": "outils", "noms": ["Bash", "Read"]},
                               {"r": "root", "t": "Voilà la réponse."}])

    def test_codex_sans_sous_agents_ni_exec_ni_consignes(self):
        self.codex()
        liste = cv.lister()["liste"]
        self.assertEqual([c["cle"] for c in liste], ["codex:c1"])
        self.assertEqual(liste[0]["titre"], "titre auto")
        fil = cv.ouvrir("codex:c1")["fil"]
        self.assertEqual([x["r"] for x in fil], ["toi", "outils", "root"])
        self.assertEqual(fil[0]["t"], "regarde contingency")

    def test_hermes_sans_cron_doublons_ecartes(self):
        self.hermes()
        liste = cv.lister()["liste"]
        self.assertEqual([c["cle"] for c in liste], ["hermes:h1"])
        self.assertEqual(liste[0]["titre"], "Prépare le hackathon de Munich")   # titre vide : le 1er message
        fil = cv.ouvrir("hermes:h1")["fil"]
        self.assertEqual([x["r"] for x in fil], ["toi", "root", "outils", "root"])
        self.assertEqual(cv.commande_reprise("hermes:h1", {}), ["hermes", "--resume", "h1"])

    def test_les_bases_des_autres_restent_intactes(self):
        self.codex(); self.hermes()
        avant = {p: p.read_bytes() for p in (cv.CODEX_DB, cv.HERMES / "state.db")}
        cv.lister(); cv.ouvrir("hermes:h1"); cv.ouvrir("codex:c1")
        cv.renommer("codex:c1", "Nouveau nom"); cv.masquer("hermes:h1")
        for p, octets in avant.items():
            self.assertEqual(p.read_bytes(), octets)

    def test_cache_ne_relit_pas_un_fichier_inchange(self):
        _jsonl(cv.CLAUDE_PROJETS / "-Users-x" / "aaa.jsonl", _claude("Salut"))
        cv.balayer()
        with mock.patch.object(cv, "lire_claude", side_effect=AssertionError("relu")):
            self.assertEqual(len(cv.balayer()), 1)


class TestRoot(Base):
    def test_sauver_lister_ouvrir_supprimer(self):
        msgs = [{"role": "system", "content": "âme"},
                {"role": "user", "content": [{"type": "text", "text": "regarde mon écran"},
                                             {"type": "image_url", "image_url": {"url": "data:image/png;base64," + "A" * 5000}}]},
                {"role": "assistant", "content": None, "tool_calls": [{"function": {"name": "capturer_ecran"}}]},
                {"role": "tool", "content": "ok"},
                {"role": "assistant", "content": "Je vois Brave."}]
        cv.sauver_root("r1", msgs, "deepseek-flash")
        brut = (cv.DOSSIER / "root" / "r1.json").read_text()
        self.assertNotIn("A" * 100, brut)                               # l'image n'est pas gardée
        c = cv.lister()["liste"][0]
        self.assertEqual((c["cle"], c["titre"], c["cerveau"]), ("root:r1", "regarde mon écran", "deepseek-flash"))
        self.assertEqual([x["r"] for x in cv.ouvrir("root:r1")["fil"]], ["toi", "outils", "root"])
        cv.supprimer_root("r1")
        self.assertEqual(cv.lister()["liste"], [])


class TestChoix(Base):
    def setUp(self):
        super().setUp()
        self.codex(); self.hermes()

    def test_projets_de_depart_et_suggestion(self):
        d = cv.lister()
        self.assertEqual([p["nom"] for p in d["projets"]], ["Contingency", "Hackathon Munich", "Root"])
        par = {c["cle"]: c for c in d["liste"]}
        ids = {p["nom"]: p["id"] for p in d["projets"]}
        self.assertEqual(par["codex:c1"]["projet"], ids["Contingency"])  # mot trouvé dans le premier message
        self.assertEqual(par["hermes:h1"]["projet"], ids["Hackathon Munich"])
        self.assertTrue(par["hermes:h1"]["auto"])

    def test_suggestion_mots_entiers(self):
        projets = [{"id": "r", "nom": "Root"}, {"id": "h", "nom": "Hackathon Munich"}]
        self.assertEqual(cv.suggerer({"cwd": "/Users/x/Projets/root-harness"}, projets), "r")
        self.assertIsNone(cv.suggerer({"titre": "un rootkit"}, projets))
        self.assertIsNone(cv.suggerer({"titre": "hackathon de Zurich"}, projets))  # tous les mots
        self.assertEqual(cv.suggerer({"titre": "Les hackathons à Münich"}, projets), "h")

    def test_renommer_ranger_epingler_masquer(self):
        p = cv.creer_projet("Doublr")
        cv.renommer("codex:c1", "  Mon audit  ")
        cv.ranger("codex:c1", p["id"])
        cv.epingler("codex:c1", True)
        cv.ranger("hermes:h1", "")                                       # « Non classées », choisi : plus de suggestion
        par = {c["cle"]: c for c in cv.lister()["liste"]}
        self.assertEqual(par["codex:c1"]["titre"], "Mon audit")
        self.assertEqual(par["codex:c1"]["projet"], p["id"])
        self.assertTrue(par["codex:c1"]["epingle"])
        self.assertEqual((par["hermes:h1"]["projet"], par["hermes:h1"]["auto"]), ("", False))
        cv.masquer("hermes:h1")
        self.assertNotIn("hermes:h1", {c["cle"] for c in cv.lister()["liste"]})

    def test_supprimer_un_projet_libere_ses_conversations(self):
        p = cv.creer_projet("Temporaire")
        cv.ranger("codex:c1", p["id"])
        cv.renommer_projet(p["id"], "Renommé")
        self.assertIn("Renommé", [x["nom"] for x in cv.lister()["projets"]])
        cv.supprimer_projet(p["id"])
        par = {c["cle"]: c for c in cv.lister()["liste"]}
        self.assertEqual(par["codex:c1"]["projet"], "")

    def test_recherche_dans_tout_le_texte_sans_accents(self):
        cles = [c["cle"] for c in cv.lister()["liste"]]
        self.assertEqual(cv.chercher("CONTINGENCY", cles), ["codex:c1"])
        self.assertEqual(cv.chercher("prepare munich", cles), ["hermes:h1"])
        self.assertEqual(cv.chercher("introuvable", cles), [])


class TestReprise(unittest.TestCase):
    def test_contexte_garde_le_debut_et_la_fin(self):
        fil = [{"r": "toi", "t": "PREMIER"}] + [{"r": "root", "t": f"milieu {i} " + "x" * 500} for i in range(60)] \
            + [{"r": "toi", "t": "DERNIER"}]
        ctx = cv.contexte_reprise("claude:a", "Titre", fil)
        self.assertIn("Vincent : PREMIER", ctx)
        self.assertIn("Vincent : DERNIER", ctx)
        self.assertIn("messages omis", ctx)
        self.assertLess(len(ctx), cv.REPRISE_MAX + 1500)

    def test_commandes(self):
        self.assertEqual(cv.commande_reprise("claude:abc", {}), ["claude", "--resume", "abc"])
        self.assertEqual(cv.commande_reprise("codex:abc", {}), ["codex", "resume", "abc"])
        self.assertIsNone(cv.commande_reprise("hermes:badcode/x", {"profil": "badcode"}))
        self.assertIsNone(cv.commande_reprise("root:x", {}))


if __name__ == "__main__":
    unittest.main()
