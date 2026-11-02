"""Small acceptance-contract regression tests; no AIR, server, DB or SDK needed.

Report shapes follow the development common/flows/ex/gacha-entry carriers.
The realistic cardinality is 11 source cases / 60 steps; common adds its seven
internal contract cases (eight steps) and excludes four EX cases (36 steps).
"""
import copy
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import run_contract as rc


def fixtures():
    data = {"schemaVersion": 2, "completed": True, "cases": []}
    for group, names, count in (
        ("tutorial", ["tutorial-present"], 2),
        ("mail", ["mail-single", "mail-batch", "mail-current"], 2),
        ("equipment", ["equipment-100013", "equipment-100023"], 5),
        ("crazy", ["crazy-gacha-100"], 6),
        ("ex", ["ex-confirm", "ex-discard", "ex-normal-confirm", "ex-normal-discard"], 9),
    ):
        for name in names:
            case = {"id": name, "group": group, "before": {}, "expectedAfter": {}, "steps": []}
            for i in range(count):
                is_load = group == "ex" and i in (3, 4, 8)
                step = {"id": f"{name}-step-{i}", "route": "/api/index.php/load" if is_load else "/api/index.php/test/action",
                        "httpStatus": 200, "request": {"body": {"viewer_id": 880000001, "api_count": i + 1}},
                        "before": {}, "expectedAfter": {}, "response": {"data_headers": {
                            "force_update": False, "asset_update": False, "force_news": None,
                            "short_udid": 0, "viewer_id": 880000001, "servertime": 1, "result_code": 1}, "data": {}}}
                if is_load:
                    step["expectedRestoreState"] = "None" if "normal" in name else "Tutorial"
                case["steps"].append(step)
            data["cases"].append(case)
    return data


def common_built():
    return {"required_case_ids": [f"synthetic-{i}" for i in range(7)],
            "required_step_ids": [f"synthetic-{i}-step-{j}" for i in range(7) for j in range(2 if i == 0 else 1)]}


def shell(rows):
    return {"status": "passed", "failed": 0, "stage_is_null": True, "cases": rows}


def successful_report(suite, data, built=None):
    built = built or {}
    if suite in ("queue", "gacha-entry"):
        result = shell([{"id": name, "status": "passed"} for name in built["required_case_ids"]])
        if suite == "queue":
            result["assertions"] = 47
        return result
    if suite == "ex":
        rows = []
        for case in data["cases"]:
            for step in case["steps"]:
                if step["route"].endswith("/load"):
                    tag = step["expectedRestoreState"]
                    rows.append({"id": step["id"], "caseId": case["id"], "status": "passed", "completeCalled": 1,
                                 "expectedRestoreState": tag, "restoreState": {
                                     "tag": tag, "index": 6 if tag == "None" else 0,
                                     "params": None if tag == "None" else [{"tag": "None", "index": 1, "params": None}]}})
        return shell(rows)
    rows = []
    for case in data["cases"]:
        if suite == "common" and case["group"] == "ex":
            continue
        steps = [{"id": s["id"], "status": "deferred_to_full_load_carrier" if s["route"].endswith("/load") else "passed",
                  "route": s["route"], "checks": [{"name": "state", "pass": True}]} for s in case["steps"]]
        rows.append({"id": case["id"], "group": case["group"], "status": "passed", "steps": steps,
                     "checks": [{"name": "final_state", "pass": True}]})
    if suite == "common":
        rows += [{"id": f"synthetic-{i}", "status": "passed", "checks": [{"name": "contract", "pass": True}],
                  "steps": [{"id": f"synthetic-{i}-step-{j}", "status": "passed", "checks": [{"name": "contract", "pass": True}]}
                            for j in range(2 if i == 0 else 1)]} for i in range(7)]
    return shell(rows)


class FixtureAndExpectationTests(unittest.TestCase):
    def test_valid_schema2_and_realistic_cardinality(self):
        data = fixtures()
        rc.validate_fixtures(data)
        self.assertEqual((len(data["cases"]), sum(len(c["steps"]) for c in data["cases"])), (11, 60))

    def test_duplicate_response_representation_rejected(self):
        data = fixtures()
        data["cases"][0]["responses"] = []
        with self.assertRaises(ValueError):
            rc.validate_fixtures(data)

    def test_duplicate_case_or_step_id_rejected(self):
        for kind in ("case", "step"):
            with self.subTest(kind=kind):
                data = fixtures()
                if kind == "case":
                    data["cases"][1]["id"] = data["cases"][0]["id"]
                else:
                    data["cases"][1]["steps"][0]["id"] = data["cases"][0]["steps"][0]["id"]
                with self.assertRaises(ValueError):
                    rc.validate_fixtures(data)

    def test_common_requires_real_and_all_internal_steps(self):
        contract = rc.expectations("common", fixtures(), common_built())
        self.assertEqual(len(contract["case_ids"]), 14)
        self.assertEqual(len(contract["step_ids"]), 32)
        self.assertTrue(set(common_built()["required_step_ids"]).issubset(contract["step_ids"]))

    def test_flow_and_ex_expected_counts(self):
        flow = rc.expectations("flows", fixtures(), {})
        self.assertEqual((len(flow["case_ids"]), len(flow["step_ids"]), len(flow["deferred_step_ids"])), (11, 60, 12))
        self.assertEqual(len(rc.expectations("ex", fixtures(), {})["case_ids"]), 12)


class ResultTests(unittest.TestCase):
    def setUp(self):
        self.data = fixtures()
        self.contract = rc.expectations("flows", self.data, {})
        self.result = successful_report("flows", self.data)

    def reject(self, result=None, contract=None, exit_code=0):
        with self.assertRaises(ValueError):
            rc.validate_result(result or self.result, contract or self.contract, exit_code)

    def test_legal_flow_report(self):
        coverage = rc.validate_result(self.result, self.contract, 0)
        self.assertEqual(coverage["steps"], 60)
        self.assertEqual(len(coverage["deferred_to_other_suite"]), 12)

    def test_exit_zero_does_not_override_failed_status(self):
        self.result["status"] = "failed"
        self.reject()

    def test_exit_zero_does_not_override_failure_count(self):
        self.result["failed"] = 1
        self.reject()

    def test_passed_json_does_not_override_nonzero_exit(self):
        self.reject(exit_code=1)

    def test_missing_or_false_cmd_stage_rejected(self):
        for value in (None, False):
            with self.subTest(value=value):
                self.result["stage_is_null"] = value
                self.reject()

    def test_missing_case_rejected(self):
        self.result["cases"].pop()
        self.reject()

    def test_duplicate_case_rejected(self):
        self.result["cases"][1]["id"] = self.result["cases"][0]["id"]
        self.reject()

    def test_missing_flow_step_rejected(self):
        self.result["cases"][0]["steps"].pop()
        self.reject()

    def test_duplicate_flow_step_rejected(self):
        self.result["cases"][0]["steps"][1]["id"] = self.result["cases"][0]["steps"][0]["id"]
        self.reject()

    def test_step_moved_to_another_case_rejected_even_when_global_ids_match(self):
        moved = self.result["cases"][0]["steps"].pop()
        self.result["cases"][1]["steps"].append(moved)
        self.reject()

    def test_false_case_assertion_rejected(self):
        self.result["cases"][0]["checks"][0]["pass"] = False
        self.reject()

    def test_false_step_assertion_rejected_despite_passed_status(self):
        self.result["cases"][0]["steps"][0]["checks"][0]["pass"] = False
        self.reject()

    def test_nonload_step_cannot_defer(self):
        self.result["cases"][0]["steps"][0]["status"] = "deferred_to_full_load_carrier"
        self.reject()

    def test_load_in_flows_cannot_claim_full_consumer_pass(self):
        step = next(s for c in self.result["cases"] for s in c["steps"] if s["id"] in self.contract["deferred_step_ids"])
        step["status"] = "passed"
        self.reject()

    def test_missing_common_steps_rejected(self):
        contract = rc.expectations("common", self.data, common_built())
        report = successful_report("common", self.data)
        for row in report["cases"]:
            row["steps"] = []
        self.reject(report, contract)

    def test_missing_one_internal_common_step_rejected(self):
        contract = rc.expectations("common", self.data, common_built())
        report = successful_report("common", self.data)
        report["cases"][-1]["steps"].pop()
        self.reject(report, contract)

    def test_legal_common_report_includes_7_internal_cases_8_steps(self):
        coverage = rc.validate_result(successful_report("common", self.data), rc.expectations("common", self.data, common_built()), 0)
        self.assertEqual((coverage["cases"], coverage["steps"]), (14, 32))

    def test_legal_gacha_entry_report(self):
        built = {"required_case_ids": [f"entry-{i}" for i in range(8)]}
        coverage = rc.validate_result(successful_report("gacha-entry", self.data, built), rc.expectations("gacha-entry", self.data, built), 0)
        self.assertEqual(coverage["cases"], 8)

    def test_queue_assertion_floor(self):
        built = {"required_case_ids": ["request-identity"], "min_assertions": 47}
        report = successful_report("queue", self.data, built)
        contract = rc.expectations("queue", self.data, built)
        rc.validate_result(report, contract, 0)
        report["assertions"] = 46
        self.reject(report, contract)


class ExRestoreTests(unittest.TestCase):
    def setUp(self):
        self.data = fixtures()
        self.contract = rc.expectations("ex", self.data, {})
        self.report = successful_report("ex", self.data)

    def reject(self):
        with self.assertRaises(ValueError):
            rc.validate_result(self.report, self.contract, 0)

    def test_legal_tutorial_and_normal_restore_reports(self):
        self.assertEqual(rc.validate_result(self.report, self.contract, 0)["cases"], 12)

    def test_expected_field_cannot_hide_wrong_actual_restore(self):
        row = next(r for r in self.report["cases"] if r["expectedRestoreState"] == "None")
        row["restoreState"] = {"tag": "Tutorial", "index": 0, "params": []}
        self.reject()

    def test_result_cannot_change_its_own_expected_restore(self):
        row = next(r for r in self.report["cases"] if r["expectedRestoreState"] == "None")
        row.update(expectedRestoreState="Tutorial", restoreState={"tag": "Tutorial", "index": 0, "params": []})
        self.reject()

    def test_none_tag_with_tutorial_enum_index_rejected(self):
        row = next(r for r in self.report["cases"] if r["expectedRestoreState"] == "None")
        row["restoreState"]["index"] = 0
        self.reject()

    def test_completion_must_run_exactly_once(self):
        for value in (0, 2, None):
            with self.subTest(value=value):
                self.report["cases"][0]["completeCalled"] = value
                self.reject()


class PhaseTwoLoadCoverageTests(unittest.TestCase):
    def setUp(self):
        self.data=fixtures()
        self.crazy=next(case for case in self.data['cases'] if case['group']=='crazy')
        for phase in ('after-exec','after-save','after-select'):
            self.crazy['steps'].append({'id':'crazy-load-'+phase,'route':'/api/index.php/load','response':{},'expectedRestoreState':'None'})
        self.loads=[step['id'] for step in self.crazy['steps'] if step['route'].endswith('/load')]

    def common_report(self):
        result=successful_report('common',self.data,common_built())
        result['excludedSteps']=[{'id':step} for step in self.loads]
        for case in result['cases']:
            case['steps']=[step for step in case['steps'] if step['id'] not in self.loads]
        return result

    def test_common_explicitly_defers_crazy_full_load(self):
        result=rc.validate_result(self.common_report(),rc.expectations('common',self.data,common_built()),0)
        self.assertEqual(set(result['deferred_to_other_suite']),set(self.loads))
        self.assertEqual(result['executed_load_steps'],[])

    def test_common_silent_load_omission_rejected(self):
        result=self.common_report();result.pop('excludedSteps')
        with self.assertRaises(ValueError):rc.validate_result(result,rc.expectations('common',self.data,common_built()),0)

    def test_ex_cannot_claim_another_groups_load(self):
        contract=rc.expectations('ex',self.data,{})
        self.assertFalse(set(self.loads)&set(contract['case_ids']))
        with self.assertRaises(ValueError):rc.validate_result(successful_report('ex',self.data),contract,0)

    def test_crazy_consumes_all_nine_steps_including_load(self):
        report=shell([{'id':self.crazy['id'],'status':'passed','steps':[{'id':s['id'],'status':'passed'} for s in self.crazy['steps']]}])
        contract=rc.expectations('crazy-flow',self.data,{})
        coverage=rc.validate_result(report,contract,0)
        self.assertEqual(coverage['steps'],9)
        self.assertEqual(set(coverage['executed_load_steps']),set(self.loads))
        report['cases'][0]['steps'][-1]['status']='deferred_to_full_load_carrier'
        with self.assertRaises(ValueError):rc.validate_result(report,contract,0)


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.built = {"proof": "proof.json", "swf": "Harness.swf"}
        self.ctx = {"swf_sha256": "a" * 64}
        self.flags = ("normalized_code_exceptions_equal", "method_info_flags_defaults_exact",
                      "stack_locals_scope_exact", "activation_traits_exact_after_pool_mapping")
        self.method = {"source_label": "Donor/method|1", "target_label": "Carrier/method|1",
                       "source_mid": 1, "target_mid": 2, "source_code_sha256": "c" * 64, "target_code_sha256": "d" * 64,
                       **dict.fromkeys(self.flags, True)}
        self.proof = {"input": {"swf_sha256": "a" * 64}, "execution_swf_sha256": "b" * 64,
                      "real_methods": [self.method], "missing_required_methods": []}

    def validate(self, actual_swf="b" * 64):
        with patch.object(rc, "read", return_value=self.proof), patch.object(rc, "sha", side_effect=lambda path: actual_swf if path == "Harness.swf" else "e" * 64):
            return rc.validate_binding(self.built, self.ctx)

    def test_legal_standard_binding(self):
        self.assertEqual(self.validate()["verified_methods"], 1)

    def test_wrong_input_swf_rejected(self):
        self.proof["input"]["swf_sha256"] = "f" * 64
        with self.assertRaises(ValueError):
            self.validate()

    def test_changed_executed_swf_rejected(self):
        with self.assertRaises(ValueError):
            self.validate("f" * 64)

    def test_missing_or_false_method_checks_rejected(self):
        for flag in self.flags:
            for missing in (True, False):
                with self.subTest(flag=flag, missing=missing):
                    self.proof["real_methods"] = [copy.deepcopy(self.method)]
                    if missing:
                        del self.proof["real_methods"][0][flag]
                    else:
                        self.proof["real_methods"][0][flag] = False
                    with self.assertRaises(ValueError):
                        self.validate()

    def test_empty_method_proof_rejected(self):
        self.proof["real_methods"] = []
        with self.assertRaises(ValueError):
            self.validate()

    def test_explicit_missing_required_methods_rejected(self):
        self.proof["missing_required_methods"] = ["Needed/method|1"]
        with self.assertRaises(ValueError):
            self.validate()


class ApplicationDescriptorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="client-air-contract-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.swf = self.root / "Harness.swf"
        self.swf.write_bytes(b"synthetic bound carrier; not executed")
        self.application = self.root / "application.xml"
        self.built = {"application": self.application, "swf": self.swf}

    def descriptor(self, content):
        self.application.write_text(
            '<application xmlns="http://ns.adobe.com/air/application/51.2">'
            '<id>local.contract.test</id><initialWindow>'
            f'<content>{content}</content></initialWindow></application>', encoding="utf-8")

    def test_legal_descriptor_binds_exact_carrier_and_records_hash(self):
        self.descriptor("Harness.swf")
        result = rc.validate_application(self.built)
        self.assertEqual(result, {"application_sha256": hashlib.sha256(self.application.read_bytes()).hexdigest()})

    def test_descriptor_pointing_to_another_existing_swf_is_rejected(self):
        (self.root / "Other.swf").write_bytes(b"different synthetic carrier; not executed")
        self.descriptor("Other.swf")
        with self.assertRaises(ValueError):
            rc.validate_application(self.built)


def purchase_fixtures():
    state={'userInfo':{'free_mana':100,'paid_mana':0,'free_vmoney':0,'vmoney':0,'stamina':0,'pooled_exp':1000},'items':{'2':4},'characters':{}}
    rows=[]
    for name,(operation,route) in rc.PURCHASE_CASES.items():
        case={'id':name,'group':'purchases','operation':operation,'before':copy.deepcopy(state),'expectedAfter':copy.deepcopy(state),'steps':[]}
        for phase in ('success','retry'):
            step={'id':name+'/'+phase,'route':route,'httpStatus':200,'response':{'data_headers':{'result_code':1},'data':{}},
                  'expectedAfter':copy.deepcopy(state),'wire':{'sha256':'a'*64,'bytes':123}}
            if operation.startswith('mana.'):step['expectedManaNodes']={'243001':[{'multiplied_id':1,'awake_level':0}]}
            case['steps'].append(step)
        rows.append(case)
    return {'schemaVersion':2,'completed':True,'cases':rows}


class PurchaseContractTests(unittest.TestCase):
    def test_six_current_purchase_cases_and_twelve_steps(self):
        data=purchase_fixtures();rc.require_purchases_fixtures(data)
        contract=rc.expectations('common',data,common_built())
        self.assertEqual((len(contract['case_ids']),len(contract['step_ids'])),(13,20))

    def test_empty_partial_or_wrong_group_rejected(self):
        for change in ('empty','missing','group'):
            data=purchase_fixtures()
            if change=='empty':data['cases']=[]
            elif change=='missing':data['cases'].pop()
            else:data['cases'][0]['group']='tutorial'
            with self.subTest(change=change),self.assertRaises(ValueError):rc.require_purchases_fixtures(data)

    def test_missing_reordered_or_misrouted_steps_rejected(self):
        for change in ('missing','reordered','route','status','operation','wire','empty-state','nodes'):
            data=purchase_fixtures();case=data['cases'][0];step=case['steps'][0]
            if change=='missing':case['steps'].pop()
            elif change=='reordered':case['steps'].reverse()
            elif change=='route':step['route']='/api/index.php/load'
            elif change=='status':step['httpStatus']=400
            elif change=='operation':case['operation']='boxGacha.exec'
            elif change=='wire':step.pop('wire')
            elif change=='empty-state':step['expectedAfter']={}
            else:data['cases'][-1]['steps'][0].pop('expectedManaNodes')
            with self.subTest(change=change),self.assertRaises(ValueError):rc.require_purchases_fixtures(data)

    def test_purchase_source_must_match_current_routes_and_codec(self):
        with tempfile.TemporaryDirectory(prefix='purchase-source-contract-') as directory:
            root=Path(directory);rows=[]
            for name in ('src/routes/api/shop.ts','src/routes/api/expod.ts','src/routes/api/boxGacha.ts','src/routes/api/character/mana.ts','src/lib/cn-response-hook.ts'):
                target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text('synthetic contract input',encoding='utf-8')
                rows.append({'path':name,'sha256':rc.sha(target)})
            data={'source':{'root':str(root),'mode':'src/ts-node/transpile-only','outUsed':False,'relatedFiles':rows}}
            rc.validate_purchase_source(data,root)
            (root/rows[0]['path']).write_text('changed',encoding='utf-8')
            with self.assertRaises(ValueError):rc.validate_purchase_source(data,root)
            data['source']['relatedFiles']=[]
            with self.assertRaises(ValueError):rc.validate_purchase_source(data,root)

    def test_purchase_result_cannot_omit_assertions_or_claim_node_coverage(self):
        data=purchase_fixtures();contract=rc.expectations('common',data,{})
        rows=[]
        for case in data['cases']:
            rows.append({'id':case['id'],'status':'passed','uncoveredFields':contract['uncovered_fields'].get(case['id'],[]),
                         'steps':[{'id':step['id'],'status':'passed','checks':[{'name':name,'pass':True} for name in contract['required_step_checks'][step['id']]]} for step in case['steps']]})
        report=shell(rows);rc.validate_result(report,contract,0)
        report['cases'][-1]['uncoveredFields']=[]
        with self.assertRaises(ValueError):rc.validate_result(report,contract,0)
        report['cases'][-1]['uncoveredFields']=['user_character_mana_node_list']
        report['cases'][0]['steps'][0]['checks'].pop()
        with self.assertRaises(ValueError):rc.validate_result(report,contract,0)

    def test_all_keeps_previous_business_groups_and_suites(self):
        import importlib.util
        path=Path(__file__).resolve().parents[1]/'run.py'
        spec=importlib.util.spec_from_file_location('air_entry_contract',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertEqual(module.ALL_GROUPS,['tutorial','mail','equipment','crazy','ex'])
        self.assertEqual([s for s in module.SUITES if s!='mvp'],['queue','common','flows','ex','gacha-entry','crazy-flow','mail-ex'])
        self.assertIn('purchases',module.GROUPS)


if __name__ == "__main__":
    unittest.main()
