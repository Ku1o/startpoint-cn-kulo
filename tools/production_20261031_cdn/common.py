"""Explicit inputs and sparse resource reads for this release's recipes.

Reuse the repository's hashed-path, orderedmap and storage codecs. This module
never writes an active chain, materializes the CDN, or runs child processes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

ROOTS = {'common': 'upload', 'medium': 'medium_upload', 'small': 'small_upload',
         'android': 'android_upload', 'ios': 'ios_upload'}
HASHED = re.compile(r'[0-9a-f]{2}/[0-9a-f]{38}')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text('utf-8-sig'))


def version(value):
    if not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise ValueError('Invalid resource version')
    return tuple(map(int, value.split('.')))


def install_codecs(repo):
    tools = Path(repo).resolve() / 'tools'
    for directory in (tools, tools / 'fantasy-gauntlet-mod-tools'):
        if str(directory) not in sys.path:
            sys.path.insert(0, str(directory))
    if not (tools / 'rebuild_character_edge.py').is_file():
        raise FileNotFoundError('Repository orderedmap helper is missing')


def member(root, logical):
    if root not in ROOTS:
        raise ValueError('Unknown asset root: ' + root)
    if logical.startswith('@sha1/'):
        relative = logical[len('@sha1/'):]
        if HASHED.fullmatch(relative) is None:
            raise ValueError('Invalid explicit hashed resource')
    else:
        from wf_mod_tool import sha1_path
        digest = sha1_path(logical)
        relative = digest[:2] + '/' + digest[2:]
    return 'production/' + ROOTS[root] + '/' + relative


class SparseChain:
    """Read only requested members from an explicitly supplied historical chain.

    Archive SHA is checked on first active payload use. Pristine ZIP central
    directories are indexed only if a requested asset has no active winner;
    pristine payloads are not extracted or globally CRC/hash scanned.
    """
    def __init__(self, manifest, active, baseline, through, baseline_version='1.4.54'):
        self.manifest_path = Path(manifest).resolve()
        self.raw = self.manifest_path.read_bytes()
        self.manifest = json.loads(self.raw)
        self.active = [Path(x).resolve() for x in active]
        self.baseline = Path(baseline).resolve()
        self.baseline_version = baseline_version
        self.through = through
        self.entries, self.verified, self.reads = [], set(), []
        self.pristine = None
        enabled = sorted((x for x in self.manifest['patches'] if x.get('enabled')),
                         key=lambda x: version(x['version']))
        if len({x['version'] for x in enabled}) != len(enabled):
            raise ValueError('Duplicate enabled version')
        tail = baseline_version
        for patch in enabled:
            if version(patch['version']) > version(through):
                break
            if patch['depends_on'] != tail:
                raise ValueError('Non-contiguous supplied chain')
            integrity = {x['name']: x for x in patch.get('archive_integrity', [])}
            for name in patch.get('chain') or [patch['archive']]:
                if Path(name).name != name:
                    raise ValueError('Archive name contains a path')
                self.entries.append((name, integrity.get(name), patch['version']))
            tail = patch['version']
        if tail != through:
            raise ValueError('Recipe baseline is absent from the supplied chain: ' + through)

    def _locate(self, name):
        for directory in self.active:
            path = directory / name
            if path.is_file():
                return path
        raise FileNotFoundError('Missing enabled archive: ' + name)

    def _read(self, path, target, receipt=None, at=None):
        with zipfile.ZipFile(path) as archive:
            matches = [x for x in archive.infolist() if x.filename == target]
            if len(matches) > 1:
                raise ValueError('Duplicate archive resource: ' + target)
            if not matches:
                return None
            if receipt and path not in self.verified:
                if path.stat().st_size != receipt['size'] or file_sha(path) != receipt['sha256']:
                    raise ValueError('Active archive identity mismatch: ' + path.name)
                self.verified.add(path)
            raw = archive.read(matches[0])
        self.reads.append({'archive': path.name, 'member': target, 'version': at,
                           'bytes': len(raw), 'sha256': sha(raw)})
        return raw

    def _pristine_index(self):
        archives = []
        for folder in self.baseline.glob('archive-*'):
            for path in folder.glob('*.zip'):
                if '-full' in folder.name:
                    archives.append((0, path.name, path))
                else:
                    match = re.match(r'pinball-\d+\.\d+\.\d+-1\.4\.(\d+)-', path.name)
                    if match and int(match[1]) <= version(self.baseline_version)[2]:
                        archives.append((int(match[1]), path.name, path))
        self.pristine = {}
        for _, _, path in sorted(archives):
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    if info.filename.startswith('production/'):
                        self.pristine[info.filename] = path

    def get_member(self, root, relative):
        if relative.startswith('production/'):
            prefix = 'production/' + ROOTS[root] + '/'
            if not relative.startswith(prefix):
                raise ValueError('Explicit member root mismatch')
            relative = relative[len(prefix):]
        target = member(root, '@sha1/' + relative)
        for name, receipt, at in reversed(self.entries):
            if receipt and 'files' in receipt and target not in receipt['files']:
                continue
            path = self._locate(name)
            raw = self._read(path, target, receipt, at)
            if raw is not None:
                return raw
            if receipt and 'files' in receipt and target in receipt['files']:
                raise ValueError('Declared active archive member is missing: ' + target)
        if self.pristine is None:
            self._pristine_index()
        path = self.pristine.get(target)
        return self._read(path, target, at=self.baseline_version) if path else None

    def get(self, root, logical):
        return self.get_member(root, member(root, logical).split('/', 2)[2])


class Context:
    def __init__(self, repo, spec_path, spec, external_locations=None, chain=None):
        self.repo = Path(repo).resolve()
        self.spec_path = Path(spec_path).resolve()
        self.spec_dir = self.spec_path.parent
        self.spec = spec
        self.chain = chain
        self.external_locations = external_locations or {}
        self.external_specs = {x['alias']: x for x in spec.get('externalInputs', [])}
        if len(self.external_specs) != len(spec.get('externalInputs', [])):
            raise ValueError('Duplicate external input alias')
        self._checked_external = set()
        install_codecs(self.repo)

    def input(self, relative):
        path = (self.spec_dir / relative).resolve()
        if not path.is_relative_to(self.spec_dir):
            raise ValueError('Input escapes the recipe directory')
        if not path.is_file():
            raise FileNotFoundError('Missing recipe input: ' + relative)
        return path

    def external(self, alias):
        if alias not in self.external_specs:
            raise KeyError('Undeclared external input: ' + alias)
        if alias not in self.external_locations:
            raise FileNotFoundError('Supply this external input alias: ' + alias)
        path = Path(self.external_locations[alias]).resolve()
        if alias not in self._checked_external:
            rule = self.external_specs[alias]
            if rule.get('kind') == 'directory':
                if not path.is_dir() or not rule.get('files'):
                    raise ValueError('A dependency directory needs an exact file contract: ' + alias)
                for entry in rule['files']:
                    file = (path / entry['path']).resolve()
                    if not file.is_relative_to(path) or not file.is_file():
                        raise ValueError('Dependency file missing or outside root')
                    if file_sha(file) != entry['sha256']:
                        raise ValueError('Dependency source identity mismatch: ' + entry['path'])
                    if 'bytes' in entry and file.stat().st_size != entry['bytes']:
                        raise ValueError('Dependency source size mismatch')
            else:
                if not path.is_file() or file_sha(path) != rule['sha256']:
                    raise ValueError('External input identity mismatch: ' + alias)
                if 'bytes' in rule and path.stat().st_size != rule['bytes']:
                    raise ValueError('External input size mismatch: ' + alias)
            self._checked_external.add(alias)
        return path

    def get(self, root, logical):
        if self.chain is None:
            raise RuntimeError('Build requires an explicit baseline chain')
        return self.chain.get(root, logical)

    def get_member(self, root, relative):
        if self.chain is None:
            raise RuntimeError('Build requires an explicit baseline chain')
        return self.chain.get_member(root, relative)
