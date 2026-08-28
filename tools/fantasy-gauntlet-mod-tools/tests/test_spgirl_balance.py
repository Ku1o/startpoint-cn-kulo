from __future__ import annotations

from pathlib import Path
import sys
import unittest
import zlib


TOOL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL_ROOT))

import wf_spgirl_balance as balance  # noqa: E402
import wf_dsl  # noqa: E402
import wf_client_legality  # noqa: E402
import wf_mod_tool as core  # noqa: E402


def current_modifier(content: str) -> list[str]:
    row = [""] * 126
    row[0] = "wind_spgirl_swim_3"
    row[1] = "true"
    row[2] = "attack_green"
    row[3] = "0"
    row[5] = "0"
    row[6] = "202"
    row[13] = "0"
    row[20] = "0"
    row[27] = "12"
    row[30] = "7700000"
    row[31] = "7700000"
    row[34] = "5"
    row[35] = "0"
    row[39] = "(None)"
    row[46] = "0"
    row[47] = content
    row[48] = "0"
    row[51] = "2500"
    row[52] = "2500"
    return row


class SpgirlAbility3BalanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.current = [current_modifier("694"), current_modifier("693")]

    def test_confirmed_spec(self) -> None:
        self.assertEqual(balance.COMBO_STEP, 77)
        self.assertEqual(balance.COMBO_RESET, 777)
        self.assertEqual(balance.MAX_LAYERS, 10)
        self.assertEqual(balance.LAYER_STRENGTH, 20_000)

    def test_builds_two_dynamic_modifiers_and_one_reset(self) -> None:
        rows, report = balance.patch_ability3_rows(self.current)
        self.assertEqual(len(rows), 3)
        self.assertEqual([row[109] for row in rows[:2]], ["411", "410"])
        for row in rows[:2]:
            self.assertEqual(row[5], "1")
            self.assertEqual(row[6], "202")
            self.assertEqual(row[85], "(None)")
            self.assertEqual(row[97], "2")
            self.assertEqual(row[100:103], ["7700000", "7700000", "10"])
            self.assertEqual(row[108], "false")
            self.assertEqual(row[110], "0")
            self.assertEqual(row[113:115], ["20000", "20000"])

        reset = rows[2]
        self.assertEqual(reset[5], "0")
        self.assertEqual(reset[6], "202")
        self.assertEqual(reset[27], "12")
        self.assertEqual(reset[30:32], ["77700000", "77700000"])
        self.assertEqual(reset[34:36], ["(None)", "0"])
        self.assertEqual(reset[47], "390")
        self.assertEqual(reset[51:53], ["0", "0"])
        self.assertEqual(report["skill_damage_max_percent"], 200)
        self.assertEqual(report["direct_damage_max_percent"], 200)

    def test_idempotent_rows(self) -> None:
        first, _ = balance.patch_ability3_rows(self.current)
        second, _ = balance.patch_ability3_rows(first)
        self.assertEqual(second, first)

    def test_rejects_lost_main_position_guard(self) -> None:
        rows = [list(row) for row in self.current]
        rows[0][6] = "0"
        with self.assertRaisesRegex(ValueError, "主位前置条件"):
            balance.patch_ability3_rows(rows)

    def test_layer_curve(self) -> None:
        expected = {
            0: 0,
            76: 0,
            77: 20,
            154: 40,
            693: 180,
            770: 200,
            776: 200,
        }
        for combo, percent in expected.items():
            layers = min(balance.MAX_LAYERS, combo // balance.COMBO_STEP)
            self.assertEqual(layers * 20, percent)


class SpgirlAbility126BalanceTest(unittest.TestCase):
    def test_a1_opens_at_full_and_combo_gauge_is_five_percent_for_101_triggers(self) -> None:
        rows, report = balance.patch_ability1_rows(balance._current_ability1_rows())
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][27], "0")
        self.assertEqual(rows[0][47:53], ["211", "0", "", "", "100000", "100000"])
        self.assertEqual(rows[1][27], "12")
        self.assertEqual(rows[1][30:32], ["7700000", "7700000"])
        self.assertEqual(rows[1][34], "101")
        self.assertEqual(rows[1][47:53], ["211", "0", "", "", "5000", "5000"])
        self.assertEqual(report["opening_skill_gauge_percent"], 100)
        self.assertEqual(report["combo_skill_gauge_total_percent"], 505)
        again, _ = balance.patch_ability1_rows(rows)
        self.assertEqual(again, rows)

    def test_a2_targets_only_wind_characters(self) -> None:
        rows, _ = balance.patch_ability2_rows(balance._ability2_rows("(None)"))
        self.assertEqual([row[47] for row in rows], ["32", "33", "34"])
        self.assertEqual([row[48] for row in rows], ["5", "5", "5"])
        self.assertEqual([row[49] for row in rows], ["Green", "Green", "Green"])
        self.assertEqual([row[34] for row in rows], ["101", "101", "101"])
        self.assertEqual([row[51] for row in rows], ["12500", "12500", "12500"])
        again, _ = balance.patch_ability2_rows(rows)
        self.assertEqual(again, rows)

    def test_a6_wind_gauge_and_xiwei_skill_invocation(self) -> None:
        rows, report = balance.patch_ability6_rows(balance._current_ability6_rows())
        self.assertEqual([row[47] for row in rows], ["211", "224", "31", "629"])
        self.assertEqual(sum(row[47] == "629" for row in rows), 1)
        self.assertNotIn("226", [row[47] for row in rows])
        gauge = rows[0]
        self.assertEqual(gauge[6], "202")
        self.assertEqual(gauge[30:32], ["7700000", "7700000"])
        self.assertEqual(gauge[34], "101")
        self.assertEqual(gauge[48:53], ["5", "Green", "", "5000", "5000"])
        self.assertEqual(rows[1][57:61], ["120000000", "120000000", "100000", "100000"])
        self.assertEqual(rows[2][57:61], ["72000000", "72000000", "100000", "100000"])
        invoke = rows[3]
        self.assertEqual(invoke[2], "special")
        self.assertEqual(invoke[6], "202")
        self.assertEqual(invoke[27:36], [
            "23", "0", "", "100000", "100000", "", "", "(None)", "60"
        ])
        self.assertEqual(invoke[47], "629")
        self.assertEqual(invoke[70], balance.XIWEI_INVOKE_STRING_ID)
        self.assertEqual(invoke[71], balance.XIWEI_ACTION_PATH)
        self.assertEqual(balance.XIWEI_ACTION_SKILL_KEY, "bigwing_shaman_smr21")
        self.assertEqual(
            balance.XIWEI_SKILL_DSL_LOGICAL,
            "battle/action/skill/action/rare5/bigwing_shaman_smr21$"
            "bigwing_shaman_smr21_2.action.dsl.amf3.deflate",
        )
        self.assertTrue(report["skill_invoke_add_combo_removed"])
        self.assertTrue(report["invoke_other_skill_added"])
        self.assertEqual(report["invoked_character_id"], "141063")
        self.assertEqual(report["invoked_character_name"], "西微")
        self.assertEqual(report["invoked_action_skill_level"], "2")
        self.assertEqual(report["invoked_action_skill_name"], "风怒龙卷＋")
        self.assertEqual(report["invoked_action_skill_display_name"], "旋风")
        self.assertEqual(report["invoke_cooldown_frames"], 60)
        self.assertEqual(report["invoke_cooldown_seconds"], 1)
        self.assertFalse(report["legacy_ram_state_migrated"])
        self.assertEqual(
            [wf_client_legality.client_legality_problems("ability", row) for row in rows],
            [[], [], [], []],
        )
        again, _ = balance.patch_ability6_rows(rows)
        self.assertEqual(again, rows)

    def test_a6_accepts_previous_confirmed_state_before_adding_xiwei(self) -> None:
        rows, report = balance.patch_ability6_rows(
            balance._patched_ability6_rows_without_invoked_skill()
        )
        self.assertEqual([row[47] for row in rows], ["211", "224", "31", "629"])
        self.assertTrue(report["invoke_other_skill_added"])

    def test_a6_migrates_unpublished_ram_intermediate_state(self) -> None:
        previous = balance._patched_ability6_rows_without_invoked_skill()
        rows, report = balance.patch_ability6_rows(
            [*previous, balance._legacy_ability6_invoke_ram_row()]
        )
        self.assertEqual([row[47] for row in rows], ["211", "224", "31", "629"])
        self.assertEqual(rows[-1][70], balance.XIWEI_INVOKE_STRING_ID)
        self.assertEqual(rows[-1][71], balance.XIWEI_ACTION_PATH)
        self.assertTrue(report["legacy_ram_state_migrated"])

    def test_a6_migrates_unsafe_direct_rare5_intermediate_state(self) -> None:
        previous = balance._patched_ability6_rows_without_invoked_skill()
        rows, report = balance.patch_ability6_rows(
            [*previous, balance._unsafe_ability6_invoke_xiwei_rare5_row()]
        )
        self.assertEqual(rows[-1][70], balance.XIWEI_INVOKE_STRING_ID)
        self.assertEqual(rows[-1][71], balance.XIWEI_ACTION_PATH)
        self.assertNotEqual(rows[-1][71], balance.XIWEI_SOURCE_ACTION_PATH)
        self.assertTrue(report["unsafe_rare5_state_migrated"])
        self.assertTrue(report["invoked_as_native_ability_skill"])

    def test_rejects_partial_a6_state(self) -> None:
        rows = balance._current_ability6_rows()
        rows[0][51] = rows[0][52] = "5000"
        with self.assertRaisesRegex(ValueError, "未审核行"):
            balance.patch_ability6_rows(rows)

    def test_ability_table_changes_only_a1_a2_a3_a6(self) -> None:
        current = {
            balance.ABILITY1_KEY: balance._current_ability1_rows(),
            balance.ABILITY2_KEY: balance._ability2_rows("(None)"),
            balance.ABILITY3_KEY: [current_modifier("694"), current_modifier("693")],
            balance.ABILITY6_KEY: balance._current_ability6_rows(),
        }
        unrelated = zlib.compress(b"other_ability,true,attack_common,0\n")
        keys = [*current, "1000011"]
        table = core.OrderedMap(
            balance.ABILITY_LOGICAL,
            keys,
            [
                zlib.compress(core.write_csv_lines(current[key]).encode("utf-8"))
                for key in current
            ]
            + [unrelated],
            Path("<fixture>"),
        )
        raw = core.build_orderedmap_raw_rows(table)
        patched, report = balance.patch_ability_table(raw)
        readback = core.read_orderedmap_raw_rows_from_bytes(patched, balance.ABILITY_LOGICAL)
        self.assertEqual(readback.rows[-1], unrelated)
        parsed = {
            key: core.read_csv_lines(zlib.decompress(value).decode("utf-8"))
            for key, value in zip(readback.keys, readback.rows)
            if key in current
        }
        self.assertEqual(parsed[balance.ABILITY1_KEY][1][34:35], ["101"])
        self.assertEqual(
            [row[49] for row in parsed[balance.ABILITY2_KEY]],
            ["Green", "Green", "Green"],
        )
        self.assertEqual(len(parsed[balance.ABILITY3_KEY]), 3)
        self.assertEqual(
            [row[47] for row in parsed[balance.ABILITY6_KEY]],
            ["211", "224", "31", "629"],
        )
        self.assertTrue(report["changed"])
        again, second_report = balance.patch_ability_table(patched)
        self.assertEqual(again, patched)
        self.assertFalse(second_report["changed"])


class SpgirlXiweiInvokeDescriptionTest(unittest.TestCase):
    def base_table(self) -> bytes:
        return core.build_orderedmap_raw_rows(
            core.OrderedMap(
                balance.CUSTOM_ABILITY_STRING_LOGICAL,
                ["existing_skill"],
                [zlib.compress("既有技能文案".encode("utf-8"))],
                Path("<fixture>"),
            )
        )

    def test_registers_whirlwind_description_without_touching_existing_rows(self) -> None:
        self.assertEqual(balance.XIWEI_INVOKE_DESCRIPTION, "额外发动「旋风」")
        raw = self.base_table()
        before = core.read_orderedmap_raw_rows_from_bytes(
            raw, balance.CUSTOM_ABILITY_STRING_LOGICAL
        )
        patched, report = balance.patch_custom_ability_string_table(raw)
        readback = core.read_orderedmap_raw_rows_from_bytes(
            patched, balance.CUSTOM_ABILITY_STRING_LOGICAL
        )
        self.assertEqual(
            readback.keys,
            ["existing_skill", balance.XIWEI_INVOKE_STRING_ID],
        )
        self.assertEqual(readback.rows[0], before.rows[0])
        self.assertEqual(
            zlib.decompress(readback.rows[1]).decode("utf-8"),
            balance.XIWEI_INVOKE_DESCRIPTION,
        )
        self.assertTrue(report["changed"])

        again, second_report = balance.patch_custom_ability_string_table(patched)
        self.assertEqual(again, patched)
        self.assertFalse(second_report["changed"])

    def test_rejects_conflicting_existing_whirlwind_description(self) -> None:
        raw = core.build_orderedmap_raw_rows(
            core.OrderedMap(
                balance.CUSTOM_ABILITY_STRING_LOGICAL,
                [balance.XIWEI_INVOKE_STRING_ID],
                [zlib.compress("冲突文案".encode("utf-8"))],
                Path("<fixture>"),
            )
        )
        with self.assertRaisesRegex(ValueError, "未审核内容"):
            balance.patch_custom_ability_string_table(raw)


class SpgirlXiweiAbilitySkillDslTest(unittest.TestCase):
    def test_builds_fixed_max_body_without_actor_control(self) -> None:
        raw, report = balance.build_xiwei_ability_skill_dsl()
        tree = wf_dsl.parse_dsl(zlib.decompress(raw, -15))["tree"]

        def walk(value):
            yield value
            if isinstance(value, dict):
                for child in value.values():
                    yield from walk(child)
            elif isinstance(value, list):
                for child in value:
                    yield from walk(child)

        names = [
            node[0]
            for node in walk(tree)
            if isinstance(node, list) and node and isinstance(node[0], str)
        ]
        self.assertNotIn("StopBall", names)
        self.assertEqual(names.count("FindNearSubjects"), 1)
        self.assertEqual(names.count("FindAllSubjects"), 1)
        attack = next(node for node in walk(tree) if isinstance(node, list) and node and node[0] == "CreateNormalAttack")
        self.assertEqual(attack[6], [{"min": 2 / 3, "max": 2 / 3}])
        pf = next(node for node in walk(tree) if isinstance(node, list) and node and node[0] == "ACPowerFlipDamage")
        self.assertEqual(pf[2], [{"min": 0.75, "max": 0.75}])
        tolerance = next(node for node in walk(tree) if isinstance(node, list) and node and node[0] == "ACToleranceOfElement")
        self.assertEqual(tolerance[3], [{"min": -0.15, "max": -0.15}])
        self.assertEqual(report["total_damage_multiplier"], 16)
        self.assertTrue(report["skill_ranges_frozen_to_max"])
        self.assertTrue(report["ability_level_ranges_removed"])
        self.assertEqual(
            balance.XIWEI_ABILITY_SKILL_DSL_LOGICAL,
            balance.XIWEI_ACTION_PATH + ".action.dsl.amf3.deflate",
        )


def current_leader_rows() -> list[list[str]]:
    def row(
        content: str,
        target: str,
        *,
        wind_six: bool,
        target_group: str = "",
    ) -> list[str]:
        value = [""] * 124
        value[0] = "wind_spgirl_swim_leader"
        value[1] = "0"
        value[3] = "0"
        value[4] = "2" if wind_six else "0"
        if wind_six:
            value[7:10] = ["600000", "600000", "Green"]
        value[11] = "0"
        value[18] = "0"
        value[25] = "12"
        value[28:30] = ["7700000", "7700000"]
        value[32:34] = ["101", "0"]
        value[37] = "(None)"
        value[44] = "0"
        value[45] = content
        value[46] = target
        value[47] = target_group
        value[49:51] = ["12500", "12500"]
        return value

    return [
        row("32", "0", wind_six=False),
        row("33", "0", wind_six=False),
        row("32", "5", wind_six=True, target_group="(None)"),
        row("33", "5", wind_six=True, target_group="(None)"),
    ]


class SpgirlLeaderAbilityTest(unittest.TestCase):
    def test_confirmed_leader_spec(self) -> None:
        rows, report = balance.patch_leader_ability_rows(current_leader_rows())
        self.assertEqual(len(rows), 5)

        self_attack, self_direct, gauge, gauge_max, pf3_gauge = rows
        self.assertEqual(self_attack[25], "12")
        self.assertEqual(self_attack[28:30], ["7700000", "7700000"])
        self.assertEqual(self_attack[32], "101")
        self.assertEqual(
            self_attack[45:51], ["32", "0", "", "", "12500", "12500"]
        )
        self.assertEqual(
            self_direct[45:51], ["33", "0", "", "", "12500", "12500"]
        )

        self.assertEqual(gauge[4], "2")
        self.assertEqual(gauge[7:10], ["600000", "600000", "Green"])
        self.assertEqual(gauge[25], "12")
        self.assertEqual(gauge[28:30], ["77700000", "77700000"])
        self.assertEqual(gauge[32], "(None)")
        self.assertEqual(
            gauge[45:51], ["211", "5", "Green", "", "150000", "150000"]
        )

        self.assertEqual(gauge_max[4], "2")
        self.assertEqual(gauge_max[7:10], ["600000", "600000", "Green"])
        self.assertEqual(gauge_max[25], "0")
        self.assertEqual(
            gauge_max[45:51], ["245", "5", "Green", "", "50000", "50000"]
        )
        self.assertEqual(pf3_gauge[4], "2")
        self.assertEqual(pf3_gauge[7:10], ["600000", "600000", "Green"])
        self.assertEqual(pf3_gauge[25], "65")
        self.assertEqual(pf3_gauge[28:30], ["100000", "100000"])
        self.assertEqual(pf3_gauge[32:34], ["(None)", "0"])
        self.assertEqual(
            pf3_gauge[45:51], ["211", "5", "Green", "", "77000", "77000"]
        )
        self.assertEqual(report["self_attack_max_percent"], 1262.5)
        self.assertEqual(report["wind_skill_gauge_effective_cap_percent"], 150)
        self.assertEqual(report["wind_skill_gauge_per_power_flip_lv3_percent"], 77)
        self.assertEqual(
            [
                wf_client_legality.client_legality_problems("leader_ability", row)
                for row in rows
            ],
            [[], [], [], [], []],
        )

    def test_leader_patch_is_idempotent(self) -> None:
        first, _ = balance.patch_leader_ability_rows(current_leader_rows())
        second, _ = balance.patch_leader_ability_rows(first)
        self.assertEqual(second, first)

    def test_leader_patch_accepts_1_4_90_terminal_rows(self) -> None:
        before = balance._leader_rows_before_pf3_gauge()
        self.assertEqual(len(before), 4)
        rows, _ = balance.patch_leader_ability_rows(before)
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[4][25], "65")
        self.assertEqual(rows[4][45:51], ["211", "5", "Green", "", "77000", "77000"])

    def test_leader_patch_rejects_unreviewed_intermediate_state(self) -> None:
        rows = current_leader_rows()
        rows[0][49] = "13000"
        with self.assertRaisesRegex(ValueError, "未审核行"):
            balance.patch_leader_ability_rows(rows)

    def test_leader_table_changes_only_149996(self) -> None:
        target = zlib.compress(core.write_csv_lines(current_leader_rows()).encode("utf-8"))
        unrelated = zlib.compress(b"other_leader,0,,0\n")
        table = core.OrderedMap(
            balance.LEADER_ABILITY_LOGICAL,
            [balance.LEADER_ABILITY_KEY, "100001"],
            [target, unrelated],
            Path("<fixture>"),
        )
        raw = core.build_orderedmap_raw_rows(table)
        patched, report = balance.patch_leader_ability_table(raw)
        readback = core.read_orderedmap_raw_rows_from_bytes(
            patched, balance.LEADER_ABILITY_LOGICAL
        )
        self.assertEqual(readback.rows[1], unrelated)
        rows = core.read_csv_lines(zlib.decompress(readback.rows[0]).decode("utf-8"))
        self.assertEqual(
            rows[2][45:51], ["211", "5", "Green", "", "150000", "150000"]
        )
        self.assertEqual(
            rows[3][45:51], ["245", "5", "Green", "", "50000", "50000"]
        )
        self.assertEqual(rows[4][25], "65")
        self.assertEqual(rows[4][28:30], ["100000", "100000"])
        self.assertEqual(
            rows[4][45:51], ["211", "5", "Green", "", "77000", "77000"]
        )
        self.assertTrue(report["changed"])
        again, second_report = balance.patch_leader_ability_table(patched)
        self.assertEqual(again, patched)
        self.assertFalse(second_report["changed"])


def action_skill_entries() -> list[tuple[str, list[str]]]:
    entries: list[tuple[str, list[str]]] = []
    for level in (1, 2, 3):
        row = [""] * 24
        row[0] = f"疾影·瞬闪{'＋' * (level - 1)}"
        row[1] = balance.OLD_SKILL_DESCRIPTION
        row[7] = (
            "battle/action/skill/action/rare5/wind_spgirl_swim$"
            f"wind_spgirl_swim_{level}"
        )
        entries.append((str(level), row))
    return entries


def character_text_rows() -> list[list[str]]:
    row = [""] * 12
    row[0] = "希尔媞"
    for column in (5, 7, 9):
        row[column] = balance.OLD_SKILL_DESCRIPTION
    return [row]


def dsl_payload(
    piercing_frames: int,
    *,
    combo_scaling: bool = True,
    combo_scaling_raw: int = 5,
) -> bytes:
    tree = [
        "ActionDsl",
        [
            "ACPiercing",
            [{"min": piercing_frames, "max": piercing_frames}],
        ],
        [
            "CreateNormalAttack",
            2,
            255,
            [],
            [],
            140,
            [{"min": 20, "max": 20}],
            [{"min": 0, "max": 0}],
            combo_scaling,
            False,
            False,
            False,
            False,
            [{"min": 25, "max": 25}],
            [{"min": combo_scaling_raw, "max": combo_scaling_raw}],
            ["Tornado"],
            True,
        ],
    ]
    encoded = wf_dsl.encode_amf3(tree)
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    return compressor.compress(encoded) + compressor.flush()


class SpgirlActionSkillTest(unittest.TestCase):
    def test_description_matches_confirmed_skill_body(self) -> None:
        entries, report = balance.patch_action_skill_entries(action_skill_entries())
        self.assertEqual([row[1] for _key, row in entries], [balance.SKILL_DESCRIPTION] * 3)
        self.assertIn("前方和后方", balance.SKILL_DESCRIPTION)
        self.assertIn("根据连击数提升伤害", balance.SKILL_DESCRIPTION)
        self.assertIn("贯通、最大速度固定", balance.SKILL_DESCRIPTION)
        self.assertNotIn("距离最近", balance.SKILL_DESCRIPTION)
        self.assertNotIn("连击数 +77", balance.SKILL_DESCRIPTION)
        self.assertNotIn("直接攻击变为", balance.SKILL_DESCRIPTION)
        self.assertNotIn("冲刺间隔缩短", balance.SKILL_DESCRIPTION)
        self.assertFalse(report["duplicates_ability6"])

    def test_description_patch_is_idempotent(self) -> None:
        first, _ = balance.patch_action_skill_entries(action_skill_entries())
        second, _ = balance.patch_action_skill_entries(first)
        self.assertEqual(second, first)

    def test_character_text_uses_the_same_description(self) -> None:
        rows, _ = balance.patch_character_text_rows(character_text_rows())
        self.assertEqual([rows[0][column] for column in (5, 7, 9)], [balance.SKILL_DESCRIPTION] * 3)

    def test_action_skill_table_changes_only_target_outer_row(self) -> None:
        target = core.encode_action_skill_row(action_skill_entries())
        other = b"unrelated-inner-row"
        table = core.OrderedMap(
            balance.ACTION_SKILL_LOGICAL,
            [balance.ACTION_SKILL_KEY, "unrelated"],
            [target, other],
            Path("<fixture>"),
        )
        raw = core.build_orderedmap_raw_rows(table)
        patched, report = balance.patch_action_skill_table(raw)
        readback = core.read_orderedmap_raw_rows_from_bytes(
            patched, balance.ACTION_SKILL_LOGICAL
        )
        self.assertEqual(readback.rows[1], other)
        self.assertEqual(
            [row[1] for _key, row in core.decode_action_skill_row(readback.rows[0])],
            [balance.SKILL_DESCRIPTION] * 3,
        )
        self.assertTrue(report["changed"])
        again, second_report = balance.patch_action_skill_table(patched)
        self.assertEqual(again, patched)
        self.assertFalse(second_report["changed"])

    def test_character_text_table_changes_only_149996(self) -> None:
        unrelated = "其他角色,OTHER\n"
        table = core.OrderedMap(
            balance.CHARACTER_TEXT_LOGICAL,
            [balance.CHARACTER_TEXT_KEY, "100001"],
            [
                core.write_csv_lines(character_text_rows()).encode("utf-8"),
                unrelated.encode("utf-8"),
            ],
            Path("<fixture>"),
        )
        raw = core.build_orderedmap(table)
        patched, report = balance.patch_character_text_table(raw)
        readback = core.read_orderedmap_file_from_bytes(patched)
        self.assertEqual(readback["100001"], unrelated)
        rows = core.read_csv_lines(readback[balance.CHARACTER_TEXT_KEY])
        self.assertEqual(
            [rows[0][column] for column in (5, 7, 9)],
            [balance.SKILL_DESCRIPTION] * 3,
        )
        self.assertTrue(report["changed"])
        again, second_report = balance.patch_character_text_table(patched)
        self.assertEqual(again, patched)
        self.assertFalse(second_report["changed"])

    def test_level3_piercing_is_normalized_to_twelve_seconds(self) -> None:
        logical = balance.SKILL_DSL_LOGICALS[3]
        patched, report = balance.patch_skill_dsl(dsl_payload(630), logical)
        tree = wf_dsl.parse_dsl(zlib.decompress(patched, -15))["tree"]
        self.assertEqual(tree[1][1], [{"min": 720, "max": 720}])
        self.assertEqual(tree[2][14], [{"min": 7, "max": 7}])
        self.assertEqual(report["combo_scaling_per_combo_percent"], 0.7)
        self.assertEqual(
            report["combo_scaling_formula"],
            "base_multiplier * (1 + combo * 0.007)",
        )
        self.assertEqual(report["piercing_duration_seconds"], 12)
        self.assertTrue(report["changed"])
        again, second_report = balance.patch_skill_dsl(patched, logical)
        self.assertEqual(again, patched)
        self.assertFalse(second_report["changed"])

    def test_combo_scaling_updates_all_three_149996_skill_forms(self) -> None:
        for level, logical in balance.SKILL_DSL_LOGICALS.items():
            with self.subTest(level=level):
                patched, report = balance.patch_skill_dsl(dsl_payload(720), logical)
                tree = wf_dsl.parse_dsl(zlib.decompress(patched, -15))["tree"]
                self.assertEqual(tree[2][14], [{"min": 7, "max": 7}])
                self.assertEqual(report["combo_scaling_raw_before"], 5)

    def test_rejects_unreviewed_combo_scaling_value(self) -> None:
        with self.assertRaisesRegex(ValueError, "连击增伤系数出现未审核值"):
            balance.patch_skill_dsl(
                dsl_payload(720, combo_scaling_raw=6),
                balance.SKILL_DSL_LOGICALS[3],
            )

    def test_rejects_non_149996_skill_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "不是149996主动技"):
            balance.patch_skill_dsl(
                dsl_payload(720),
                "battle/action/skill/action/rare5/wind_spgirl$wind_spgirl_3.action.dsl.amf3.deflate",
            )

    def test_rejects_dsl_without_combo_scaling(self) -> None:
        with self.assertRaisesRegex(ValueError, "连击增伤开关"):
            balance.patch_skill_dsl(
                dsl_payload(630, combo_scaling=False),
                balance.SKILL_DSL_LOGICALS[3],
            )


if __name__ == "__main__":
    unittest.main()
