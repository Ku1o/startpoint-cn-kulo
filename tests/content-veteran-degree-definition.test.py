#!/usr/bin/env python3
"""Bounded definition audit regressions for the one reviewed degree placeholder.

Loads existing native-rule and effective-getter receipts; no database, network,
native client, asset generation, or transaction handler is executed.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
KEY = "event_item_shop:9700118"
RAW_SHA = "b79a56c6b24c3c1cd8dd8ac799b49ea7095e0738475ff5cd6209bea4a3387001"
SPEC = importlib.util.spec_from_file_location("veteran_definition_tool", ROOT / "tools/build-content-history-readiness.py")
TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOL)


class VeteranDegreeDefinitionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rules = json.loads((ROOT / "assets/content_history_shop_rules.json").read_text(encoding="utf8"))
        receipts = json.loads((ROOT / "assets/content_history_definition_evidence.json").read_text(encoding="utf8"))
        rule = rules["products"][KEY]
        cls.raw_fixture = rule["source"]["raw"]
        cls.native_fixture = rule["native"]
        cls.columns = rules["source"]["fieldSchema"]["columns"]
        cls.value_fixture = receipts["effectiveShopDefinitionEvidence"]["rows"][KEY]["effectiveGetterValue"]
        cls.getter_evidence = receipts["effectiveShopDefinitionEvidence"]["getterProof"]
        cls.row = {"key": KEY, "type": "event_item_shop", "id": 9700118, "parentKey": "rush_event:700099"}

    def setUp(self):
        self.raw = copy.deepcopy(self.raw_fixture)
        self.native = copy.deepcopy(self.native_fixture)
        self.value = copy.deepcopy(self.value_fixture)

    def legacy(self, raw=None, value=None):
        return TOOL.audit_product(self.row, self.raw if raw is None else raw,
                                  self.value if value is None else value, self.columns, {})

    def effective(self, raw=None, value=None, native=None):
        raw = self.raw if raw is None else raw
        value = self.value if value is None else value
        return TOOL.effective_shop_field_audit(self.legacy(raw, value), self.native if native is None else native,
                                               raw, value, self.getter_evidence)

    def test_reviewed_fixture_is_exact_original_51_column_row(self):
        digest = hashlib.sha256(json.dumps(self.raw, ensure_ascii=False, sort_keys=True,
                                          separators=(",", ":")).encode("utf8")).hexdigest()
        self.assertEqual(len(self.raw), 51)
        self.assertEqual(digest, RAW_SHA)
        self.assertEqual(self.raw[8], "9700118")
        self.assertEqual(self.raw[7], "资深玩家")
        self.assertEqual(self.raw[13], "item/etc/degree")
        self.assertEqual(self.raw[32:35], ["6", "(None)", "1"])
        self.assertTrue(TOOL.reviewed_veteran_degree_semantics(self.raw, self.value))
        legacy, effective = self.legacy(), self.effective()
        self.assertEqual(legacy["status"], "verified_static")
        self.assertEqual(effective["status"], "verified_static")
        self.assertTrue(effective["definitionFieldsMatched"])
        self.assertEqual(effective["semanticBridge"]["degreeId"], 9900006)
        # A semantic bridge documents the different enum; it does not rewrite raw evidence.
        self.assertEqual(legacy["nativeRewards"], [{"type": 6, "count": 1}])
        self.assertEqual(effective["nativeRewards"], [{"type": 6, "count": 1}])
        self.assertEqual(self.value["rewards"], [{"type": 5, "id": 9900006, "count": 1}])

    def test_every_raw_column_mutation_loses_the_bridge(self):
        for column in range(51):
            with self.subTest(column=column):
                raw = copy.deepcopy(self.raw)
                raw[column] = raw[column] + "_changed"
                self.assertFalse(TOOL.reviewed_veteran_degree_semantics(raw, self.value))
        self.assertFalse(TOOL.reviewed_veteran_degree_semantics(self.raw + ["extra"], self.value))
        self.assertFalse(TOOL.reviewed_veteran_degree_semantics(self.raw[:-1], self.value))

    def test_changed_id_name_icon_price_and_other_kind6_do_not_pass_audits(self):
        changes = {"different_product": (8, "9700119"), "name": (7, "另一称号"),
                   "icon": (13, "item/etc/item"), "native_reward_id": (33, "9900006"),
                   "native_reward_count": (34, "2"), "price": (16, "4999999")}
        for name, (column, replacement) in changes.items():
            with self.subTest(case=name):
                raw = copy.deepcopy(self.raw)
                raw[column] = replacement
                effective = self.effective(raw=raw)
                self.assertFalse(TOOL.reviewed_veteran_degree_semantics(raw, self.value))
                self.assertNotIn("semanticBridge", effective)
                self.assertFalse(effective["definitionFieldsMatched"])
                self.assertNotEqual(effective["status"], "verified_static")

    def test_price_and_reward_changes_cannot_use_bridge(self):
        values = []
        for field, replacement in [("type", 1), ("amount", 4999999), ("amount", 5000001),
                                   ("amount", -5000000), ("type", False), ("amount", True)]:
            value = copy.deepcopy(self.value)
            value["userCost"][field] = replacement
            values.append(("price_" + field + "_" + repr(replacement), value))
        for field, replacement in [("type", 6), ("id", 9900007), ("count", 2),
                                   ("count", True), ("id", 9900006.0), ("type", 5.0)]:
            value = copy.deepcopy(self.value)
            value["rewards"][0][field] = replacement
            values.append(("reward_" + field + "_" + repr(replacement), value))
        value = copy.deepcopy(self.value)
        value["costs"] = [{"id": 1, "amount": 1}]
        values.append(("extra_cost", value))
        value = copy.deepcopy(self.value)
        value["rewards"].append({"type": 5, "id": 9900007, "count": 1})
        values.append(("extra_reward", value))
        for name, value in values:
            with self.subTest(case=name):
                self.assertFalse(TOOL.reviewed_veteran_degree_semantics(self.raw, value))
                effective = self.effective(value=value)
                self.assertNotIn("semanticBridge", effective)
                self.assertFalse(effective["definitionFieldsMatched"])

    def test_limit_changes_are_not_approved_by_reward_bridge(self):
        for column, native_field in [(29, "buy_max_count"), (30, "max_frequency")]:
            with self.subTest(native_field=native_field):
                raw, native = copy.deepcopy(self.raw), copy.deepcopy(self.native)
                raw[column], native[native_field] = "2", 2
                effective = self.effective(raw=raw, native=native)
                self.assertNotIn("semanticBridge", effective)
                self.assertFalse(effective["definitionFieldsMatched"])
        for limit in ["perRequest", "lifetime"]:
            with self.subTest(effective_limit=limit):
                value = copy.deepcopy(self.value)
                value["nativeStockLimits"][limit] = 2
                self.assertFalse(self.effective(value=value)["definitionFieldsMatched"])
        value = copy.deepcopy(self.value)
        value["stock"] = 2
        self.assertFalse(self.legacy(value=value)["matches"]["cumulativeStock"])

    def test_empty_price_and_reward_keep_ordinary_matching_path(self):
        raw, native, value = copy.deepcopy(self.raw), copy.deepcopy(self.native), copy.deepcopy(self.value)
        raw[15:17] = ["(None)", "(None)"]
        raw[32:35] = ["(None)", "(None)", "(None)"]
        native["price"], native["kind1"] = None, None
        value.pop("userCost")
        value["rewards"] = []
        legacy = self.legacy(raw=raw, value=value)
        effective = self.effective(raw=raw, value=value, native=native)
        self.assertFalse(TOOL.reviewed_veteran_degree_semantics(raw, value))
        self.assertEqual(legacy["status"], "verified_static")
        self.assertEqual(effective["status"], "verified_static")
        self.assertTrue(effective["definitionFieldsMatched"])
        self.assertNotIn("semanticBridge", effective)

    def test_native_stone_price_rejects_nonpositive_unknown_or_loose_types(self):
        invalid = [{"kind": kind, "count": count} for kind, count in
                   [(0, -1), (0, 0), (1, 5000000), (2, 5000000), (99, 5000000),
                    (False, 5000000), (0.0, 5000000), (0, True), (0, 5000000.0),
                    ("0", 5000000), (0, "5000000")]]
        for price in invalid:
            with self.subTest(price=price):
                server = {"userCost": {"type": price["kind"], "amount": price["count"]}}
                self.assertFalse(TOOL.native_stone_price_matches(price, server))
        self.assertTrue(TOOL.native_stone_price_matches({"kind": 0, "count": 5000000}, self.value))
        self.assertFalse(TOOL.native_stone_price_matches(None, self.value))
        self.assertTrue(TOOL.native_stone_price_matches(None, {}))

    def test_malformed_server_cost_or_reward_does_not_trigger_bridge(self):
        for cost in [None, [], "5000000", {"type": 0}, {"amount": 5000000}]:
            with self.subTest(cost=cost):
                value = copy.deepcopy(self.value)
                value["userCost"] = cost
                self.assertFalse(TOOL.reviewed_veteran_degree_semantics(self.raw, value))
        for rewards in [None, {}, [], "degree", [None], [[5, 9900006, 1]],
                        [{"type": 5, "id": 9900006}], [{"type": 5, "id": 9900006, "count": 1, "extra": 1}]]:
            with self.subTest(rewards=rewards):
                value = copy.deepcopy(self.value)
                value["rewards"] = rewards
                self.assertFalse(TOOL.reviewed_veteran_degree_semantics(self.raw, value))

    def test_audits_preserve_inputs_and_unrelated_review_blockers(self):
        before = copy.deepcopy((self.raw, self.native, self.value))
        legacy = self.legacy()
        legacy["review"].append("需要独立核对额外资格")
        effective = TOOL.effective_shop_field_audit(legacy, self.native, self.raw, self.value, self.getter_evidence)
        self.assertEqual(effective["status"], "unreviewed")
        self.assertIn("需要独立核对额外资格", effective["review"])
        self.assertEqual((self.raw, self.native, self.value), before)
        self.assertIn("需要独立核对额外资格", legacy["review"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
