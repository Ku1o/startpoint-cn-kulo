(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const list = (value) => Array.isArray(value) ? value : [];
  const str = (value) => value == null ? '' : String(value);
  const node = (tag, text, className) => {
    const el = document.createElement(tag);
    if (text != null) el.textContent = str(text);
    if (className) el.className = className;
    return el;
  };
  const empty = (target, text) => target.appendChild(node('p', text, 'empty'));
  const statusNames = {ready: '素材就绪', pending: '待制作 / 待核对', not_applicable: '不适用', offline_checked: '已离线检查', approved: '已确认', deferred_to_game: '待游戏验证'};
  const categoryNames = {ui: '界面', motion: '动作', audio: '声音', illustration: '立绘', skill: '技能'};
  const badge = (state) => node('span', statusNames[state] || '状态未登记', 'badge ' + (Object.hasOwn(statusNames, state) ? state : 'pending'));
  const data = window.CHARACTER_PREVIEW;
  if (!data || data.schemaVersion !== 1) {
    $('fatalError').hidden = false;
    $('fatalError').textContent = '预览数据未加载或版本不支持。请确认同目录存在 preview-data.js，且定义 schemaVersion 为 1 的 window.CHARACTER_PREVIEW。';
    return;
  }
  const assets = new Map(list(data.assets).map((asset) => [asset.id, asset]));
  const forms = list(data.forms);
  const formNames = new Map(forms.map((form) => [form.id, form.label]));
  // Only relative local asset paths are eligible for browser media loading.
  function assetFor(id, kind) {
    const asset = assets.get(id);
    if (!asset || asset.kind !== kind || typeof asset.path !== 'string') return null;
    if (!asset.path || /^(?:[a-z][a-z\d+.-]*:|[\\/])/i.test(asset.path) || /[\u0000-\u001f]/.test(asset.path)) return null;
    return asset;
  }
  function imageFor(id, label) {
    const asset = assetFor(id, 'image');
    if (!asset) return node('p', '待制作或图片资源未登记', 'empty');
    const img = node('img');
    img.alt = str(label);
    img.loading = 'lazy';
    img.addEventListener('error', () => {
      const message = node('p', '图片加载失败：' + asset.path, 'empty');
      img.replaceWith(message);
    }, {once: true});
    img.src = asset.path;
    return img;
  }
  function option(select, value, label) {
    const item = node('option', label);
    item.value = str(value);
    select.appendChild(item);
  }
  function titleRow(target, title, state) {
    const head = node('div', null, 'card-title');
    head.appendChild(node('h3', title));
    if (state) head.appendChild(badge(state));
    target.appendChild(head);
  }
  const character = data.character || {};
  $('characterName').textContent = str(character.name || '未命名角色');
  $('characterSubtitle').textContent = str(character.subtitle);
  $('characterCode').textContent = character.code ? '角色代号：' + str(character.code) : '角色代号待登记';
  document.title = str(character.name || 'MOD 角色') + ' · 离线预览';
  const computed = data.computed || {};
  const missing = list(computed.missing);
  const summary = [
    [computed.assetCount ?? assets.size, '已登记素材'],
    [computed.inventoryCount ?? list(data.inventory).length, '资源槽位'],
    [computed.coveredCount ?? 0, '已覆盖槽位'],
    [missing.length, '构建检查缺项']
  ];
  summary.forEach(([value, label]) => {
    const stat = node('div', null, 'stat');
    stat.appendChild(node('strong', value)); stat.appendChild(node('span', label)); $('summary').appendChild(stat);
  });
  $('missingSummary').textContent = missing.length ? '存在 ' + missing.length + ' 项构建检查缺项，请到「验收」查看；各栏目还会保留待制作占位。' : '构建检查未列出缺项；实际验收状态请查看「验收」栏目。';
  const inventoryScope = '清单统计范围：' + str(data.inventoryScope || '尚未登记；当前分母仅来自提供的槽位清单，完整性待核验。');
  $('inventoryScopeSummary').textContent = inventoryScope;
  $('inventoryScopeDetail').textContent = inventoryScope;
  $('coverageMeaning').textContent = str(computed.coverageMeaning || '仅核对提供的资源清单与展示映射，不能据此确认原生资源全集已覆盖。');

  forms.forEach((form) => option($('formSelect'), form.id, form.label));
  function renderIllustration() {
    const form = forms.find((entry) => str(entry.id) === $('formSelect').value);
    $('illustration').replaceChildren();
    if (form) $('illustration').appendChild(imageFor(form.illustration, form.label));
    else empty($('illustration'), '尚未登记形态与立绘。');
  }
  $('formSelect').disabled = !forms.length;
  $('formSelect').addEventListener('change', renderIllustration);
  renderIllustration();
  const ui = list(data.ui);
  option($('uiForm'), '*', '全部形态');
  forms.forEach((form) => option($('uiForm'), 'form:' + form.id, form.label));
  if (ui.some((entry) => entry.form == null)) option($('uiForm'), 'shared', '通用 / 无形态');
  option($('uiVariant'), '*', '全部版本');
  [...new Set(ui.map((entry) => str(entry.variant)))].forEach((value) => option($('uiVariant'), 'variant:' + value, value || '未标版本'));
  function renderUI() {
    const entries = ui.filter((entry) => ($('uiForm').value === '*' || (entry.form == null ? 'shared' : 'form:' + entry.form) === $('uiForm').value) && ($('uiVariant').value === '*' || 'variant:' + str(entry.variant) === $('uiVariant').value));
    $('uiGrid').replaceChildren();
    $('uiCount').textContent = '当前显示 ' + entries.length + ' / ' + ui.length + ' 个界面槽位';
    entries.forEach((entry) => {
      const card = node('article', null, 'ui-card');
      titleRow(card, entry.label || entry.id, entry.status || 'pending');
      card.appendChild(node('p', (entry.form == null ? '通用' : (formNames.get(entry.form) || entry.form)) + ' · ' + (entry.variant || '未标版本'), 'note'));
      const stage = node('div', null, 'ui-stage ' + $('uiSize').value + ' ' + $('uiBackground').value);
      if (entry.status === 'not_applicable' && assetFor(entry.asset, 'image')) {
        card.appendChild(node('p', '参考图：本槽位不适用直接图片检查，以下图片仅作辅助对照，不改变该槽位的验收状态。', 'note'));
        stage.appendChild(imageFor(entry.asset, entry.label || entry.id));
      } else if (entry.status === 'not_applicable') empty(stage, '不适用');
      else stage.appendChild(imageFor(entry.asset, entry.label || entry.id));
      card.appendChild(stage);
      if (entry.note) card.appendChild(node('p', entry.note, 'note'));
      const details = node('details');
      details.appendChild(node('summary', '原生资源键 · ' + list(entry.resourceKeys).length));
      const keys = node('ul', null, 'key-list');
      list(entry.resourceKeys).forEach((key) => keys.appendChild(node('li', key)));
      if (!keys.childNodes.length) keys.appendChild(node('li', '尚未登记'));
      details.appendChild(keys); card.appendChild(details); $('uiGrid').appendChild(card);
    });
    if (!entries.length) empty($('uiGrid'), ui.length ? '没有匹配的界面槽位。' : '界面槽位尚未登记，待补齐清单。');
  }
  ['uiForm', 'uiVariant', 'uiSize', 'uiBackground'].forEach((id) => $(id).addEventListener('change', renderUI));
  renderUI();

  function renderMedia(section, targetId) {
    const target = $(targetId);
    const allEntries = list(data.media).filter((entry) => entry.section === section);
    const search = section === 'overview' ? $('mediaSearch').value.trim().toLocaleLowerCase() : '';
    const entries = allEntries.filter((entry) => section !== 'overview' || (($('mediaKind').value === 'all' || entry.kind === $('mediaKind').value) && (str(entry.label) + ' ' + str(entry.caption) + ' ' + str(entry.id)).toLocaleLowerCase().includes(search)));
    target.querySelectorAll?.('audio, video').forEach((media) => media.pause());
    target.replaceChildren();
    if (section === 'overview') $('mediaCount').textContent = '当前显示 ' + entries.length + ' / ' + allEntries.length + ' 项媒体；声音展开后才创建播放器。';
    entries.forEach((entry) => {
      const card = node('article', null, 'media-card');
      titleRow(card, entry.label || entry.id, entry.status || 'pending');
      const asset = assetFor(entry.asset, entry.kind);
      if (entry.status === 'not_applicable') empty(card, '不适用');
      else if (!asset || !['audio', 'video'].includes(entry.kind)) empty(card, '待制作或媒体资源未登记。');
      else {
        function createPlayer(container) {
          const media = node(entry.kind); media.controls = true; media.preload = 'none';
          if (entry.kind === 'video') media.playsInline = true;
          media.setAttribute('aria-label', str(entry.label || entry.id));
          media.addEventListener('error', () => { container.appendChild(node('p', '媒体加载失败或浏览器不支持此格式：' + asset.path, 'error')); }, {once: true});
          media.src = asset.path; container.appendChild(media); return media;
        }
        if (entry.kind === 'audio') {
          const details = node('details'); details.appendChild(node('summary', '展开试听'));
          let player = null;
          details.addEventListener('toggle', () => { if (details.open && !player) player = createPlayer(details); else if (!details.open && player) player.pause(); });
          card.appendChild(details);
        } else createPlayer(card);
      }
      if (entry.caption) card.appendChild(node('p', entry.caption, 'note'));
      target.appendChild(card);
    });
    if (!entries.length) empty(target, allEntries.length ? '没有匹配的媒体。' : section === 'skill' ? '技能视频待制作 / 待登记。' : '尚未登记声音或视频。');
  }
  renderMedia('overview', 'overviewMedia'); renderMedia('actions', 'actionsMedia'); renderMedia('skill', 'skillMedia');
  $('mediaSearch').addEventListener('input', () => renderMedia('overview', 'overviewMedia'));
  $('mediaKind').addEventListener('change', () => renderMedia('overview', 'overviewMedia'));
  function renderTextCards(entries, targetId, placeholder) {
    entries.forEach((entry) => { const card = node('article', null, 'rule'); card.appendChild(node('h3', entry.title)); card.appendChild(node('p', entry.text)); $(targetId).appendChild(card); });
    if (!entries.length) empty($(targetId), placeholder);
  }
  renderTextCards(list(data.mechanics), 'mechanicsGrid', '技能与数值说明待补齐。');
  renderTextCards(list(data.extras), 'extrasGrid', '暂无补充说明。');
  list(data.checks).forEach((entry) => {
    const card = node('article', null, 'check'); titleRow(card, entry.label || entry.id, entry.state || 'pending');
    card.appendChild(node('p', entry.note || '尚无补充记录。', 'note')); $('checks').appendChild(card);
  });
  if (!list(data.checks).length) empty($('checks'), '验收项目尚未登记，不能据此认定已完成。');
  missing.forEach((entry) => { const item = node('div', null, 'missing-item'); item.appendChild(node('strong', entry.id)); item.appendChild(node('p', entry.reason, 'note')); $('missingList').appendChild(item); });
  if (!missing.length) empty($('missingList'), '构建检查未列出缺项。请继续核对素材占位与游戏验收状态。');
  list(data.inventory).forEach((entry) => {
    const row = node('tr'); row.appendChild(node('td', entry.key)); row.appendChild(node('td', categoryNames[entry.category] || entry.category)); row.appendChild(node('td', entry.entry == null ? '未关联展示条目' : entry.entry));
    const cell = node('td'); cell.appendChild(badge(entry.status || 'pending')); if (entry.note) cell.appendChild(node('p', entry.note)); row.appendChild(cell); $('inventory').appendChild(row);
  });
  if (!list(data.inventory).length) { const row = node('tr'); const cell = node('td', '槽位清单尚未登记。'); cell.colSpan = 4; row.appendChild(cell); $('inventory').appendChild(row); }

  const motions = list(data.motions);
  const canvas = $('motionCanvas');
  const ctx = canvas.getContext('2d');
  const images = new Map();
  let motion = null, frames = [], starts = [], totalTicks = 0, playhead = 0, playing = false, lastClock = null;
  let motionValid = false, motionPlaybackReady = false, requiredFrameIds = [];
  function pause() { playing = false; lastClock = null; $('motionPlay').textContent = '播放'; }
  function frameIndex() {
    let index = starts.length - 1;
    while (index > 0 && starts[index] > Math.floor(playhead)) index--;
    return Math.max(0, index);
  }
  function currentImage(asset) {
    if (images.has(asset.id)) return images.get(asset.id);
    const img = new Image(); const record = {img, ready: false, failed: false}; images.set(asset.id, record);
    img.onload = () => { record.ready = true; updateLoadStatus(); draw(); };
    img.onerror = () => { record.failed = true; updateLoadStatus(); draw(); };
    img.src = asset.path; return record;
  }
  function updateLoadStatus() {
    if (!motionValid) { motionPlaybackReady = false; $('motionPlay').disabled = true; $('motionLoadStatus').textContent = ''; return; }
    let loaded = 0;
    const failures = [];
    requiredFrameIds.forEach((id) => {
      const asset = assetFor(id, 'image');
      const record = asset && images.get(asset.id);
      if (!asset) failures.push('未登记图片：' + str(id));
      else if (record && record.failed) failures.push('加载失败：' + asset.path);
      else if (record && record.ready) {
        const v = motion.viewport;
        if (!record.img.naturalWidth || !record.img.naturalHeight || (v && (![v.x, v.y, v.width, v.height].every(Number.isFinite) || v.x < 0 || v.y < 0 || v.width <= 0 || v.height <= 0 || v.x + v.width > record.img.naturalWidth || v.y + v.height > record.img.naturalHeight))) failures.push('源尺寸或视口无效：' + asset.path);
        else loaded++;
      }
    });
    motionPlaybackReady = loaded === requiredFrameIds.length && !failures.length;
    $('motionPlay').disabled = !motionPlaybackReady;
    $('motionLoadStatus').className = failures.length ? 'error' : 'note';
    $('motionLoadStatus').textContent = '当前动作帧预载：已就绪 ' + loaded + ' / ' + requiredFrameIds.length + ' 张唯一图片。' + (failures.length ? '无法播放，失败 ' + failures.length + ' 项：' + failures.slice(0, 3).join('；') + (failures.length > 3 ? '；其余 ' + (failures.length - 3) + ' 项请逐帧检查。' : '') : motionPlaybackReady ? '可手动播放。' : '全部就绪前暂不能播放，仍可逐帧检查。');
    if (!motionPlaybackReady && playing) pause();
  }
  function draw() {
    if (!motion || !frames.length) return;
    const index = frameIndex(); const frame = frames[index]; const asset = assetFor(frame.asset, 'image');
    const record = asset ? currentImage(asset) : null;
    const viewport = motion.viewport;
    const validViewport = !viewport || ([viewport.x, viewport.y, viewport.width, viewport.height].every(Number.isFinite) && viewport.x >= 0 && viewport.y >= 0 && viewport.width > 0 && viewport.height > 0 && record && viewport.x + viewport.width <= record.img.naturalWidth && viewport.y + viewport.height <= record.img.naturalHeight);
    const show = Boolean(record && record.ready && record.img.naturalWidth && ctx && validViewport);
    canvas.hidden = !show; $('motionEmpty').hidden = show;
    if (show) {
      const source = viewport || {x: 0, y: 0, width: record.img.naturalWidth, height: record.img.naturalHeight};
      canvas.width = Math.max(1, Math.round(source.width * motion.displayScale)); canvas.height = Math.max(1, Math.round(source.height * motion.displayScale));
      ctx.imageSmoothingEnabled = false; ctx.clearRect(0, 0, canvas.width, canvas.height); ctx.drawImage(record.img, source.x, source.y, source.width, source.height, 0, 0, canvas.width, canvas.height);
      canvas.style.width = canvas.width + 'px'; canvas.style.height = canvas.height + 'px';
    } else $('motionEmpty').textContent = !asset ? '该帧图片未登记，待制作。' : record.failed ? '动作帧加载失败：' + asset.path : !ctx ? '当前浏览器无法绘制画布。' : record.ready && !validViewport ? '固定视口无效或超出源帧边界，请检查动作 viewport。' : '正在载入当前帧…';
    $('motionTime').value = String(Math.floor(playhead));
    $('motionStatus').textContent = '帧 ' + (index + 1) + ' / ' + frames.length + ' · 源 tick ' + (Math.floor(playhead) + 1) + ' / ' + totalTicks + ' · 当前帧 ' + frame.ticks + ' ticks · ' + motion.fps + ' ticks/秒 · 显示 ' + motion.displayScale + ' 倍 · ' + (playhead / motion.fps).toFixed(2) + ' / ' + (totalTicks / motion.fps).toFixed(2) + ' 秒';
  }
  function selectMotion(entry) {
    pause(); motionPlaybackReady = false; motion = entry; frames = list(entry.frames); starts = []; totalTicks = 0; playhead = 0;
    const valid = Number.isFinite(entry.fps) && entry.fps > 0 && Number.isFinite(entry.displayScale) && entry.displayScale > 0 && frames.length && frames.every((frame) => Number.isInteger(frame.ticks) && frame.ticks > 0);
    motionValid = Boolean(valid); requiredFrameIds = [...new Set(frames.map((frame) => frame.asset))];
    $('motionTitle').textContent = str(entry.label || entry.id); $('motionNote').textContent = str(entry.note);
    document.querySelectorAll('[data-motion]').forEach((button) => { const selected = button.dataset.motion === str(entry.id); button.classList.toggle('selected', selected); button.setAttribute('aria-pressed', String(selected)); });
    ['motionPlay', 'motionPrev', 'motionNext', 'motionRestart', 'motionTime'].forEach((id) => { $(id).disabled = !valid; });
    if (!valid) { frames = []; canvas.hidden = true; $('motionEmpty').hidden = false; $('motionEmpty').textContent = '动作待制作，或帧率、倍率、源 ticks 尚未正确登记。'; $('motionStatus').textContent = '无法播放'; $('motionTime').max = '0'; $('motionTime').value = '0'; updateLoadStatus(); return; }
    frames.forEach((frame) => { starts.push(totalTicks); totalTicks += frame.ticks; });
    $('motionTime').max = String(totalTicks - 1);
    updateLoadStatus();
    requiredFrameIds.forEach((id) => { const asset = assetFor(id, 'image'); if (asset) currentImage(asset); });
    updateLoadStatus(); draw();
  }
  motions.forEach((entry) => { const button = node('button', entry.label || entry.id); button.type = 'button'; button.dataset.motion = str(entry.id); button.setAttribute('aria-pressed', 'false'); button.addEventListener('click', () => selectMotion(entry)); $('motionList').appendChild(button); });
  if (motions.length) selectMotion(motions[0]);
  else { empty($('motionList'), '动作清单待登记。'); canvas.hidden = true; ['motionPlay', 'motionPrev', 'motionNext', 'motionRestart', 'motionTime'].forEach((id) => { $(id).disabled = true; }); }
  $('motionPlay').addEventListener('click', () => { if (!frames.length || !motionPlaybackReady) return; if (playing) pause(); else { if (playhead >= totalTicks - 1) playhead = 0; playing = true; lastClock = null; $('motionPlay').textContent = '暂停'; } });
  function step(direction) { if (!frames.length) return; pause(); const next = Math.min(frames.length - 1, Math.max(0, frameIndex() + direction)); playhead = starts[next]; draw(); }
  $('motionPrev').addEventListener('click', () => step(-1)); $('motionNext').addEventListener('click', () => step(1));
  $('motionRestart').addEventListener('click', () => { if (!frames.length) return; playhead = 0; lastClock = null; draw(); });
  $('motionTime').addEventListener('input', () => { pause(); playhead = Math.max(0, Math.min(totalTicks - 1, Number($('motionTime').value) || 0)); draw(); });
  function tick(now) {
    if (playing && motion && frames.length) {
      if (lastClock != null) playhead += Math.max(0, now - lastClock) * motion.fps / 1000;
      lastClock = now;
      if (playhead >= totalTicks) {
        if ($('motionLoop').checked) playhead %= totalTicks;
        else { playhead = totalTicks - 1; pause(); }
      }
      draw();
    }
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
  const tabs = Array.from(document.querySelectorAll('[data-tab]'));
  function showTab(button) {
    pause(); document.querySelectorAll('audio, video').forEach((media) => media.pause());
    tabs.forEach((tab) => { const selected = tab === button; tab.setAttribute('aria-selected', String(selected)); tab.tabIndex = selected ? 0 : -1; $(tab.dataset.tab).hidden = !selected; });
  }
  tabs.forEach((button, index) => { button.addEventListener('click', () => showTab(button)); button.addEventListener('keydown', (event) => {
    let next;
    if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
    else if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = tabs.length - 1;
    if (next != null) { event.preventDefault(); showTab(tabs[next]); tabs[next].focus(); }
  }); });
  document.addEventListener('visibilitychange', () => { if (document.hidden) { pause(); document.querySelectorAll('audio, video').forEach((media) => media.pause()); } });
}());
