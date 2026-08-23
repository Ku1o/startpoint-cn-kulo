from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


MOD_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MOD_DIR))

import wf_quest_lib as q  # noqa: E402
import wf_rogue_build as rb  # noqa: E402


class BundledGrowthCurveCase(unittest.TestCase):
    def setUp(self) -> None:
        self._old_curves = rb._CURVES
        self._old_bundled = rb._BUNDLED_CURVES
        rb._CURVES = None
        rb._BUNDLED_CURVES = None
        self.addCleanup(self._restore_caches)

    def _restore_caches(self) -> None:
        rb._CURVES = self._old_curves
        rb._BUNDLED_CURVES = self._old_bundled

    def test_apk_base_supplies_client_default_hp_correction_curve(self) -> None:
        logical = rb.BUNDLED_CURVE_TABLES["hp"]
        payload = q.build_node({
            "hit_hp_correction_normal": {
                "79": "17.24699977",
                "100": "31.26519",
            },
        })
        relative = q.hashed_rel(logical).replace("\\", "/")
        inner_bytes = io.BytesIO()
        with zipfile.ZipFile(inner_bytes, "w") as inner:
            inner.writestr(f"production/android_bundle/{relative}", payload)

        with tempfile.TemporaryDirectory() as temporary:
            apk = Path(temporary) / "client.apk"
            with zipfile.ZipFile(apk, "w") as outer:
                outer.writestr("assets/bundle.zip", inner_bytes.getvalue())
            missing_store_file = Path(temporary) / "missing"
            with (
                mock.patch.dict(os.environ, {"WF_APK": str(apk)}, clear=False),
                mock.patch.object(q, "store_path", return_value=missing_store_file),
            ):
                self.assertEqual(
                    31.26519,
                    rb.curve_value("hp", "hit_hp_correction_normal", 100),
                )


if __name__ == "__main__":
    unittest.main()
