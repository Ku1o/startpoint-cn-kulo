"""Guarded Android overlimit method ports (archive O1-O12, O9-O12 revision r2).

The caller owns SWF parsing, ABC serialization and package assembly. The support
object supplies asm, bodies.resolve, mn_at, splice_with_exits, Refused and
check_body from the shared patch core; no bundled bytecode library is imported.
Only the exact confirmed input bodies are accepted. Pool appends are forbidden.
No registration, signing, network, service or device operations occur here.
"""
from __future__ import annotations

import copy
import hashlib

RARITY = 5
RETAIL_STEPS = 4
EXT_STEPS = 8
EXT_LEVEL = 120
PARADOX_CORE = (10000, 1000, 302)
FULLWIDTH_PLUS = '＋'

PATCHES = [{'id': 'O1',
  'tag': b'boot_ffc6',
  'label': 'GeneralCharacterLogic/get_maxOverLimitStep',
  'apply': 'o1_apply',
  'before': '3ffa287364fb8098635d7127b0dc3d66234cafbb658b4bed2b33fc355053a6ca',
  'after': 'a1b57b4034b60def3d9b1a328b7ceb321157f45e5243c246353d733a7643ebab'},
 {'id': 'O2',
  'tag': b'boot_ffc6',
  'label': 'OwnedOverLimitLogic/getOwnAwakingCrystalToOverLimit',
  'apply': 'o2_apply',
  'before': 'e492781cdd1f0c121eb996d1c5ff69735f0912b2a2d4bad1f7c038e5cffc245f',
  'after': '2be9af1fa92ed8bb56a5ee90b9eb511f7f94c6941f38a223e406207e17be61b2'},
 {'id': 'O3',
  'tag': b'boot_ffc6',
  'label': 'OwnedOverLimitLogic/getAwakingCrystalToOverLimit',
  'apply': 'o3_apply',
  'before': '6ff7cce512d71facbd7acf7aeef5a234bd5c70d8e3531d31369381f1a58b77ad',
  'after': '2e584914a2f67e60a268e62502f8e7af84a6a6e1e38af444b8de79c446470b34'},
 {'id': 'O4',
  'tag': b'boot_ffc6',
  'label': 'OwnedOverLimitLogic/getOverLimitState',
  'apply': 'o4_apply',
  'before': '27f4d717747a8c567a3b1e8690c8a499a3811173489d222f8aff2db1a3b7a546',
  'after': '98f9c7121ac212729daaf7a0e9b740e2de275dcc26e2536ad4d8e1d63d023fd0'},
 {'id': 'O5',
  'tag': b'boot_ffc6',
  'label': 'OwnedCharacterLogic/getPossibleOverLimitCountByItem',
  'apply': 'o5_apply',
  'before': '2dc44da607ffab595b1c44f2c257587ea699294f1636847cbee7ab33677a7991',
  'after': '7fa65be8a2181e01a0a17b400d74fecbd0565c2600be4e78a7be8d96a94e837e'},
 {'id': 'O6',
  'tag': b'boot_ffc6',
  'label': 'GeneralCharacterLogic/getPedestalImagePath',
  'apply': 'o6_apply',
  'before': '9713b7437a4eddaf978f704d4b6721ca65a63f6d24138b05817c32b97cbe9ce2',
  'after': '1c5905b65f624a24c01cf58adeeb90c300a9e9ae965577c4b295c093f0be117d'},
 {'id': 'O7',
  'tag': b'boot_ffc6',
  'label': 'GeneralCharacterLogic/getHalfPedestalImagePath',
  'apply': 'o7_apply',
  'before': '3c050c660a915c1f8c18f16f2fad519ffba84f42d6661c86fcaa64f9af9b16bd',
  'after': '0dc8e515702c2c3c77cca60549da8e063eec0785f89a57e503b5ddf41be6a28a'},
 {'id': 'O8',
  'tag': b'boot_ffc6',
  'label': 'PixelArtCharacter/getPedestalImagePath',
  'apply': 'o8_apply',
  'before': '7a286e705e1416d02a1d9dcbb811f80d238fe48976b8b1b0ab4cbb54888330ed',
  'after': '10eb1e21f915782bcd5715a3fb58670cb18737ae8a5f0f569781f774b1a48f0d'},
 {'id': 'O9',
  'tag': b'boot_ffc6',
  'label': 'OverLimitWindow/getOverLimitState',
  'apply': 'o9_apply',
  'before': 'd39a4847f5adfd05c660a4bacd1ea2bad9b13bdabe8b72a72927fa9bbca7bc9b',
  'after': 'ae683cc1f5574ac7b415c43cf779ea642535cd6a66531aa1ee51a150d1492068'},
 {'id': 'O10',
  'tag': b'boot_ffc6',
  'label': 'OverLimitWindow/run',
  'apply': 'o10_apply',
  'before': '2787a647de463c9493d6347076db09a4b4417434174a9394f4e77c7352fbc14a',
  'after': 'b96160fc0f1046a50cf78065ed8d907861a2a65fb13c4f365abad60cbd4b2a7e'},
 {'id': 'O11',
  'tag': b'boot_ffc6',
  'label': 'OverLimitWindow/getStatusInformation',
  'apply': 'o11_apply',
  'before': '5a3d0744321eb787d738b56df42059611df979f493b0c121fdc239ce491ad83d',
  'after': 'c64d19bbf7957fd9490406d4d251abb9d1e16eeb3062e1b49148f56afbd29aa4'},
 {'id': 'O12',
  'tag': b'boot_ffc6',
  'label': 'ExpodOverLimitByItemDialog/getDescription',
  'apply': 'o12_apply',
  'before': '479e1323bda6560e5033a2f4d303e2932412d19c39b340844ecfb9a2d46fbbec',
  'after': 'a0468818a62ad753f0d18a755b29af19c61ebf5c3cd4a145c7a5a8cfc8a8be55'}]

class _Port:
    def __init__(self, support):
        for name in ("asm", "bodies", "mn_at", "splice_with_exits", "Refused"):
            setattr(self, name, getattr(support, name))

    def _code(self, body):
        return self.asm.decode(body[5])

    def _require(self, cond, what):
        if not cond:
            raise self.Refused(what)

    def o1_apply(self, abc, index, pool):
        body = abc.bodies[index]
        self._require(body[1:5] == [1, 1, 1, 2] and (not body[6]) and (not body[7]), 'get_maxOverLimitStep header')
        code = self._code(body)
        self._require([c.name for c in code] == ['getlocal_0', 'pushscope', 'findproperty', 'getproperty', 'callproperty', 'convert_i', 'returnvalue'], 'get_maxOverLimitStep shape')
        m_level = self.mn_at(abc, body, 3, 'getproperty', 'levelLogic')
        m_getmax = self.mn_at(abc, body, 4, 'callproperty', 'getMaxOverLimitStep')
        m_rarity = pool.find('get_rarity', 7)
        m_base = pool.find('baseStatusLogic', 7)
        m_keys = pool.find('keyLevels', 7)
        m_len = pool.find('length', 7)
        m_step = pool.find('overLimitStep', 7)
        s_step = pool.string('overLimitStep')
        mnl = self._index_multiname_l(abc)
        src = [('getlocal_0',), ('pushscope',), ('findproperty', code[2].args[0]), ('getproperty', m_level), ('callproperty', m_getmax, 0), ('convert_i',), ('setlocal_1',), ('getlocal_0',), ('callproperty', m_rarity, 0), ('convert_i',), ('pushbyte', RARITY), ('ifne', 'RET_N'), ('getlocal_0',), ('getproperty', m_base), ('getproperty', m_keys), ('dup',), ('getproperty', m_len), ('convert_i',), ('pushbyte', 1), ('subtract',), ('getproperty', mnl), ('convert_i',), ('pushbyte', EXT_LEVEL), ('iflt', 'RET_RETAIL'), ('pushstring', s_step), ('getlocal_0',), ('in',), ('iffalse', 'RET_N'), ('getlocal_0',), ('getproperty', m_step), ('convert_i',), ('pushbyte', RETAIL_STEPS), ('iflt', 'RET_RETAIL'), ('label', 'RET_N'), ('getlocal_1',), ('returnvalue',), ('label', 'RET_RETAIL'), ('pushbyte', RETAIL_STEPS), ('returnvalue',)]
        new, _ = self.asm.encode(self.asm.assemble(src))
        body[1:5] = [3, 2, 1, 2]
        body[5] = new
        return {'replaced': 'whole body', 'new_len': len(new)}

    def _index_multiname_l(self, abc):
        """数组下标用的 MultinameL（kind 0x1B）：取 CharacterBaseStatusLogic/getParameterAt 里读 keyLevels[i] 的同一个。"""
        donor = abc.bodies[self.bodies.resolve(abc, 'CharacterBaseStatusLogic/getParameterAt')]
        hits = {c.args[0] for c in self.asm.decode(donor[5]) if c.name == 'getproperty' and abc.multinames[c.args[0]][0] == 27}
        if len(hits) != 1:
            raise self.Refused(f'MultinameL donor ambiguous: {hits}')
        return hits.pop()

    def _mode_and_ext_block(self, abc, pool, rarity_local, target_local, allow_local, mode_local, ext_local):
        m_char = pool.find('character', 7)
        m_step = pool.find('overLimitStep', 7)
        return [('getlocal', rarity_local), ('pushbyte', RARITY), ('ifne', 'M_FALSE'), ('findproperty', m_char), ('getproperty', m_char), ('getproperty', m_step), ('convert_i',), ('pushbyte', RETAIL_STEPS), ('iflt', 'M_FALSE'), ('pushtrue',), ('setlocal', mode_local), ('jump', 'M_DONE'), ('label', 'M_FALSE'), ('pushfalse',), ('setlocal', mode_local), ('label', 'M_DONE'), ('getlocal', target_local), ('pushbyte', RARITY), ('ifne', 'E_FALSE'), ('getlocal', allow_local), ('iffalse', 'E_FALSE'), ('pushtrue',), ('setlocal', ext_local), ('jump', 'E_DONE'), ('label', 'E_FALSE'), ('pushfalse',), ('setlocal', ext_local), ('label', 'E_DONE'), ('getlocal', mode_local), ('getlocal', ext_local), ('ifstrictne', 'SKIP')]

    def _crystal_filter(self, abc, index, pool, *, header, push_at, skip_to, rarity_local, target_local, allow_local, target_at, allow_at):
        body = abc.bodies[index]
        self._require(body[1:5] == header and (not body[6]) and (not body[7]), 'crystal header')
        code = self._code(body)
        self._require(code[target_at].name == 'getproperty' and abc.mn_name(code[target_at].args[0]) == 'target_character_rarity', 'target anchor')
        self._require(code[allow_at].name == 'getproperty' and abc.mn_name(code[allow_at].args[0]) == 'is_allow_below_rarity', 'allow anchor')
        self._require(code[push_at + 2].name == 'callpropvoid' and abc.mn_name(code[push_at + 2].args[0]).endswith('::push'), 'push anchor')
        self._require(code[push_at - 1].name == 'iffalse' and code[push_at - 1].target == skip_to, 'condition anchor')
        self._require(code[skip_to].name == 'jump', 'skip anchor')
        mode_local, ext_local = (header[1], header[1] + 1)
        block = self._mode_and_ext_block(abc, pool, rarity_local, target_local, allow_local, mode_local, ext_local)
        old = body[5]
        new, exc, _merged, n = self.splice_with_exits(body, push_at, block, {'SKIP': skip_to})
        self._require(self.asm.unsplice(new, push_at, n) == old, 'inverse splice differs')
        body[1:5] = [max(header[0], 2), header[1] + 2, header[2], header[3]]
        body[5], body[6] = (new, exc)
        return {'inserted_at': push_at, 'block_len': n, 'new_locals': [mode_local, ext_local]}

    def o2_apply(self, abc, index, pool):
        return self._crystal_filter(abc, index, pool, header=[3, 10, 1, 2], push_at=86, skip_to=89, rarity_local=2, target_local=8, allow_local=9, target_at=62, allow_at=67)

    def o3_apply(self, abc, index, pool):
        return self._crystal_filter(abc, index, pool, header=[3, 11, 1, 2], push_at=97, skip_to=100, rarity_local=1, target_local=9, allow_local=10, target_at=73, allow_at=78)

    def o4_apply(self, abc, index, pool):
        body = abc.bodies[index]
        self._require(body[1:5] == [3, 12, 1, 2] and (not body[6]) and (not body[7]), 'getOverLimitState header')
        code = self._code(body)
        self._require([c.name for c in code[24:32]] == ['findproperty', 'getproperty', 'callproperty', 'convert_i', 'pushbyte', 'greaterthan', 'convert_b', 'setlocal'] and code[31].args == [4], 'stack anchor')
        self._require(abc.mn_name(code[26].args[0]) == 'get_stack', 'get_stack anchor')
        m_char = pool.find('character', 7)
        m_rarity = pool.find('get_rarity', 7)
        m_step = pool.find('overLimitStep', 7)
        block = [('getlocal', 4), ('iffalse', 'DONE'), ('findproperty', m_char), ('getproperty', m_char), ('callproperty', m_rarity, 0), ('convert_i',), ('pushbyte', RARITY), ('ifne', 'DONE'), ('findproperty', m_char), ('getproperty', m_char), ('getproperty', m_step), ('convert_i',), ('pushbyte', RETAIL_STEPS), ('iflt', 'DONE'), ('pushfalse',), ('setlocal', 4), ('label', 'DONE')]
        old = body[5]
        new, exc, _merged, n = self.splice_with_exits(body, 32, block, {})
        self._require(self.asm.unsplice(new, 32, n) == old, 'inverse splice differs')
        body[5], body[6] = (new, exc)
        return {'inserted_at': 32, 'block_len': n}

    def o5_apply(self, abc, index, pool):
        """超限模式下可突破次数 = min(超限结晶持有数, 悖论之核持有数, 剩余次数)。"""
        body = abc.bodies[index]
        self._require(body[1:5] == [2, 5, 1, 2] and (not body[6]) and (not body[7]), 'getPossibleOverLimitCountByItem header')
        code = self._code(body)
        self._require(code[17].name == 'setlocal_3' and code[18].name == 'findproperty' and (abc.mn_name(code[18].args[0]) == 'getRestOverLimitStep'), 'count anchor')
        m_items = self.mn_at(abc, body, 14, 'callproperty', 'getItemNumber')
        m_rarity = pool.find('get_rarity', 7)
        m_step = pool.find('overLimitStep', 7)
        a, b, c = PARADOX_CORE
        block = [('getlocal_0',), ('callproperty', m_rarity, 0), ('convert_i',), ('pushbyte', RARITY), ('ifne', 'DONE'), ('getlocal_0',), ('getproperty', m_step), ('convert_i',), ('pushbyte', RETAIL_STEPS), ('iflt', 'DONE'), ('getlocal_1',), ('pushshort', a), ('pushshort', b), ('multiply',), ('pushshort', c), ('add',), ('convert_i',), ('callproperty', m_items, 1), ('convert_i',), ('setlocal', 5), ('getlocal', 5), ('getlocal_3',), ('ifnlt', 'DONE'), ('getlocal', 5), ('setlocal_3',), ('label', 'DONE')]
        old = body[5]
        new, exc, _merged, n = self.splice_with_exits(body, 18, block, {})
        self._require(self.asm.unsplice(new, 18, n) == old, 'inverse splice differs')
        body[1:5] = [3, 6, 1, 2]
        body[5], body[6] = (new, exc)
        return {'inserted_at': 18, 'block_len': n}

    def _pedestal_apply(self, abc, index, pool, resolver_method):
        """★5 台座两档（bundle.zip 台座图集已追加 _6/_7 帧）：
        超限（第 5 次突破起）→ <color>_6[_half]；突破 8 次、Lv120 且第一张盘全部觉醒 → <color>_7[_half]。"""
        body = abc.bodies[index]
        self._require(body[1:5] == [2, 1, 1, 2] and (not body[6]) and (not body[7]), 'pedestal getter header')
        code = self._code(body)
        self._require([c.name for c in code] == ['getlocal_0', 'pushscope', 'getlex', 'getlocal_0', 'callproperty', 'coerce', 'returnvalue'], 'pedestal getter shape')
        self._require(abc.mn_name(code[4].args[0]) == resolver_method, 'resolver anchor')
        m_rarity = pool.find('get_rarity', 7)
        m_step = pool.find('overLimitStep', 7)
        s_step = pool.string('overLimitStep')
        m_split = pool.find('http://adobe.com/AS3/2006/builtin::split', 7)
        m_join = pool.find('http://adobe.com/AS3/2006/builtin::join', 7)
        m_level = pool.find('get_level', 7)
        m_awaked = pool.find('hasAwakedAllManaNodeOfManaBoard', 7)
        src = [('getlocal_0',), ('pushscope',), ('getlex', code[2].args[0]), ('getlocal_0',), ('callproperty', code[4].args[0], 1), ('coerce', code[5].args[0]), ('setlocal_1',), ('getlocal_0',), ('callproperty', m_rarity, 0), ('convert_i',), ('pushbyte', RARITY), ('ifne', 'RET'), ('pushstring', s_step), ('getlocal_0',), ('in',), ('iffalse', 'RET'), ('getlocal_0',), ('getproperty', m_step), ('convert_i',), ('pushbyte', RETAIL_STEPS), ('ifle', 'RET'), ('pushbyte', RARITY + 1), ('setlocal_2',), ('getlocal_0',), ('getproperty', m_step), ('convert_i',), ('pushbyte', EXT_STEPS), ('iflt', 'SWAP'), ('getlocal_0',), ('callproperty', m_level, 0), ('convert_i',), ('pushbyte', EXT_LEVEL), ('iflt', 'SWAP'), ('getlocal_0',), ('pushbyte', 1), ('callproperty', m_awaked, 1), ('iffalse', 'SWAP'), ('pushbyte', RARITY + 2), ('setlocal_2',), ('label', 'SWAP'), ('getlocal_1',), ('pushbyte', RARITY), ('convert_s',), ('callproperty', m_split, 1), ('getlocal_2',), ('convert_s',), ('callproperty', m_join, 1), ('coerce', code[5].args[0]), ('setlocal_1',), ('label', 'RET'), ('getlocal_1',), ('returnvalue',)]
        new, _ = self.asm.encode(self.asm.assemble(src))
        body[1:5] = [3, 3, 1, 2]
        body[5] = new
        return {'replaced': 'whole body', 'new_len': len(new)}

    def o6_apply(self, abc, index, pool):
        return self._pedestal_apply(abc, index, pool, 'resolveFull')

    def o7_apply(self, abc, index, pool):
        return self._pedestal_apply(abc, index, pool, 'resolveHalf')

    def o8_apply(self, abc, index, pool):
        body = abc.bodies[index]
        self._require(body[1:5] == [3, 4, 1, 2] and (not body[6]) and (not body[7]), 'getPedestalImagePath header')
        code = self.asm.decode(body[5])
        self._require(code[19].name == 'setlocal_3' and code[20].name == 'getlocal_1' and (code[21].name == 'lookupswitch'), 'pedestal switch anchor')
        m_gcl = code[17].args[0]
        self._require(abc.mn_name(m_gcl).endswith('GeneralCharacterLogic'), 'GeneralCharacterLogic coerce')
        run = abc.bodies[self.bodies.resolve(abc, 'PixelArtCharacter/run')]
        m_player = self.mn_at(abc, run, 10, 'initproperty', 'player')
        m_id = pool.find('id', 7)
        m_has = pool.find('hasOwnedCharacter', 7)
        m_get = pool.find('getOwnedCharacter', 7)
        block = [('getlocal_0',), ('getproperty', m_player), ('setlocal', 4), ('getlocal', 4), ('iffalse', 'CONT'), ('getlocal', 4), ('getlocal_3',), ('getproperty', m_id), ('callproperty', m_has, 1), ('iffalse', 'CONT'), ('getlocal', 4), ('getlocal_3',), ('getproperty', m_id), ('callproperty', m_get, 1), ('coerce', m_gcl), ('setlocal_3',), ('label', 'CONT')]
        old = body[5]
        new, exc, _merged, n = self.splice_with_exits(body, 20, block, {})
        self._require(self.asm.unsplice(new, 20, n) == old, 'inverse splice differs')
        body[1:5] = [3, 5, 1, 2]
        body[5], body[6] = (new, exc)
        return {'inserted_at': 20, 'block_len': n}

    def o9_apply(self, abc, index, pool):
        body = abc.bodies[index]
        self._require(body[1:5] == [2, 3, 1, 2] and (not body[6]) and (not body[7]), 'OverLimitWindow.getOverLimitState header')
        code = self.asm.decode(body[5])
        self._require(code[13].name == 'setlocal_2' and code[14].name == 'findproperty', 'item list anchor')
        m_player = self.mn_at(abc, body, 3, 'getproperty', 'player')
        m_array = self.mn_at(abc, body, 11, 'coerce', 'Array')
        m_target = self.mn_at(abc, body, 15, 'getproperty', 'targetCharacter')
        m_rarity = pool.find('get_rarity', 7)
        m_step = pool.find('overLimitStep', 7)
        m_items = pool.find('getItemNumber', 7)
        a, b, c = PARADOX_CORE
        block = [('getlocal_0',), ('getproperty', m_target), ('callproperty', m_rarity, 0), ('convert_i',), ('pushbyte', RARITY), ('ifne', 'CONT'), ('getlocal_0',), ('getproperty', m_target), ('getproperty', m_step), ('convert_i',), ('pushbyte', RETAIL_STEPS), ('iflt', 'CONT'), ('getlocal_0',), ('getproperty', m_target), ('callproperty', pool.find('get_maxOverLimitStep', 7), 0), ('convert_i',), ('pushbyte', RETAIL_STEPS), ('ifle', 'CONT'), ('getlocal_0',), ('getproperty', m_player), ('pushshort', a), ('pushshort', b), ('multiply',), ('pushshort', c), ('add',), ('convert_i',), ('callproperty', m_items, 1), ('convert_i',), ('pushbyte', 0), ('ifgt', 'CONT'), ('newarray', 0), ('coerce', m_array), ('setlocal_2',), ('label', 'CONT')]
        old = body[5]
        new, exc, _merged, n = self.splice_with_exits(body, 14, block, {})
        self._require(self.asm.unsplice(new, 14, n) == old, 'inverse splice differs')
        body[1:5] = [4, 3, 1, 2]
        body[5], body[6] = (new, exc)
        return {'inserted_at': 14, 'block_len': n}

    def _paradox_slot_block(self, m_target, m_rarity, m_step, m_push, get_list, m_max):
        a, b, c = PARADOX_CORE
        return [('getlocal_0',), ('getproperty', m_target), ('callproperty', m_rarity, 0), ('convert_i',), ('pushbyte', RARITY), ('ifne', 'CONT'), ('getlocal_0',), ('getproperty', m_target), ('getproperty', m_step), ('convert_i',), ('pushbyte', RETAIL_STEPS), ('iflt', 'CONT'), ('getlocal_0',), ('getproperty', m_target), ('callproperty', m_max, 0), ('convert_i',), ('pushbyte', RETAIL_STEPS), ('ifle', 'CONT'), get_list, ('pushshort', a), ('pushshort', b), ('multiply',), ('pushshort', c), ('add',), ('convert_i',), ('callpropvoid', m_push, 1), ('label', 'CONT')]

    def _push_mn(self, abc):
        donor = abc.bodies[self.bodies.resolve(abc, 'OwnedOverLimitLogic/getOverLimitState')]
        code = self.asm.decode(donor[5])
        for ins in code:
            if ins.name == 'callpropvoid' and abc.mn_name(ins.args[0]).endswith('::push'):
                return ins.args[0]
        raise self.Refused('push multiname donor')

    def _o10_like(self, abc, index, pool, at, local, header_in, header_out, what):
        body = abc.bodies[index]
        self._require(body[1:5] == header_in and (not body[6]) and (not body[7]), f'{what} header')
        code = self.asm.decode(body[5])
        self._require(code[at - 4].name == 'callproperty' and abc.mn_name(code[at - 4].args[0]) == 'getAwakingCrystalToOverLimit' and (code[at - 1].name in ('setlocal', 'setlocal_2')), f'{what} crystal list anchor')
        m_target = self.mn_at(abc, body, at - 5, 'getproperty', 'targetCharacter')
        block = self._paradox_slot_block(m_target, pool.find('get_rarity', 7), pool.find('overLimitStep', 7), self._push_mn(abc), local, pool.find('get_maxOverLimitStep', 7))
        old = body[5]
        new, exc, _merged, n = self.splice_with_exits(body, at, block, {})
        self._require(self.asm.unsplice(new, at, n) == old, 'inverse splice differs')
        body[1:5] = header_out
        body[5], body[6] = (new, exc)
        return {'inserted_at': at, 'block_len': n}

    def o10_apply(self, abc, index, pool):
        """突破窗口按钮：超限模式在超限结晶后追加悖论之核格（点按 = 道具详情）。"""
        return self._o10_like(abc, index, pool, 88, ('getlocal', 4), [11, 12, 1, 2], [11, 12, 1, 2], 'run')

    def o11_apply(self, abc, index, pool):
        """突破窗口道具栏：超限模式显示两格（超限结晶 + 悖论之核，各自持有数，0 个灰掉）。"""
        return self._o10_like(abc, index, pool, 19, ('getlocal_2',), [10, 7, 1, 2], [10, 7, 1, 2], 'getStatusInformation')

    def o12_apply(self, abc, index, pool):
        """超限模式确认框：「确定要消耗 1 个超限结晶＋悖论之核吗？」——itemName 后接「＋」+ 悖论之核道具名（取自道具表）。"""
        body = abc.bodies[index]
        self._require(body[1:5] == [6, 2, 1, 2] and (not body[6]) and (not body[7]), 'getDescription header')
        code = self.asm.decode(body[5])
        self._require(code[10].name == 'coerce' and code[11].name == 'pushstring' and (abc.strings[code[11].args[0]] == b'value'), 'itemName anchor')
        m_char = pool.find('character', 7)
        m_glob = pool.find('globalLogic', 7)
        m_getitem = pool.find('getItem', 7)
        m_name = self.mn_at(abc, body, 9, 'callproperty', 'get_name')
        m_string = code[10].args[0]
        a, b, c = PARADOX_CORE
        block = [('getlocal_0',), ('getproperty', m_char), ('callproperty', pool.find('get_rarity', 7), 0), ('convert_i',), ('pushbyte', RARITY), ('ifne', 'CONT'), ('getlocal_0',), ('getproperty', m_char), ('getproperty', pool.find('overLimitStep', 7)), ('convert_i',), ('pushbyte', RETAIL_STEPS), ('iflt', 'CONT'), ('getlocal_0',), ('getproperty', m_char), ('callproperty', pool.find('get_maxOverLimitStep', 7), 0), ('convert_i',), ('pushbyte', RETAIL_STEPS), ('ifle', 'CONT'), ('pushstring', pool.string(FULLWIDTH_PLUS)), ('add',), ('findproperty', m_glob), ('getproperty', m_glob), ('pushshort', a), ('pushshort', b), ('multiply',), ('pushshort', c), ('add',), ('convert_i',), ('callproperty', m_getitem, 1), ('callproperty', m_name, 0), ('add',), ('coerce', m_string), ('label', 'CONT')]
        old = body[5]
        new, exc, _merged, n = self.splice_with_exits(body, 11, block, {})
        self._require(self.asm.unsplice(new, 11, n) == old, 'inverse splice differs')
        body[1:5] = [9, 2, 1, 2]
        body[5], body[6] = (new, exc)
        return {'inserted_at': 11, 'block_len': n}

def apply(patch, abc, pool, support):
    """Apply one O1-O12 port to an ABC and return its narrow change receipt.

    ``patch`` is an ID or a descriptor from PATCHES. ``pool`` must prohibit
    appends. ``support`` exposes the shared core API described above. On any
    mismatch the target body is restored and the exception propagates.
    """
    patch_id = patch if isinstance(patch, str) else patch["id"]
    matches = [item for item in PATCHES if item["id"] == patch_id]
    if len(matches) != 1:
        raise ValueError(f"Unknown overlimit patch: {patch_id!r}")
    definition = matches[0]
    if getattr(pool, "allow_append", True):
        raise support.Refused("Overlimit main-ABC pool must forbid appends")
    index = support.bodies.resolve(abc, definition["label"])
    body = abc.bodies[index]
    before = hashlib.sha256(body[5]).hexdigest()
    if before == definition["after"]:
        return {"id": patch_id, "label": definition["label"], "body": index,
                "status": "already_present", "sha256": before}
    if before != definition["before"]:
        raise support.Refused(f"{patch_id}: unknown input body {before}")
    saved = copy.deepcopy(body)
    pool_lengths = (len(abc.strings), len(abc.multinames))
    try:
        details = getattr(_Port(support), definition["apply"])(abc, index, pool)
        after = hashlib.sha256(body[5]).hexdigest()
        if after != definition["after"]:
            raise support.Refused(f"{patch_id}: output body differs: {after}")
        if pool_lengths != (len(abc.strings), len(abc.multinames)):
            raise support.Refused(f"{patch_id}: constant pool changed")
        validation = support.check_body(abc, body)
    except Exception:
        abc.bodies[index] = saved
        raise
    return {"id": patch_id, "label": definition["label"], "body": index,
            "status": "applied", "before": before, "after": after,
            "header_before": saved[1:5], "header_after": body[1:5],
            "details": details, "validation": validation, "pool_added": []}
