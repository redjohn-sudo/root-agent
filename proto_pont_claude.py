"""
Prototype du pont Claude <-> Root (jetable, n'est importé par personne).

But : prouver que Claude, lancé via l'Agent SDK sur l'abonnement Max, peut
penser ET n'agir QU'AVEC un outil fourni par nous (format MCP), ses propres
outils natifs (Read/Edit/Bash) étant coupés. Si ça marche, on généralise aux
42 outils de Root.
"""
from __future__ import annotations
import anyio
from claude_agent_sdk import (
    tool, create_sdk_mcp_server, ClaudeAgentOptions, query,
    AssistantMessage, TextBlock, ToolUseBlock, ResultMessage,
    PermissionResultAllow,
)


# ── Un outil "de Root" : compter les lignes d'un fichier. ───────────────────
@tool("compter_lignes", "Compte les lignes d'un fichier texte", {"chemin": str})
async def compter_lignes(args):
    from pathlib import Path
    n = len(Path(args["chemin"]).read_text(encoding="utf-8").splitlines())
    return {"content": [{"type": "text", "text": f"{n} lignes"}]}


serveur = create_sdk_mcp_server("root", tools=[compter_lignes])


async def autoriser(nom, entree, ctx):
    # On n'autorise QUE nos outils ; tout le reste est refusé.
    if nom.startswith("mcp__root__"):
        return PermissionResultAllow()
    from claude_agent_sdk import PermissionResultDeny
    return PermissionResultDeny(message="Seuls les outils de Root sont permis.")


options = ClaudeAgentOptions(
    tools=[],                                   # coupe les outils natifs de Claude Code
    mcp_servers={"root": serveur},
    allowed_tools=["mcp__root__compter_lignes"],   # seul outil permis ; tools=[] coupe les natifs
    system_prompt="Tu es Root, l'agent local de Vincent. Tu agis seulement avec tes propres outils.",
    model="haiku",                              # pas cher pour le test
    max_turns=5,
    strict_mcp_config=True,
    can_use_tool=autoriser,
)


async def main():
    prompt = ("Combien de lignes compte le fichier "
              "~/Projets/root-harness/root.py ? Utilise ton outil.")
    a_appele = False
    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, AssistantMessage):
            for b in msg.content:
                if isinstance(b, ToolUseBlock):
                    a_appele = True
                    print(f"[Claude appelle un outil de Root] {b.name} {b.input}")
                elif isinstance(b, TextBlock):
                    print(f"[Claude dit] {b.text.strip()}")
        elif isinstance(msg, ResultMessage):
            print(f"[fin] tours={msg.num_turns} cout_estime_usd={getattr(msg, 'total_cost_usd', None)}")
    print("VERDICT:", "Claude a bien utilisé l'outil de Root ✅" if a_appele
          else "Claude n'a PAS appelé l'outil ❌")


if __name__ == "__main__":
    anyio.run(main)
