// Insert into the compact review bootstrap before the preserved Movie player.
const clips = JSON.parse(document.getElementById('native-recordings').textContent);
const presentation = JSON.parse(document.getElementById('skill-presentation').textContent);
const clipByRole = new Map(clips.clips.map(clip => [clip.roleId, clip]));
const posters = new Map(presentation.characters.map(role => [role.id, role.posterPage]));
const profileIdFor = new Map(presentation.characters.map(role => [role.posterPage, role.id]));
model.pageOrder = presentation.order.map(entry => entry.page);
model.skillPresentation = presentation;
for (const entry of presentation.order.filter(entry => entry.kind === 2)) {
  const roleId = entry.roleId;
  const role = presentation.characters.find(role => role.id === roleId);
  const clip = clipByRole.get(roleId);
  if (!clip || !role) throw Error('缺少角色原生录像：' + roleId);
  const frameCount = clip.lastFrame - clip.firstFrame + 1;
  const profile = model.profiles[roleId] ?? model.profiles[role.posterPage];
  model.pages[entry.page] = {
    label: entry.label ?? [role.name, profile?.skill ?? '主动技能'].join(' · '),
    characterId: roleId, frameCount, cells: [], frames: [],
    timeline: {sequences: [{name: '原生主动技能', begin: 1, end: frameCount}]},
    nativeClip: clip,
  };
}

const continuous = document.getElementById('continuous');
const recordingClock = document.getElementById('recordingClock');
let navigation = 0;
let opening = Promise.resolve();
function reportMediaError(error) {
  document.documentElement.dataset.mediaError = error.message;
  document.getElementById('ready').textContent = error.message;
  pause(true);
}
const nativeMedia = window.createNativeClipPlayer(clips, {
  onFrame(capture) {
    const clip = D.pages[key].nativeClip;
    if (!clip || clip.roleId !== capture.roleId) return;
    frame = capture.frame - clip.firstFrame;
    seconds = frame / clips.fps;
    draw();
  },
  onEnd(roleId) {
    if (!playing || D.pages[key].nativeClip?.roleId !== roleId) return;
    cycles++;
    if (continuous.checked) select(keys[(keys.indexOf(key) + 1) % keys.length]);
    else replay();
  },
  onError: reportMediaError,
});

function openCapture(clip) {
  const active = ++navigation;
  nativeMedia.clear();
  opening = clip ? (async () => {
    await nativeMedia.show(clip.roleId);
    if (active === navigation && playing) await nativeMedia.play(speed);
  })() : Promise.resolve();
  opening.catch(reportMediaError);
  return opening;
}

function updateCaptureClock(page) {
  const clip = page.nativeClip;
  recordingClock.hidden = !clip;
  if (!clip) return;
  const captureFrame = clip.firstFrame + frame;
  const event = clip.events.filter(event => event.frame <= captureFrame).at(-1);
  recordingClock.textContent = '捕获帧 ' + captureFrame + ' / ' + clip.lastFrame +
    (event ? ' · ' + event.kind + '（战斗帧 ' + (event.battleFrame ?? event.frame) + '）' : '');
}

async function renderAt(page, tick) {
  if (key !== page) await select(page);
  await go(tick);
}
