"""
Pont Root <-> Claude via l'Agent SDK, sur l'ABONNEMENT Max (pas l'API payante).

Ici Claude mène la boucle, mais n'agit qu'avec les 39 outils de Root, exposés
en serveur MCP en processus. Les outils natifs de Claude Code sont coupés.
C'est un MODE d'exécution distinct de la boucle OpenAI de root.py.

Prudence : ce pont exécute les outils de Root que Claude demande. La demande
d'autorisation de Root (doit_demander / ecran.demander) n'est PAS encore
rebranchée ici : à faire avant tout usage réel avec des outils à risque.
"""
from __future__ import annotations
import time
import anyio
import root
from claude_agent_sdk import (
    tool, create_sdk_mcp_server, ClaudeAgentOptions, query,
    AssistantMessage, TextBlock, ToolUseBlock, ResultMessage,
    PermissionResultAllow, PermissionResultDeny,
)


def _handler(nom):
    """Un outil SDK qui délègue à l'outil Root `nom`."""
    async def h(args):
        res = root.executer_outil(nom, args or {})
        if isinstance(res, dict):
            txt = res.get("texte") or res.get("_image") and "(image)" or "(résultat)"
        else:
            txt = str(res)
        return {"content": [{"type": "text", "text": txt[:20000]}]}
    return h


def outils_sdk():
    """Les 39 outils de root.OUTILS traduits en outils MCP SDK."""
    liste = []
    for nom, o in root.OUTILS.items():
        schema = o["schema"]["parameters"]
        liste.append(tool(nom, o["schema"]["description"], schema)(_handler(nom)))
    return liste


async def _permission(nom, entree, ctx):
    """Garde-fou v1 : refuse tout outil que Root ferait confirmer (doit_demander).
    Accord interactif via l'UI à brancher ensuite."""
    court = nom.replace("mcp__root__", "")
    try:
        risque = root.doit_demander(court, entree or {})
    except Exception:
        risque = True
    if risque:
        return PermissionResultDeny(message="Outil a risque bloque en mode Max (v1).")
    return PermissionResultAllow()


def options(modele: str = "sonnet", systeme: str | None = None,
            effort: str | None = None) -> ClaudeAgentOptions:
    serveur = create_sdk_mcp_server("root", tools=outils_sdk())
    return ClaudeAgentOptions(
        tools=[],                               # couper les outils natifs de Claude Code
        mcp_servers={"root": serveur},
        system_prompt=systeme if systeme is not None else root.AME,
        model=modele,
        effort=effort,                          # low|medium|high|xhigh|max, ou None = défaut
        max_turns=12,
        strict_mcp_config=True,
        can_use_tool=_permission,               # consulté car pas d'allowed_tools large
    )


async def demander_ui(texte: str, ecran, modele: str = "sonnet", systeme: str | None = None,
                      effort: str | None = None):
    """Un tour piloté par Claude (Max), émis vers l'écran de la fenêtre.
    `ecran` expose outil(nom,args), reponse(texte), fin(secondes, usage)."""
    t0 = time.time()
    final = ""
    async for msg in query(prompt=texte, options=options(modele, systeme, effort)):
        if isinstance(msg, AssistantMessage):
            for b in msg.content:
                if isinstance(b, ToolUseBlock):
                    ecran.outil(b.name.replace("mcp__root__", ""), b.input)
                elif isinstance(b, TextBlock) and b.text.strip():
                    final = b.text
                    ecran.reponse(b.text)
    ecran.fin(int(time.time() - t0), None)
    return final


async def demander(texte: str, modele: str = "sonnet", systeme: str | None = None):
    """Version terminal pour tester hors fenêtre."""
    class EcranCLI:
        def outil(self, nom, args): print(f"[outil Root] {nom} {args}")
        def reponse(self, texte): print(f"[Claude] {texte}")
        def fin(self, secondes, usage): print(f"[fin] {secondes}s")
    return await demander_ui(texte, EcranCLI(), modele, systeme)


if __name__ == "__main__":
    anyio.run(lambda: demander(
        "Combien de lignes compte ~/Projets/root-harness/root.py ? Utilise tes outils."))
