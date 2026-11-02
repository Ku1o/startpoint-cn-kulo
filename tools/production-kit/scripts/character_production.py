"""Hash-bound, manually recorded whole-character offline production ledger.

This program checks identities and bookkeeping only. It does not run engineering
checks, interpret a report's PASS, generate assets, compile, or certify gameplay.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
WORK_ROOT = Path(os.environ.get('STARPOINT_WORK_ROOT', Path.cwd() / 'work')).resolve()
SOURCE_ROOT = Path(__file__).resolve().parents[3]
STAGES = ('brief', 'mechanics', 'illustration', 'ui', 'pixel_motion',
          'active_fx', 'audio', 'assembly', 'preview')
RESERVED = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)),
            *(f'LPT{i}' for i in range(1, 10))}
NON_GOALS = ['No art generation or native compilation', 'No arbitrary command execution',
             'No game integration, service, source-repository, or release writes',
             'No interpretation of evidence JSON PASS fields',
             'No automated visual, mechanic, sound-quality, or game certification',
             'No semantic verification of selected pointers, recipes, or preview contents; '
             'register those files as inputs to detect byte changes']


class LedgerError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise LedgerError(message)


def identifier(value, label):
    require(isinstance(value, str) and re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', value)
            and value.upper() not in RESERVED, f'{label}: unsafe identifier')
    return value


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def bounded_output(value):
    lexical = Path(value).absolute()
    resolved = lexical.resolve()
    require(resolved != WORK_ROOT and resolved.is_relative_to(WORK_ROOT),
            'Output must resolve strictly inside STARPOINT_WORK_ROOT')
    require(not resolved.is_relative_to(SOURCE_ROOT), 'Source-repository output forbidden')
    for part in (*lexical.parts, *resolved.parts):
        require(part.lower() not in {'.cdn', 'outputs'}, 'Output in .cdn/outputs forbidden')
        require(part.rstrip(' .') == part and part.split('.')[0].upper() not in RESERVED
                and (':' not in part or part == lexical.anchor or part == resolved.anchor),
                'Unsafe output path component')
    return resolved


def parse_json_bytes(path, raw):
    try:
        result = json.loads(raw.decode('utf-8-sig'))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise LedgerError(f'Cannot read JSON {path}: {exc}') from exc
    require(isinstance(result, dict), f'{path}: JSON root must be an object')
    return result


def load_json(path):
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise LedgerError(f'Cannot read JSON {path}: {exc}') from exc
    return parse_json_bytes(path, raw)


def write_new(path, data):
    bounded_output(path)
    require(path.parent.is_dir(), 'Output parent must already exist')
    require(not path.exists() and not path.is_symlink(), 'Refusing to overwrite existing output')
    with path.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def node(status='pending'):
    return {'status': status, 'evidence': [], 'inputBindings': []}


def review():
    return {**node(), 'reason': ''}


def initialize(out, code):
    # Every new production workspace starts with a reviewable, explicitly empty
    # preview. Existing character workspaces are never recreated or overwritten.
    from character_preview import starter, build
    identifier(code, 'character-code')
    out = bounded_output(out)
    require(not out.exists(), 'Preserve existing workspace; choose a new --out')
    require(out.parent.is_dir(), 'Workspace parent must already exist')
    out.mkdir()
    plan_path = out / 'audio-plan.json'
    plan = {'schemaVersion': 1, 'scopeReason': '', 'silentDesign': False,
            'designEvidence': [], 'slots': []}
    write_new(plan_path, plan)
    preview_path = out / 'preview-spec.json'
    write_new(preview_path, starter(code))
    preview_result = build(preview_path, out / 'preview-start')
    ledger = {'schemaVersion': 1, 'kind': 'character_production_ledger',
              'characterCode': code,
              'inputs': [{'id': 'audio_plan', 'path': str(plan_path), 'sha256': sha(plan_path)},
                         {'id': 'preview_spec', 'path': str(preview_path), 'sha256': sha(preview_path)}],
              'stages': {stage: {'content': node(), 'offlineChecks': node(), 'review': review()}
                         for stage in STAGES},
              'audioSlots': {}, 'audioVolumeReview': review(),
              'game_testing': {'status': 'pending', 'reason': ''}}
    write_new(out / 'character-production.json', ledger)
    return {'status': 'initialized_empty_ledger', 'manifest': str(out / 'character-production.json'),
            'audioPlan': str(plan_path), 'previewSpec': str(preview_path),
            'previewIndex': preview_result['index'],
            'nextStep': 'Fill preview-spec.json from this character, then run character_preview.py build into a new version directory; update ledger bindings after changes.',
            'gameVerified': False, 'nonGoals': NON_GOALS}


class Checker:
    def __init__(self, manifest):
        self.path = manifest.resolve()
        self.base = self.path.parent
        raw = self.path.read_bytes()
        self.manifest_identity = {'path': str(self.path), 'sha256': hashlib.sha256(raw).hexdigest()}
        self.data = parse_json_bytes(self.path, raw)
        checker_path = Path(__file__).resolve()
        self.checker_identity = {'path': str(checker_path), 'sha256': sha(checker_path)}
        self.missing = []
        self.stale = []
        self.pending = []
        self.inputs = {}
        self.input_valid = {}
        self.manual = []

    def miss(self, location, message):
        self.missing.append({'location': location, 'message': message})

    def binding(self, binding, location):
        if not isinstance(binding, dict) or not isinstance(binding.get('path'), str) or not binding['path']:
            self.miss(location, 'Expected nonempty local path and sha256')
            return False
        expected = binding.get('sha256')
        if not isinstance(expected, str) or not re.fullmatch('[a-fA-F0-9]{64}', expected):
            self.miss(location, 'Expected 64 hexadecimal sha256 characters')
            return False
        try:
            raw = binding['path']
            require('://' not in raw and not raw.startswith(('\\\\', '//')), 'Network paths are forbidden')
            path = Path(raw)
            if not path.is_absolute():
                path = self.base / path
            path = path.resolve()
            require(path.is_file(), 'Not a readable local file')
            actual = sha(path)
        except (OSError, ValueError, RuntimeError) as exc:
            self.stale.append({'location': location, 'path': binding['path'], 'message': str(exc)})
            return False
        if actual.lower() != expected.lower():
            self.stale.append({'location': location, 'path': str(path), 'message': 'SHA256 mismatch',
                               'expected': expected.lower(), 'actual': actual})
            return False
        return True

    def evidence(self, values, location, required=False):
        if not isinstance(values, list):
            self.miss(location, 'Expected an evidence list')
            return False
        if required and not values:
            self.miss(location, 'Completed claims require nonempty local file evidence')
            return False
        good = True
        for index, binding in enumerate(values):
            good = self.binding(binding, f'{location}[{index}]') and good
        return good

    def dependencies(self, values, location, required=False, audio=False):
        if not isinstance(values, list):
            self.miss(location, 'Expected inputBindings list')
            return False
        if required and not values:
            self.miss(location, 'Completed claims require at least one input snapshot')
            return False
        good, ids = True, set()
        for index, value in enumerate(values):
            loc = f'{location}[{index}]'
            if not isinstance(value, dict):
                self.miss(loc, 'Expected {id,sha256} input snapshot')
                good = False
                continue
            key, expected = value.get('id'), value.get('sha256')
            if not isinstance(key, str) or key in ids or key not in self.inputs:
                self.miss(loc, 'Unknown or duplicate input id')
                good = False
                continue
            ids.add(key)
            if expected != self.inputs[key].get('sha256') or not self.input_valid.get(key, False):
                self.stale.append({'location': loc, 'inputId': key, 'message': 'Input snapshot no longer current'})
                good = False
        if required and audio and 'audio_plan' not in ids:
            self.miss(location, 'Audio completion must bind audio_plan')
            good = False
        return good

    def check_node(self, value, location, category, audio=False):
        if not isinstance(value, dict):
            self.miss(location, 'Required node is missing')
            return False
        terminal = {'content': 'done', 'offlineChecks': 'pass', 'review': 'approved'}[category]
        allowed = {'pending', terminal}
        if category == 'review':
            allowed.add('deferred_to_game')
        status = value.get('status')
        if not isinstance(status, str) or status not in allowed:
            self.miss(location, f'Status must be one of {sorted(allowed)}')
        completed = status == terminal
        evidence_ok = self.evidence(value.get('evidence'), location + '.evidence', completed)
        deps_ok = self.dependencies(value.get('inputBindings'), location + '.inputBindings', completed, audio)
        if category == 'review' and status != 'approved':
            if status == 'deferred_to_game' and (not isinstance(value.get('reason'), str)
                                                or not value['reason'].strip()):
                self.miss(location + '.reason', 'Deferred review requires a reason')
            self.pending.append({'location': location, 'status': status, 'reason': value.get('reason', '')})
        elif completed:
            self.manual.append({'location': location, 'claim': status,
                                'classification': 'manual_registration_with_file_identity_checks_only'})
        elif category != 'review':
            self.miss(location, 'Not completed')
        return completed and evidence_ok and deps_ok

    def check_audio(self):
        input_record = self.inputs.get('audio_plan')
        if not input_record or not self.input_valid.get('audio_plan'):
            self.miss('inputs.audio_plan', 'A current hash-bound audio-plan input is required')
            return False
        plan_path = Path(input_record['path'])
        if not plan_path.is_absolute():
            plan_path = self.base / plan_path
        plan = load_json(plan_path)
        require(type(plan.get('schemaVersion')) is int and plan['schemaVersion'] == 1,
                'Unsupported audio-plan schemaVersion')
        good = True
        if not isinstance(plan.get('scopeReason'), str) or not plan['scopeReason'].strip():
            self.miss('audioPlan.scopeReason', 'Describe why the declared slots cover this character')
            good = False
        good = self.evidence(plan.get('designEvidence'), 'audioPlan.designEvidence', True) and good
        declared = plan.get('slots')
        require(isinstance(declared, list), 'audio-plan slots must be a list')
        if not declared and plan.get('silentDesign') is not True:
            self.miss('audioPlan.slots', 'Explicit nonempty recording slots required, or silentDesign=true with design evidence')
            good = False
        require(type(plan.get('silentDesign', False)) is bool, 'silentDesign must be boolean')
        registered = self.data.get('audioSlots')
        require(isinstance(registered, dict), 'audioSlots must be an object keyed by declared slot id')
        ids = set()
        brief_stage = self.data.get('stages', {}).get('brief')
        brief_node = brief_stage.get('content') if isinstance(brief_stage, dict) else None
        brief = brief_node.get('evidence', []) if isinstance(brief_node, dict) else []
        omission_sources = [*(plan.get('designEvidence') or []), *(brief if isinstance(brief, list) else [])]
        for index, slot in enumerate(declared):
            require(isinstance(slot, dict), 'audio-plan slot must be an object')
            sid = identifier(slot.get('id'), 'audio slot id')
            require(sid not in ids, 'Duplicate audio slot id: ' + sid)
            ids.add(sid)
            loc = 'audioSlots.' + sid
            if not isinstance(slot.get('role'), str) or not slot['role'].strip():
                self.miss(loc + '.role', 'Explicit recording role required')
                good = False
            require(type(slot.get('required')) is bool, 'Each audio slot requires explicit required boolean')
            if slot['required']:
                good = self.check_node(registered.get(sid), loc, 'content', audio=True) and good
            else:
                omission = slot.get('omissionDocument')
                reason = slot.get('omissionReason')
                if not isinstance(reason, str) or not reason.strip() or omission not in omission_sources:
                    self.miss(loc, 'Omitted slot needs reason and a brief/design evidence binding')
                    good = False
                good = self.binding(omission, loc + '.omissionDocument') and good
                if sid not in registered:
                    self.miss(loc, 'Declare omitted slot explicitly as {status: omitted}')
                    good = False
                elif registered[sid] != {'status': 'omitted'}:
                    self.miss(loc, 'Nonrequired slot registration must be exactly {status: omitted}')
                    good = False
        extra = set(registered) - ids
        if extra:
            self.miss('audioSlots', 'Undeclared slot ids: ' + ', '.join(sorted(extra)))
            good = False
        return good

    def run(self):
        data = self.data
        require(type(data.get('schemaVersion')) is int and data['schemaVersion'] == 1,
                'Unsupported schemaVersion; expected integer 1')
        require(data.get('kind') == 'character_production_ledger', 'Wrong ledger kind')
        identifier(data.get('characterCode'), 'characterCode')
        inputs = data.get('inputs')
        require(isinstance(inputs, list), 'inputs must be a list')
        for index, item in enumerate(inputs):
            require(isinstance(item, dict), 'input must be an object')
            key = identifier(item.get('id'), 'input id')
            require(key not in self.inputs, 'Duplicate input id: ' + key)
            self.inputs[key] = item
            self.input_valid[key] = self.binding(item, f'inputs[{index}]')
        stages = data.get('stages')
        require(isinstance(stages, dict), 'stages must be an object')
        unknown = set(stages) - set(STAGES)
        require(not unknown, 'Unknown stages: ' + ', '.join(sorted(unknown)))
        content, offline = [], []
        for stage in STAGES:
            value = stages.get(stage)
            if not isinstance(value, dict):
                self.miss('stages.' + stage, 'Fixed required stage is missing')
                content.append(False)
                offline.append(False)
                continue
            for category in ('content', 'offlineChecks', 'review'):
                ok = self.check_node(value.get(category), f'stages.{stage}.{category}', category,
                                     audio=stage == 'audio')
                if category == 'content':
                    content.append(ok)
                elif category == 'offlineChecks':
                    offline.append(ok)
        content.append(self.check_audio())
        self.check_node(data.get('audioVolumeReview'), 'audioVolumeReview', 'review', audio=True)
        game = data.get('game_testing')
        require(isinstance(game, dict), 'game_testing is required')
        require(isinstance(game.get('status'), str) and game['status'] in {'pending', 'deferred_to_game'},
                'Tool cannot certify game_testing; use pending or deferred_to_game')
        if game['status'] == 'deferred_to_game' and (not isinstance(game.get('reason'), str)
                                                   or not game['reason'].strip()):
            self.miss('game_testing.reason', 'Deferred game testing requires a reason')
        self.pending.append({'location': 'game_testing', **game})
        for location, identity in (('manifest', self.manifest_identity), ('checker', self.checker_identity)):
            try:
                actual = sha(Path(identity['path']))
            except OSError as exc:
                self.stale.append({'location': location, 'path': identity['path'],
                                   'message': 'Identity became unreadable during check: ' + str(exc)})
            else:
                if actual != identity['sha256']:
                    self.stale.append({'location': location, 'path': identity['path'],
                                       'message': 'File changed during check',
                                       'expected': identity['sha256'], 'actual': actual})
        # Any stale binding, including an unused global input, invalidates the whole snapshot.
        clean = not self.stale and not self.missing
        content_complete = all(content) and clean
        offline_complete = all(offline) and clean
        return {'schemaVersion': 1, 'characterCode': data['characterCode'],
                'manifest': self.manifest_identity, 'checker': self.checker_identity,
                'contentComplete': content_complete, 'offlineEvidenceComplete': offline_complete,
                'readyForOfflineReview': content_complete and offline_complete and not self.missing,
                'gameVerified': False, 'missing': self.missing, 'stale': self.stale,
                'pendingReviews': self.pending, 'manualRegistrations': self.manual,
                'evidenceSemantics': 'registered_claims_with_fresh_file_identities_not_independent_engine_validation',
                'audioCoverageMeaning': 'Declared design slots only; completeness of the authored slot list '
                'requires human design review. Unreferenced package recordings do not satisfy slots.',
                'evidenceMeaning': 'Only file identity is automatically checked. done/pass/approved '
                'are manual claims; content, engineering semantics and aesthetics are not certified.',
                'nonGoals': NON_GOALS}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init', help='Create an empty ledger in a new isolated work directory')
    init.add_argument('--out', required=True)
    init.add_argument('--character-code', required=True)
    check = commands.add_parser('check', help='Read-only hash and ledger checks; no commands are run')
    check.add_argument('--manifest', required=True)
    check.add_argument('--report', help='New JSON file strictly within STARPOINT_WORK_ROOT')
    args = parser.parse_args(argv)
    try:
        if args.command == 'init':
            result = initialize(args.out, args.character_code)
            exit_code = 0
        else:
            if args.report:
                report = bounded_output(args.report)
                require(not report.exists() and not report.is_symlink(), 'Report already exists')
                require(report.parent.is_dir(), 'Report parent must already exist')
            result = Checker(Path(args.manifest)).run()
            if args.report:
                write_new(report, result)
            exit_code = 0 if result['readyForOfflineReview'] else 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return exit_code
    except (LedgerError, OSError, RuntimeError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
