'use strict';

const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const { compactMovie, extractTemplate, hash, packedMovie, render } = require('./gacha_skill_media/movie.cjs');

const read = file => JSON.parse(fs.readFileSync(file,'utf8'));
const write = (file,data) => fs.writeFileSync(file, JSON.stringify(data,null,2)+'\n',{flag:'wx'});
const identity = file => {
  const bytes = fs.readFileSync(file);
  return {file:path.resolve(file),sha256:hash(bytes),bytes:bytes.length};
};
const safeKey = value => typeof value === 'string' && /^[A-Za-z0-9_.:-]+$/.test(value)
  && !['__proto__','constructor','prototype'].includes(value);

function context(file) {
  const config = read(file);
  assert.equal(config.schemaVersion,1);
  const base = path.dirname(path.resolve(file));
  const resolve = value => path.resolve(base,value);
  const bound = (binding,label) => {
    assert(binding && typeof binding.file==='string' && /^[a-f0-9]{64}$/.test(binding.sha256), 'Missing identity for '+label);
    const current = identity(resolve(binding.file));
    assert.equal(current.sha256,binding.sha256,label+' SHA-256 changed');
    if (binding.bytes!==undefined) assert.equal(current.bytes,binding.bytes,label+' size changed');
    return current;
  };
  const out = key => {
    assert.equal(typeof config.output?.[key],'string','Missing output.'+key);
    return resolve(config.output[key]);
  };
  const characters = config.characters.map(({id,name,posterPage}) => {
    id = String(id);
    assert(/^[1-9]\d*$/.test(id) && safeKey(posterPage) && typeof name==='string' && name.length,'Invalid character');
    return {id,name,posterPage};
  });
  assert(characters.length && new Set(characters.map(role=>role.id)).size===characters.length
    && new Set(characters.map(role=>role.posterPage)).size===characters.length,'Duplicate or empty characters');
  const order = config.featureOrder.map(entry => {
    assert([0,2].includes(entry.kind) && safeKey(entry.page),'Invalid feature order entry');
    assert(entry.screenshotTick===undefined || Number.isSafeInteger(entry.screenshotTick) && entry.screenshotTick>=0,
      'Invalid screenshot tick');
    if (entry.kind===0) return {kind:0,page:entry.page};
    const roleId = String(entry.roleId);
    assert(characters.some(role=>role.id===roleId) && safeKey(entry.skillKey),'Unknown skill role or key');
    return {...entry,roleId};
  });
  assert(order[0]?.kind===0 && new Set(order.map(entry=>entry.page)).size===order.length,'Expected first Movie and distinct pages');
  const skills = order.filter(entry=>entry.kind===2);
  assert.deepEqual(skills.map(entry=>entry.roleId).sort(),characters.map(role=>role.id).sort());
  for (const entry of skills) {
    const posterPage = characters.find(role=>role.id===entry.roleId).posterPage;
    assert(order.some(row=>row.kind===0 && row.page===posterPage),'Missing poster page '+posterPage);
  }
  const limits = {maxHtmlCharacters:4500000,videoWidth:360,movieScale:0.42,movieQuality:68,...config.limits};
  assert(Number.isInteger(limits.maxHtmlCharacters) && limits.maxHtmlCharacters>40000
    && limits.maxHtmlCharacters<=5000000 && Number.isInteger(limits.videoWidth) && limits.videoWidth>0
    && limits.movieScale>0 && limits.movieScale<=1 && limits.movieQuality>=40 && limits.movieQuality<=92,'Invalid limits');
  return {config,characters,order,skills,resolve,bound,out,limits,
    tools:{python:'python',ffmpeg:'ffmpeg',ffprobe:'ffprobe',...config.tools}};
}

function movieInput(ctx) {
  const html = ctx.bound(ctx.config.movie,'Movie HTML');
  const receiptFile = ctx.bound(ctx.config.movie.receipt,'Movie receipt');
  const receipt = read(receiptFile.file);
  assert.equal(receipt.sha256,html.sha256,'Movie receipt does not bind HTML');
  return {html,receiptFile,receipt};
}

function prepare(ctx) {
  const input = movieInput(ctx);
  if (input.receipt.kind==='packed-gacha-movie') {
    const current = preparedMovie(ctx);
    return {movie:{...current.html,receipt:input.receiptFile}};
  }
  assert.equal(input.receipt.nativeUIRendererByteExact,true,'Expected a verified generated Movie receipt');
  const template = extractTemplate(fs.readFileSync(input.html.file));
  const result = compactMovie(template,{...ctx.tools,...ctx.limits});
  const directory = ctx.out('movieDir');
  const html = path.join(directory,'review.html');
  const receipt = path.join(directory,'preview-receipt.json');
  const output = render(template,result.bytes);
  assert(output.length<ctx.limits.maxHtmlCharacters,'Movie alone exceeds delivery character budget');
  fs.mkdirSync(directory);
  fs.writeFileSync(html,output,{flag:'wx'});
  const binding = identity(html);
  write(receipt,{schemaVersion:1,kind:'packed-gacha-movie',sha256:binding.sha256,
    source:{...input.html,receipt:input.receiptFile},payloadSHA256:hash(result.bytes),frameHashes:result.frameHashes,
    htmlCharacters:output.length,movieScale:ctx.limits.movieScale,movieQuality:ctx.limits.movieQuality});
  return {movie:{...binding,receipt:identity(receipt)}};
}

function preparedMovie(ctx) {
  const input = movieInput(ctx);
  assert.equal(input.receipt.kind,'packed-gacha-movie','Run prepare and bind the packed Movie first');
  const source = ctx.bound(input.receipt.source,'Generated Movie');
  const sourceReceipt = ctx.bound(input.receipt.source.receipt,'Generated Movie receipt');
  assert.equal(read(sourceReceipt.file).sha256,source.sha256);
  const template = extractTemplate(fs.readFileSync(source.file));
  const packed = packedMovie(fs.readFileSync(input.html.file,'utf8'));
  assert.equal(hash(packed.bytes),input.receipt.payloadSHA256);
  const movieOrder = ctx.order.filter(entry=>entry.kind===0).map(entry=>entry.page);
  assert.deepEqual(movieOrder,packed.model.pageOrder,'Feature Movie order does not match generated art');
  for (const {id,posterPage} of ctx.characters) {
    assert(packed.model.pages[posterPage] && packed.model.characters[id]
      && (packed.model.profiles[id] || packed.model.profiles[posterPage]),'Movie has no role UI for '+id);
  }
  for (const [key,page] of Object.entries(template.model.pages)) {
    assert.equal(hash(JSON.stringify(page.frames)),input.receipt.frameHashes[key]);
    assert.deepEqual(page.frames,packed.frameLibrary[packed.model.pages[key].frameLibraryIndex]);
  }
  return {...input,template,packed,source,sourceReceipt};
}

function invoke(tool,args,timeout=120000) {
  const result = spawnSync(tool,args,{encoding:'utf8',windowsHide:true,timeout,maxBuffer:20*1024*1024});
  assert.equal(result.status,0,String(result.error??result.stderr));
  return result.stdout;
}

function eventsFrom(frames) {
  const result = [];
  const push = (f,type,kind) => {if(f) result.push({frame:f.tick,type,kind,battleFrame:f.frame});};
  push(frames[0],'begin','原生回放开始');
  push(frames.find(f=>f.inSkillCutin),'cutinObserved','技能准备／切入');
  push(frames.find((f,i)=>i>0 && f.members.some((member,slot)=>
    (member?.skillExecutions??0)>(frames[i-1].members[slot]?.skillExecutions??0))),
  'executionObserved','观察到技能执行');
  const targets = new Map();
  const damage = frames.find(frame => {
    let changed = false;
    const seen = new Set();
    for (const target of frame.targets) {
      if (!['enemy','zako'].includes(target.kind) || seen.has(target.id) || !Number.isFinite(target.hp)) continue;
      seen.add(target.id);
      if (targets.has(target.id) && target.hp < targets.get(target.id)) changed = true;
      targets.set(target.id,target.hp);
    }
    return changed;
  });
  push(damage,'damageObserved','观察到目标生命值下降');
  push(frames.at(-1),'end','原生回放结束');
  return result.sort((a,b)=>a.frame-b.frame);
}

function acceptedCapture(ctx, capture, movie, verifyFrames) {
  const native = ctx.bound(capture.receipt,'Native capture receipt');
  const report = read(native.file);
  const roleId = String(capture.roleId);
  assert(report.schemaVersion===1 && report.kind==='native-gacha-capture' && report.passed===true
    && String(report.input.role)===roleId && report.presentation.defaultState==='native-replay','Native capture mismatch '+roleId);
  const visual = ctx.bound(capture.visual,'Human visual review');
  const accepted = read(visual.file);
  const audit = ctx.bound(capture.audit,'Machine UI audit');
  assert.equal(ctx.bound(accepted.audit,'Reviewed machine audit').sha256,audit.sha256);
  assert(accepted.schemaVersion===1 && String(accepted.roleId)===roleId && accepted.decision==='accept'
    && typeof accepted.observations==='string' && accepted.observations.trim()
    && Array.isArray(accepted.reviewedFrames) && accepted.reviewedFrames.length,'Missing positive human UI review '+roleId);
  const auditData = read(audit.file);
  assert(auditData.kind==='native-gacha-full-ui-audit' && String(auditData.roleId)===roleId
    && auditData.inputs.native.sha256===native.sha256 && auditData.inputs.packedMovie.sha256===movie.html.sha256
    && auditData.inputs.nativePNGSequenceSHA256===report.pngs.sequenceSHA256,'Visual audit input changed '+roleId);
  ctx.bound(auditData.inputs.layers,'Audited UI layers');
  if(auditData.inputs.scene) ctx.bound(auditData.inputs.scene,'Audited scene');
  const host = ctx.bound(report.captureReceipt,'Native host result');
  assert.equal(auditData.inputs.host.sha256,host.sha256);
  const data = read(host.file);
  const frames = data.nativeFrames;
  assert(data.passed && data.viewPhase==='native-finished' && frames.length===report.pngs.count
    && frames.every((frame,index)=>frame.tick===index) && frames.at(-1).previewStateTag==='Finish','Incomplete native frames '+roleId);
  const observed = data.battleBootstrap.previewSource;
  assert(String(observed.character)===roleId && observed.pool===report.input.pool && observed.quest===report.input.quest
    && observed.log+'.battle.amf3.deflate'===report.input.nativeLog,'Host differs from native receipt '+roleId);
  assert.deepEqual([observed.clipLeft,observed.clipTop],report.input.clip);
  assert.deepEqual(report.pngs.dimensions,report.presentation.viewport.slice(2));
  assert.equal(auditData.frames,frames.length);
  assert.deepEqual(auditData.nativeMask,report.presentation.viewport);
  assert.equal(auditData.fps,report.presentation.fps);
  const reviewed = new Set(accepted.reviewedFrames);
  assert(reviewed.size>=3,'Visual review requires at least three distinct native frames');
  for (const frame of reviewed) {
    const evidence = auditData.keyframeEvidence.find(entry=>entry.battleFrame===frame);
    assert(evidence && frames[evidence.tick]?.frame===frame,'Visual decision has no matching native frame '+frame);
    ctx.bound({file:path.resolve(path.dirname(audit.file),evidence.comparison),sha256:evidence.sha256},'Reviewed UI comparison');
  }
  const framesDir = capture.framesDir ? ctx.resolve(capture.framesDir) : path.join(path.dirname(host.file),'frames');
  if (verifyFrames) {
    const sequence = createHash('sha256');
    assert.equal(report.pngs.frameManifest.length,frames.length);
    assert.equal(fs.readdirSync(framesDir).filter(name=>/^\d{4}\.png$/.test(name)).length,frames.length);
    for (const {tick} of frames) {
      const name = String(tick).padStart(4,'0')+'.png';
      const png = fs.readFileSync(path.join(framesDir,name));
      assert.equal(png.toString('ascii',12,16),'IHDR');
      assert.deepEqual([png.readUInt32BE(16),png.readUInt32BE(20)],report.pngs.dimensions);
      const sha256 = hash(png);
      assert.deepEqual(report.pngs.frameManifest[tick],{name,sha256},'Original PNG changed '+roleId+'/'+name);
      sequence.update(name+' '+sha256+'\n','ascii');
    }
    assert.equal(sequence.digest('hex'),report.pngs.sequenceSHA256,'PNG sequence changed '+roleId);
  }
  return {roleId,framesDir,firstFrame:0,lastFrame:frames.length-1,events:eventsFrom(frames),
    presentation:report.presentation,native,host,audit,visual,
    binding:report.input,sourcePNGSequenceSHA256:report.pngs.sequenceSHA256};
}

function captures(ctx,movie,verifyFrames) {
  assert.equal(ctx.config.captures.length,ctx.skills.length);
  return ctx.skills.map(({roleId})=>{
    const binding = ctx.config.captures.filter(entry=>String(entry.roleId)===roleId);
    assert.equal(binding.length,1,'Expected one capture for '+roleId);
    return acceptedCapture(ctx,binding[0],movie,verifyFrames);
  });
}

function encode(ctx) {
  const movie = preparedMovie(ctx);
  const source = captures(ctx,movie,true);
  const [{presentation:{fps,viewport:stageMask,stage}}] = source;
  assert(Number.isInteger(fps) && fps>0 && stageMask.length===4);
  if (ctx.limits.fps!==undefined) assert.equal(fps,ctx.limits.fps,'Native playback rate differs from requested rate');
  for (const {presentation} of source) {
    assert.equal(presentation.fps,fps);
    assert.deepEqual(presentation.viewport,stageMask);
    assert.deepEqual(presentation.stage,stage);
  }
  assert.deepEqual(stage,[movie.packed.model.stage.width??1080,movie.packed.model.stage.uiHeight]);
  const totalSeconds = source.reduce((n,entry)=>n+entry.lastFrame+1,0)/fps;
  const maxVideoBytes = Math.floor((ctx.limits.maxHtmlCharacters-fs.readFileSync(movie.html.file,'utf8').length-45000)*3/4);
  const target = ctx.limits.maxVideoBytes??Math.min(maxVideoBytes,1350000);
  assert(target>0 && target<=maxVideoBytes,'Video budget exceeds the available HTML space');
  const kbps = Math.min(500,Math.floor(target*8/totalSeconds/1000));
  assert(kbps>=20,'Insufficient encoding budget for full playback');
  const width = ctx.limits.videoWidth, height = width*stageMask[3]/stageMask[2];
  assert(Number.isInteger(height) && width%2===0 && height%2===0 && width<=stageMask[2],'Video size must preserve the native aspect ratio');
  const output = ctx.out('mediaDir');
  fs.mkdirSync(output);
  const clips = source.map(({framesDir,presentation,...clip})=>{
    const file = path.join(output,clip.roleId+'.webm');
    const args = ['-v','error','-n','-framerate',String(fps),'-i',path.join(framesDir,'%04d.png'),
      '-frames:v',String(clip.lastFrame+1),'-vf','scale='+width+':'+height+':flags=area','-fps_mode','passthrough',
      '-c:v','libvpx-vp9','-deadline','good','-cpu-used','4','-threads','2','-row-mt','1',
      '-g',String(fps*2),'-b:v',kbps+'k','-pix_fmt','yuv420p','-an','-passlogfile',path.join(output,clip.roleId+'-vp9')];
    invoke(ctx.tools.ffmpeg,[...args,'-pass','1','-f','null','-']);
    invoke(ctx.tools.ffmpeg,[...args,'-pass','2',file]);
    return {...clip,video:identity(file)};
  });
  const manifest = path.join(output,'native-captures.json');
  write(manifest,{schemaVersion:1,kind:'gacha-skill-media',movie:movie.html,fps,stageMask,stage,
    encoding:{codec:'vp9',width,height,kbps,totalSeconds},clips});
  return {media:identity(manifest),fps,totalSeconds,videoBytes:clips.reduce((n,clip)=>n+clip.video.bytes,0)};
}

function probeVideo(ctx, video, {width,height}, frames, fps) {
  const raw = invoke(ctx.tools.ffprobe,['-v','error','-show_streams','-show_frames','-show_format',
    '-show_entries','format=format_name,duration:stream=codec_name,codec_type,width,height:frame=best_effort_timestamp_time','-of','json',video]);
  const {streams,frames:decoded,format} = JSON.parse(raw);
  assert(format.format_name.split(',').includes('webm') && streams.length===1
    && streams[0].codec_name==='vp9' && streams[0].codec_type==='video');
  assert.deepEqual([streams[0].width,streams[0].height],[width,height]);
  assert.equal(decoded.length,frames);
  for (const [index,frame] of decoded.entries()) {
    assert(Math.abs(Number(frame.best_effort_timestamp_time)-index/fps)<=0.001,'Missing/retimed frame '+index);
  }
  assert(Math.abs(Number(format.duration)-frames/fps)<=0.002,'Native media end time changed');
}

function assemble(ctx) {
  const movie = preparedMovie(ctx);
  const native = captures(ctx,movie,false);
  const manifestFile = path.join(ctx.out('mediaDir'),'native-captures.json');
  const manifest = read(manifestFile);
  assert(manifest.schemaVersion===1 && manifest.kind==='gacha-skill-media' && manifest.movie.sha256===movie.html.sha256);
  const {fps,stageMask,stage,encoding} = manifest;
  assert.equal(manifest.clips.length,native.length);
  const clips = manifest.clips.map((clip,index)=>{
    const expected = native[index];
    const {framesDir,presentation,...binding} = expected;
    const {video,...stored} = clip;
    assert.deepEqual(stored,binding,'Media bindings do not match accepted capture '+expected.roleId);
    assert.equal(fps,presentation.fps);
    assert.deepEqual(stageMask,presentation.viewport);
    assert.deepEqual(stage,presentation.stage);
    const file = ctx.bound(video,'Encoded video');
    probeVideo(ctx,file.file,encoding,clip.lastFrame+1,fps);
    return {...stored,width:encoding.width,height:encoding.height,videoHash:file.sha256,data:fs.readFileSync(file.file).toString('base64')};
  });
  const html = ctx.out('html'), receipt = ctx.out('receipt');
  const pages = {order:ctx.order,characters:ctx.characters};
  const messages = ctx.config.presentation??{};
  const embedded = clips.map(({roleId,firstFrame,lastFrame,events,width,height,videoHash,sourcePNGSequenceSHA256,data})=>
    ({roleId,firstFrame,lastFrame,events,width,height,videoHash,sourcePNGSequenceSHA256,data}));
  const output = render(movie.template,movie.packed.bytes,pages,{fps,stageMask,stage,clips:embedded},messages);
  assert(output.length<ctx.limits.maxHtmlCharacters,'Final HTML exceeds character budget: '+output.length);
  assert(html!==receipt && !fs.existsSync(html) && !fs.existsSync(receipt),'Choose new HTML and receipt paths');
  fs.mkdirSync(path.dirname(html),{recursive:true});
  fs.writeFileSync(html,output,{flag:'wx'});
  const result = {schemaVersion:1,kind:'offline-native-gacha-preview',html:identity(html),htmlCharacters:output.length,
    movie:movie.html,moviePayloadSHA256:hash(movie.packed.bytes),media:identity(manifestFile),featureOrder:ctx.order,
    stage,stageMask,fps,clips:clips.map(({data,...clip})=>clip)};
  write(receipt,result);
  return {...result,receipt:identity(receipt)};
}

async function main(args) {
  const [mode,flag,file] = args;
  assert(args.length===3 && flag==='--config' && ['prepare','layers','encode','assemble','browser','record'].includes(mode),
    'Usage: node gacha_skill_media.cjs <prepare|layers|encode|assemble|browser|record> --config FILE');
  const ctx = context(file);
  const operation = {prepare,encode,assemble}[mode];
  const result = operation ? operation(ctx) : await require('./gacha_skill_media/browser.cjs')[mode](ctx);
  console.log(JSON.stringify(result));
}

module.exports = {context,preparedMovie,identity,read,write,invoke};
if (require.main===module) main(process.argv.slice(2)).catch(error=>{console.error('[gacha-skill-media] '+error.stack);process.exitCode=1;});
