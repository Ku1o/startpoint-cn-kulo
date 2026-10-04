#!/usr/bin/env python3
"""Patch BattleStartableLogic with the Fantasy equipment party gate."""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
CONTRACT = json.loads((HERE / "contract.json").read_text(encoding="utf-8"))
TARGET_SIGNATURE = (
    "public function isPartyStartable(param1:PartyPeek) : Boolean"
)
NEXT_SIGNATURE = "public function isItemStartable("
ANCHOR = "return _loc3_;"
BEGIN_MARKER = "WF_FANTASY_EQUIPMENT_PARTY_GATE_V1_BEGIN"
END_MARKER = "WF_FANTASY_EQUIPMENT_PARTY_GATE_V1_END"

ITEM_MIN = int(CONTRACT["exclusive_item_id_min"])
ITEM_MAX = int(CONTRACT["exclusive_item_id_max"])
SINGLE = CONTRACT["allowed_quests"][0]
MULTI = CONTRACT["allowed_quests"][1]

PATCH_LINES = (
    f"// {BEGIN_MARKER}",
    "if(!_loc3_)",
    "{",
    "   return false;",
    "}",
    "_loc9_ = false;",
    "_loc10_ = questId;",
    "if(_loc10_.index == 0)",
    "{",
    "   _loc11_ = _loc10_.params[0];",
    f"   if(_loc11_.index == {SINGLE['inner_index']})",
    "   {",
    "      _loc12_ = int(_loc11_.params[0]);",
    f"      _loc9_ = _loc12_ >= {SINGLE['quest_id_min']} && _loc12_ <= {SINGLE['quest_id_max']};",
    "   }",
    "}",
    "else if(_loc10_.index == 1)",
    "{",
    "   _loc11_ = _loc10_.params[0];",
    f"   if(_loc11_.index == {MULTI['inner_index']})",
    "   {",
    "      _loc12_ = int(_loc11_.params[0]);",
    f"      _loc9_ = _loc12_ >= {MULTI['quest_id_min']} && _loc12_ <= {MULTI['quest_id_max']};",
    "   }",
    "}",
    "if(!_loc9_)",
    "{",
    "   _loc12_ = 0;",
    "   while(_loc12_ < 3)",
    "   {",
    "      _loc6_ = param1.getEquipmentPeek(_loc12_);",
    "      if(_loc6_.index == 0)",
    "      {",
    "         _loc7_ = int(_loc6_.params[0].id);",
    f"         if(_loc7_ >= {ITEM_MIN} && _loc7_ <= {ITEM_MAX})",
    "         {",
    "            return false;",
    "         }",
    "      }",
    "      _loc6_ = param1.getAbilitySoulPeek(_loc12_);",
    "      if(_loc6_.index == 0)",
    "      {",
    "         _loc7_ = int(_loc6_.params[0].get_abilitySoulId());",
    f"         if(_loc7_ >= {ITEM_MIN} && _loc7_ <= {ITEM_MAX})",
    "         {",
    "            return false;",
    "         }",
    "      }",
    "      _loc12_++;",
    "   }",
    "}",
    "return _loc3_;",
    f"// {END_MARKER}",
)

LOCAL_DECLARATIONS = (
    "var _loc6_:Option;",
    "var _loc7_:int = 0;",
    "var _loc9_:Boolean = false;",
    "var _loc10_:QuestIdGroupKind;",
    "var _loc11_:* = null;",
    "var _loc12_:int = 0;",
)


class PatchError(RuntimeError):
    """The input source or patched semantics do not match the contract."""


def is_allowed_quest(group_index: int, inner_index: int, quest_id: int) -> bool:
    for row in CONTRACT["allowed_quests"]:
        if (
            group_index == int(row["group_index"])
            and inner_index == int(row["inner_index"])
            and int(row["quest_id_min"]) <= quest_id <= int(row["quest_id_max"])
        ):
            return True
    return False


def is_party_allowed(
    group_index: int,
    inner_index: int,
    quest_id: int,
    equipment_ids: list[int | None],
    ability_soul_ids: list[int | None],
    official_allowed: bool = True,
) -> bool:
    if not official_allowed:
        return False
    if is_allowed_quest(group_index, inner_index, quest_id):
        return True
    return not any(
        ITEM_MIN <= int(item_id) <= ITEM_MAX
        for item_id in [*equipment_ids[:3], *ability_soul_ids[:3]]
        if item_id is not None
    )


def _method_bounds(text: str) -> tuple[int, int]:
    if text.count(TARGET_SIGNATURE) != 1:
        raise PatchError("expected exactly one isPartyStartable method")
    start = text.index(TARGET_SIGNATURE)
    end = text.find(NEXT_SIGNATURE, start + len(TARGET_SIGNATURE))
    if end < 0:
        raise PatchError("isPartyStartable has no isItemStartable boundary")
    return start, end


def _indent_of(text: str, offset: int) -> str:
    line_start = text.rfind("\n", 0, offset) + 1
    return re.match(r"[ \t]*", text[line_start:offset]).group(0)


def _render(lines: tuple[str, ...], indent: str, newline: str) -> str:
    return newline.join(indent + line if line else "" for line in lines)


def validate(text: str, require_markers: bool = True) -> dict[str, object]:
    start, end = _method_bounds(text)
    method = text[start:end]
    begin_count = method.count(BEGIN_MARKER)
    end_count = method.count(END_MARKER)
    if require_markers:
        if begin_count != 1 or end_count != 1:
            raise PatchError("gate markers must each occur once")
    elif begin_count not in (0, 1) or end_count not in (0, 1):
        raise PatchError("invalid gate marker count")
    if begin_count != end_count:
        raise PatchError("gate markers must both be present or both be absent")
    for declaration in LOCAL_DECLARATIONS:
        if method.count(declaration) != 1:
            raise PatchError(f"missing or repeated local declaration: {declaration}")
    required = [
        f"_loc11_.index == {SINGLE['inner_index']}",
        f"_loc12_ >= {SINGLE['quest_id_min']} && _loc12_ <= {SINGLE['quest_id_max']}",
        f"_loc11_.index == {MULTI['inner_index']}",
        f"_loc12_ >= {MULTI['quest_id_min']} && _loc12_ <= {MULTI['quest_id_max']}",
        "param1.getEquipmentPeek(_loc12_)",
        "param1.getAbilitySoulPeek(_loc12_)",
        f"_loc7_ >= {ITEM_MIN} && _loc7_ <= {ITEM_MAX}",
    ]
    for snippet in required:
        if method.count(snippet) < 1:
            raise PatchError(f"missing gate semantic: {snippet}")
    if method.count(ANCHOR) != 1:
        raise PatchError("patched method must retain exactly one terminal return")
    begin = method.find(BEGIN_MARKER) if begin_count else method.find("_loc9_ = false;")
    terminal = method.rfind(ANCHOR)
    if begin < 0 or terminal < begin:
        raise PatchError("gate must replace the original terminal return")
    return {
        "status": "verified",
        "target": "BattleStartableLogic.isPartyStartable",
        "exclusive_item_range": [ITEM_MIN, ITEM_MAX],
        "allowed_quests": CONTRACT["allowed_quests"],
        "equipment_slots_checked": 3,
        "ability_soul_slots_checked": 3,
        "official_conditions_preserved": True,
    }


def patch_text(text: str) -> str:
    start, end = _method_bounds(text)
    method = text[start:end]
    if BEGIN_MARKER in method or END_MARKER in method:
        validate(text)
        return text
    if method.count(ANCHOR) != 1:
        raise PatchError("expected exactly one isPartyStartable return anchor")
    newline = "\r\n" if "\r\n" in text else "\n"

    first_declaration = method.find("var _loc5_:")
    if first_declaration < 0:
        raise PatchError("expected official _loc5_ declaration")
    declaration_end = method.find(";", first_declaration)
    if declaration_end < 0:
        raise PatchError("unterminated official _loc5_ declaration")
    declaration_indent = _indent_of(method, first_declaration)
    declarations = newline + _render(
        LOCAL_DECLARATIONS, declaration_indent, newline,
    )
    method = method[:declaration_end + 1] + declarations + method[declaration_end + 1:]

    anchor = method.index(ANCHOR)
    anchor_indent = _indent_of(method, anchor)
    block = _render(PATCH_LINES, anchor_indent, newline)
    method = method[:anchor] + block + method[anchor + len(ANCHOR):]
    output = text[:start] + method + text[end:]
    validate(output)
    return output


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--allow-markerless", action="store_true")
    args = parser.parse_args()
    if args.verify:
        print(json.dumps(
            validate(
                args.verify.read_text(encoding="utf-8-sig"),
                require_markers=not args.allow_markerless,
            ),
            ensure_ascii=False,
            indent=2,
        ))
        return
    if not args.source or not args.output:
        parser.error("--source and --output are required unless --verify is used")
    source = args.source.read_text(encoding="utf-8-sig")
    patched = patch_text(source)
    atomic_write(args.output, patched)
    print(json.dumps(validate(patched), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
