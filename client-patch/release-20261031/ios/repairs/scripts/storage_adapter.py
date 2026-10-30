"""Task-local wildcard ledger adapter. Imported only in a future bounded stage.

No compiler or preparation runs at import. The old generic algorithm is reused
only for the explicitly selected ledger; never rediscover all 26 old states by
comparing Android slots against the current iOS accessor-based declarations.
"""
import sys as _release_sys
from pathlib import Path as _ReleasePath
_release_sys.path.insert(0, str(next(p for p in _ReleasePath(__file__).resolve().parents if (p / 'input_config.py').is_file())))
import input_config as cfg
cfg.bootstrap()
from pathlib import Path
import importlib.util
from unittest.mock import patch

TASK = Path(__file__).resolve().parents[1]
SHARED = Path(cfg.local('capabilities/static_proxies.py'))
OWNER = 'pinball.scene.battle.battle.ability::InstantAbility'
NAME = 'wfxHpLossLedger'
STATE = 'cn.release::AcceptanceRepairsState20261031'
STATE_CLASS = 'AcceptanceRepairsState20261031'

def library():
    spec = importlib.util.spec_from_file_location('acceptance_storage_algorithm',SHARED)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def definitions(target, donor):
    owners = [i for i,r in enumerate(donor.a.instances) if donor.a.mn_name(r[0]) == OWNER]
    assert len(owners) == 1, 'exact InstantAbility source owner required'
    ci, = owners
    traits = [t for t in donor.a.classes[ci][1]
              if donor.a.mn_name(t.name).split('::')[-1] == NAME]
    assert len(traits) == 1, 'one source ledger declaration required'
    trait, = traits
    assert trait.kind == 0 and trait.attr == 0 and not trait.metadata
    assert trait.data[2] == 0 and trait.data[3] == 0 and trait.data[4] is None, 'wildcard/default semantics changed'
    mn = donor.a.multinames[trait.name]
    assert mn[0] == 7, 'ledger must retain an exact QName'
    ns = donor.a.namespaces[mn[1]]
    assert ns[0] == 0x16 and donor.a.s(ns[1]) == '', 'public empty-package namespace required'
    current, = [i for i,r in enumerate(target.a.instances) if target.a.mn_name(r[0]) == OWNER]
    assert not any(target.a.mn_name(t.name).split('::')[-1] == NAME
                   for t in target.a.classes[current][1]), 'ledger already exists; inspect rather than overwrite'
    assert not any(target.a.mn_name(r[0]) == STATE for r in target.a.instances), 'new sidecar QName collides'
    return [dict(owner=OWNER,name=NAME,qname=donor.a.mn_name(trait.name),
                 namespace_semantics=donor.mn(trait.name),source_multiname=trait.name,
                 type='*',source_type=0,static=True,default='AVM2 undefined',sidecar_field='hpLossLedger')]

def source_text(rows):
    assert len(rows) == 1 and rows[0]['source_type'] == 0 and rows[0]['type'] == '*'
    source = library().source_text(rows)
    assert source.count('class ReleaseState20261031') == 1, 'shared source renderer shape changed'
    source = source.replace('class ReleaseState20261031','class '+STATE_CLASS)
    assert 'public static var hpLossLedger:*;' in source
    assert 'Dictionary' not in source and '=' not in source, 'do not eagerly initialize or narrow wildcard storage'
    return source

def audit_accesses(p, donor, rows, method_ids):
    """Audit semantic QName aliases, not only one constant-pool index."""
    assert len(rows) == 1 and rows[0]['name'] == NAME
    expected = donor.mn(rows[0]['source_multiname'])
    aliases = [i for i in range(1,len(donor.a.multinames)) if donor.mn(i) == expected]
    assert aliases, 'ledger QName has no source pool index'
    found = []
    for body in donor.a.bodies:
        if body[0] not in method_ids:continue
        for at,ins in enumerate(p.asm.decode(body[5])):
            if ins.op in p.MULTINAME_OPS or ins.op in (0x4b,0x4d):
                mn=ins.args[0]
                if donor.a.mn_name(mn).split('::')[-1] != NAME:continue
                assert donor.mn(mn) == expected and mn in aliases, 'same-name ledger access has a different/dynamic namespace'
                assert ins.op in (0x61,0x66), 'ledger access is not getproperty/setproperty'
                found.append(dict(method=body[0],label=donor.labels.get(body[0]),instruction=at,
                                  operation=ins.name,multiname=mn,qname_semantics=expected))
            elif ins.op == 0x2c and donor.a.s(ins.args[0]) == NAME:
                raise ValueError('ledger reflection string requires another explicit adapter')
    return dict(semantic_qname=expected,all_equivalent_pool_indices=aliases,accesses=found,
                allowed_operations=['getproperty','setproperty'],all_selected_methods_audited=sorted(method_ids))

def import_and_install(p, target, donor, helper, source_root, rows):
    assert len(rows) == 1 and rows[0]['source_type'] == 0
    assert [helper.a.mn_name(r[0]) for r in helper.a.instances] == [STATE]
    assert p.Importer(target,donor).pool('multinames',0) == 0, 'wildcard sentinel must remain zero'
    algorithm = library()
    with patch.object(algorithm,'STATE',STATE):
        lifecycle = algorithm.import_sidecar(p,target,helper,source_root)
        # Caller must rebuild the View after importing the sidecar, then use
        # the same underlying ABC when appending the owner accessors.
        import types
        refreshed = p.View(types.SimpleNamespace(abc=target.a),p.asm)
        mapped = p.Importer(refreshed,donor)
        proxies = algorithm.install_accessors(p,refreshed,donor,mapped,rows)
    for row in proxies:
        for accessor in row['accessors']:
            info = target.a.methods[accessor['method_id']]
            if accessor['kind'] == 'getter':
                assert info[0] == 0 and info[1] == [], 'getter must return Atom/*'
            else:
                assert info[1] == [0] and target.a.mn_name(info[0]) == 'void', 'setter must take Atom/*'
    # The actual compiler can emit more initializer helpers. These IDs are
    # source lifecycles/accessors, not a promised final AOT symbol count.
    return dict(source_lifecycle_method_ids=lifecycle,proxy_records=proxies,
                sidecar_owner=STATE,wildcard_type=0,atom_abi_native_verified=False)
