"""Surgically replace BattlePartyLogic.getUnitedCharacters with a bounded cache call."""
from __future__ import annotations

import copy
import json
import struct
import sys
import zlib
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "client-patch" / "loading-diagnostic"))
import common as c  # type: ignore

s = c.s
TARGET_LABEL = "pinball.common.data.party::BattlePartyLogic/getUnitedCharacters|1"
TARGET_BODY = 20565
BASE_SWF_SHAS = {
    "50680e41d5ea4e9d075fd267645141235ef07f0eabe1aee3b6e6ee64a17b4359",
    "c5a40aea2ccb8e352e7893e027b955679955a65ecf40562400ab826bd5bea865",
}


def _qname(view, abc, pool, namespace: str, name: str) -> int:
    want = (7, (22, namespace), name)
    matches = [i for i in range(1, len(abc.multinames)) if view.mn(i) == want]
    if matches:
        return matches[0]
    spaces = [
        i for i, row in enumerate(abc.namespaces)
        if i and row[0] == 22 and abc.s(row[1]) == namespace
    ]
    if spaces:
        space = spaces[0]
    else:
        space = len(abc.namespaces)
        abc.namespaces.append((22, pool.string(namespace)))
    abc.multinames.append((7, space, pool.string(name)))
    return len(abc.multinames) - 1


def patch(source: Path, helper: Path, output: Path) -> dict:
    source = source.resolve()
    helper = helper.resolve()
    output = output.resolve()
    assert source.exists() and helper.exists()
    assert not output.exists() and ".cdn" not in output.parts
    source_bytes = source.read_bytes()
    source_sha = s.sha(source_bytes)
    assert source_sha in BASE_SWF_SHAS, source_sha

    version, header, tags = s.parts(source)
    abcs = [row for row in tags if row[0] == 82]
    main = next(row for row in abcs if row[2][4:-1] == b"boot_ffc6")
    abc = main[3]
    original_abc_count = len(abcs)
    original_body_count = sum(len(row[3].bodies) for row in abcs)
    assert s.serialize(abc, main[4]) == main[4]
    before = copy.deepcopy(abc)
    view = s.m.View(SimpleNamespace(abc=abc), s.m.asm)
    assert view.by_label[TARGET_LABEL] == [TARGET_BODY]
    body = abc.bodies[TARGET_BODY]
    assert body[2] == 15 and body[3] == 1 and body[4] == 2
    pool = s.PoolEditor(abc)
    helper_q = _qname(view, abc, pool, "cn.loading", "PartyDerivedCache")
    call_q = _qname(view, abc, pool, "", "get")
    rows = s.m.asm.assemble([
        ("getlocal_0",),
        ("pushscope",),
        ("getlex", helper_q),
        ("getlocal_0",),
        ("getlocal_1",),
        ("getlocal_2",),
        ("getlocal_3",),
        ("callproperty", call_q, 4),
        ("returnvalue",),
    ])
    body[5] = s.m.asm.encode(rows)[0]
    body[6] = []
    body[1] = max(body[1], s.m.check_body(body, abc)["max_stack"])
    check = s.m.check_body(body, abc)
    assert check["unreachable_instructions"] == 0
    assert check["max_scope"] <= body[4]
    assert len(body[6]) == 0

    changed = [
        i for i, value in enumerate(abc.bodies)
        if s.m.freeze(value) != s.m.freeze(before.bodies[i])
    ]
    assert changed == [TARGET_BODY], changed
    for name in ("methods", "metadata", "instances", "classes", "scripts"):
        assert s.m.freeze(getattr(abc, name)) == s.m.freeze(getattr(before, name)), name
    for name in ("ints", "uints", "doubles", "strings", "namespaces", "ns_sets"):
        old = getattr(before, name)
        assert s.m.freeze(getattr(abc, name)[: len(old)]) == s.m.freeze(old), name

    extra = s.helper_abc(helper)
    assert len(extra.instances) == 1
    assert extra.mn_name(extra.instances[0][0]) == "cn.loading::PartyDerivedCache"
    for value in extra.bodies:
        s.m.check_body(value, extra)
    payload = main[2] + abc.serialize()
    main[1] = struct.pack("<HI", (82 << 6) | 63, len(payload)) + payload
    extra_payload = struct.pack("<I", 1) + b"cn.loading.PartyDerivedCache\0" + extra.serialize()
    extra_tag = struct.pack("<HI", (82 << 6) | 63, len(extra_payload)) + extra_payload
    raw = header + b"".join((extra_tag if row is main else b"") + row[1] for row in tags)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"CWS" + bytes([version]) + struct.pack("<I", len(raw) + 8) + zlib.compress(raw))

    final_tags = s.parts(output)[2]
    final_abcs = [row for row in final_tags if row[0] == 82]
    assert len(final_abcs) == original_abc_count + 1
    assert sum(len(row[3].bodies) for row in final_abcs) == original_body_count + len(extra.bodies)
    final_main = next(row[3] for row in final_abcs if row[2] == main[2])
    assert final_main.bodies[TARGET_BODY][5] == abc.bodies[TARGET_BODY][5]
    assert all(
        s.m.freeze(final_main.bodies[i]) == s.m.freeze(before.bodies[i])
        for i in range(len(before.bodies)) if i != TARGET_BODY
    )
    result = {
        "status": "static_verified_party_derived_cache_candidate",
        "input_swf_sha256": source_sha,
        "output_swf_sha256": s.sha(output.read_bytes()),
        "main_abc_index": abcs.index(main),
        "original_method_bodies": original_body_count,
        "added_helper_bodies": len(extra.bodies),
        "changed_original_bodies": [TARGET_BODY],
        "target_method": TARGET_LABEL,
        "helper_swc_sha256": s.sha(helper.read_bytes()),
        "helper_abc_sha256": s.sha(extra.serialize()),
        "method_check": check,
        "all_other_original_bodies_unchanged": True,
        "cache_scope": "same source party/asset container/quest group/debug list/ability flag",
        "max_entries": 12,
        "max_uses_per_entry": 3,
        "calculated_objects_reused": True,
        "battle_and_scene_state_shared": False,
        "persistent_state_changed": False,
    }
    output.with_suffix(".json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    print(json.dumps(patch(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])), ensure_ascii=False))
