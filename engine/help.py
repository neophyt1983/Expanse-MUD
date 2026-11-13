# engine/help.py
from engine.commands import CommandContext, CommandRegistry


def generate_help(ctx: CommandContext, registry: CommandRegistry) -> str:
    lines = []
    hints = _hints(ctx)
    if hints:
        lines.append("Looking around:")
        lines.extend("  • " + h for h in hints)
        lines.append("")
    lines.append("Commands available right now:")
    for cmd in sorted(registry.available(ctx), key=lambda c: c.name):
        lines.append(f"  {cmd.usage:<22} {cmd.brief}")
    lines.append("")
    lines.append("Type 'help <command>' for usage and an example.")
    return "\n".join(lines)


def _hints(ctx: CommandContext) -> list:
    hints = []
    room = ctx.room

    if room.exits:
        exits = ", ".join(sorted(room.exits.keys()))
        hints.append(f"Exits: {exits}   (try 'go <direction>')")

    for eid in room.entities:
        ent = ctx.world.entities.get(eid)
        if ent and ent.alive and ent.id != ctx.player.id and not ent.is_player:
            first = ent.name.split()[0].lower()
            hints.append(f"{ent.name} is here.   (try 'attack {first}')")

    for item_id in room.items:
        item = ctx.world.items.get(item_id)
        if item:
            hints.append(f"{item['name']} lies here.   (try 'take {item['name'].lower()}')")

    if ctx.player.inventory:
        names = [ctx.world.items[i]["name"] for i in ctx.player.inventory
                 if i in ctx.world.items]
        if names:
            hints.append("You carry: " + ", ".join(names))

    if ctx.player.hp < ctx.player.max_hp:
        hints.append(f"Your HP is {ctx.player.hp}/{ctx.player.max_hp}.")

    return hints


def command_help(ctx: CommandContext, registry: CommandRegistry, args: str) -> str:
    arg = args.strip().lower()
    if not arg:
        return generate_help(ctx, registry)
    cmd = registry.resolve(arg)
    if not cmd:
        return f"No command '{arg}'."
    out = [f"{cmd.name} — {cmd.brief}"]
    if cmd.usage:
        out.append(f"Usage: {cmd.usage}")
    if cmd.aliases:
        out.append(f"Aliases: {', '.join(cmd.aliases)}")
    if cmd.example:
        out.append(f"Example: {cmd.example}")
    if cmd.help_text:
        out.append("")
        out.append(cmd.help_text)
    return "\n".join(out)
