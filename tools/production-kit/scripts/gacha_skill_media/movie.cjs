'use strict';

const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { gzipSync, gunzipSync } = require('node:zlib');
const { extractTemplate } = require('../gacha_preview.cjs');

const hash = raw => createHash('sha256').update(raw).digest('hex');
const read = name => fs.readFileSync(path.join(__dirname, name), 'utf8');
const json = value => JSON.stringify(value).replaceAll('<', '\\u003c');
const escape = value => String(value).replace(/[&<>"]/g, key => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'})[key]);
const blob = (id, type, value) => '<script id="' + id + '" type="' + type + '">' + value + '</script>';
const packedID = 'compact-review-data';
const viewHook = 'window.review={state,select,seek:go,pause,replay,draw,pickupPanels,drawTicketText};';

function once(source, from, to) {
  assert.equal(source.split(from).length, 2, 'Unsupported reviewed player span: ' + from);
  return source.replace(from, () => to);
}

function compactMovie(template, {python, movieScale, movieQuality}) {
  const model = structuredClone(template.model);
  const jobs = [], ui = [], movieSlots = [], movieIndices = new Map();
  for (const page of Object.values(model.pages)) {
    const magnification = Array(page.cells.length).fill(0);
    for (const frame of page.frames) for (const [index,a,b,c,d] of frame) {
      magnification[index] = Math.max(magnification[index], Math.hypot(a,b), Math.hypot(c,d));
    }
    page.cells = page.cells.map((cell, index) => {
      let asset = movieIndices.get(cell.uri);
      const ratio = magnification[index] * movieScale;
      if (asset === undefined) {
        asset = movieSlots.length;
        movieIndices.set(cell.uri, asset);
        movieSlots.push(jobs.length);
        jobs.push({uri:cell.uri, ratio, quality:movieQuality});
      } else {
        const job = jobs[movieSlots[asset]];
        job.ratio = Math.max(job.ratio, ratio);
      }
      return {asset, frame:cell.frame};
    });
  }
  function schedule(record, key, lossless) {
    ui.push({record, key, slot:jobs.length});
    jobs.push({uri:record[key],ratio:1,quality:84,nativeSize:true,lossless});
  }
  for (const key of ['banner','screenshot']) schedule(model, key, false);
  for (const record of [model.footerTextures,model.ticketButton]) {
    for (const key of Object.keys(record)) schedule(record, key, true);
  }
  const encoded = spawnSync(python, ['-B',path.join(__dirname,'compact_images.py')], {
    input:JSON.stringify(jobs),encoding:'utf8',windowsHide:true,maxBuffer:150*1024*1024,timeout:180000,
  });
  assert.equal(encoded.status, 0, String(encoded.error ?? '') + '\n' + encoded.stderr);
  const assets = JSON.parse(encoded.stdout);
  assert.equal(assets.length, jobs.length);
  model.movieAssets = movieSlots.map(slot => assets[slot]);
  for (const {record,key,slot} of ui) record[key] = assets[slot].uri;

  const frameLibrary = [], frameIndices = new Map(), frameHashes = {};
  for (const [key,page] of Object.entries(model.pages)) {
    const old = template.model.pages[key];
    assert.deepEqual(page.cells.map(cell => cell.frame), old.cells.map(cell => cell.frame));
    assert.deepEqual(page.timeline, old.timeline);
    const frameHash = hash(JSON.stringify(page.frames));
    frameHashes[key] = frameHash;
    if (!frameIndices.has(frameHash)) {
      frameIndices.set(frameHash, frameLibrary.length);
      frameLibrary.push(page.frames);
    }
    page.frameLibraryIndex = frameIndices.get(frameHash);
    delete page.frames;
  }
  for (const key of ['characters','nativeUI','ticketStrings','ticketPreview','pageOrder','footerOrder','profiles']) {
    assert.deepEqual(model[key], template.model[key]);
  }
  const bytes = gzipSync(JSON.stringify({model,frameLibrary}),{level:9});
  return {bytes, model, frameHashes};
}

function packedMovie(html) {
  const match = html.match(/<script id="compact-review-data" type="application\/octet-stream">([A-Za-z0-9+/=]+)<\/script>/);
  assert(match, 'Missing compact Movie model');
  const bytes = Buffer.from(match[1],'base64');
  const payload = JSON.parse(gunzipSync(bytes));
  return {bytes, ...payload};
}

function render(template, packed, presentation, recordings, messages={}) {
  let player = template.player.body;
  const replace = (from,to) => { player = once(player,from,to); };
  replace('const cell=p.cells[c[0]];ctx.drawImage(cells[key][c[0]],-cell.frame[0],-cell.frame[1]);',
    'const cell=p.cells[c[0]],asset=D.movieAssets[cell.asset];ctx.drawImage(cells[key][c[0]],-cell.frame[0],-cell.frame[1],asset.width,asset.height);');
  replace('p.cells.map(c=>image(c.uri))','p.cells.map(c=>image(D.movieAssets[c.asset].uri))');
  let shell = template.source.slice(0,template.tree.scripts[0].start);
  if (recordings) {
    replace('ui.checked?D.stage.uiHeight:D.stage.movieHeight',
      'ui.checked?D.stage.uiHeight:D.pages[key].nativeClip?clips.stageMask[1]+clips.stageMask[3]:D.stage.movieHeight');
    replace('const p=D.pages[key];for(const c of p.frames[frame])',
      'const p=D.pages[key];if(p.nativeClip){nativeMedia.draw(ctx)}else for(const c of p.frames[frame])');
    replace("p.label+' · 编译资源回放';updateProfile();",
      "p.label+(p.nativeClip?' · 客户端原生录制':' · 编译资源回放');updateProfile();updateCaptureClock(p);");
    replace("document.getElementById('candidateCaption').textContent=ui.checked?D.paymentCaption:",
      "document.getElementById('candidateCaption').textContent=p.nativeClip?'客户端离线原生录制':ui.checked?D.paymentCaption:");
    replace('ui:ui.checked}}','ui:ui.checked,skill:D.pages[key].nativeClip?nativeMedia.state()??null:null}}');
    replace('last=0;draw()}\nfunction select',
      'last=0;if(D.pages[key].nativeClip){if(value)nativeMedia.pause();else opening.then(()=>{if(playing)return nativeMedia.play(speed)}).catch(reportMediaError)}draw()}\nfunction select');
    replace("key=value;frame=0;seconds=0;acc=0;seek.max=D.pages[key].frameCount-1;document.getElementById('page').value=key;draw()}",
      "key=value;frame=0;seconds=0;acc=0;last=0;seek.max=D.pages[key].frameCount-1;document.getElementById('page').value=key;const loaded=openCapture(D.pages[key].nativeClip);draw();return loaded}");
    replace('function go(value){pause(true);frame=Math.max(0,Math.min(D.pages[key].frameCount-1,value));seconds=frame/60;acc=0;draw()}',
      'async function go(value){pause(true);const page=D.pages[key],target=Math.max(0,Math.min(page.frameCount-1,value)),active=navigation;await opening;if(active!==navigation)return;if(page.nativeClip){await nativeMedia.seek(page.nativeClip.firstFrame+target);return}frame=target;seconds=frame/60;acc=0;draw()}');
    replace('function replay(){frame=0;seconds=0;acc=0;pause(false)}',
      'async function replay(){if(D.pages[key].nativeClip){const active=navigation;await go(0);if(active!==navigation)return}else{frame=0;seconds=0;acc=0}pause(false)}');
    replace('if(playing&&ready){seconds+=dt*speed;','if(playing&&ready&&!D.pages[key].nativeClip){seconds+=dt*speed;');
    replace('if(frame>=D.pages[key].endBegin-1){frame=0;cycles++}',
      'if(frame>=D.pages[key].endBegin-1){frame=0;cycles++;if(continuous.checked){select(keys[(keys.indexOf(key)+1)%keys.length]);break}}');
    replace("speed=Number(e.target.value);acc=0",
      "speed=Number(e.target.value);acc=0;if(playing&&D.pages[key].nativeClip)opening.then(()=>{if(playing)return nativeMedia.play(speed)}).catch(reportMediaError)");
    replace('for(const id of D.pageOrder.filter(id=>D.profiles[id])){',
      'for(const {id,name,posterPage} of presentation.characters){');
    replace('choice.textContent=D.profiles[id].name;', 'choice.textContent=name;');
    replace('choice.onclick=()=>select(id);','choice.onclick=()=>select(posterPage);');
    replace('const profile=D.profiles[key],opacity=fade();',
      'const roleId=profileIdFor.get(key)??key,profile=D.profiles[roleId]??D.profiles[key],opacity=fade();');
    replace('drawPixel(key,...D.calibration.infoPixel,.86);',
      'drawPixel(roleId,...D.calibration.infoPixel,.86);');
    replace('const profile=D.profiles[key];','const profileId=D.pages[key].characterId??profileIdFor.get(key)??key;const profile=D.profiles[profileId]??D.profiles[key];');
    replace('String(button.dataset.role===key)','String(button.dataset.role===profileId)');
    const coverLabel = /document\.getElementById\('roleName'\)\.textContent=profile\?profile\.title\+' · '\+profile\.name:'[^']*';/;
    const prior = player.match(coverLabel);
    assert(prior,'Unsupported reviewed role display');
    replace(prior[0],"document.getElementById('roleName').textContent=profile?profile.title+' · '+profile.name:'精选角色';");
    replace('return index >= 0 ? D.footerOrder[index] : null;',
      'return index >= 0 ? (posters.get(String(D.footerOrder[index]))??D.footerOrder[index]) : null;');
    replace(viewHook,viewHook.replace('draw,pickupPanels','draw,renderAt,pickupPanels'));
    shell = once(shell, '<label><input type="checkbox" id="ui" checked>校准 UI</label>',
      '<label><input type="checkbox" id="ui" checked>校准 UI</label><label><input type="checkbox" id="continuous" checked>整池连播</label>');
    shell = once(shell, '<p id="roleMetadata"></p>', '<p id="roleMetadata"></p><p id="recordingClock" hidden></p>');
    if (messages.title) {
      shell = shell.replace(/<title>[^<]*<\/title>/, () => '<title>'+escape(messages.title)+'</title>')
        .replace(/<h1>[^<]*<\/h1>/, () => '<h1>'+escape(messages.title)+'</h1>');
    }
    if (messages.notes) {
      shell = shell.replace(/<div class="notes">[\s\S]*?<\/div>/,
        () => '<div class="notes">'+messages.notes.map(note=>'<p>'+escape(note)+'</p>').join('')+'</div>');
    }
  }
  const boot = `(async()=>{
const compressed=Uint8Array.from(atob(document.getElementById('${packedID}').textContent),c=>c.charCodeAt(0));
const stream=new Blob([compressed]).stream().pipeThrough(new DecompressionStream('gzip'));
const {model,frameLibrary}=JSON.parse(await new Response(stream).text());
for(const page of Object.values(model.pages))page.frames=frameLibrary[page.frameLibraryIndex];
${recordings ? read('bridge.js') : ''}
const ReviewData=window.ReviewData=model;
window.NATIVE_GACHA_UI_DATA=model.nativeUI;
${template.tree.scripts[1].body}
${player}
})().catch(error=>{
document.documentElement.dataset.compactError=error.message;
document.getElementById('ready').textContent=error.message;
throw error;
});`;
  vm.createScript(boot);
  const media = recordings ? read('player.js') : '';
  if (media) vm.createScript(media);
  const after = template.source.slice(template.tree.scripts[2].end);
  return shell + blob(packedID, 'application/octet-stream', packed.toString('base64')) +
    (recordings ? blob('skill-presentation','application/json',json(presentation))
      + blob('native-recordings','application/json',json(recordings)) + '<script>'+media+'</script>' : '') +
    '<script>'+boot+'</script>'+after;
}

module.exports = { compactMovie, extractTemplate, hash, packedMovie, render, viewHook, once };
