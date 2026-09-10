import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("details_air_policy_test", HERE / "air_validation.py")
air = importlib.util.module_from_spec(spec)
spec.loader.exec_module(air)


class AirWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.paths = {"swf": self.work / "payload", "fixtures": self.work / "fixtures"}
        for path in self.paths.values():
            path.write_text("original", "utf8")
        self.runner = Mock(side_effect=lambda: air.save(self.work / "harness-result.json",
                           {"passed": True, "checks": ["native checks"]}))

    def test_default_never_starts_air_and_is_not_claimed_as_passed(self):
        state = air.validate(self.work, self.paths, runner=self.runner)
        self.runner.assert_not_called()
        self.assertEqual("not_run", state["status"])
        with self.assertRaises(ValueError):
            air.require_validated(self.work, self.paths)

    def test_explicit_run_then_exact_cache_requires_no_second_launch(self):
        state = air.validate(self.work, self.paths, run_air_tests=True, runner=self.runner)
        self.assertEqual("passed", state["status"])
        state = air.validate(self.work, self.paths, runner=self.runner)
        self.assertEqual("reused", state["status"])
        self.runner.assert_called_once()
        self.assertTrue(air.require_validated(self.work, self.paths)["passed"])

    def test_changed_swf_or_fixtures_invalidates_cached_validation(self):
        for key in self.paths:
            air.validate(self.work, self.paths, run_air_tests=True, runner=self.runner)
            self.paths[key].write_text("changed-" + key, "utf8")
            state = air.validate(self.work, self.paths, runner=self.runner)
            self.assertEqual("not_run", state["status"])
            with self.assertRaises(ValueError):
                air.require_validated(self.work, self.paths)

    def test_stale_or_tampered_result_cannot_be_packaged(self):
        air.validate(self.work, self.paths, run_air_tests=True, runner=self.runner)
        air.save(self.work / "harness-result.json", {"passed": True, "checks": ["changed"]})
        with self.assertRaises(ValueError):
            air.require_validated(self.work, self.paths)

    def test_failed_rerun_invalidates_an_older_pass(self):
        air.validate(self.work, self.paths, run_air_tests=True, runner=self.runner)
        with self.assertRaises(RuntimeError):
            air.validate(self.work, self.paths, run_air_tests=True,
                         runner=Mock(side_effect=RuntimeError("native failure")))
        self.assertEqual("not_run", air.validate(self.work, self.paths)["status"])

    def test_build_cli_requires_explicit_air_flag(self):
        spec = importlib.util.spec_from_file_location("details_build_policy_test", HERE / "build.py")
        driver = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(driver)
        args = ["--work", str(self.work), "--fixtures", str(self.paths["fixtures"])]
        self.assertFalse(driver.parse_args(args).run_air_tests)
        self.assertTrue(driver.parse_args(args + ["--run-air-tests"]).run_air_tests)


if __name__ == "__main__":
    unittest.main()
