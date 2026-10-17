"""Exact twelve-method overlimit import contract for the accepted iOS AOT unit.

Pass the existing shared Importer(target_view, android_source_view). This module
never parses packages, edits traits, compiles native code, links or registers a
carrier. Imported body code still requires AOT compilation and method redirects.
All iOS input bodies below are stripped stubs, not native behavior evidence.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path

TARGETS = [{'id': 'O1',
  'label': 'pinball.common.data.character::GeneralCharacterLogic/get_maxOverLimitStep|1',
  'ios_method_id': 18290,
  'ios_code_sha256': '4d31a31bcc76e5207e451de19f99412493a2c0e7be9f9bc42849c9d585dbbf97',
  'android_code_sha256': 'a1b57b4034b60def3d9b1a328b7ceb321157f45e5243c246353d733a7643ebab'},
 {'id': 'O2',
  'label': 'pinball.common.data.character.parameter::OwnedOverLimitLogic/getOwnAwakingCrystalToOverLimit|1',
  'ios_method_id': 18971,
  'ios_code_sha256': 'ccf5360dcc1e18fdf89baebff7ff0230fd92a9a68bae4dabaac88b46f8b77cb7',
  'android_code_sha256': '2be9af1fa92ed8bb56a5ee90b9eb511f7f94c6941f38a223e406207e17be61b2'},
 {'id': 'O3',
  'label': 'pinball.common.data.character.parameter::OwnedOverLimitLogic/getAwakingCrystalToOverLimit|1',
  'ios_method_id': 18974,
  'ios_code_sha256': 'ccf5360dcc1e18fdf89baebff7ff0230fd92a9a68bae4dabaac88b46f8b77cb7',
  'android_code_sha256': '2e584914a2f67e60a268e62502f8e7af84a6a6e1e38af444b8de79c446470b34'},
 {'id': 'O4',
  'label': 'pinball.common.data.character.parameter::OwnedOverLimitLogic/getOverLimitState|1',
  'ios_method_id': 18972,
  'ios_code_sha256': 'ccf5360dcc1e18fdf89baebff7ff0230fd92a9a68bae4dabaac88b46f8b77cb7',
  'android_code_sha256': '98f9c7121ac212729daaf7a0e9b740e2de275dcc26e2536ad4d8e1d63d023fd0'},
 {'id': 'O5',
  'label': 'pinball.common.data.character::OwnedCharacterLogic/getPossibleOverLimitCountByItem|1',
  'ios_method_id': 18655,
  'ios_code_sha256': '4d31a31bcc76e5207e451de19f99412493a2c0e7be9f9bc42849c9d585dbbf97',
  'android_code_sha256': '7fa65be8a2181e01a0a17b400d74fecbd0565c2600be4e78a7be8d96a94e837e'},
 {'id': 'O6',
  'label': 'pinball.common.data.character::GeneralCharacterLogic/getPedestalImagePath|1',
  'ios_method_id': 18316,
  'ios_code_sha256': 'ccf5360dcc1e18fdf89baebff7ff0230fd92a9a68bae4dabaac88b46f8b77cb7',
  'android_code_sha256': '1c5905b65f624a24c01cf58adeeb90c300a9e9ae965577c4b295c093f0be117d'},
 {'id': 'O7',
  'label': 'pinball.common.data.character::GeneralCharacterLogic/getHalfPedestalImagePath|1',
  'ios_method_id': 18336,
  'ios_code_sha256': 'ccf5360dcc1e18fdf89baebff7ff0230fd92a9a68bae4dabaac88b46f8b77cb7',
  'android_code_sha256': '0dc8e515702c2c3c77cca60549da8e063eec0785f89a57e503b5ddf41be6a28a'},
 {'id': 'O8',
  'label': 'pinball.ui.component.pixelArtCharacter::PixelArtCharacter/getPedestalImagePath|1',
  'ios_method_id': 96481,
  'ios_code_sha256': 'ccf5360dcc1e18fdf89baebff7ff0230fd92a9a68bae4dabaac88b46f8b77cb7',
  'android_code_sha256': '10eb1e21f915782bcd5715a3fb58670cb18737ae8a5f0f569781f774b1a48f0d'},
 {'id': 'O9',
  'label': 'pinball.scene.expod.overLimitWindow::OverLimitWindow/getOverLimitState|1',
  'ios_method_id': 80527,
  'ios_code_sha256': 'ccf5360dcc1e18fdf89baebff7ff0230fd92a9a68bae4dabaac88b46f8b77cb7',
  'android_code_sha256': 'ae683cc1f5574ac7b415c43cf779ea642535cd6a66531aa1ee51a150d1492068'},
 {'id': 'O10',
  'label': 'pinball.scene.expod.overLimitWindow::OverLimitWindow/run|1',
  'ios_method_id': 80515,
  'ios_code_sha256': '333e0a1e27815d0ceee55c473fe3dc93d56c63e3bee2b3b4aee8eed6d70191a3',
  'android_code_sha256': 'b96160fc0f1046a50cf78065ed8d907861a2a65fb13c4f365abad60cbd4b2a7e'},
 {'id': 'O11',
  'label': 'pinball.scene.expod.overLimitWindow::OverLimitWindow/getStatusInformation|1',
  'ios_method_id': 80525,
  'ios_code_sha256': 'ccf5360dcc1e18fdf89baebff7ff0230fd92a9a68bae4dabaac88b46f8b77cb7',
  'android_code_sha256': 'c64d19bbf7957fd9490406d4d251abb9d1e16eeb3062e1b49148f56afbd29aa4'},
 {'id': 'O12',
  'label': 'pinball.dialog.expod.overLimit::ExpodOverLimitByItemDialog/getDescription|1',
  'ios_method_id': 36710,
  'ios_code_sha256': 'ccf5360dcc1e18fdf89baebff7ff0230fd92a9a68bae4dabaac88b46f8b77cb7',
  'android_code_sha256': 'a0468818a62ad753f0d18a755b29af19c61ebf5c3cd4a145c7a5a8cfc8a8be55'}]

SOURCE_REVISIONS = {
    "initial": {},
    "old-server-compat": {
        "O2": ("5683f86962cb16e6e44eb5c6586f9bd4ba4331ef4bb86a1d2b82028c5d81f7ab", [3, 12, 1, 2]),
        "O3": ("dbcce3ec29e494186f7930c538383a60e22359f9485db790d8f496b0d1444365", [3, 14, 1, 2]),
    },
}

def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _signature(view, body):
    ret, params, name, flags, options, names = view.a.methods[body[0]]
    return view.mn(ret), tuple(view.mn(i) for i in params), flags, options


def inspect(importer, *, source_revision="initial"):
    """Return precise indices and native redirect IDs, refusing unknown inputs."""
    if source_revision not in SOURCE_REVISIONS:
        raise ValueError(f"Unknown source revision: {source_revision}")
    target, source = importer.target, importer.source
    result = []
    for original in TARGETS:
        item = dict(original)
        revision = SOURCE_REVISIONS[source_revision].get(item['id'])
        if revision:
            item['android_code_sha256'] = revision[0]
        label = item["label"]
        ti, si = target.by_label.get(label, []), source.by_label.get(label, [])
        if len(ti) != 1 or len(si) != 1:
            raise ValueError(f"Ambiguous or missing overlimit method: {label}")
        target_body, source_body = target.a.bodies[ti[0]], source.a.bodies[si[0]]
        if target_body[0] != item["ios_method_id"]:
            raise ValueError(f"iOS method identity drift: {label}")
        if _sha(source_body[5]) != item["android_code_sha256"]:
            raise ValueError(f"Android final-method identity drift: {label}")
        if revision and source_body[1:5] != revision[1]:
            raise ValueError(f"Android final-method header drift: {label}")
        if _signature(target, target_body) != _signature(source, source_body):
            raise ValueError(f"Method signature mismatch: {label}")
        if target_body[6] or target_body[7] or source_body[6] or source_body[7]:
            raise ValueError(f"Unexpected exception/activation traits: {label}")
        present = target.normalized(ti[0]) == source.normalized(si[0])
        if not present and _sha(target_body[5]) != item["ios_code_sha256"]:
            raise ValueError(f"Unknown iOS preimage: {label}")
        result.append(dict(item, target_body_index=ti[0], source_body_index=si[0],
                           status="already_present" if present else "pending",
                           native_redirect_method=target_body[0]))
    return result


def import_methods(importer, *, verify_body=None, source_revision="initial"):
    """Import real Android bodies, keeping iOS method signatures and all traits.

    Optional verify_body accepts (body, abc), matching the shared AOT preparation
    check. The caller must include each returned native_redirect_method in its
    AOT compile/link plan; changing full ABC alone cannot update the native code.
    Discard the importer after a failed import, even though ABC changes roll back.
    """
    plan = inspect(importer, source_revision=source_revision)
    target, source, abc = importer.target, importer.source, importer.a
    saved_bodies = {row["target_body_index"]: copy.deepcopy(abc.bodies[row["target_body_index"]])
                    for row in plan}
    pool_fields = ("ints", "uints", "doubles", "strings", "namespaces", "ns_sets", "multinames")
    lengths = {name: len(getattr(abc, name)) for name in pool_fields}
    # The shared body importer only appends constants. It must never import a
    # class/trait, replace a signature, add state or change a native slot layout.
    metadata = {name: copy.deepcopy(getattr(abc, name))
                for name in ("methods", "metadata", "instances", "classes", "scripts")}
    receipts = []
    try:
        for row in plan:
            ti, si = row["target_body_index"], row["source_body_index"]
            old = abc.bodies[ti]
            if row["status"] == "already_present":
                receipts.append(row)
                continue
            imported = importer.body(si, old[0], scope=old[3])
            abc.bodies[ti] = imported
            if target.normalized(ti) != source.normalized(si):
                raise ValueError(f"Imported operations differ: {row['label']}")
            if imported[0] != old[0] or imported[3] != old[3]:
                raise ValueError(f"iOS method/scope identity changed: {row['label']}")
            if verify_body is not None:
                verify_body(imported, abc)
            receipts.append(dict(row, status="imported", before_header=old[1:5],
                                 after_header=imported[1:5],
                                 normalized_instructions_exact=True))
        for name, original in metadata.items():
            if getattr(abc, name) != original:
                # Traits use identity comparison in some parser versions; compare
                # serialized semantic fields instead of object identity there.
                normalized = _freeze(getattr(abc, name))
                if normalized != _freeze(original):
                    raise ValueError(f"Existing iOS metadata changed: {name}")
    except Exception:
        for index, body in saved_bodies.items():
            abc.bodies[index] = body
        for name, original in metadata.items():
            setattr(abc, name, original)
        for name, length in lengths.items():
            del getattr(abc, name)[length:]
        raise
    return {"methods": receipts, "source_revision": source_revision,
            "native_redirects": [r["native_redirect_method"] for r in receipts],
            "pool_appended": {name: len(getattr(abc, name)) - n for name, n in lengths.items()},
            "existing_traits_and_signatures_preserved": True,
            "requires_aot_compile_and_native_redirects": True}


def _freeze(value):
    if hasattr(value, "__slots__"):
        return tuple((name, _freeze(getattr(value, name))) for name in value.__slots__)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    return value


RESOURCE_TARGETS = [{'logical': 'master/character/level_cap_iosbundled.orderedmap',
  'ipa_member': 'Payload/worldflipper.app/asset/production/ios_bundle/c7/b8f9c6f9d572bb625885e0d0c9226c01d9a385',
  'before_sha256': 'ef1214e38f5e7514c6f6ee60c79f9126e482e39a9566188698dccbf026102190',
  'after_sha256': '9b816e7f05479519549357df3fe7a5193f56689e4c419ec554030757fd49d4ba'},
 {'logical': 'master/character/character_level_iosbundled.orderedmap',
  'ipa_member': 'Payload/worldflipper.app/asset/production/ios_bundle/23/a83b55daad153a95f8d5b66667b32e47f3dca2',
  'before_sha256': 'eb21a7fe67d9f58730235ce276d1421b26a14cb84e7d27fd35cb2e0cae2b3565',
  'after_sha256': '8ce0cbe4ab540483a535068a6b6005dba3eefabb2cd42938294ca0995ef53828'},
 {'logical': 'character_pedestal/sprite_sheet.png',
  'ipa_member': 'Payload/worldflipper.app/asset/production/ios_bundle/96/b97133a2b5c5bc58a4f234d531960136f0729f',
  'before_sha256': '9755243e07fc77bdb57f6047263f65cf450a07178083935b08528c8b991e8551',
  'after_sha256': 'c7618668e916b823926795523a1612acf99e0f1d998ecaaa898280469ac3b8d0'},
 {'logical': 'character_pedestal/sprite_sheet.atlas.amf3.deflate',
  'ipa_member': 'Payload/worldflipper.app/asset/production/ios_bundle/ce/d720392bdd8eeb25b339c2e3943f327fea27ba',
  'before_sha256': '0c97536686a770ea83664846d20e1e5eb1cb2e8843aa3445c43d2fdf056acad1',
  'after_sha256': 'c8b460ff58f075cc6260878decf5c4eb394f2d3f4b03b9463bc45c4a67255964'}]

def resource_replacements(prepared_dir, read_member):
    """Return exactly four iOS IPA sparse replacements, pinning both sides.

    ``read_member`` is a read-only callable such as ZipFile.read. The iOS
    originals equal the Android resource originals byte-for-byte. All four
    prepared payloads are shared formats; the pedestal texture is stored PNG,
    not ATF. No encoder, bundle rewrite or CDN work is performed here.
    """
    root = Path(prepared_dir).resolve()
    result = {}
    for item in RESOURCE_TARGETS:
        old = read_member(item["ipa_member"])
        if _sha(old) != item["before_sha256"]:
            raise ValueError(f"iOS resource preimage mismatch: {item['logical']}")
        file = root / item["logical"]
        raw = file.read_bytes()
        if _sha(raw) != item["after_sha256"]:
            raise ValueError(f"Prepared resource identity mismatch: {item['logical']}")
        if item["logical"].endswith(".png") and raw[:8] != b"\x89png\r\n\x1a\n":
            raise ValueError("Pedestal requires a strict stored PNG payload")
        result[item["ipa_member"]] = raw
    return result
