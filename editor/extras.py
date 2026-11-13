# editor/extras.py
"""Standalone extra CLI tools for Expanse diagnostics and repair.

Commands:
  python -m editor.extras check-items --game <slug> [--skip-orphans]
  python -m editor.extras check-exits --game <slug>
  python -m editor.extras fix       --game <slug> [--dry-run]

All read-only except `fix`, which backs up rooms.json before writing.
"""
import argparse
import copy
import sys
import time
from difflib import get_close_matches
from pathlib import Path

from editor.cli import Editor, GAMES_DIR

_OPPOSITE = {
    "north": "south", "south": "north",
    "east": "west", "west": "east",
    "up": "down", "down": "up",
    "northeast": "southwest", "southwest": "northeast",
    "northwest": "southeast", "southeast": "northwest",
}


# ─── diagnostics ────────────────────────────────────────────────────
def check_items(ed, skip_orphans=False):
    item_ids = {i["id"] for i in ed.data["item"]}
    referenced = set()
    issues = []
    for room in ed.data["room"]:
        items = room.get("items", [])
        for item_id in items:
            referenced.add(item_id)
            if item_id not in item_ids:
                issues.append(
                    f"room '{room['id']}' references unknown item '{item_id}'"
                )
        for item_id in set(items):
            n = items.count(item_id)
            if n > 1:
                issues.append(
                    f"room '{room['id']}' has {n}x '{item_id}' stacked"
                )
    if not skip_orphans:
        for item in ed.data["item"]:
            if item["id"] not in referenced:
                issues.append(
                    f"item '{item['id']}' is defined but not placed in any room"
                )
    if not issues:
        return f"OK — {len(item_ids)} items, all correctly placed."
    return f"{len(issues)} issue(s):\n " + "\n ".join(issues)


def check_exits(ed):
    room_by_id = {r["id"]: r for r in ed.data["room"]}
    warnings = []
    seen = set()
    hard_errors = []
    for room in ed.data["room"]:
        for direction, target in room.get("exits", {}).items():
            if target not in room_by_id:
                continue
            if target == room["id"]:
                hard_errors.append(
                    f"room '{room['id']}' exits {direction} back to itself"
                )
                continue
            target_room = room_by_id[target]
            target_exits = target_room.get("exits", {})
            if direction in target_exits and target_exits[direction] == room["id"]:
                hard_errors.append(
                    f"room '{room['id']}' {direction} -> '{target}' "
                    f"AND '{target}' {direction} -> '{room['id']}' "
                    f"(impossible direction)"
                )
                continue
            opposite = _OPPOSITE.get(direction)
            if not opposite:
                continue
            key = (room["id"], target, direction)
            rev = (target, room["id"], opposite)
            if key in seen or rev in seen:
                continue
            seen.add(key)
            if opposite not in target_exits:
                warnings.append(
                    f"room '{room['id']}' {direction} -> '{target}' "
                    f"has no reciprocal {opposite} exit back"
                )
            elif target_exits[opposite] != room["id"]:
                warnings.append(
                    f"room '{room['id']}' {direction} -> '{target}' "
                    f"but '{target}' {opposite} -> "
                    f"'{target_exits[opposite]}' (asymmetric)"
                )
    return hard_errors, warnings


# ─── fixer ──────────────────────────────────────────────────────────
def fix_game(ed, dry_run=False):
    """Auto-repair self-loops, missing reciprocals, dangling item refs.

    Works on a deep copy first, then saves back only if dry_run is
    False. That keeps dry-run honest: even though mutations happen
    during the pass, they land on the copy and every downstream
    check sees the post-fix state.

    Returns (changes, unfixable, backup_path_or_None).
    """
    changes = []
    unfixable = []
    working = copy.deepcopy(ed.data)
    rooms = {r["id"]: r for r in working["room"]}
    item_ids = {i["id"] for i in working["item"]}

    # ─── 1. Self-loops ─────────────────────────────────────────────
    # Look for a room that points opposite-direction to us. That's the
    # intended target. Otherwise, delete the exit.
    for rid, room in rooms.items():
        exits = room.get("exits", {})
        for direction in list(exits.keys()):
            target = exits[direction]
            if target != rid:
                continue
            opposite = _OPPOSITE.get(direction)
            inferred = None
            if opposite:
                for other_id, other_room in rooms.items():
                    if other_id == rid:
                        continue
                    if other_room.get("exits", {}).get(opposite) == rid:
                        inferred = other_id
                        break
            if inferred:
                changes.append(
                    f"{'would fix' if dry_run else 'fixed'}: "
                    f"{rid}.{direction}: self-loop -> '{inferred}' (inferred)")
                exits[direction] = inferred
            else:
                changes.append(
                    f"{'would remove' if dry_run else 'removed'}: "
                    f"{rid}.{direction}: self-loop (no inferred target)")
                del exits[direction]

    # ─── 2. Missing reciprocals ────────────────────────────────────
    # If A.direction -> B but B has no opposite exit at all, add B.opposite -> A.
    # If B.opposite points elsewhere, flag it (don't touch).
    for rid, room in rooms.items():
        exits = room.get("exits", {})
        for direction, target_id in exits.items():
            if target_id not in rooms or target_id == rid:
                continue
            opposite = _OPPOSITE.get(direction)
            if not opposite:
                continue
            target_room = rooms[target_id]
            target_exits = target_room.get("exits", {})
            if opposite in target_exits:
                if target_exits[opposite] != rid:
                    unfixable.append(
                        f"{target_id}.{opposite} -> "
                        f"'{target_exits[opposite]}' (expected '{rid}') "
                        f"— manual review"
                    )
                continue
            changes.append(
                f"{'would add' if dry_run else 'added'}: "
                f"{target_id}.{opposite} -> '{rid}' "
                f"(missing reciprocal for {rid}.{direction})")
            target_room.setdefault("exits", {})[opposite] = rid

    # ─── 3. Dangling item refs via fuzzy match ─────────────────────
    for room in working["room"]:
        items = room.get("items", [])
        for i, item_id in enumerate(items):
            if item_id in item_ids:
                continue
            candidates = get_close_matches(item_id, item_ids, n=1, cutoff=0.7)
            if candidates:
                fix_to = candidates[0]
                changes.append(
                    f"{'would fix' if dry_run else 'fixed'}: "
                    f"{room['id']}.items[{i}]: '{item_id}' -> '{fix_to}'")
                items[i] = fix_to
            else:
                unfixable.append(
                    f"{room['id']}.items[{i}] references unknown "
                    f"'{item_id}' (no close match)"
                )

    # ─── 4. Persist (only if not dry_run) ──────────────────────────
    backup = None
    if changes and not dry_run:
        # Copy mutated rooms back into ed.data before saving
        ed.data["room"] = working["room"]
        src = ed.data_dir / "rooms.json"
        if src.exists():
            ts = time.strftime("%Y%m%d-%H%M%S")
            backup = ed.data_dir / f"rooms.json.bak-{ts}"
            backup.write_bytes(src.read_bytes())
        ed.dirty.add("room")
        ed.save()

    return changes, unfixable, backup


# ─── CLI ────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        prog="editor.extras",
        description="Standalone diagnostics and repair for Expanse games.",
    )
    parser.add_argument(
        "command",
        choices=["check-items", "check-exits", "fix"],
    )
    parser.add_argument("--game", default="default",
                        help="Game slug (default: default)")
    parser.add_argument("--dry-run", action="store_true",
                        help="(fix only) show what would change without saving")
    parser.add_argument("--skip-orphans", action="store_true",
                        help="(check-items only) skip defined-but-unplaced items")
    args = parser.parse_args()

    game_dir = GAMES_DIR / args.game
    if not game_dir.exists():
        print(f"Game '{args.game}' not found in {GAMES_DIR}.", file=sys.stderr)
        sys.exit(1)

    ed = Editor(game_dir)
    print(f"Game: {args.game}  ({len(ed.data['room'])} rooms, "
          f"{len(ed.data['item'])} items)")

    if args.command == "check-items":
        print(check_items(ed, skip_orphans=args.skip_orphans))
        return

    if args.command == "check-exits":
        hard_errors, warnings = check_exits(ed)
        if hard_errors:
            print(f"Impossible exits: {len(hard_errors)}")
            for e in hard_errors:
                print(f"  X {e}")
        if warnings:
            print(f"Asymmetric exits: {len(warnings)}")
            for w in warnings:
                print(f"  - {w}")
        if not hard_errors and not warnings:
            print("OK - all exits are reciprocal and consistent.")
        return

    if args.command == "fix":
        changes, unfixable, backup = fix_game(ed, dry_run=args.dry_run)
        if args.dry_run:
            print(f"DRY RUN — {len(changes)} would be changed:")
        else:
            print(f"{len(changes)} change(s) applied:")
        for c in changes:
            print(f"  {c}")
        if unfixable:
            print(f"\n{len(unfixable)} unfixable issue(s) — manual review needed:")
            for u in unfixable:
                print(f"  ? {u}")
        if not changes and not unfixable:
            print("Nothing to fix — world is consistent.")
        if backup:
            print(f"\nBackup: {backup}")
            print("Note: if the game server is running, Apply or restart "
                  "to pick up the new content.")
        return


if __name__ == "__main__":
    main()
