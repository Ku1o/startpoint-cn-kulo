'use strict';

const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { once, viewHook } = require('./movie.cjs');
const { identity, invoke, preparedMovie, read, write } = require('../gacha_skill_media.cjs');

const sleep = ms => new Promise(resolve=>setTimeout(resolve,ms));
function findBrowser(configured) {
  if (configured) return configured;
  const candidates = [
    process.env['ProgramFiles(x86)'] && path.join(process.env['ProgramFiles(x86)'],'Microsoft/Edge/Application/msedge.exe'),
    process.env.ProgramFiles && path.join(process.env.ProgramFiles,'Google/Chrome/Application/chrome.exe'),
  ];
  const browser = candidates.find(file=>file && fs.existsSync(file));
  assert(browser,'Set tools.browser to an installed Chromium browser');
  return browser;
}

async function withBrowser(ctx, output, timeout, use) {
  fs.mkdirSync(output);
  const browser = spawn(findBrowser(ctx.tools.browser),[
    '--headless','--disable-gpu','--disable-background-networking','--disable-component-update','--no-first-run',
    '--no-proxy-server','--host-resolver-rules=MAP * ~NOTFOUND','--disable-renderer-backgrounding',
    '--disable-background-timer-throttling','--disable-backgrounding-occluded-windows',
    '--remote-debugging-pipe','--user-data-dir='+path.join(output,'edge-profile'),'about:blank',
  ],{windowsHide:true,stdio:['ignore','ignore','ignore','pipe','pipe']});
  let id=0, input='', closed=false;
  const pending=new Map(), exceptions=[], network=[];
  function fail(error){closed=true;for(const waiter of pending.values())waiter.reject(error);pending.clear()}
  browser.on('error',fail);
  browser.on('exit',()=>fail(Error('Browser exited')));
  browser.stdio[3].on('error',fail);
  browser.stdio[4].setEncoding('utf8');
  browser.stdio[4].on('data',chunk=>{
    input+=chunk;
    for(let end;(end=input.indexOf('\0'))!==-1;){
      const msg=JSON.parse(input.slice(0,end));input=input.slice(end+1);
      if(msg.method==='Runtime.exceptionThrown')exceptions.push(msg.params.exceptionDetails.exception?.description??msg.params.exceptionDetails.text);
      if(msg.method==='Network.requestWillBeSent'&&/^(https?|wss?):/i.test(msg.params.request.url))network.push(msg.params.request.url);
      const waiter=pending.get(msg.id);
      if(waiter){pending.delete(msg.id);if(msg.error)waiter.reject(Error(JSON.stringify(msg.error)));else waiter.resolve(msg.result)}
    }
  });
  function send(method,params={},sessionId){
    if(closed)return Promise.reject(Error('Browser pipe is closed'));
    return new Promise((resolve,reject)=>{
      const key=++id;pending.set(key,{resolve,reject});
      browser.stdio[3].write(JSON.stringify({id:key,method,params,sessionId})+'\0');
    });
  }
  const deadline=setTimeout(()=>{fail(Error('Offline browser timed out'));browser.kill()},timeout);
  try {
    const {targetId}=await send('Target.createTarget',{url:'about:blank'});
    const {sessionId}=await send('Target.attachToTarget',{targetId,flatten:true});
    const call=(method,params)=>send(method,params,sessionId);
    const evaluate=async expression=>{
      const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
      if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description??r.exceptionDetails.text);
      return r.result.value;
    };
    await call('Runtime.enable');
    await call('Network.enable');
    await call('Network.emulateNetworkConditions',{offline:true,latency:0,downloadThroughput:0,uploadThroughput:0});
    const result=await use(call,evaluate);
    assert.deepEqual(exceptions,[]);
    assert.deepEqual(network,[]);
    return {...result,exceptions,network};
  } finally {
    clearTimeout(deadline);
    await send('Browser.close').catch(()=>{});
    if(browser.exitCode===null && !browser.killed) {
      const timer=setTimeout(()=>browser.kill(),2000);
      browser.once('exit',()=>clearTimeout(timer));
    }
  }
}

async function ready(evaluate) {
  for(let attempt=0;attempt<500;attempt++){
    await sleep(40);
    if(await evaluate('document.documentElement.dataset.ready==="true"'))return;
  }
  throw Error('Review did not report ready');
}

function savePNG(file,data){fs.writeFileSync(file,Buffer.from(data.split(',')[1],'base64'),{flag:'wx'});}

async function layers(ctx) {
  const movie=preparedMovie(ctx);
  const reports=ctx.config.captures.map(entry=>read(ctx.bound(entry.receipt,'Native capture receipt').file));
  assert(reports.length,'Layer capture requires native capture timelines');
  const {fps,stage,nativeMask}= {fps:reports[0].presentation.fps,stage:reports[0].presentation.stage,
    nativeMask:reports[0].presentation.viewport};
  for(const report of reports){
    assert.equal(report.presentation.fps,fps);
    assert.deepEqual(report.presentation.stage,stage);
    assert.deepEqual(report.presentation.viewport,nativeMask);
  }
  const maxTicks=Math.max(...reports.map(report=>report.pngs.count));
  const output=ctx.out('uiLayersDir');
  const instrumented=once(fs.readFileSync(movie.html.file,'utf8'),viewHook,viewHook+`
window.auditLayerAt=(at,fps)=>{
  pause(true);
  ui.checked=true;
  canvas.height=D.stage.uiHeight;
  seconds=at/fps;
  const pixels=D.footerOrder.map(id=>{
    const c=D.characters[id];
    let tick=(seconds*c.fps*c.cardPlaybackSpeed)%c.totalTicks,sum=0;
    return c.frames.findIndex(f=>{sum+=f.hold;return tick<sum});
  });
  const base=ctx.createPattern(footer.quest_bg_panel,'repeat');
  ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);
  ctx.fillStyle=base;ctx.fillRect(0,0,canvas.width,canvas.height);
  const background=canvas.toDataURL();
  ctx.clearRect(0,0,canvas.width,canvas.height);
  topUI();footerUI();
  return {signature:pixels.join(','),background,overlay:canvas.toDataURL(),size:[canvas.width,canvas.height]};
};
window.auditPhases=(count,fps)=>{
  const phases=[];
  for(let at=0;at<count;at++){
    const seconds=at/fps;
    phases.push(D.footerOrder.map(id=>{
      const c=D.characters[id];
      let tick=(seconds*c.fps*c.cardPlaybackSpeed)%c.totalTicks,sum=0;
      return c.frames.findIndex(f=>{sum+=f.hold;return tick<sum});
    }).join(','));
  }
  return phases;
};`);
  const result=await withBrowser(ctx,output,120000,async(call,evaluate)=>{
    await call('Page.enable');
    const {frameTree}=await call('Page.getFrameTree');
    await call('Page.setDocumentContent',{frameId:frameTree.frame.id,html:instrumented});
    await ready(evaluate);
    const phases=await evaluate('auditPhases('+maxTicks+','+fps+')');
    const ids=new Map(), overlays=[];
    let background;
    for(const [tick,signature] of phases.entries()){
      if(ids.has(signature))continue;
      const layer=await evaluate('auditLayerAt('+tick+','+fps+')');
      assert.equal(layer.signature,signature);
      assert.deepEqual(layer.size,stage,'Native/UI stage dimensions disagree');
      if(!background){
        const file=path.join(output,'background.png');savePNG(file,layer.background);background=identity(file);
      }
      const phase=overlays.length;ids.set(signature,phase);
      const file=path.join(output,'overlay-'+phase+'.png');
      savePNG(file,layer.overlay);overlays.push(identity(file));
    }
    return {background,overlays,tickLayers:phases.map(signature=>ids.get(signature))};
  });
  const file=path.join(output,'LAYERS.json');
  write(file,{schemaVersion:1,kind:'gacha-ui-layers',packedMovie:movie.html,stage,nativeMask,fps,...result});
  return {layers:identity(file),phaseCount:result.overlays.length};
}

function completeHTML(ctx) {
  const html=identity(ctx.out('html')), receipt=read(ctx.out('receipt'));
  assert.equal(receipt.html.sha256,html.sha256,'Final HTML changed since assembly');
  assert.deepEqual(receipt.featureOrder,ctx.order);
  return {html,receipt};
}

async function browser(ctx) {
  const {html,receipt}=completeHTML(ctx);
  const output=ctx.out('browserDir');
  const result=await withBrowser(ctx,output,180000,async(call,evaluate)=>{
    await call('Page.navigate',{url:pathToFileURL(html.file).href});
    await ready(evaluate);
    const verified=await evaluate(`(async()=>{
      const d=ReviewData,r=review,screen=document.getElementById('screen'),continuous=document.getElementById('continuous');
      const expected=${JSON.stringify(ctx.order.map(entry=>entry.page))};
      const check=(ok,name)=>{if(!ok)throw Error(name)};
      const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
      const until=async test=>{for(let n=0;n<60&&!test();n++)await wait(40);return test()};
      const clips=d.pageOrder.filter(key=>d.pages[key].nativeClip);
      check(JSON.stringify(d.pageOrder)===JSON.stringify(expected),'Page order changed');
      const samples=[];
      for(const [index,key] of d.pageOrder.entries()){
        const p=d.pages[key],clip=p.nativeClip;
        r.pause(true);
        const middle=Math.floor(p.frameCount/2);
        await r.renderAt(key,middle);
        check(r.state().key===key&&r.state().frame===middle,'Page/seek failed '+key);
        if(!clip)continue;
        await r.renderAt(key,p.frameCount-1);
        check(r.state().skill.frame===clip.lastFrame,'Native last frame failed '+key);
        await r.replay();
        check(await until(()=>r.state().frame>0),'Native replay failed '+key);
        r.pause(true);
        const paused=r.state().frame;
        await wait(120);
        check(r.state().frame===paused,'Pause failed '+key);
        await r.renderAt(key,Math.max(0,p.frameCount-10));
        r.pause(false);
        check(await until(()=>r.state().key===expected[(index+1)%expected.length]),'Native ended did not advance '+key);
        samples.push({key,paused,firstFrame:clip.firstFrame,lastFrame:clip.lastFrame});
      }
      r.pause(true);
      const key=clips.find(id=>d.pages[id].frameCount>=60)??clips[0], p=d.pages[key];
      const speeds=document.getElementById('speed');
      const advance=async value=>{
        await r.renderAt(key,0);
        speeds.value=String(value);speeds.dispatchEvent(new Event('change'));
        r.pause(false);await wait(Math.min(400,p.frameCount*6));r.pause(true);
        return r.state().key===key?r.state().frame:NaN;
      };
      const halfAdvance=await advance(.5),fullAdvance=await advance(1);
      check(halfAdvance>0&&fullAdvance>halfAdvance,'Half speed failed');
      const ui=document.getElementById('ui');
      ui.click();check(screen.height===${receipt.stageMask[1]+receipt.stageMask[3]},'Native viewport height');
      ui.click();check(screen.height===d.stage.uiHeight,'UI stage height');
      const bounds=screen.getBoundingClientRect();
      const click=(x,y)=>screen.dispatchEvent(new MouseEvent('click',{clientX:bounds.left+x*bounds.width/screen.width,clientY:bounds.top+y*bounds.height/screen.height}));
      const index=expected.indexOf(key);
      click(screen.width-60,785);check(r.state().key===expected[(index+1)%expected.length],'Right arrow');
      click(30,785);check(r.state().key===key,'Left arrow');
      const posterByRole=Object.fromEntries(d.skillPresentation.characters.map(role=>[role.id,role.posterPage]));
      const footerSelections=[];
      for(const [i,role] of d.footerOrder.entries()){
        await r.renderAt(key,0);
        click(d.calibration.upOrigins[i],d.calibration.upY);
        check(r.state().key===posterByRole[role],'Footer selection '+role);
        footerSelections.push(role);
      }
      const unchanged=r.state().key;
      click(screen.width/2,1575);check(r.state().key===unchanged,'Draw button triggered navigation');
      const roleButtons=[...document.querySelectorAll('#rolePicker button')];
      check(roleButtons.length===Object.keys(posterByRole).length,'Role controls');
      for(const button of roleButtons){
        button.click();check(r.state().key===posterByRole[button.dataset.role]&&button.getAttribute('aria-pressed')==='true','Role button '+button.dataset.role);
      }
      const picker=document.getElementById('page');
      picker.value=key;picker.dispatchEvent(new Event('change'));
      check(r.state().key===key,'Page selector');
      const seek=document.getElementById('seek'),tick=Math.min(30,p.frameCount-2);
      seek.value=String(tick);seek.dispatchEvent(new Event('input'));
      check(await until(()=>r.state().skill?.frame===tick),'Timeline seek');
      document.getElementById('prev').click();check(await until(()=>r.state().skill?.frame===tick-1),'Previous frame');
      document.getElementById('next').click();check(await until(()=>r.state().skill?.frame===tick),'Next frame');
      const play=document.getElementById('play');play.click();
      check(await until(()=>r.state().frame>tick),'Play button');play.click();
      const guide=document.getElementById('guides');guide.click();check(guide.checked,'Guide toggle');guide.click();
      check(continuous.checked&&!document.documentElement.dataset.mediaError,'Media state');
      return {pageOrder:expected,samples,halfAdvance,fullAdvance,footerSelections,
        roleButtons:roleButtons.map(button=>button.dataset.role),uiAndNavigationChecked:true};
    })()`);
    const shots=[];
    for(const entry of ctx.order){
      const {tick,data}=await evaluate(`(async()=>{
        const page=${JSON.stringify(entry.page)},p=ReviewData.pages[page];
        const cast=p.nativeClip?.events.find(event=>event.type==='executionObserved');
        const tick=Math.min(p.frameCount-1,${entry.screenshotTick??'cast ? cast.frame + 12 : Math.floor(p.frameCount / 2)'});
        await review.renderAt(page,tick);
        const src=document.getElementById('screen'),c=document.createElement('canvas');
        c.width=src.width/2;c.height=src.height/2;c.getContext('2d').drawImage(src,0,0,c.width,c.height);
        return {tick,data:c.toDataURL('image/webp',.88)};
      })()`);
      const file=path.join(output,'page-'+String(shots.length).padStart(2,'0')+'.webp');
      savePNG(file,data);shots.push({page:entry.page,tick,...identity(file)});
    }
    return {...verified,shots};
  });
  const file=path.join(output,'browser-receipt.json');
  const {exceptions,network,...observations}=result;
  write(file,{schemaVersion:1,kind:'gacha-skill-browser-check',source:html.file,sourceSHA256:html.sha256,
    html,result:observations,exceptions,network});
  return {browser:identity(file),pageCount:result.pageOrder.length};
}

async function record(ctx) {
  const {html,receipt}=completeHTML(ctx);
  const output=ctx.out('recordDir');
  const expected=ctx.order.map(entry=>entry.page);
  const nativeSeconds=receipt.clips.reduce((n,clip)=>n+(clip.lastFrame-clip.firstFrame+1)/receipt.fps,0);
  const timeout=ctx.config.limits?.recordTimeoutMs??Math.max(120000,Math.ceil(nativeSeconds*1000)+80000);
  const result=await withBrowser(ctx,output,timeout+60000,async(call,evaluate)=>{
    await call('Page.navigate',{url:pathToFileURL(html.file).href});
    await ready(evaluate);
    const info=await evaluate(`(async()=>{
      const r=review,source=document.getElementById('screen'),canvas=document.createElement('canvas');
      canvas.width=source.width/2;canvas.height=source.height/2;
      const ctx=canvas.getContext('2d'),stream=canvas.captureStream(30);
      const recorder=new MediaRecorder(stream,{mimeType:'video/webm;codecs=vp9',videoBitsPerSecond:2500000});
      const chunks=[];
      const stopped=new Promise((resolve,reject)=>{
        recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};
        recorder.onstop=resolve;recorder.onerror=e=>reject(e.error);
      });
      const order=${JSON.stringify(expected)},pages=[{page:order[0],ms:0}];
      r.pause(true);await r.renderAt(order[0],0);
      const draw=()=>ctx.drawImage(source,0,0,canvas.width,canvas.height);
      draw();const start=performance.now();
      recorder.start(250);r.pause(false);
      try {
        await new Promise((resolve,reject)=>{
          let last=0;
          const next=now=>{
            if(now-start>${timeout}){reject(Error('Entire review timed out'));return}
            if(now-last>=30){draw();last=now}
            const key=r.state().key;
            if(key!==pages.at(-1).page){
              if(key===order[0]&&pages.length===order.length){resolve();return}
              if(key!==order[pages.length]){reject(Error('Unexpected page '+key));return}
              pages.push({page:key,ms:Math.round(now-start)});
            }
            requestAnimationFrame(next);
          };
          requestAnimationFrame(next);
        });
      } finally {r.pause(true);recorder.stop()}
      await stopped;
      const blob=new Blob(chunks,{type:'video/webm'});
      window.fullPreviewBase64=await new Promise((resolve,reject)=>{
        const reader=new FileReader();
        reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=reject;reader.readAsDataURL(blob);
      });
      stream.getTracks().forEach(track=>track.stop());
      return {pages,elapsedMs:Math.round(performance.now()-start),base64Length:window.fullPreviewBase64.length};
    })()`);
    const webm=path.join(output,'browser-capture.webm'),fd=fs.openSync(webm,'wx');
    try {
      for(let start=0;start<info.base64Length;start+=500000){
        const part=await evaluate('window.fullPreviewBase64.slice('+start+','+(start+500000)+')');
        fs.writeSync(fd,Buffer.from(part,'base64'));
      }
    } finally {fs.closeSync(fd)}
    const mp4=path.join(output,ctx.config.output.recordName??'performance.mp4');
    assert.equal(path.dirname(mp4),output,'Record name must stay inside its directory');
    invoke(ctx.tools.ffmpeg,['-v','error','-n','-i',webm,'-c:v','libx264','-preset','fast','-crf','20',
      '-pix_fmt','yuv420p','-movflags','+faststart',mp4]);
    invoke(ctx.tools.ffmpeg,['-v','error','-i',mp4,'-f','null','-']);
    const stream=JSON.parse(invoke(ctx.tools.ffprobe,['-v','error','-show_streams','-of','json',mp4])).streams[0];
    assert.equal(stream.codec_name,'h264');
    assert(Number(stream.duration)>nativeSeconds,'Recording is shorter than native skills');
    return {pages:info.pages,elapsedMs:info.elapsedMs,video:identity(mp4),seconds:Number(stream.duration),
      width:stream.width,height:stream.height};
  });
  const file=path.join(output,'browser-receipt.json');
  const {exceptions,network,...observations}=result;
  write(file,{schemaVersion:1,kind:'gacha-skill-full-performance-record',source:html.file,sourceSHA256:html.sha256,
    html,result:{...observations,mp4:result.video.file,sha256:result.video.sha256},exceptions,network});
  return {record:identity(file),video:result.video,seconds:result.seconds,pageCount:result.pages.length};
}

module.exports={layers,browser,record};
