from __future__ import annotations

import hashlib
import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = Path(r"F:\codex")
FILES = (
    "src/routes/api/rushEvent.ts",
    "out/routes/api/rushEvent.js",
    "assets/rogue_event.json",
    "assets/asset-patch/manifest.json",
    "assets/asset-patch/active/"
    "pinball-1.4.76-1.4.77-1-0812-abyss-floor24-fix.zip",
    "assets/asset-patch/production/upload/b6/"
    "595dedd9cfa79b7e6eccab25dd9a2a81b066a2",
)


def main() -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = OUTPUT_ROOT / (
        f"startpoint-cn-cloud-update-abyss-floor24-no-auto-reroll-{stamp}.zip"
    )
    missing = [relative for relative in FILES if not (ROOT / relative).is_file()]
    if missing:
        raise FileNotFoundError(f"missing package files: {missing}")

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative in FILES:
            archive.write(ROOT / relative, relative)

    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        if names != list(FILES):
            raise ValueError(f"unexpected package members: {names}")
        for relative in FILES:
            if archive.read(relative) != (ROOT / relative).read_bytes():
                raise ValueError(f"package payload mismatch: {relative}")

    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(f"ZIP={output}")
    print(f"SHA256={digest}")
    print("MEMBERS:")
    for relative in FILES:
        print(relative)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
