'use strict'
// Offline reward discovery only. No runtime, player database, or resource writes.
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm')
const crypto = require('node:crypto'), cp = require('node:child_process')
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex')
const slash = value => value.replaceAll('\\', '/')
function physical(target) {
  target = path.resolve(target)
  if (fs.existsSync(target)) return fs.realpathSync.native(target)
  return path.join(physical(path.dirname(target)), path.basename(target))
}
function assertOutput(output, repo, source) {
  const resolved = slash(physical(output)).toLowerCase()
  if (resolved.split('/').includes('.cdn') || slash(path.resolve(output)).toLowerCase().split('/').includes('.cdn')) throw Error('output under .cdn is forbidden')
  for (const protectedRoot of [source, path.join(repo, '.cdn')]) {
    const root = slash(physical(protectedRoot)).toLowerCase()
    if (resolved === root || resolved.startsWith(root + '/')) throw Error('output under protected source/CDN is forbidden')
  }
  return physical(output)
}
function reader(repo) {
  const sourceInputs = {}, rawCache = new Map(), jsonCache = new Map()
  const read = relative => {
    const absolute = path.resolve(repo, relative), normalized = slash(path.relative(repo, absolute))
    if (normalized.startsWith('../') || path.isAbsolute(normalized)) throw Error('read outside checkout: ' + relative)
    if(rawCache.has(normalized))return rawCache.get(normalized)
    const raw = fs.readFileSync(absolute)
    sourceInputs[normalized] = sha(raw)
    rawCache.set(normalized,raw)
    return raw
  }
  return { read, json: relative => {if(!jsonCache.has(relative))jsonCache.set(relative,JSON.parse(read(relative)));return jsonCache.get(relative)}, sourceInputs }
}
function pureLoader(repo, io) {
  const ts = require(require.resolve('typescript', { paths: [repo] })), cache = new Map()
  const allowed = new Set(['src/lib/assets.ts', 'src/lib/content-master.ts', 'src/lib/content-shop-rules.ts',
    'src/lib/content-quest-rules.ts', 'src/lib/abyss-modes.ts', 'src/lib/boss/boss-tables.ts',
    'src/lib/equipment-awakening-rules.ts', 'src/lib/quest/finish/rogue-drop-schedule.ts',
    'src/lib/pass-card.ts', 'src/lib/mission/rewards.ts', 'src/lib/mission/awake-master-assets.ts',
    'src/lib/raid-event-config.ts', 'src/multi/rescue-fragment-reward.ts', 'src/multi/five-boss/rewards.ts',
    'src/lib/types.ts'])
  function evaluate(relative, code, globals = {}) {
    const module = { exports: {} }, filename = path.join(repo, relative)
    const customRequire = spec => {
      if (spec === 'path') return { join: path.join }
      if (spec === 'fs') return { readFileSync: (absolute, encoding) => {
        const raw = io.read(path.relative(repo, absolute)); return encoding ? raw.toString(encoding) : raw
      } }
      if (!spec.startsWith('.')) throw Error('non-pure import forbidden: ' + spec)
      let next = slash(path.relative(repo, path.resolve(path.dirname(filename), spec)))
      if (!path.extname(next)) next += '.ts'
      return load(next)
    }
    const js = ts.transpileModule(code, { compilerOptions: { target: ts.ScriptTarget.ES2020,
      module: ts.ModuleKind.CommonJS, esModuleInterop: true } }).outputText
    vm.runInNewContext(js, { module, exports: module.exports, require: customRequire,
      __dirname: path.dirname(filename), __filename: filename, ...globals }, { filename, timeout: 10000 })
    return module.exports
  }
  function load(relative) {
    if (cache.has(relative)) return cache.get(relative)
    if (relative.endsWith('.json') && relative.startsWith('assets/')) {
      const result = io.json(relative); cache.set(relative, result); return result
    }
    if (!allowed.has(relative) && !relative.startsWith('src/lib/types/')) throw Error('non-pure module forbidden: ' + relative)
    const result = evaluate(relative, io.read(relative).toString('utf8')); cache.set(relative, result); return result
  }
  // Explicitly extract only named pure declarations from a stateful consumer.
  // Its imports, top-level initializers and database functions are never evaluated.
  function declarations(relative, names, globals) {
    const code = io.read(relative).toString('utf8'), ast = ts.createSourceFile(relative, code, ts.ScriptTarget.Latest, true)
    const wanted = new Set(names), found = new Set(), parts = []
    for (const statement of ast.statements) {
      const name = statement.name?.text ?? statement.declarationList?.declarations?.[0]?.name?.text
      if (wanted.has(name)) { parts.push(statement.getText(ast)); found.add(name) }
    }
    if (found.size !== wanted.size) throw Error('pure declaration missing: ' + [...wanted].filter(n => !found.has(n)))
    return evaluate(relative, parts.join('\n') + '\nmodule.exports = {' + names.join(',') + '}', globals)
  }
  return { load, declarations }
}
function nativeNames(exporter, source) {
  const program = `import sys,importlib.util,pathlib,json\nsys.dont_write_bytecode=True\ns=importlib.util.spec_from_file_location('discovery_native',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\nkeys=['master/character/character_text.orderedmap','master/item/item.orderedmap','master/item/equipment.orderedmap','master/quest/event/raid_event.orderedmap','master/quest/event/world_story_event.orderedmap','master/quest/event/story_event_single_quest.orderedmap','master/quest/event/daily_exp_mana_event_quest.orderedmap','master/mission/collect_item_event_mission.orderedmap','master/reward/event/collect_item_event.orderedmap','master/shop/event_item_shop.orderedmap']\nd,source=m.resolve(pathlib.Path(sys.argv[2]),keys)\nprint(json.dumps({'source':source,'tables':{k:m.nested_rows(raw,k,2 if k in keys[5:7] else 1) for k,(raw,r) in d.items()},'resources':[dict(logicalPath=k,member=m.member(k),**r) for k,(raw,r) in d.items()]}))`
  return JSON.parse(cp.execFileSync('python', ['-B', '-c', program, exporter, source], { encoding: 'utf8', maxBuffer: 20 * 1024 * 1024 }))
}
function build(options) {
  const repo = path.resolve(options.repo), source = path.resolve(options.source)
  assertOutput(options.output, repo, source)
  const io = reader(repo), loader = pureLoader(repo, io), catalog = io.json('assets/content_catalog.json')
  const presentation = io.json('assets/content_presentation.json'), manifest = io.read('assets/asset-patch/manifest.json')
  if (sha(manifest) !== presentation.source.manifestSha256) throw Error('presentation does not match current manifest')
  if (fs.readFileSync(path.join(source, 'assets/asset-patch/manifest.json')).compare(manifest)) throw Error('resource source manifest differs')
  const native = nativeNames(options.exporter, source)
  const tables = native.tables, assets = loader.load('src/lib/assets.ts'), rewards = loader.load('src/lib/mission/rewards.ts')
  const pass = loader.load('src/lib/pass-card.ts'), rescue = loader.load('src/multi/rescue-fragment-reward.ts')
  const types = loader.load('src/lib/types.ts'), raid = loader.load('src/lib/raid-event-config.ts')
  const raidOverall = loader.declarations('src/lib/raidEventGlobal.ts', ['RaidEventResponseRewardKind',
    'BATTLE_BANQUET_TOTAL_REWARDS','getBattleBanquetRewardsBetween','originalInteger','getRaidEventOverallRewardsBetween'],
    { nativeOverallRewards: io.json('assets/raid_event_overall_reward.json'), isSupportedRaidEventId: raid.isSupportedRaidEventId })
  const rows = {}, catalogRows = new Map(catalog.rows.map(row => [row.key, row])), gaps = {}
  function note(row, message) { if (!row.notes.includes(message)) row.notes.push(message) }
  function evidence(row, value) {
    const serialized = JSON.stringify(value)
    if (!row._evidence.has(serialized)) { row._evidence.add(serialized); row.evidence.push(value) }
  }
  function gap(key, message) { if (!gaps[key]) gaps[key] = []; if (!gaps[key].includes(message)) gaps[key].push(message) }
  function nameFor(kind, id) {
    if(kind==='currency')return id===3?{name:'星导石',aliases:['免费星导石','星石']}:{name:'玛纳',aliases:['法力']}
    if(kind==='experience')return {name:'经验池',aliases:['经验值','储存经验']}
    const logical = kind === 'character' ? 'master/character/character_text.orderedmap'
      : kind === 'equipment' ? 'master/item/equipment.orderedmap' : 'master/item/item.orderedmap'
    const fields = tables[logical]?.[String(id)]?.[0]
    if (!fields) return { name: `${kind === 'character' ? '角色' : kind === 'equipment' ? '装备' : '道具'} #${id}`, aliases: [] }
    const name = fields[kind === 'character' ? 0 : kind === 'equipment' ? 1 : 2]
    const title = kind === 'character' ? fields[3] : null
    return { name: title && title !== '(None)' ? `${name}（${title}）` : name, aliases: title && title !== '(None)' ? [name,title] : [] }
  }
  function add(key, kind, id, relation, origin) {
    const row = rows[key]
    if (!row || !['character','equipment','item','currency','experience'].includes(kind) || !Number.isSafeInteger(Number(id)) || Number(id) <= 0) return
    id = Number(id)
    const named = nameFor(kind, id)
    const token = `${kind}:${id}:${relation}`
    if (!row._relations.has(token)) {
      row._relations.add(token)
      if (kind === 'character') row.characters.push({ id, ...named, relation: relation === 'exchange' ? 'exchange' : 'reward' })
      else row.rewards.push({ kind, id, ...named, relation })
    }
    evidence(row, { ...origin, entity: { kind, id }, relation })
  }
  const normal = (key, reward, relation, origin) => {
    const kind = { 0: 'item', 1: 'equipment', 2: 'character' }[reward?.type]
    if (kind) add(key, kind, reward.id, relation, origin)
    else if(reward&&Number(reward.count)>0&&[3,4,5].includes(reward.type))add(key,reward.type===5?'experience':'currency',reward.type,relation,{...origin,identity:'src/lib/types/rewards.ts#RewardType',rewardType:reward.type})
  }
  const mission = (key, reward, relation, origin) => {
    const kind = { 1: 'item', 2: 'equipment', 4: 'character' }[reward?.kind]
    if (kind) add(key, kind, reward[{ item: 'itemId', equipment: 'equipmentId', character: 'characterId' }[kind]], relation, origin)
    else if(Number(reward?.amount)>0&&[0,3,5].includes(reward.kind))normal(key,{type:{0:3,3:4,5:5}[reward.kind],count:reward.amount},relation,{...origin,consumer:'src/lib/mission/grants.ts#MissionRewardGranter.grant',missionRewardKind:reward.kind})
  }
  for (const [key, parent] of Object.entries(presentation.rows)) {
    if (parent.type === 'gacha') continue
    rows[key] = { characters: [], rewards: [], notes: ['奖励关联仅表示已核实的配置来源；开放状态、概率、首次条件、个人资格及领取权益仍以原有玩法规则为准。'],
      status: 'verified', evidence: [], _relations: new Set(), _evidence: new Set() }
    if (!catalogRows.has(key)) gap(key, '展示父项缺少目录定义')
  }
  const elementMap = io.json('assets/reward_element_map.json'), enemy = [3,0,1,2,5,4]
  const questCounts = {}
  for (const [questKey, key] of Object.entries(catalog.questMap)) {
    if (!rows[key]) continue
    const [category, questId] = questKey.split(':').map(Number), quest = assets.getQuestFromCategorySync(category, questId)
    if (!quest) { gap(key, '运行关卡不存在：' + questKey); continue }
    if(quest.eventId!==undefined && quest.eventId!==Number(key.split(':')[1])){gap(key,'目录与运行活动外键不一致：'+questKey);continue}
    questCounts[key] = (questCounts[key] ?? 0) + 1
    const origin = { source: 'assets/content_catalog.json', field: `questMap.${questKey}`, consumer: 'src/lib/assets.ts#getQuestFromCategorySync' }
    normal(key, quest.clearReward, 'firstClear', { ...origin, field: origin.field + ' → clearReward' })
    normal(key, quest.sPlusReward, 'firstClear', { ...origin, field: origin.field + ' → sPlusReward', condition: '首次SS' })
    const nativeRule=io.json('assets/content_history_quest_rules.json').quests[questKey]
    if(nativeRule?.kind!=='Story') {
      normal(key,{type:4,count:quest.manaReward},'drop',{...origin,field:origin.field+' → manaReward',consumer:'src/lib/quest/finish/single-finish-transaction.ts + multi-finish-transaction.ts'})
      normal(key,{type:5,count:quest.poolExpReward},'drop',{...origin,field:origin.field+' → poolExpReward',consumer:'src/lib/quest/finish/single-finish-transaction.ts + multi-finish-transaction.ts'})
    }
    for (const [index, slot] of (nativeRule?.kind==='Story'?[]:quest.scoreRewardGroup ?? []).entries()) {
      const at = { ...origin, field: origin.field + ` → scoreRewardGroup:${quest.scoreRewardGroupId}[${index}]`, consumer: 'src/lib/quest.ts#givePlayerScoreRewardsSync' }
      if (slot.type === 1 && Number(slot.rarity) > 0) {
        const rare = assets.getRareScoreRewardGroup(slot.id)
        if (!rare) gap(key, '缺少运行稀有奖励组：' + slot.id)
        for (const entry of rare ?? []) normal(key, entry, 'drop', { ...at, rareGroupId: slot.id, condition: '概率掉落；稀有组内部当前为等概率选择' })
      } else if (slot.type === 0 && Number(slot.count) > 0) {
        if (slot.reward_type === 0) add(key, 'item', slot.id, 'drop', at)
        else if([4,5].includes(slot.reward_type))normal(key,{type:slot.reward_type,count:slot.count},'drop',at)
        else if ([6,7].includes(slot.reward_type)) {
          const id = Number(elementMap[slot.reward_type === 6 ? '1' : '2']?.[String(slot.id)]?.[String(enemy[quest.element ?? 0] ?? 3)]?.[0]?.[0])
          if (id) add(key, 'item', id, 'drop', { ...at, element: quest.element, fieldMap: 'assets/reward_element_map.json' })
          else gap(key, '元素/以太奖励解析缺口：' + questKey)
        }
        // The actual common-score consumer does not grant equipment/characters.
      }
    }
    const rescueReward = rescue.getRescueFragmentReward(category, questId)
    normal(key, rescueReward, 'drop', { ...origin, consumer: 'src/multi/rescue-fragment-reward.ts#getRescueFragmentReward', condition: '成功救援结算，仅支持配置内多人关卡' })
  }
  const missionFiles = { 0:'active',1:'regular',2:'daily',3:'event',4:'collect_item',6:'pass_daily',7:'pass_week',8:'pass_event' }
  function addMission(key, category, id, origin) {
    const filename = 'assets/mission_' + missionFiles[category] + '_reward.json', data = io.json(filename)
    if (!data[String(id)]) { gap(key, '任务缺少奖励表：' + category + ':' + id); return }
    for (const stage of Object.keys(data[String(id)])) {
      const values = category === 0 ? rewards.getActiveMissionRewards(id, Number(stage))
        : rewards.getCategoryMissionRewardStageDefinition(category,id,Number(stage))?.rewards ?? []
      for (const reward of values) mission(key, reward, category >= 6 ? 'pass' : 'mission',
        { ...origin, rewardSource: filename, missionKey: category + ':' + id, stage: Number(stage), consumer: 'src/lib/mission/rewards.ts' })
    }
  }
  for (const [missionKey, key] of Object.entries(catalog.missionMap)) if (rows[key]) {
    const [category, id] = missionKey.split(':').map(Number)
    addMission(key,category,id,{ source:'assets/content_catalog.json',field:'missionMap.' + missionKey })
  }
  // Category-3 task progress reads this exact pattern→quest mapping. Only
  // narrowly scoped definitions whose mapped quests resolve to one parent
  // become event associations; general/all-content tasks are not copied out.
  const eventMissions=io.json('assets/mission_event.json'),eventQuestMap=io.json('assets/mission_event_quest_map.json')
  for(const [missionId,values]of Object.entries(eventMissions)) {
    const definition=values[0],mapping=eventQuestMap[definition?.[0]]
    if(!mapping||!definition[7]||definition[7]==='(None)'||!Array.isArray(mapping.categories)||!Array.isArray(mapping.questIds))continue
    const owners=new Set(),matched=[]
    for(const questId of mapping.questIds)for(const category of mapping.categories) {
      const questKey=category+':'+questId,parent=catalog.questMap[questKey]
      if(parent){owners.add(parent);matched.push(questKey)}
    }
    if(owners.size!==1)continue
    const key=[...owners][0]
    if(!rows[key])continue
    addMission(key,3,Number(missionId),{source:'assets/mission_event_quest_map.json',field:definition[0],definitionSource:'assets/mission_event.json',consumer:'src/lib/mission/computer-event.ts#EventComputer.compute',questKeys:matched,condition:'独立任务的时间、可见性与领取条件仍需满足；并非关卡直接掉落'})
  }
  // Raid's explicit mission accessor is authoritative; do not infer generic event ownership from dates.
  for (const [key, row] of Object.entries(rows)) if (key.startsWith('raid_event:')) {
    const id = Number(key.split(':')[1])
    for (const missionId of raid.getRaidEventMissionIds(id)) addMission(key,3,missionId,{source:'src/lib/raid-event-config.ts',field:'getRaidEventMissionIds'})
    for (const entry of raidOverall.getRaidEventOverallRewardsBetween(id,0,10000)) {
      if (entry.kind === 1) add(key,'item',entry.kind_id,'overall',{source:'src/lib/raidEventGlobal.ts',field:'getRaidEventOverallRewardsBetween', condition:'按全体击杀里程碑；活动7采用自定义获胜配置'})
      else if([3,8,9].includes(entry.kind))normal(key,{type:{3:3,8:4,9:5}[entry.kind],count:entry.number},'overall',{source:'src/lib/raidEventGlobal.ts',field:'getRaidEventOverallRewardsBetween',identity:'RaidEventResponseRewardKind → RewardType'})
    }
    note(row, '全体报酬读取实际发放函数，活动7不采用被运行逻辑替换的原始总报酬行。')
  }
  const eventType = {advent_event:0,story_event:2,challenge_dungeon_event:4,world_story_event:6,collect_item_event:9,carnival_event:10,rush_event:11,score_attack_event:12}
  const shopMap = loader.load('src/lib/content-master.ts').serverEventShopIdMap
  for (const [key, row] of Object.entries(rows)) {
    const [type, rawId] = key.split(':'), id = Number(rawId)
    if (eventType[type] !== undefined) {
      const items = assets.getEventShopItemsSync(eventType[type],id)
      for (const [productId, product] of Object.entries(items ?? {})) {
        const mapping = shopMap[productId]
        if (!mapping || mapping.eventType !== eventType[type] || (mapping.eventId !== id && !(type==='rush_event' && (mapping.eventId === id-10 || (id===700100 && mapping.eventId===700099)))) ) {
          gap(key,'兑换商品缺少精确运行父映射：' + productId); continue
        }
        for (const reward of product.rewards ?? []) {
          const kind = {0:'item',3:'character',4:'equipment'}[reward.type]
          if (kind) add(key,kind,reward.id,'exchange',{source:'src/lib/assets.ts',field:`getEventShopItemsSync(${eventType[type]},${id}).${productId}.rewards`,mappingSource:'src/lib/content-master.ts#serverEventShopIdMap'})
          else if([1,2].includes(reward.type))normal(key,{type:reward.type===1?5:4,count:reward.count},'exchange',{source:'src/lib/assets.ts',field:`getEventShopItemsSync(${eventType[type]},${id}).${productId}.rewards`,identity:'src/lib/types/rewards.ts#ShopItemRewardType'})
        }
      }
    }
    if (type === 'pass_card_event') {
      const events = io.json('assets/pass_card_event.json'), raw = events[String(id)]?.[0]
      if (raw?.[8] && raw?.[9]) row.editionLabel = `活动期 ${raw[8].slice(0,10)} 至 ${raw[9].slice(0,10)}`
      note(row,'原生资料未提供独立期数名称；活动期直接读取pass_card_event[8]/[9]，不把ID或资源代号推断为原版期数。')
      const table = io.json('assets/pass_card_reward.json')
      let count = 0
      for (const [rewardId, data] of Object.entries(table)) if (Number(data[0]?.[0]) === id) {
        const definition = pass.getPassCardRewardDefinition(Number(rewardId)); count++
        if (!definition) { gap(key,'通行证奖励解析失败：' + rewardId); continue }
        for (const track of ['reward1','reward2']) mission(key,definition[track],'pass',{source:'assets/pass_card_reward.json',field:rewardId+'.'+track,eventId:id,consumer:'src/lib/pass-card.ts#getPassCardRewardDefinition',condition:'免费/付费轨道及等级资格按原有规则'})
      }
      if (!count) gap(key,'无通行证等级奖励')
    }
    if (type === 'box_gacha') {
      const box = assets.getBoxGachaSync(id)
      if (!box) gap(key,'运行箱池缺少箱或奖励定义')
      for (const [boxId, entries] of Object.entries(box?.boxes ?? {})) for (const [rewardId, reward] of Object.entries(entries)) {
        if (Number(reward.available) <= 0 || Number(reward.count) <= 0) continue
        const kind = {0:'item',1:'equipment',6:'character'}[reward.type]
        if (kind) add(key,kind,reward.id,'box',{source:'assets/box_reward.json',field:`${id}.${boxId}.${rewardId}`,consumer:'src/lib/assets.ts#getBoxGachaSync → src/lib/gacha.ts#rewardPlayerBoxGachaResultSync'})
        else if([3,4].includes(reward.type))normal(key,{type:reward.type===3?4:5,count:reward.count},'box',{source:'assets/box_reward.json',field:`${id}.${boxId}.${rewardId}`,identity:'src/lib/types/box-gacha.ts#BoxGachaRewardType'})
      }
    }
    if (type.endsWith('exchange_campaign')) {
      row.status='not_applicable'; note(row,'delegated: 角色/装备自选兑换由独立campaign核查片段补齐；本片段不以标题推断奖励。')
    }
    if (type === 'rush_event') {
      const folders = io.json('assets/rush_event_quest_folder.json'), cfg = assets.getRogueEventConfig(id)
      const original = folders[id] ?? (id>=700010 && id<=700019 ? folders[id-10] : undefined)
      for (const [folderId, entries] of Object.entries(original ?? {})) {
        if ([700099,700100].includes(id) && Number(folderId)!==1) continue
        for (const reward of entries) normal(key,reward,'drop',{source:'assets/rush_event_quest_folder.json',field:`${id}.${folderId}`,consumer:'src/lib/assets.ts#getRushEventFolderClearRewards',condition:'整组通关'})
      }
      const questList = Object.entries(catalog.questMap).filter(([,parent])=>parent===key).map(([q])=>q.split(':').map(Number))
      const rounds = questList.map(([category,questId])=>assets.getQuestFromCategorySync(category,questId)?.rushEventRound).filter(Number.isInteger)
      const schedule = loader.load('src/lib/quest/finish/rogue-drop-schedule.ts')
      for (const round of new Set(rounds)) for (const drop of cfg ? schedule.resolveRogueRoundDrops(cfg,round,()=>0) : []) {
        add(key,drop.type,drop.id,'drop',{source:'assets/rogue_event.json + assets/rogue_event_cnmod.json',field:'events.'+id+'.per_round_drops',consumer:'src/lib/quest/finish/rogue-drops.ts',round,condition:'仅适用轮次与槽位；概率条件仍生效'})
      }
      if (Number(cfg?.pool_draws)>0) for (const drop of cfg?.drop_pool ?? []) add(key,drop.type,drop.id,'drop',{source:'assets/rogue_event.json',field:'events.'+id+'.drop_pool',condition:'随机池；队伍元素过滤'})
      for (const reward of cfg?.folder_clear_chance ?? []) if (Number(reward.chance)>0) normal(key,reward,'drop',{source:'assets/rogue_event.json + assets/rogue_event_cnmod.json',field:'events.'+id+'.folder_clear_chance',condition:'整组通关概率追加'})
      for (const reward of cfg?.folder_clear_random ?? []) if (reward.chance===undefined || Number(reward.chance)>0) for (const itemId of reward.pool ?? []) normal(key,{type:reward.type??0,id:itemId},'drop',{source:'assets/rogue_event.json',field:'events.'+id+'.folder_clear_random',condition:'整组通关随机奖励'})
    }
  }
  const mode15=loader.declarations('src/lib/mode15.ts',['MODE15_RUSH_EVENT_ID','MODE15_MULTI_EVENT_ID','MODE15_TOKEN_ID','MODE15_FULL_CLEAR_TOKEN_ID','MODE15_FULL_CLEAR_TICKET_ID','MODE15_DREAM_EMBLEM_ID','MODE15_BOSS_TOKEN_REWARDS','ELEMENT_TIER_1','ELEMENT_TIER_2','ELEMENT_TIER_3','ELEMENT_TIER_4','ETHER_TIER_1','ETHER_TIER_2','ETHER_TIER_3','itemSet','MODE15_SOLO_FIXED_REWARDS'],{})
  for(const [round,entries]of Object.entries(mode15.MODE15_SOLO_FIXED_REWARDS))for(const reward of entries) {
    const key=catalog.questMap[`24:${mode15.MODE15_RUSH_EVENT_ID*1000+Number(round)}`]
    if(key)add(key,'item',reward.id,'drop',{source:'src/lib/mode15.ts',field:'MODE15_SOLO_FIXED_REWARDS.'+round,consumer:'settleMode15BattleSync'})
  }
  for(const [index,stage]of [5,10,15].entries()) {
    const key=catalog.questMap[`7:${mode15.MODE15_MULTI_EVENT_ID*1000+index+1}`]
    if(!key)continue
    add(key,'item',mode15.MODE15_TOKEN_ID,'drop',{source:'src/lib/mode15.ts',field:'MODE15_BOSS_TOKEN_REWARDS.'+stage,consumer:'settleMode15BattleSync'})
    if(stage===15)for(const id of [mode15.MODE15_DREAM_EMBLEM_ID,mode15.MODE15_FULL_CLEAR_TOKEN_ID,mode15.MODE15_FULL_CLEAR_TICKET_ID])add(key,'item',id,'drop',{source:'src/lib/mode15.ts',field:'settleMode15BattleSync.fullClear',condition:'完整连战通关'})
  }
  // Explicit native box foreign keys attach its actual runtime prizes to its event.
  for(const [type,index]of [['raid_event',18],['world_story_event',14]]) {
    const logical=`master/quest/event/${type}.orderedmap`
    for(const [id,values]of Object.entries(tables[logical]??{})) {
      const key=type+':'+id,boxId=Number(values[0]?.[index]),box=Number.isSafeInteger(boxId)?assets.getBoxGachaSync(boxId):null
      if(!rows[key]||!box)continue
      for(const [boxNumber,entries]of Object.entries(box.boxes))for(const [rewardId,reward]of Object.entries(entries)) {
        if(reward.available<=0||reward.count<=0)continue
        const kind={0:'item',1:'equipment',6:'character'}[reward.type]
        if(kind)add(key,kind,reward.id,'box',{source:logical,field:`${id}[0][${index}]`,boxGachaId:boxId,rewardSource:'assets/box_reward.json',rewardField:`${boxId}.${boxNumber}.${rewardId}`,condition:'对应原生奖励箱；箱与活动的开放、抽取资格仍分别判断'})
        else if([3,4].includes(reward.type))normal(key,{type:reward.type===3?4:5,count:reward.count},'box',{source:logical,field:`${id}[0][${index}]`,boxGachaId:boxId,rewardSource:'assets/box_reward.json',rewardField:`${boxId}.${boxNumber}.${rewardId}`,identity:'src/lib/types/box-gacha.ts#BoxGachaRewardType'})
      }
    }
  }
  for (const [file,type,relation] of [['ranking_event_ranking_reward','ranking_event','ranking'],['raid_event_ranking_reward','raid_event','ranking']]) {
    const table=io.json('assets/'+file+'.json')
    for(const [id,tiers] of Object.entries(table.events??{})) for(const tier of tiers) for(const reward of tier.rewards??[]) {
      const kind={0:'item',1:'equipment',6:'character'}[reward.kind]
      if(kind) add(type+':'+id,kind,reward.id,relation,{source:'assets/'+file+'.json',field:'events.'+id,condition:'排名/击杀条件；非关卡掉落'})
      else if([2,3,4].includes(reward.kind))normal(type+':'+id,{type:{2:3,3:4,4:5}[reward.kind],count:reward.number},relation,{source:'assets/'+file+'.json',field:'events.'+id,consumer:'src/lib/ranking-event-rewards.ts'})
    }
  }
  const carnival=io.json('assets/carnival_event_total_score_rewards.json')
  for(const [id,tiers]of Object.entries(carnival))for(const [rewardId,,entries]of tiers)for(const [kind,itemId,count]of entries)if(count>0) {
    const entity={0:'item',1:'equipment',6:'character'}[kind]
    if(entity)add('carnival_event:'+id,entity,itemId,'overall',{source:'assets/carnival_event_total_score_rewards.json',field:id+'.'+rewardId,consumer:'src/lib/quest/finish/carnival-reward-handler.ts',condition:'累计分数里程碑'})
    else if([2,3,4].includes(kind))normal('carnival_event:'+id,{type:{2:3,3:4,4:5}[kind],count},'overall',{source:'assets/carnival_event_total_score_rewards.json',field:id+'.'+rewardId,consumer:'src/lib/quest/finish/carnival-reward-handler.ts'})
  }
  const border=io.json('assets/score_attack_border_reward.json')
  for(const [key,tiers]of Object.entries(border))for(const tier of tiers)for(const reward of tier.rewards??[])if(reward.kind===0&&reward.amount>0)add('score_attack_event:'+tier.eventId,'item',reward.id,'overall',{source:'assets/score_attack_border_reward.json',field:key+'.'+tier.id,consumer:'src/lib/quest/finish/score-attack-handler.ts'})
  // Identity-bind inspected consumers as well as pure evaluated modules.
  for(const file of ['src/lib/quest.ts','src/lib/quest/finish/single-finish-transaction.ts','src/lib/quest/finish/multi-finish-transaction.ts','src/lib/quest/finish/rogue-drops.ts','src/lib/quest/finish/carnival-reward-handler.ts','src/lib/quest/finish/score-attack-handler.ts','src/lib/ranking-event-rewards.ts','src/lib/gacha.ts','src/routes/api/boxGacha.ts','src/routes/api/passCard.ts','src/routes/api/storyQuest.ts','src/routes/api/shop.ts','src/lib/content-economy-operations.ts','src/lib/mission/computer-event.ts','src/lib/mission/grants.ts','tools/build-content-discovery-rewards.cjs'])io.read(file)
  const focusedReview=[]
  const reviewedKeys=['collect_item_event:5','collect_item_event:80003','story_event:202013','story_event:200030','story_event:200022','story_event:200014','story_event:200001','story_event:100002','story_event:200004','daily_exp_mana_event:1']
  for(const key of reviewedKeys) {
    const [type,id]=key.split(':'),mapped=Object.entries(catalog.questMap).filter(([,owner])=>owner===key)
    const logical=`master/quest/event/${type==='story_event'?'story_event_single_quest':'daily_exp_mana_event_quest'}.orderedmap`
    const nativeQuestIds=Object.values(tables[logical]?.[id]??{}).map(values=>Number(values[0]?.[0])).sort((a,b)=>a-b)
    const quests=mapped.map(([quest])=>assets.getQuestFromCategorySync(...quest.split(':').map(Number)))
    const unique=values=>[...new Set(values.filter(v=>v!==undefined))].sort()
    const review={key,title:presentation.rows[key].title,nativeName:presentation.rows[key].nativeName,nativeQuestCount:nativeQuestIds.length,runtimeQuestCount:quests.filter(Boolean).length,questIdsMatch:JSON.stringify(nativeQuestIds)===JSON.stringify(mapped.map(([q])=>Number(q.split(':')[1])).sort((a,b)=>a-b)),questKinds:unique(mapped.map(([q])=>io.json('assets/content_history_quest_rules.json').quests[q]?.kind)),clearRewardTypes:unique(quests.map(q=>q?.clearReward?.type)),ssRewardTypes:unique(quests.map(q=>q?.sPlusReward?.type)),scoreRewardTypes:unique(quests.flatMap(q=>(q?.scoreRewardGroup??[]).map(r=>r.type===0?r.reward_type:'rare'))),baseMana:unique(quests.map(q=>q?.manaReward)),basePoolExp:unique(quests.map(q=>q?.poolExpReward)),baseCharacterExp:unique(quests.map(q=>q?.characterExpReward)),rewardTypesEnum:'src/lib/types/rewards.ts#RewardType',rewardNames:unique(rows[key].rewards.map(r=>r.name))}
    if(type==='collect_item_event') {
      const nativeMissions=Object.entries(tables['master/mission/collect_item_event_mission.orderedmap']).filter(([,values])=>values[0]?.[0]===id)
      const runtimeMissions=Object.entries(io.json('assets/mission_collect_item.json')).filter(([,values])=>values[0]?.[0]===id)
      const nativeShops=Object.entries(tables['master/shop/event_item_shop.orderedmap']).filter(([,values])=>values[0]?.[0]==='4'&&values[0]?.[1]===id)
      const runtimeShopCount=Object.keys(assets.getEventShopItemsSync(9,Number(id))??{}).length
      Object.assign(review,{nativeMissionCount:nativeMissions.length,runtimeMissionCount:runtimeMissions.length,nativeShopProductCount:nativeShops.length,runtimeShopProductCount:runtimeShopCount,parentDefinitionPresent:Boolean(tables['master/reward/event/collect_item_event.orderedmap'][id])})
      if(review.parentDefinitionPresent&&!nativeMissions.length&&!runtimeMissions.length&&!nativeShops.length&&!runtimeShopCount) {
        rows[key].status='not_applicable';note(rows[key],'当前获胜原生表与运行表均为零所属任务、零兑换商品；保留父活动定义，未据此改变开放资格。')
        evidence(rows[key],{source:'master/mission/collect_item_event_mission.orderedmap + master/shop/event_item_shop.orderedmap',field:'mission[0]=eventId; shop[0]=4,shop[1]=eventId',eventId:Number(id),nativeMissionCount:0,runtimeMissionCount:0,nativeShopProductCount:0,runtimeShopProductCount:0})
      }
    }
    focusedReview.push(review)
  }
  for(const [key,row]of Object.entries(rows)) {
    if(gaps[key]?.length){row.status='unavailable';for(const text of gaps[key])note(row,text)}
    if(!row.characters.length&&!row.rewards.length&&row.status==='verified') {
      row.status='unavailable';note(row,'未在已核实路径发现角色、装备、道具关联；不能据此宣称无奖励。')
    }
    if(questCounts[key])evidence(row,{source:'assets/content_catalog.json',field:'questMap',questCount:questCounts[key],consumer:'src/lib/assets.ts#getQuestFromCategorySync'})
    row.publicNotes=[]
    if(row.status==='unavailable')row.publicNotes.push(row.characters.length||row.rewards.length?'已收录可确认的奖励，部分奖励关联资料尚未确认。':'该内容的角色、装备或道具奖励关联尚未确认。')
    if(row.status==='not_applicable'&&key.startsWith('collect_item_event:'))row.publicNotes.push('原生与当前配置均未配置所属任务及兑换商品，保留该历史活动条目。')
    row.characters.sort((a,b)=>a.id-b.id||a.relation.localeCompare(b.relation));row.rewards.sort((a,b)=>a.kind.localeCompare(b.kind)||a.id-b.id||a.relation.localeCompare(b.relation))
    // Characters carry reward/exchange only; merge multiple proven reward channels.
    row.characters=row.characters.filter((value,index,list)=>list.findIndex(other=>other.id===value.id&&other.relation===value.relation)===index)
    delete row._relations;delete row._evidence
  }
  return {schemaVersion:1,source:{manifestSha256:sha(manifest),presentationSha256:io.sourceInputs['assets/content_presentation.json'],catalogSha256:io.sourceInputs['assets/content_catalog.json']},
    sourceInputs:io.sourceInputs,resources:native.resources,rows,focusedReview,
    sourceNotes:[`目录头为历史快照 ${catalog.source.manifestSha256}；索引绑定当前manifest和实际目录文件SHA，运行奖励经当前纯静态消费者核实。`],
    stats:{parents:Object.keys(rows).length,verified:Object.values(rows).filter(r=>r.status==='verified').length,unavailable:Object.values(rows).filter(r=>r.status==='unavailable').length,notApplicable:Object.values(rows).filter(r=>r.status==='not_applicable').length,delegated:36,characters:Object.values(rows).reduce((n,r)=>n+r.characters.length,0),rewards:Object.values(rows).reduce((n,r)=>n+r.rewards.length,0),passParents:Object.keys(rows).filter(k=>k.startsWith('pass_card_event:')).length},
    externalInputs:{exporterSha256:sha(fs.readFileSync(options.exporter))}}
}
if(require.main===module){
  const args={};for(let i=2;i<process.argv.length;i+=2){if(!process.argv[i].startsWith('--')||!process.argv[i+1])throw Error('expected --option value');args[process.argv[i].slice(2)]=process.argv[i+1]}
  for(const key of ['repo','source','exporter','output'])if(!args[key])throw Error('missing --'+key)
  const result=build(args),output=assertOutput(args.output,args.repo,args.source)
  fs.mkdirSync(path.dirname(output),{recursive:true});fs.writeFileSync(output,JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result.stats))
}
module.exports={build,assertOutput,pureLoader,reader}
