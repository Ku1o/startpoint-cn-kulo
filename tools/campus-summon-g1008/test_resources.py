"""Exact-resource regressions and bounded lifecycle models; not device gameplay.

Run after prepare: python -B test_resources.py --work <prepared directory>
"""
from __future__ import annotations

import argparse
import copy
import csv
from dataclasses import dataclass
import io
import json
from pathlib import Path
import re
import sys
import unittest

import build_resources as b


@dataclass(eq=False)
class Dragon:
    owner: str
    generation: int
    dead: bool = False
    disposed: bool = False


def bianca_replay(tree, casts, deaths=None, initial_owners=("A",), end=110):
    """Execute lookup, Wait, cancellation, condition targets and removal.

    Cast/event ticks are illustrative action-update ticks, not measured input
    intervals or real seconds. Damage calculation, animations and input gating
    are excluded; the actual unchanged damage-trigger payload is recorded.
    """
    dragons = [Dragon(owner, 1) for owner in initial_owners]
    generations = {owner: 1 for owner in initial_owners}
    listeners, impacts, trace = [], [], []
    event_serial = 0
    frame, error = 0, None

    def record(kind, **kw):
        trace.append({"frame": frame, "event": kind, **kw})

    def eval_expr(expr, env, cast_id, owner):
        nonlocal event_serial
        kind = expr[0]
        if kind == "Block":
            for child in expr[1]:
                eval_expr(child, env, cast_id, owner)
        elif kind == "Event":
            event = expr[1]
            if event[0] != "Wait":
                raise AssertionError("unmodeled event")
            event_serial += 1
            listeners.append({"counter": -1, "limit": event[1], "name": event[2], "body": event[3],
                              "env": env, "cast": cast_id, "owner": owner, "serial": event_serial})
        elif kind == "Command":
            cmd = expr[1]
            if cmd[0] == "FindMultiballSubjects":
                assert cmd[1:5] == [10, 11, True, [1199891]]
                targets = [x for x in dragons if x.owner == owner and not x.disposed]
                if not targets:
                    eval_expr(cmd[5], dict(env), cast_id, owner)
                for target in targets:
                    eval_expr(cmd[6], {**env, 11: target}, cast_id, owner)
            elif cmd[0] == "RemoveEventFromOwner":
                listeners[:] = [x for x in listeners if not (x["owner"] == owner and x["name"] == cmd[1])]
            elif cmd[0] == "CreateCondition" and cmd[1] == 11:
                impacts.append((env[11], cmd, cast_id))
            elif cmd[0] == "CreateCondition" and cmd[1] == -17:
                record("self_condition", owner=owner, cast=cast_id, condition=cmd[2])
            elif cmd[0] == "AddFeverPoint":
                record("fever", owner=owner, cast=cast_id, amount=cmd[1][0]["max"])
            elif cmd[0] == "RemoveMultiball":
                assert cmd[1:] == [True, [1199891]]
                for target in dragons:
                    if target.owner == owner and not target.disposed:
                        target.dead = True
                        record("depart", owner=owner, generation=target.generation, cast=cast_id)
            elif cmd[0] == "CreateSummonsMultiball":
                assert cmd[2] == 1199891
                generations[owner] = generations.get(owner, 0) + 1
                target = Dragon(owner, generations[owner])
                dragons.append(target)
                record("spawn", owner=owner, generation=target.generation, cast=cast_id)
                # Activation timing is out of scope; only the generation and
                # existing callback cleanup are needed for these regressions.

    for frame in range(end):
        for owner in (deaths or {}).get(frame, []):
            for target in dragons:
                if target.owner == owner and not target.disposed:
                    target.dead = target.disposed = True
                    record("external_death", owner=owner, generation=target.generation)
        for serial, (at, owner) in enumerate(casts, 1):
            if at == frame:
                eval_expr(tree[11], {}, serial, owner)
        # Haxe List.add inserts at the head. A cast's nested events start at -1
        # and are first updated in its next ActionEvaluator.update call.
        cast_ids = sorted({x["cast"] for x in listeners}, reverse=True)
        for cast_id in cast_ids:
            current = sorted([x for x in listeners if x["cast"] == cast_id], key=lambda x: -x["serial"])
            for event in current:
                event["counter"] += 1
            for event in current:
                if event not in listeners:
                    continue
                if event["counter"] == event["limit"]:
                    eval_expr(event["body"], event["env"], event["cast"], event["owner"])
                    listeners.remove(event)
        for target, cmd, cast_id in impacts:
            # Unique 11998902 overrides DSL p12 with master forceApply=true.
            forced = cmd[12] or cmd[2][0][0] == "ACUnique"
            if target.dead and not forced:
                continue
            if target.disposed:
                error = {"code": "G1008", "frame": frame, "cast": cast_id, "generation": target.generation}
                break
            record("dragon_condition", owner=target.owner, generation=target.generation,
                   cast=cast_id, condition=cmd[2])
        impacts.clear()
        if error:
            break
        for target in dragons:
            if target.dead:
                target.disposed = True
    return {"error": error, "trace": trace}


def breath_events(result):
    return [x for x in result["trace"] if x["event"] == "dragon_condition" and x["condition"][0][0] == "ACUnique"]


def neph_replay(conditions, modes, count=1, queued_while_live=True):
    """Replay a held impact batch across OnlySquad expiration with real flags."""
    age, lifetime, dead, disposed = 1498, 1500, False, False
    pending, trace, error = [], [], None
    for tick, mode in enumerate(modes):
        if not disposed:
            age += 1
            if age > lifetime:
                dead = True
        if mode == "AllEntities":
            current, pending = pending, []
            for condition in current:
                if dead and not condition[12]:
                    trace.append("skip_dead")
                elif disposed:
                    error = "G1008"
                    break
                else:
                    trace.append("apply")
            if error:
                break
        if dead:
            disposed = True
        # End-of-frame RunAction queues a Member reference for the next impact
        # pass. A selection-time alive check also passes at this exact point.
        if tick == 0 and (not queued_while_live or not dead):
            pending.extend(conditions * count)
    return {"error": error, "trace": trace, "summons": count}


def function_body(source, name):
    match = re.search(r"public (?:static )?function " + re.escape(name) + r"\(", source)
    assert match, name
    begin = source.index("{", match.end())
    depth, end = 1, begin + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[begin:end]


def source_evidence():
    roots = {
        "old": Path("F:/codex/work/practice-g1008-h400-20260913/decompiled/scripts"),
        "bianca": Path("F:/codex/work/campus-bianca-g1008-repro-20260913/decompiled/scripts"),
        "neph": Path("F:/codex/work/campus-nephtim-g1008-20260913/decompiled/scripts"),
    }
    receipts = []
    def read(root, path):
        file = roots[root] / path
        raw = file.read_bytes()
        receipts.append({"path": str(file), "sha256": b.sha(raw)})
        return raw.decode("utf-8-sig")
    prefix = "pinball/scene/battle/battle/"
    ae = read("old", prefix + "action/ActionEvaluator.as")
    manager = read("bianca", prefix + "action/ActionEvaluatorManager.as")
    wait = read("bianca", prefix + "action/ListeningEvent.as")
    assert "frameCount = -1;" in wait
    assert "frameCount == int(_loc4_.params[0])" in wait
    assert "_loc4_.get_executor() == param2" in function_body(manager, "removeEvent")
    assert "manager.removeEvent(_loc8_,get_executor())" in ae
    assert "new UniqueConditionLogic(_loc24_,get_zone().asset).get_forceApply()" in ae
    unique_values = read("old", "pinball/master/generated/UniqueConditionValues.as")
    assert "_loc11_ = param1[10];" in unique_values and "force_apply = _loc12_;" in unique_values
    update = function_body(ae, "update")
    assert update.index("_loc2_.updatePhase()") < update.index("_loc2_.evaluationPhase(dispatchedEvents)")
    assert "listeningEvents.add(new ListeningEvent" in ae
    battle = read("old", prefix + "Battle.as")
    full = function_body(battle, "stepLifeCycleAsAllEntitiesMode")
    only = function_body(battle, "stepLifeCycleAsOnlySquadMode")
    assert full.index("zoneManager.updatePhase()") < full.index("zoneManager.impactPhase()") < full.index("squadManager.removalPhase")
    assert "squadManager.removalPhase" in only and "zoneManager" not in only
    assert function_body(battle, "proceed").index("stepLifeCycleAsAllEntitiesMode()") < function_body(battle, "proceed").index("abilityTrigger.update()")
    squad = read("bianca", prefix + "squad/SquadImpl.as")
    assert "frameCount += 1;" in function_body(squad, "update")
    assert "if(frameCount > int(_loc1_.params[0]))" in function_body(squad, "update")
    assert "param1 != null ? param1.indexOf(_loc2_.params[0].id) != -1 : true" in function_body(squad, "matchMultiball")
    member = read("old", prefix + "squad/member/MemberImpl.as")
    assert "if((!isDead() || _loc4_) && _loc3_)" in function_body(member, "applyImpact")
    assert "gear.absorbWithKey(BattleDiffuseKey.KBattleId" in function_body(member, "internalApplyConditionChanges")
    disposal = read("old", prefix + "squad/SquadManagerImpl.as")
    assert "gear.removeChild(param1)" in function_body(disposal, "disposeActiveSquad")
    assert "param1.deactivate()" not in function_body(disposal, "disposeActiveSquad")
    impact = read("old", prefix + "impact/ImpactManagerImpl.as")
    assert "new ImpactOfBeforeCalculation(param1,param2,1)" in function_body(impact, "_add")
    resolver = read("neph", prefix + "action/ActionEvaluationResolver.as")
    assert "case 86:" in function_body(resolver, "findSubjectByCondition")
    gear = read("old", "jp/sipo/gipo/core/Gear.as")
    assert "throw new SipoError(1008," in function_body(gear, "absorbWithKey")
    swf = Path("F:/codex/work/practice-g1008-h400-20260913/accepted-public.swf")
    assert b.sha(swf.read_bytes()) == "e60cc4a82e3b305257040dedc54d180794234e2c2d4d3cef68a105b9f8405927"
    return {"swf_sha256": b.sha(swf.read_bytes()), "class_files": receipts, "AIR_or_device_executed": False}


class Resources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = {logical: (WORK / "before" / b.quest.hashed_rel(logical)).read_bytes() for logical in b.PREIMAGES}
        cls.after = {logical: (WORK / "after" / b.quest.hashed_rel(logical)).read_bytes() for logical in b.PREIMAGES}
        cls.old = {k: b.parse(v) for k, v in cls.before.items()}
        cls.new = {k: b.parse(v) for k, v in cls.after.items()}

    def test_source_order_matches_models(self):
        (WORK / "runtime-source-evidence.json").write_bytes(b.json_bytes(source_evidence()))

    def test_original_bianca_reproduces_and_single_cast_keeps_timing(self):
        for logical in b.BIANCA:
            self.assertEqual(bianca_replay(self.old[logical], [(0, "A"), (12, "A")])["error"]["code"], "G1008")
            old = bianca_replay(self.old[logical], [(0, "A")])
            new = bianca_replay(self.new[logical], [(0, "A")])
            self.assertEqual(old, new)
            self.assertEqual([x["frame"] for x in new["trace"] if x["event"] == "depart"], [29])

    def test_all_overlap_intervals_preserve_both_breaths(self):
        for logical in b.BIANCA:
            for gap in range(0, 30):
                result = bianca_replay(self.new[logical], [(0, "A"), (gap, "A")])
                self.assertIsNone(result["error"], (logical, gap))
                self.assertEqual(len(breath_events(result)), 2, gap)
                self.assertEqual(sum(x.get("amount", 0) for x in result["trace"]), 500, gap)
                self.assertEqual([x["frame"] for x in result["trace"] if x["event"] == "depart"], [gap + 29])

    def test_three_overlapping_casts_keep_three_signals(self):
        for logical in b.BIANCA:
            result = bianca_replay(self.new[logical], [(0, "A"), (12, "A"), (24, "A")])
            self.assertIsNone(result["error"])
            self.assertEqual(len(breath_events(result)), 3)
            self.assertEqual(sum(x.get("amount", 0) for x in result["trace"]), 750)
            self.assertEqual([x["frame"] for x in result["trace"] if x["event"] == "depart"], [53])

    def test_no_old_callbacks_touch_new_dragon(self):
        for logical in b.BIANCA:
            for death, recast in ((10, 12), (25, 25)):
                result = bianca_replay(self.new[logical], [(0, "A"), (recast, "A")], {death: ["A"]})
                self.assertIsNone(result["error"])
                spawn = next(x for x in result["trace"] if x["event"] == "spawn")
                future = [x for x in result["trace"] if x["frame"] >= spawn["frame"]]
                self.assertFalse(any(x["event"] in ("depart", "dragon_condition", "self_condition", "fever") for x in future))
            # Cast after normal removal summons a fresh dragon, without replaying
            # any event from the previous generation.
            normal = bianca_replay(self.new[logical], [(0, "A"), (40, "A")])
            self.assertIsNone(normal["error"])
            self.assertEqual(len(breath_events(normal)), 1)

    def test_departure_cancellation_is_scoped_to_caster(self):
        result = bianca_replay(self.new[b.BIANCA[0]], [(0, "A"), (0, "B"), (12, "A")], initial_owners=("A", "B"))
        self.assertIsNone(result["error"])
        self.assertEqual([(x["owner"], x["frame"]) for x in result["trace"] if x["event"] == "depart"], [("B", 29), ("A", 41)])

    def test_lifecycle_guards_have_independent_regressions(self):
        repaired = self.new[b.BIANCA[0]]
        without_refresh = copy.deepcopy(repaired)
        b.bianca_parts(without_refresh)[1].pop(0)
        result = bianca_replay(without_refresh, [(0, "A"), (12, "A")])
        self.assertEqual(len(breath_events(result)), 1)  # Safety alone loses cast 2's damage signal.
        without_cleanup = copy.deepcopy(repaired)
        del b.bianca_parts(without_cleanup)[0][:4]
        result = bianca_replay(without_cleanup, [(0, "A"), (12, "A")], {10: ["A"]})
        self.assertTrue(any(x.get("generation") == 2 for x in breath_events(result)))
        no_respawn = bianca_replay(repaired, [(0, "A")], {10: ["A"]})
        self.assertIsNone(no_respawn["error"])
        self.assertEqual(breath_events(no_respawn), [])

    def test_neph_queued_buffs_expire_in_cutin(self):
        for logical in (*b.NEPHTIM, *b.AURAS):
            target = 81 if logical == b.AURAS[1] else 71
            old = [n for n in b.walk(self.old[logical]) if n[0] == "CreateCondition" and n[1] == target]
            new = [n for n in b.walk(self.new[logical]) if n[0] == "CreateCondition" and n[1] == target]
            for count in (1, 9):
                modes = ["AllEntities", "OnlySquad", "OnlySquad", "AllEntities"]
                self.assertEqual(neph_replay(old, modes, count)["error"], "G1008")
                result = neph_replay(new, modes, count)
                self.assertIsNone(result["error"])
                self.assertEqual(result["trace"].count("skip_dead"), len(new) * count)
                self.assertEqual(neph_replay(new, ["AllEntities"] * 4, count), neph_replay(old, ["AllEntities"] * 4, count))

    def test_condition_values_filters_and_special_effects_are_unchanged(self):
        for logical in (*b.NEPHTIM, *b.AURAS):
            old, new = self.old[logical], self.new[logical]
            old_conditions = [n for n in b.walk(old) if n[0] == "CreateCondition"]
            new_conditions = [n for n in b.walk(new) if n[0] == "CreateCondition"]
            self.assertEqual([n[:12] for n in old_conditions], [n[:12] for n in new_conditions])
            for n in new_conditions:
                if n[1] == -17:
                    self.assertTrue(n[12])
        source = b.parse((WORK / "before" / b.quest.hashed_rel(b.SPAWN)).read_bytes())
        self.assertEqual(b.sha((WORK / "before" / b.quest.hashed_rel(b.SPAWN)).read_bytes()), b.UNCHANGED_DSL[b.SPAWN])
        summons = [n for n in b.walk(source) if n[0] == "CreateSummonsMultiball"]
        self.assertEqual({n[2] for n in summons}, {1699891, 1699892})
        self.assertTrue(all(n[3] == [{"min": 1500, "max": 1500}] for n in summons))
        for logical in b.PFS:
            tree = b.parse((WORK / "before" / b.quest.hashed_rel(logical)).read_bytes())
            self.assertTrue(all(not n[12] for n in b.walk(tree) if n[0] == "CreateCondition"))
        # The master-only override is why changing Bianca DSL p12 is inadequate.
        unique = b.assets.parse_table((WORK / "before" / b.quest.hashed_rel("master/character/unique_condition.orderedmap")).read_bytes())
        row = next(csv.reader(io.StringIO(unique["11998902"])))
        self.assertEqual(row[10], "true")  # Native UniqueConditionValues force_apply; c11 is direction.

    def test_reproducible_and_rejects_undeclared_id_or_multiplier_edits(self):
        for logical, original in self.before.items():
            self.assertEqual(b.transform(logical, original, original), self.after[logical])
            self.assertEqual(b.transform(logical, self.after[logical], original), self.after[logical])
            drift = copy.deepcopy(self.new[logical])
            node = next(n for n in b.walk(drift) if n[0] == "CreateCondition")
            node[1] += 1  # Still an int and schema-valid, but the wrong subject ID.
            raw = b.zlib.compress(b.wf_dsl.encode_amf3(drift), 9, wbits=-15)
            with self.assertRaisesRegex(ValueError, "unrecognized current tree"):
                b.transform(logical, raw, original)
            with self.assertRaisesRegex(ValueError, "unrecognized original"):
                b.transform(logical, original, original + b"x")
        drift = copy.deepcopy(self.new[b.AURAS[1]])
        next(n for n in b.walk(drift) if n[0] == "ACSeparatedTermDirectDamage")[2][0]["max"] = 0.6
        raw = b.zlib.compress(b.wf_dsl.encode_amf3(drift), 9, wbits=-15)
        with self.assertRaisesRegex(ValueError, "unrecognized current tree"):
            b.transform(b.AURAS[1], raw, self.before[b.AURAS[1]])

    def test_manifest_preserves_prior_content_and_rejects_collision(self):
        before = json.loads((WORK / "manifest.before.json").read_bytes())
        report = json.loads((WORK / "report.json").read_bytes())
        after = b.merge_manifest(before, report["archive"])
        self.assertEqual(after["patches"][:-1], before["patches"][:-1])
        old, new = before["patches"][-1], after["patches"][-1]
        self.assertEqual(new["chain"][:-1], old["chain"])
        self.assertEqual(new["archive_integrity"][:-1], old["archive_integrity"])
        self.assertEqual(new["changes"][:-2], old["changes"])
        for key in old:
            if key not in {"chain", "archive_integrity", "archive_size", "changes", "files", "audit"}:
                self.assertEqual(new[key], old[key])
        self.assertEqual(after["cdn_version"], "1.4.108")
        with self.assertRaisesRegex(ValueError, "split 3 already occupied"):
            b.merge_manifest(after, report["archive"])
        collided = copy.deepcopy(before)
        collided["patches"][-1]["files"].append(report["archive"]["files"][0])
        with self.assertRaisesRegex(ValueError, "overlaps"):
            b.merge_manifest(collided, report["archive"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True, type=Path)
    args, remaining = parser.parse_known_args()
    WORK = args.work
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Resources)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {"tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
              "passed": result.wasSuccessful(), "scope": "actual before/after resources and source-grounded bounded lifecycle models",
              "device_or_AIR_tested": False}
    (WORK / "regression-results.json").write_bytes(b.json_bytes(report))
    sys.exit(0 if result.wasSuccessful() else 1)
