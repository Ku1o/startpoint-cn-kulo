import unittest
import sys
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gacha_capture as capture


class CandidateValidationTests(unittest.TestCase):
    def setUp(self):
        self.replay = {
            "config": {"start_frame": 0, "end_frame": 300, "ball": {"x": 0, "y": -40, "vx": 0, "vy": 0}},
            "log_parts": [{"f": 107, "c": [2, 0]}, {"f": 240, "c": [13, False]}],
        }

    def check_candidate(self, kind, source, modified, allowed, changes=None):
        logical = "battle/terrain/skill_preview/example.amf3.deflate" if kind == "terrain" else "example.battle.amf3.deflate"
        proof = {"kind": kind, "logical": logical, "sourceProof": {"logical": logical}, "allowedChanges": allowed}
        if changes is not None:
            proof["changes"] = changes
        with patch.object(capture, "archive_member", return_value=b"original"), patch.object(
            capture, "decode", side_effect=lambda data, core: source if data == b"original" else modified
        ):
            return capture.restore_candidate(Path("."), proof, b"candidate", None)

    def test_trim_requires_original_commands_after_restoring_tail(self):
        shorter = deepcopy(self.replay)
        shorter["config"]["end_frame"] = 270
        self.assertEqual(self.check_candidate("replay", self.replay, shorter, ["config.end_frame"]), shorter)
        shorter["log_parts"][1]["c"][1] = True
        with self.assertRaisesRegex(ValueError, "beyond the allowed edits"):
            self.check_candidate("replay", self.replay, shorter, ["config.end_frame"])

    def test_trim_cannot_hide_a_source_command(self):
        shorter = deepcopy(self.replay)
        shorter["config"]["end_frame"] = 239
        with self.assertRaisesRegex(ValueError, "after all commands"):
            self.check_candidate("replay", self.replay, shorter, ["config.end_frame"])

    def test_only_known_terrain_objects_are_editable(self):
        original = {"layers": [{"objects": [{"type": "BOUNDS", "id": 11, "x": 1, "y": 2}]}]}
        modified = deepcopy(original)
        modified["layers"][0]["objects"][0]["y"] = 3
        path = "layers[0].objects[0].y"
        with self.assertRaisesRegex(ValueError, "Unsupported or mismatched terrain object"):
            self.check_candidate("terrain", original, modified, [path], [
                {"path": path, "layerIndex": 0, "objectIndex": 0, "objectId": 11, "property": "y", "before": 2, "after": 3}
            ])

    def test_protected_output_is_rejected(self):
        root = Path(__file__).resolve().parent
        with patch.object(capture, "load_plan", return_value={"protected": [root]}):
            with self.assertRaisesRegex(ValueError, "overlaps a protected"):
                capture.safe_output(root / "example.json", root / "example-capture-must-not-exist")

    def test_command_override_is_rejected_before_toolchain_access(self):
        with patch.object(Path, "read_bytes", return_value=b'{"command":["adl.exe"]}'):
            with self.assertRaisesRegex(ValueError, "Unexpected native capture config fields"):
                capture.load_plan(__file__)


if __name__ == '__main__':
    unittest.main()
