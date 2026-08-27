import copy
import json
import unittest
from pathlib import Path

import wf_equipment_enhancement_shop as enhancement_shop
import wf_mod_tool as core


ROOT = Path(__file__).resolve().parents[3]


def client_row(group_id: int, equipment_id: int, max_level: int = 99) -> str:
    row = [""] * 50
    row[0] = "2"
    row[1] = "(None)"
    row[2] = str(group_id)
    row[3] = "1"
    row[4] = "1"
    row[5] = "2"
    row[14] = "40313"
    row[15] = "1"
    row[22] = "2024-01-01 00:00:00"
    row[29] = str(equipment_id)
    row[30] = str(max_level)
    row[31] = "1"
    return core.write_csv_lines([row])


class EquipmentEnhancementShopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.shop = json.loads(
            (ROOT / "assets" / "equipment_enhancement_shop.json").read_text(
                encoding="utf-8"
            )
        )

    def source_table(self) -> core.OrderedMap:
        return core.OrderedMap(
            enhancement_shop.LOGICAL_PATH,
            ["unrelated-before", "1001", "1002", "unrelated-after"],
            [
                b"unchanged-before",
                client_row(1, 5010070).encode("utf-8"),
                client_row(2, 5020043).encode("utf-8"),
                b"unchanged-after",
            ],
            Path("source.zip"),
        )

    def test_builds_two_thirteen_stage_groups_and_preserves_other_rows(self) -> None:
        source = self.source_table()
        output = enhancement_shop.build_client_table(source, self.shop)

        self.assertEqual(len(output.keys), 28)
        self.assertEqual(output.rows[output.keys.index("unrelated-before")], b"unchanged-before")
        self.assertEqual(output.rows[output.keys.index("unrelated-after")], b"unchanged-after")
        rows = output.text_rows()
        for equipment_id, (_base, keys) in enhancement_shop.TARGETS.items():
            decoded = [core.read_csv_lines(rows[key])[0] for key in keys]
            self.assertEqual([int(row[3]) for row in decoded], list(range(1, 14)))
            self.assertEqual(
                [int(row[30]) for row in decoded],
                list(enhancement_shop.EXPECTED_CAPS),
            )
            self.assertTrue(all(int(row[29]) == equipment_id for row in decoded))
            self.assertTrue(all((row[14], row[15]) == ("40313", "1") for row in decoded))

    def test_rejects_server_cost_drift(self) -> None:
        shop = copy.deepcopy(self.shop)
        shop["1014"]["costs"][0]["amount"] = 2
        with self.assertRaisesRegex(ValueError, "one Pina crystal"):
            enhancement_shop.build_client_table(self.source_table(), shop)


if __name__ == "__main__":
    unittest.main()
