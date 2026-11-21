'use strict';

const video = document.querySelector('#video');
const screenEl = document.querySelector('#screen');
const start = document.querySelector('#start');
const fullscreen = document.querySelector('#fullscreen');
const exit = document.querySelector('#exit');
const previous = document.querySelector('#previous');
const next = document.querySelector('#next');
const replay = document.querySelector('#replay');
const jump = document.querySelector('#jump');
const input = document.querySelector('#number');
const jumpButton = document.querySelector('#jump-button');
const position = document.querySelector('#position');
const notice = document.querySelector('#notice');
const STORAGE = 'low-voltage-board-question';
const chapters = [];
const groups = [];
let current = 0;
let source = -1;
let pending = null;

function storage(value) {
  try {
    if (value === undefined) return localStorage.getItem(STORAGE);
    localStorage.setItem(STORAGE, String(value));
  } catch {
    return null;
  }
  return null;
}

function updatePosition(index) {
  const chapter = chapters[index];
  if (!chapter) return;
  current = index;
  position.textContent = '第 ' + chapter.id + ' 题 / 共 ' + chapters.length + ' 题';
  if (document.activeElement !== input) input.value = chapter.id;
  previous.disabled = index === 0;
  next.disabled = index === chapters.length - 1;
  storage(chapter.id);
}

function play() {
  notice.textContent = '';
  const attempt = video.play();
  attempt?.catch(error => {
    if (error.name === 'AbortError') return;
    start.hidden = false;
    notice.textContent = '请点播放继续。';
  });
}

function select(index, autoplay = false) {
  if (!chapters[index]) return;
  const chapter = chapters[index];
  updatePosition(index);
  input.value = chapter.id;
  notice.textContent = '';
  pending = chapter;
  if (source !== chapter.group) {
    source = chapter.group;
    video.src = './media/' + groups[source].file;
  }
  applySeek();
  if (autoplay) play();
}

function applySeek() {
  if (!pending || video.readyState < 1) return;
  const chapter = pending;
  pending = null;
  if (Math.abs(chapter.start - video.currentTime) > 0.03) video.currentTime = chapter.start;
}

function syncPosition() {
  if (pending || video.seeking || source < 0) return;
  const group = groups[source];
  if (!group) return;
  const time = video.currentTime;
  let low = group.first;
  let high = group.last + 1;
  while (low + 1 < high) {
    const middle = (low + high) >> 1;
    if (chapters[middle].start <= time + 0.025) low = middle;
    else high = middle;
  }
  if (low !== current) updatePosition(low);
}

function expanded(enabled) {
  screenEl.classList.toggle('expanded', enabled);
  document.body.classList.toggle('overview-expanded', enabled);
}

function landscapeFullscreen() {
  if (document.fullscreenElement || document.webkitFullscreenElement || video.webkitDisplayingFullscreen || screenEl.classList.contains('expanded')) return;
  const request = screenEl.requestFullscreen || screenEl.webkitRequestFullscreen;
  if (request) {
    try {
      Promise.resolve(request.call(screenEl))
        .then(() => window.screen.orientation?.lock?.('landscape')?.catch(() => {}))
        .catch(() => expanded(true));
      return;
    } catch {
      expanded(true);
      return;
    }
  }
  // On iPhone a portrait viewport can still show the 16:9 player rotated inline.
  if (matchMedia('(orientation: portrait) and (pointer: coarse)').matches) {
    expanded(true);
    return;
  }
  if (video.webkitSupportsFullscreen && video.webkitEnterFullscreen) {
    try {
      video.webkitEnterFullscreen();
      return;
    } catch {
      // Inline fullscreen is also available when the surrounding app blocks native fullscreen.
    }
  }
  expanded(true);
}

function startFullscreen() {
  if (source < 0) return;
  play();
  landscapeFullscreen();
}

start.addEventListener('click', startFullscreen);
fullscreen.addEventListener('click', startFullscreen);
exit.addEventListener('click', () => {
  if (screenEl.classList.contains('expanded')) expanded(false);
  else if (document.fullscreenElement) document.exitFullscreen();
  else document.webkitExitFullscreen?.();
  window.screen.orientation?.unlock?.();
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && screenEl.classList.contains('expanded')) expanded(false);
});
previous.addEventListener('click', () => select(current - 1, !video.paused));
next.addEventListener('click', () => select(current + 1, !video.paused));
replay.addEventListener('click', () => select(current, true));
jump.addEventListener('submit', event => {
  event.preventDefault();
  const number = Number(input.value);
  const index = chapters.findIndex(chapter => chapter.id === number);
  if (index < 0) {
    notice.textContent = '请输入 1 到 ' + chapters.length + ' 之间的题号。';
    return;
  }
  select(index, !video.paused);
});
video.addEventListener('loadedmetadata', applySeek);
video.addEventListener('timeupdate', syncPosition);
video.addEventListener('seeked', syncPosition);
video.addEventListener('playing', () => { start.hidden = true; });
video.addEventListener('ended', () => {
  if (groups[source].last + 1 < chapters.length) select(groups[source].last + 1, true);
  else notice.textContent = '全部题目已播放完。';
});
video.addEventListener('error', () => {
  notice.textContent = '视频加载失败。请重播本题或刷新后重试。';
  start.hidden = false;
});

fetch('./media/index.json')
  .then(response => {
    if (!response.ok) throw Error('media index missing');
    return response.json();
  })
  .then(manifest => {
    for (const [file, entries] of manifest) {
      const first = chapters.length;
      for (const [id, time] of entries) chapters.push({id, start:time, group:groups.length});
      groups.push({file, first, last:chapters.length - 1});
    }
    if (!chapters.length) throw Error('empty media index');
    const target = Number(new URLSearchParams(location.search).get('q') || storage());
    const index = chapters.findIndex(chapter => chapter.id === target);
    input.max = chapters.at(-1).id;
    for (const control of [start, fullscreen, replay, input, jumpButton]) control.disabled = false;
    select(Math.max(0,index));
  })
  .catch(() => { position.textContent = '题库载入失败，请刷新重试。'; });
