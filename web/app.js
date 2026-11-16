"use strict";
// YouMixer's page: everything the user sees and does. The server (server.py) keeps the data and talks to YouTube.
const $ = (id) => document.getElementById(id);
const esc = (text) => String(text ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

// Languages: texts live in web/i18n/<language>.json; English fills in whatever is missing
const LANG_STORAGE = "youmixer-lang";
const IN_WINDOW = new URLSearchParams(location.search).has("window");
const i18n = { lang: "es", dict: {}, fallback: {} };

function t(key, vars = {}) {
  const text = i18n.dict[key] ?? i18n.fallback[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (match, name) => (name in vars ? vars[name] : match));
}

function tn(key, count, vars = {}) {
  return t(`${key}.${count === 1 ? "one" : "other"}`, { count, ...vars });
}

// Static texts are declared in the HTML: data-i18n (text), data-i18n-html (text with markup)
// and data-i18n-attr ("attribute:key" pairs separated by ";").
function applyI18n(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  root.querySelectorAll("[data-i18n-html]").forEach((el) => { el.innerHTML = t(el.dataset.i18nHtml); });
  root.querySelectorAll("[data-i18n-attr]").forEach((el) => {
    el.dataset.i18nAttr.split(";").forEach((pair) => {
      const [attr, key] = pair.split(":");
      el.setAttribute(attr, t(key));
    });
  });
}

function guessLanguage() {
  try {
    const saved = localStorage.getItem(LANG_STORAGE);
    if (saved) return saved;
  } catch {
    // No browser storage: guess from the browser's language
  }
  return (navigator.language || "en").toLowerCase().startsWith("es") ? "es" : "en";
}

async function loadLanguage(lang) {
  const get = (code) => fetch(`/i18n/${code}.json`).then((r) => (r.ok ? r.json() : {})).catch(() => ({}));
  const [dict, fallback] = await Promise.all([get(lang), lang === "en" ? {} : get("en")]);
  i18n.lang = Object.keys(dict).length ? lang : "en";
  i18n.dict = Object.keys(dict).length ? dict : fallback;
  i18n.fallback = fallback;
  try { localStorage.setItem(LANG_STORAGE, i18n.lang); } catch { /* only a convenience for the offline page */ }
  document.documentElement.lang = i18n.lang;
  applyI18n();
  document.documentElement.classList.remove("i18n-pending");
}

// Changes language in place, without reloading, so the video keeps playing
async function switchLanguage(lang) {
  if (lang === i18n.lang) return;
  await loadLanguage(lang);
  renderSources();
  renderQueue();
  renderNow();
  renderModes();
  renderToggle(playback.playing);
  renderExplore();
  renderProfileKey();
  renderWindowToggle();
  updateBookmarklet();
  updatePowerLabel();
  if (state.settings) renderSettings(state.settings);
  if ($("welcome").open) renderTour();
  const open = [...document.querySelectorAll("#drawer section")].find((section) => !section.hidden);
  if ($("drawer").open && open) {
    $("drawer-title").textContent = open.dataset.title;
    if (open.id === "section-activity") await renderActivity();
    if (open.id === "section-profiles") await renderProfiles();
  }
}

const KIND_KEY = { playlist: "type.playlist", mix: "type.mix", saved: "type.saved" };
const DISCOVERY_EXPLORE = 80;

function sourceType(source) {
  if (source.kind !== "generated") return KIND_KEY[source.kind] ? t(KIND_KEY[source.kind]) : source.kind;
  const params = source.meta.params || {};
  return t(!params.terms?.length && params.explore >= DISCOVERY_EXPLORE ? "type.discovery" : "type.custom");
}
const SKIP_ALWAYS_FINISH = 0.8;
const AUTOPLAY_WAIT_MS = 5000;
const STALL_WAIT_MS = 60000;
const MAX_ERRORS_IN_A_ROW = 3;
const SIDE_DEFAULT = 420;
const SIDE_MIN = 280;
const STAGE_MIN = 360;

const state = {
  sources: [], queue: [], index: 0, reactions: {}, selected: new Set(), sourceIds: [], shuffle: true, repeat: "off",
  profile: null, settings: null,
};
const REPEAT_MODES = ["off", "all", "one"];
const YEAR_KEY = { copyright: "year.copyright", released: "year.released", upload: "year.upload" };
const KIND_CLASS = { playlist: "playlist", mix: "mix", generated: "generated", saved: "saved" };
const svg = (body, { size = 22, fill = false } = {}) => `<svg viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true" `
  + (fill ? 'fill="currentColor">' : 'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">')
  + `${body}</svg>`;
const ICONS = {
  play: svg('<path d="M7 4l13 8-13 8z"/>', { size: 24, fill: true }),
  pause: svg('<path d="M6 4h4.4v16H6zM13.6 4H18v16h-4.4z"/>', { size: 24, fill: true }),
  repeat: svg('<path d="M4 11V9a3 3 0 0 1 3-3h12"/><path d="M16 3l3 3-3 3"/><path d="M20 13v2a3 3 0 0 1-3 3H5"/><path d="M8 21l-3-3 3-3"/>'),
  repeatOne: svg('<path d="M4 11V9a3 3 0 0 1 3-3h12"/><path d="M16 3l3 3-3 3"/><path d="M20 13v2a3 3 0 0 1-3 3H5"/><path d="M8 21l-3-3 3-3"/><path d="M11.5 10.5l1.5-1v5"/>'),
  playSmall: svg('<path d="M7 4l13 8-13 8z"/>', { size: 15, fill: true }),
  refresh: svg('<path d="M20 12a8 8 0 1 1-2.3-5.7"/><path d="M20 4v5h-5"/>', { size: 15 }),
  rename: svg('<path d="M4 20h4L19 9l-4-4L4 16z"/>', { size: 15 }),
  remove: svg('<path d="M6 6l12 12M18 6L6 18"/>', { size: 15 }),
  keep: svg('<path d="M5 12.5l4.5 4.5L19 7.5"/>', { size: 15 }),
  ban: svg('<circle cx="12" cy="12" r="8"/><path d="M6.5 6.5l11 11"/>', { size: 15 }),
  current: svg('<path d="M7 4l13 8-13 8z"/>', { size: 14, fill: true }),
  window: svg('<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M7 6.5h.01M10 6.5h.01"/>', { size: 21 }),
  browser: svg('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z"/>', { size: 21 }),
};
const playback = { player: null, ready: false, started: false, playing: false, errors: 0, watchdog: null, resume: 0 };

async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || t("common.failed"));
  return data;
}

function toast(text) {
  const box = $("toast");
  box.textContent = text;
  box.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { box.hidden = true; }, 5000);
}

function notice(text) {
  $("notice").textContent = text || "";
  $("notice").hidden = !text;
}

async function runJob(job, button) {
  if (button) button.disabled = true;
  try {
    let current = job;
    while (current.status === "running") {
      toast(current.message);
      await new Promise((done) => setTimeout(done, 700));
      current = await api(`/api/jobs/${job.id}`);
    }
    if (current.status === "error") throw new Error(current.message);
    return current.result;
  } finally {
    if (button) button.disabled = false;
  }
}

// Wraps a handler so any failure ends up as a message on screen instead of a silent error
const guarded = (fn) => async (event) => {
  if (event?.type === "submit") event.preventDefault();
  try { await fn(event); } catch (error) { toast(error.message); }
};

function ask(text, value = "") {
  return new Promise((resolve) => {
    const dialog = $("ask");
    $("ask-text").textContent = text;
    $("ask-input").value = value;
    dialog.returnValue = "";
    dialog.addEventListener("close", () => {
      resolve(dialog.returnValue === "ok" ? $("ask-input").value.trim() : null);
    }, { once: true });
    dialog.showModal();
  });
}

// Deleting asks the user to type a word, so it can't happen by a stray click
async function confirmDelete(prompt) {
  const word = t("confirm.word");
  return (await ask(prompt(word)))?.toUpperCase() === word;
}

// Lists
async function refreshSources() {
  const data = await api("/api/bootstrap");
  state.sources = data.sources;
  state.reactions = data.reactions;
  state.selected = new Set([...state.selected].filter((id) => data.sources.some((s) => s.id === id)));
  renderSources();
  renderSettings(data.settings);
}

function renderSources() {
  $("sources-empty").hidden = state.sources.length > 0;
  $("sources").innerHTML = state.sources.map((s) => `
    <li class="tape">
      <button class="select" data-select="${s.id}" aria-pressed="${state.selected.has(s.id)}"
              aria-label="${esc(t("tape.select_aria", { name: s.name }))}" title="${esc(t("tape.select_title"))}">
        <span class="select-label" aria-hidden="true">${esc(t("tape.mix_label"))}</span>
        <span class="slot" aria-hidden="true"><span class="knob"></span></span>
        <span class="led" aria-hidden="true"></span>
      </button>
      <div class="tape-label ${KIND_CLASS[s.kind] || ""}">
        <strong>${esc(s.name)}</strong>
        <span class="kind">${esc(t("tape.songs", { type: sourceType(s), count: s.count }))}</span>
        ${s.meta.target ? `<label class="switch"><input type="checkbox" role="switch" data-auto="${s.id}" ${s.auto_update ? "checked" : ""}>
          <span class="track" aria-hidden="true"></span>${esc(t("tape.auto"))}</label>` : ""}
      </div>
      <div class="tape-actions">
        <button data-act="play" data-id="${s.id}" aria-label="${esc(t("common.play_aria", { name: s.name }))}" title="${esc(t("common.play"))}">${ICONS.playSmall}</button>
        ${s.meta.target ? `<button data-act="refresh" data-id="${s.id}" aria-label="${esc(t("common.refresh_aria", { name: s.name }))}" title="${esc(t("common.refresh_title"))}">${ICONS.refresh}</button>` : ""}
        <button data-act="rename" data-id="${s.id}" aria-label="${esc(t("common.rename_aria", { name: s.name }))}" title="${esc(t("common.rename"))}">${ICONS.rename}</button>
        <button data-act="delete" data-id="${s.id}" aria-label="${esc(t("common.delete_aria", { name: s.name }))}" title="${esc(t("common.delete"))}">${ICONS.remove}</button>
      </div>
    </li>`).join("");
  renderSelection();
}

function renderSelection() {
  const count = state.selected.size;
  // The selection bar takes the place of the link field, so nothing below moves
  $("selection-bar").hidden = count === 0;
  $("import-form").hidden = count > 0;
  $("selection-count").textContent = tn("lists.selection", count);
  $("create-sources").textContent = count ? tn("create.from", count) : t("create.from.none");
}

$("sources").addEventListener("change", guarded(async (event) => {
  const autoId = Number(event.target.dataset.auto);
  if (autoId) {
    await api(`/api/sources/${autoId}/auto`, { value: event.target.checked });
    const source = state.sources.find((s) => s.id === autoId);
    if (source) source.auto_update = event.target.checked;
    toast(t(event.target.checked ? "lists.auto_on" : "lists.auto_off"));
  }
}));

async function watchAutoUpdate(jobId) {
  let job;
  do {
    await new Promise((done) => setTimeout(done, 3000));
    job = await api(`/api/jobs/${jobId}`);
  } while (job.status === "running");
  if (job.status !== "done") return;
  const { count, failed } = job.result;
  if (count) toast(t("lists.auto_updated", { count }));
  if (failed.length) toast(t("lists.auto_failed", { names: failed.join(", ") }));
  if (count) await refreshSources();
}

$("sources").addEventListener("click", guarded(async (event) => {
  const select = event.target.closest("button[data-select]");
  if (select) {
    const id = Number(select.dataset.select);
    state.selected.has(id) ? state.selected.delete(id) : state.selected.add(id);
    select.setAttribute("aria-pressed", state.selected.has(id));
    renderSelection();
    return;
  }
  const button = event.target.closest("button[data-act]");
  if (!button) return;
  const id = Number(button.dataset.id);
  const source = state.sources.find((s) => s.id === id);
  const action = button.dataset.act;
  if (action === "play") {
    applyQueue(await api(`/api/sources/${id}/play`, { shuffle: state.shuffle }), true);
    return;
  } else if (action === "refresh") {
    const result = await runJob(await api(`/api/sources/${id}/refresh`, {}), button);
    toast(t("lists.updated", { count: result.count }));
  } else if (action === "rename") {
    const name = await ask(t("lists.rename_prompt"), source.name);
    if (name) await api(`/api/sources/${id}/rename`, { name });
  } else if (action === "delete") {
    if (!(await confirmDelete((word) => t("lists.delete_prompt", { word, name: source.name })))) return;
    await api(`/api/sources/${id}/delete`, {});
  }
  await refreshSources();
}));

$("import-form").addEventListener("submit", guarded(async () => {
  const url = $("import-url").value.trim();
  if (!url) return;
  const result = await runJob(await api("/api/import", { url }), $("import-form").querySelector("button"));
  $("import-url").value = "";
  toast(t("lists.saved", { count: result.count }));
  state.selected.add(result.source_id);
  await refreshSources();
}));

$("clear-selection").addEventListener("click", () => {
  state.selected.clear();
  renderSources();
  $("import-url").focus();
});

$("shuffle-selected").addEventListener("click", guarded(async () => {
  applyQueue(await api("/api/shuffle", { source_ids: [...state.selected] }), true);
  if (!state.shuffle) { state.shuffle = true; renderModes(); saveModes(); }
  toast(t("lists.shuffled"));
}));

async function generate(params, button) {
  const result = await runJob(await api("/api/generate", params), button);
  closeDrawer();
  applyQueue(result, true);
  toast(t("create.done", { name: result.name, count: result.count }));
  await refreshSources();
}

$("discover-selected").addEventListener("click", guarded((event) =>
  generate({ source_ids: [...state.selected], explore: 100, size: 50 }, event.currentTarget)));
$("discover-profile").addEventListener("click", guarded((event) =>
  generate({ explore: 100, size: 50 }, event.currentTarget)));

$("create-form").addEventListener("submit", guarded(async () => {
  const genres = [...document.querySelectorAll("#genres input:checked")].map((input) => input.value);
  const terms = genres.concat($("terms").value.split(",").map((term) => term.trim()).filter(Boolean));
  await generate({
    terms, source_ids: [...state.selected], explore: Number($("explore").value), size: Number($("size").value),
  }, $("create-form").querySelector("button.red"));
}));

function renderExplore() {
  const value = Number($("explore").value);
  $("explore-label").textContent = t("create.explore", { new: value, known: 100 - value });
}
$("explore").addEventListener("input", renderExplore);

// Queue and playback
function applyQueue(data, autoplay) {
  state.queue = data.queue;
  state.index = Math.min(data.player.index || 0, Math.max(0, data.queue.length - 1));
  state.sourceIds = data.player.source_ids || [];
  playback.resume = autoplay ? 0 : data.player.time || 0;
  renderQueue();
  if (autoplay) showPane("queue");
  if (state.queue.length) loadCurrent(autoplay);
}

function queueType() {
  const sources = state.sourceIds.map((id) => state.sources.find((s) => s.id === id)).filter(Boolean);
  if (sources.length > 1) return t("type.blend", { count: sources.length });
  return sources.length ? sourceType(sources[0]) : t("type.queue");
}

function queueName() {
  const names = state.sourceIds.map((id) => state.sources.find((s) => s.id === id)?.name).filter(Boolean);
  if (!names.length) return t("type.queue");
  return names.length > 2 ? t("queue.name_more", { first: names.slice(0, 2).join(" + "), more: names.length - 2 }) : names.join(" + ");
}

function renderQueue() {
  const count = state.queue.length;
  // With an empty queue the header says so and explains what to do
  $("queue-name").textContent = count ? queueName() : t("queue.empty_title");
  $("queue-count").textContent = count ? t("queue.position", { type: queueType(), index: state.index + 1, count }) : "";
  $("queue-count").hidden = count === 0;
  $("queue").style.setProperty("--pos-width", `${String(count).length}ch`);
  $("queue-badge").textContent = count ? `· ${count}` : "";
  $("queue-empty").hidden = count > 0;
  $("save-queue").hidden = count === 0;
  $("video-empty").hidden = count > 0;
  $("queue").innerHTML = state.queue.map((track, i) => `
    <li class="clickable ${i === state.index ? "current" : ""}" data-index="${i}" tabindex="0"
        ${i === state.index ? 'aria-current="true"' : ""}>
      <span class="pos">${i === state.index ? ICONS.current : i + 1}</span>
      <div class="meta"><strong>${esc(track.title)}</strong><span>${esc(track.artist)}</span></div>
    </li>`).join("");
  document.querySelector("#queue .current")?.scrollIntoView({ block: "nearest" });
}

function currentTrack() { return state.queue[state.index]; }

function yearText(track) {
  return track?.year && YEAR_KEY[track.year_kind] ? t(YEAR_KEY[track.year_kind], { year: track.year }) : "";
}

async function loadYear(track) {
  if (!track || track.year_kind != null || track.yearAsked) return;
  track.yearAsked = true;  // once per song and session, even if it fails
  try {
    const { year, kind } = await api(`/api/year/${track.video_id}`);
    track.year = year;
    track.year_kind = kind;
    if (kind && currentTrack() === track) renderNow();
  } catch {
    // The display simply shows no year
  }
}

function renderModesDisplay() {
  $("now-modes").textContent = `${t(state.shuffle ? "display.shuffle" : "display.ordered")} · ${t(`repeat.${state.repeat}_display`)}`;
}

function clock(seconds) {
  const s = Math.max(0, Math.floor(seconds || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function renderProgress() {
  if (!playback.ready || !playback.player.getCurrentTime || !currentTrack()) {
    $("now-time").textContent = "";
    $("now-bar").style.width = "0";
    return;
  }
  const position = playback.player.getCurrentTime() || 0;
  const duration = playback.player.getDuration() || currentTrack().duration || 0;
  $("now-time").textContent = duration ? `${clock(position)} / ${clock(duration)}` : clock(position);
  $("now-bar").style.width = duration ? `${Math.min(100, (position / duration) * 100)}%` : "0";
}

function renderNow() {
  const track = currentTrack();
  $("now-title").textContent = track?.title || "";
  $("now-artist").textContent = [track?.artist, yearText(track)].filter(Boolean).join(" · ");
  $("now-pos").textContent = track ? t("display.track", { index: state.index + 1, count: state.queue.length }) : "";
  renderModesDisplay();
  renderProgress();
  loadYear(track);
  document.title = track ? `${track.title} · YouMixer` : "YouMixer";
  const reaction = track ? state.reactions[track.video_id] || 0 : 0;
  $("like").setAttribute("aria-pressed", reaction > 0);
  $("dislike").setAttribute("aria-pressed", reaction < 0);
  if (track && "mediaSession" in navigator) {
    navigator.mediaSession.metadata = new MediaMetadata({
      title: track.title, artist: track.artist, artwork: track.thumb ? [{ src: track.thumb }] : [],
    });
  }
}

function loadCurrent(autoplay) {
  const track = currentTrack();
  renderNow();
  if (!track || !playback.ready) return;
  playback.started = false;
  const options = { videoId: track.alt_video_id || track.video_id, startSeconds: playback.resume };
  clearWatchdogs();
  if (!autoplay) {
    playback.player.cueVideoById(options);
    return;
  }
  playback.player.loadVideoById(options);
  playback.watchdog = setTimeout(() => {
    if (!playback.started && !isBuffering()) notice(t("player.autoplay_blocked"));
  }, AUTOPLAY_WAIT_MS);
  playback.stall = setTimeout(() => {
    if (playback.started || !isBuffering()) return;
    toast(t("player.stalled", { title: track.title }));
    guarded(advance)();
  }, STALL_WAIT_MS);
}

function isBuffering() { return playback.player.getPlayerState() === YT.PlayerState.BUFFERING; }

function clearWatchdogs() {
  clearTimeout(playback.watchdog);
  clearTimeout(playback.stall);
}

function goTo(index, autoplay = true) {
  state.index = index;
  playback.resume = 0;
  notice("");
  renderQueue();
  saveState();
  loadCurrent(autoplay);
}

function reportLeaving() {
  const track = currentTrack();
  if (!track || !playback.started) return;
  const position = playback.player.getCurrentTime() || 0;
  const duration = playback.player.getDuration() || 0;
  const type = duration && position / duration >= SKIP_ALWAYS_FINISH ? "finish" : "skip";
  api("/api/event", { video_id: track.video_id, type, position, duration }).catch(() => {});
}

async function advance() {
  if (state.index + 1 < state.queue.length) return goTo(state.index + 1);
  if (state.repeat === "off") return notice(t("player.queue_ended"));
  if (state.shuffle && state.sourceIds.length) {
    applyQueue(await api("/api/shuffle", { source_ids: state.sourceIds, avoid_recent: true }), true);
    return toast(t("player.reshuffled"));
  }
  goTo(0);
}

// Shuffle and repeat
function renderModes() {
  $("shuffle").setAttribute("aria-pressed", state.shuffle);
  $("shuffle").title = t(state.shuffle ? "controls.shuffle_on_title" : "controls.shuffle_off_title");
  const label = t(`repeat.${state.repeat}`);
  $("repeat").innerHTML = state.repeat === "one" ? ICONS.repeatOne : ICONS.repeat;
  $("repeat").setAttribute("aria-pressed", state.repeat !== "off");
  $("repeat").setAttribute("aria-label", label);
  $("repeat").title = `${label} (R)`;
  renderModesDisplay();
}

function saveModes() { api("/api/ui", { shuffle: state.shuffle, repeat: state.repeat }).catch(() => {}); }

async function toggleShuffle() {
  state.shuffle = !state.shuffle;
  renderModes();
  saveModes();
  const track = currentTrack();
  if (!track) return;
  const data = await api("/api/queue/order", { shuffle: state.shuffle, video_id: track.video_id });
  state.queue = data.queue;
  state.index = data.player.index;
  renderQueue();
  toast(t(state.shuffle ? "player.shuffle_on" : "player.shuffle_off"));
}

function cycleRepeat() {
  state.repeat = { off: "all", all: "one", one: "off" }[state.repeat];
  renderModes();
  saveModes();
  toast(t(`repeat.${state.repeat}`));
}

function renderToggle(playing) {
  playback.playing = playing;
  $("toggle").innerHTML = playing ? ICONS.pause : ICONS.play;
  $("toggle").setAttribute("aria-label", t(playing ? "controls.pause" : "controls.play"));
  document.body.classList.toggle("playing", playing);
}

function saveState() {
  const time = playback.ready && playback.player.getCurrentTime ? playback.player.getCurrentTime() || 0 : 0;
  return api("/api/state", { index: state.index, time }).catch(() => {});
}

function onStateChange(event) {
  const track = currentTrack();
  renderToggle(event.data === YT.PlayerState.PLAYING || event.data === YT.PlayerState.BUFFERING);
  if (event.data === YT.PlayerState.PLAYING) {
    clearWatchdogs();
    playback.errors = 0;
    notice("");
    if (!playback.started && track) {
      playback.started = true;
      api("/api/event", { video_id: track.video_id, type: "play" }).catch(() => {});
    }
  } else if (event.data === YT.PlayerState.ENDED && track) {
    const duration = playback.player.getDuration() || 0;
    api("/api/event", { video_id: track.video_id, type: "finish", position: duration, duration }).catch(() => {});
    playback.started = false;
    if (state.repeat === "one") {
      playback.player.seekTo(0, true);
      playback.player.playVideo();
      return;
    }
    guarded(advance)();
  }
}

const KNOWN_ERRORS = [2, 5, 100, 101, 150, 153];

const onError = guarded(async (event) => {
  const track = currentTrack();
  if (!track) return;
  const code = event.data;
  const text = t(KNOWN_ERRORS.includes(code) ? `yterror.${code}` : "yterror.unknown");
  const reason = t("player.error_reason", { text, code });
  clearWatchdogs();
  playback.errors += 1;
  if ([100, 101, 150].includes(code)) toast(t("player.searching_alt", { title: track.title, reason }));
  const result = await api("/api/error", { video_id: track.video_id, code });
  if (result.action === "alt") {
    track.alt_video_id = result.play_id;
    toast(t("player.using_alt", { title: track.title, reason }));
    return loadCurrent(true);
  }
  if (playback.errors >= MAX_ERRORS_IN_A_ROW) {
    return notice(t("player.too_many_errors", { count: playback.errors, reason }));
  }
  toast(t("player.skipped", { title: track.title, reason }));
  await advance();
});

window.onYouTubeIframeAPIReady = () => {
  playback.player = new YT.Player("yt", {
    width: "100%", height: "100%",
    playerVars: { origin: location.origin, playsinline: 1, rel: 0, autoplay: 0 },
    events: {
      onReady: () => { playback.ready = true; if (currentTrack()) loadCurrent(false); },
      onStateChange, onError,
    },
  });
};

function toggle() {
  if (!playback.ready) return;
  const playing = playback.player.getPlayerState() === YT.PlayerState.PLAYING;
  playing ? playback.player.pauseVideo() : playback.player.playVideo();
}
function next() { if (state.queue.length) { reportLeaving(); guarded(advance)(); } }
function prev() { if (state.index > 0) { reportLeaving(); goTo(state.index - 1); } }

async function react(value) {
  const track = currentTrack();
  if (!track) return;
  const updated = state.reactions[track.video_id] === value ? 0 : value;
  await api("/api/react", { video_id: track.video_id, value: updated });
  if (updated) state.reactions[track.video_id] = updated; else delete state.reactions[track.video_id];
  renderNow();
  // A dislike moves on, but without also counting as a skip: it already weighs enough
  if (updated < 0 && state.queue.length) guarded(advance)();
}

$("toggle").addEventListener("click", toggle);
$("shuffle").addEventListener("click", guarded(toggleShuffle));
$("repeat").addEventListener("click", cycleRepeat);
$("next").addEventListener("click", next);
$("prev").addEventListener("click", prev);
$("like").addEventListener("click", guarded(() => react(1)));
$("dislike").addEventListener("click", guarded(() => react(-1)));
$("queue").addEventListener("click", (event) => {
  const item = event.target.closest("li[data-index]");
  if (item) { reportLeaving(); goTo(Number(item.dataset.index)); }
});
$("queue").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && event.target.dataset.index) { reportLeaving(); goTo(Number(event.target.dataset.index)); }
});
$("save-queue").addEventListener("click", guarded(async () => {
  const name = await ask(t("queue.save_prompt"));
  if (!name) return;
  await api("/api/queue/save", { name });
  toast(t("queue.saved"));
  await refreshSources();
}));

document.addEventListener("keydown", (event) => {
  if (event.target.closest("input, textarea, select, button, dialog, a, [tabindex]") || $("drawer").open || event.ctrlKey || event.altKey || event.metaKey) return;
  const actions = {
    " ": toggle, n: next, p: prev, l: () => react(1), d: () => react(-1), s: guarded(toggleShuffle), r: cycleRepeat,
  };
  const action = actions[event.key.toLowerCase()];
  if (action) { event.preventDefault(); action(); }
});
if ("mediaSession" in navigator) {
  navigator.mediaSession.setActionHandler("nexttrack", next);
  navigator.mediaSession.setActionHandler("previoustrack", prev);
}
setInterval(() => { if (playback.started) saveState(); }, 10000);
setInterval(renderProgress, 500);
window.addEventListener("pagehide", () => {
  if (playback.ready && playback.player.getCurrentTime) {
    navigator.sendBeacon("/api/state", new Blob(
      [JSON.stringify({ index: state.index, time: playback.player.getCurrentTime() || 0 })], { type: "application/json" },
    ));
  }
});

window.YouMixer = { state, playback, onError, saveState };  // for the browser tests

// Queue and Lists tabs
function showPane(name) {
  document.querySelectorAll("[data-pane]").forEach((tab) => {
    const active = tab.dataset.pane === name;
    tab.setAttribute("aria-selected", active);
    $(`pane-${tab.dataset.pane}`).hidden = !active;
  });
}
document.querySelectorAll("[data-pane]").forEach((tab) => tab.addEventListener("click", () => showPane(tab.dataset.pane)));
// Delegated: links to tabs come inside translated texts, which are inserted later
document.addEventListener("click", (event) => {
  const link = event.target.closest("[data-goto]");
  if (link) showPane(link.dataset.goto);
});
$("queue").addEventListener("keydown", (event) => {
  const item = event.target.closest("li[data-index]");
  if (!item || !["ArrowDown", "ArrowUp"].includes(event.key)) return;
  event.preventDefault();
  (event.key === "ArrowDown" ? item.nextElementSibling : item.previousElementSibling)?.focus();
});

// Tools panel: it slides in over the page, without stopping the music
async function openDrawer(name) {
  document.querySelectorAll("#drawer section").forEach((section) => {
    section.hidden = section.id !== `section-${name}`;
  });
  $("drawer-title").textContent = $(`section-${name}`).dataset.title;
  if (!$("drawer").open) $("drawer").showModal();
  if (name === "activity") await renderActivity();
  if (name === "profiles") await renderProfiles();
}
document.querySelectorAll("[data-open]").forEach((button) =>
  button.addEventListener("click", guarded(() => openDrawer(button.dataset.open))));
function closeDrawer() {
  const drawer = $("drawer");
  if (!drawer.open || drawer.classList.contains("closing")) return;
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return drawer.close();
  drawer.classList.add("closing");
  const finish = () => {
    clearTimeout(fallback);
    drawer.removeEventListener("animationend", onEnd);
    drawer.classList.remove("closing");
    drawer.close();
  };
  const onEnd = (event) => { if (event.animationName === "drawer-out") finish(); };
  const fallback = setTimeout(finish, 400);  // in case the browser never reports the end of the animation
  drawer.addEventListener("animationend", onEnd);
}

$("drawer").addEventListener("cancel", (event) => {
  event.preventDefault();
  closeDrawer();
});
$("drawer-close").addEventListener("click", closeDrawer);
$("drawer").addEventListener("click", (event) => {
  if (event.target === $("drawer") && event.clientX < $("drawer").getBoundingClientRect().left) closeDrawer();
});

// Draggable divider between the lists and the player
const layout = $("layout");
const splitter = $("splitter");
let sideWidth = SIDE_DEFAULT;

function setSide(width, save) {
  const max = Math.max(SIDE_MIN, layout.clientWidth - STAGE_MIN);
  sideWidth = Math.round(Math.max(SIDE_MIN, Math.min(max, width)));
  layout.style.setProperty("--side", `${sideWidth}px`);
  splitter.setAttribute("aria-valuenow", sideWidth);
  splitter.setAttribute("aria-valuemin", SIDE_MIN);
  splitter.setAttribute("aria-valuemax", max);
  if (save) api("/api/ui", { side: sideWidth }).catch(() => {});
}

splitter.addEventListener("pointerdown", (event) => {
  splitter.setPointerCapture(event.pointerId);
  document.body.classList.add("resizing");
});
splitter.addEventListener("pointermove", (event) => {
  if (!splitter.hasPointerCapture(event.pointerId)) return;
  const padding = parseFloat(getComputedStyle(layout).paddingLeft);
  setSide(event.clientX - layout.getBoundingClientRect().left - padding, false);
});
splitter.addEventListener("pointerup", (event) => {
  splitter.releasePointerCapture(event.pointerId);
  document.body.classList.remove("resizing");
  setSide(sideWidth, true);
});
splitter.addEventListener("dblclick", () => setSide(SIDE_DEFAULT, true));
splitter.addEventListener("keydown", (event) => {
  const step = event.shiftKey ? 80 : 24;
  const moves = { ArrowLeft: -step, ArrowRight: step };
  if (event.key in moves) { event.preventDefault(); setSide(sideWidth + moves[event.key], true); }
  if (event.key === "Home") setSide(SIDE_MIN, true);
  if (event.key === "End") setSide(Infinity, true);
});
window.addEventListener("resize", () => setSide(sideWidth, false));

function historyDetail(detail) {
  if (!detail) return "";
  // Errors are stored as a bare code; older entries hold a text that was already written out
  return /^\d+$/.test(detail) ? t("activity.error_code", { code: detail }) : detail;
}

// Activity panel
async function renderActivity() {
  const [profile, history] = await Promise.all([api("/api/profile"), api("/api/history")]);
  const list = (items, move) => `<ul class="artists">${items.map((i) => `
    <li><span class="artist">${esc(i.artist)}${i.pinned ? ` <span class="tag">${esc(t("activity.pinned"))}</span>` : ""}</span>
      <span class="artist-actions">
        <button class="pref" data-artist="${esc(i.key)}" data-name="${esc(i.artist)}" data-value="${move.value}"
                aria-label="${esc(t(move.label, { name: i.artist }))}" title="${esc(t(move.title))}">${move.icon}</button>
        <button class="forget" data-artist="${esc(i.key)}" aria-label="${esc(t("activity.forget_artist", { name: i.artist }))}"
                title="${esc(t("activity.forget_artist_title"))}">${ICONS.remove}</button>
      </span></li>`).join("")}</ul>`;
  $("profile").innerHTML = `<h3>${esc(t("activity.learned"))}</h3>
    <p class="hint">${esc(t("activity.stats", { likes: profile.likes, finished: profile.finished, skipped: profile.skipped }))}</p>
    ${profile.top.length ? `<span class="label">${esc(t("activity.your_artists"))}</span>${list(profile.top, { value: -1, icon: ICONS.ban, label: "activity.avoid", title: "activity.avoid_title" })}` : ""}
    ${profile.avoid.length ? `<span class="label">${esc(t("activity.avoided"))}</span>${list(profile.avoid, { value: 1, icon: ICONS.keep, label: "activity.keep", title: "activity.keep_title" })}` : ""}`;
  $("history").innerHTML = history.map((h) => `
    <li><img src="${esc(h.thumb)}" alt="" loading="lazy">
      <div class="meta"><strong>${esc(h.title)}</strong><span>${esc(h.artist)}</span></div>
      <span class="tag">${esc(t(`event.${h.type}`))}${h.detail ? ` · ${esc(historyDetail(h.detail))}` : ""}</span>
      <button class="forget" data-event="${h.id}" aria-label="${esc(t("activity.forget_entry"))}" title="${esc(t("activity.forget_entry"))}">${ICONS.remove}</button></li>`).join("")
    || `<li class="empty">${esc(t("activity.empty"))}</li>`;
}

$("section-activity").addEventListener("click", guarded(async (event) => {
  const pref = event.target.closest("button.pref");
  if (pref) {
    const value = Number(pref.dataset.value);
    await api("/api/artist-pref", { artist: pref.dataset.artist, name: pref.dataset.name, value });
    toast(t(value > 0 ? "activity.moved_keep" : "activity.moved_avoid", { name: pref.dataset.name }));
    return renderActivity();
  }
  const button = event.target.closest("button.forget");
  if (!button) return;
  if (button.dataset.event) {
    await api("/api/forget", { event_id: Number(button.dataset.event) });
    toast(t("activity.entry_forgotten"));
  } else {
    await api("/api/forget", { artist: button.dataset.artist });
    toast(t("activity.artist_forgotten"));
  }
  await renderActivity();
}));

// Settings
function renderSettings(settings) {
  $("lastfm-status").textContent = settings.lastfm ? t("settings.saved") : "";
  $("youtube-status").textContent = settings.youtube ? t("settings.saved") : "";
  $("account-status").textContent = t(settings.account ? "settings.account_on" : "settings.account_off");
  $("account-on").hidden = !settings.account;
  $("tray").checked = settings.tray && settings.tray_available;
  $("tray").disabled = !settings.tray_available;
  $("tray-hint").textContent = t(settings.tray_available ? "settings.tray_hint" : "settings.tray_missing");
  $("login-form").hidden = settings.account;
  $("language").innerHTML = settings.languages.map((l) =>
    `<option value="${esc(l.code)}" ${l.code === settings.language ? "selected" : ""}>${esc(l.name)}</option>`).join("");
  state.settings = settings;
  $("open-mode").value = settings.open_mode;
  $("open-mode").querySelector("[value=window]").disabled = !settings.window_available;
  $("open-mode-hint").textContent = t(settings.window_available ? "settings.window_hint" : "settings.window_unavailable");
  $("version-current").textContent = t("settings.version_current", { version: settings.version });
  $("check-updates").checked = settings.check_updates;
  renderUpdate(settings.check_updates ? settings.update : null, settings.check_updates);
  renderWindowToggle();
}

function renderUpdate(update, enabled = true) {
  const status = !enabled ? "off" : update?.status || "unknown";
  $("update-status").textContent = status === "available"
    ? t("update.available", { version: update.latest })
    : t({ current: "update.current", none: "update.none", error: "update.error", off: "update.off" }[status] || "update.unknown");
  $("update-download").hidden = status !== "available";
  if (status === "available") $("update-download").href = update.page;
  $("settings-key").classList.toggle("has-update", status === "available");
}

$("open-mode").addEventListener("change", guarded(async (event) => {
  renderSettings(await api("/api/settings", { open_mode: event.target.value }));
  toast(t("settings.mode_saved"));
}));
$("check-updates").addEventListener("change", guarded(async (event) => {
  renderSettings(await api("/api/settings", { check_updates: event.target.checked }));
}));
$("check-now").addEventListener("click", guarded(async (event) => {
  event.currentTarget.disabled = true;
  try {
    renderUpdate(await api("/api/updates/check", {}));
  } finally {
    $("check-now").disabled = false;
  }
}));

// Own window or browser: the key at the top shows where it would switch to
function renderWindowToggle() {
  const target = IN_WINDOW ? "browser" : "window";
  const label = t(IN_WINDOW ? "tool.open_browser" : "tool.open_window");
  $("window-toggle").innerHTML = ICONS[target];
  $("window-toggle").setAttribute("aria-label", label);
  $("window-toggle").title = label;
  $("window-toggle").hidden = !IN_WINDOW && state.settings && !state.settings.window_available;
}

function stopHere() {
  // It has been opened elsewhere: this copy stops so two players never play at once
  clearWatchdogs();
  if (playback.ready) playback.player.stopVideo();
  closeDrawer();
  document.body.innerHTML = `<div class="handoff"><p>${esc(t("handoff.moved"))}</p>
    <button class="red" onclick="location.reload()">${esc(t("handoff.use_here"))}</button></div>`;
}

$("window-toggle").addEventListener("click", guarded(async () => {
  await saveState();
  await api("/api/open", { mode: IN_WINDOW ? "browser" : "window" });
  if (IN_WINDOW) window.close();
  stopHere();
}));

$("language").addEventListener("change", guarded(async (event) => {
  await api("/api/settings", { language: event.target.value });
  await switchLanguage(event.target.value);
}));

$("settings-form").addEventListener("submit", guarded(async () => {
  const values = {};
  if ($("lastfm-key").value.trim()) values.lastfm_key = $("lastfm-key").value;
  if ($("youtube-key").value.trim()) values.youtube_key = $("youtube-key").value;
  renderSettings(await api("/api/settings", values));
  $("lastfm-key").value = $("youtube-key").value = "";
  toast(t("settings.keys_saved"));
}));
$("tray").addEventListener("change", guarded(async (event) => {
  renderSettings(await api("/api/settings", { tray: event.target.checked }));
  toast(t(event.target.checked ? "settings.tray_on" : "settings.tray_off"));
}));
$("login-form").addEventListener("submit", guarded(async () => {
  renderSettings(await api("/api/login", { headers: $("login-headers").value }));
  $("login-headers").value = "";
  toast(t("settings.account_connected"));
}));
// Turning the server on and off from the page. Polled every few seconds, in case it changes from another tab or browser.
const PING_MS = 5000;
const START_WAIT_MS = 15000;
let serverOn = true;

async function pingServer() {
  try {
    const response = await fetch("/api/ping", { cache: "no-store" });
    return response.ok ? await response.json() : null;
  } catch {
    return null;
  }
}

async function isServerOn() { return (await pingServer()) !== null; }

function setPower(on) {
  serverOn = on;
  document.body.classList.toggle("off", !on);
  $("offline").hidden = on;
  $("power-led").classList.toggle("on", on);
  $("power-state").textContent = on ? "On" : "Off";
  updatePowerLabel();
  if (on) return;
  renderToggle(false);
  clearWatchdogs();
  if (playback.ready) playback.player.stopVideo();
  closeDrawer();
  document.title = t("power.page_title_off");
}

function updatePowerLabel() {
  $("power").setAttribute("aria-label", t(serverOn ? "power.off_aria" : "power.on_aria"));
}

async function turnOn() {
  $("power").disabled = true;
  $("offline-text").textContent = t("offline.starting");
  const launcher = document.createElement("a");
  launcher.href = "youmixer://start";
  launcher.click();
  for (let waited = 0; waited < START_WAIT_MS; waited += 500) {
    await new Promise((done) => setTimeout(done, 500));
    if (await isServerOn()) return location.reload();
  }
  $("power").disabled = false;
  $("offline-text").textContent = t("offline.failed");
}

async function turnOff() {
  if (!confirm(t("power.confirm_off"))) return;
  await saveState();
  await api("/api/shutdown", {});
  tabs?.postMessage({ type: "shutdown" });
  setPower(false);
}

$("power").addEventListener("click", guarded(() => (serverOn ? turnOff() : turnOn())));

function watchPower() {
  setInterval(async () => {
    const info = await pingServer();
    const on = info !== null;
    // If another tab or browser switches profile or language, this one catches up
    if (on && serverOn && state.profile && info.profile && info.profile !== state.profile.id) location.reload();
    else if (on && !serverOn) location.reload();
    else if (on && serverOn) {
      if (info.language && info.language !== i18n.lang) await switchLanguage(info.language);
      await noticeImport(info.last_import);
    }
    else if (!on && serverOn) {
      setPower(false);
      toast(t("power.went_off"));
    }
  }, PING_MS);
}

// Profiles
function renderProfileKey() {
  const name = state.profile?.name || t("profile.main");
  $("profile-name").textContent = name;
  $("profile-key").setAttribute("aria-label", t("profile.key_aria", { name }));
  $("profile-copy-label").textContent = t("profiles.copy", { name });
}

async function renderProfiles() {
  const { active, main, profiles } = await api("/api/profiles");
  $("profiles-list").innerHTML = profiles.map((p) => `
    <li>
      <button class="use" data-use="${esc(p.id)}" aria-pressed="${p.id === active}"
              aria-label="${esc(t(p.id === active ? "profiles.in_use_aria" : "profiles.use_aria", { name: p.name }))}">
        <span class="led" aria-hidden="true"></span><span>${esc(p.name)}</span>
      </button>
      <button class="square" data-rename="${esc(p.id)}" data-name="${esc(p.name)}" aria-label="${esc(t("common.rename_aria", { name: p.name }))}" title="${esc(t("common.rename"))}">${ICONS.rename}</button>
      ${p.id !== active && p.id !== main
        ? `<button class="square" data-delete="${esc(p.id)}" data-name="${esc(p.name)}" aria-label="${esc(t("common.delete_aria", { name: p.name }))}" title="${esc(t("common.delete"))}">${ICONS.remove}</button>`
        : '<span class="square-gap" aria-hidden="true" style="width:44px"></span>'}
    </li>`).join("");
}

async function useProfile(request) {
  await saveState();
  await request();
  location.reload();
}

$("profiles-list").addEventListener("click", guarded(async (event) => {
  const use = event.target.closest("[data-use]");
  if (use && use.getAttribute("aria-pressed") !== "true") {
    return useProfile(() => api("/api/profiles/switch", { id: use.dataset.use }));
  }
  const rename = event.target.closest("[data-rename]");
  if (rename) {
    const name = await ask(t("profiles.rename_prompt"), rename.dataset.name);
    if (!name) return;
    await api("/api/profiles/rename", { id: rename.dataset.rename, name });
    if (state.profile?.id === rename.dataset.rename) { state.profile.name = name; renderProfileKey(); }
    return renderProfiles();
  }
  const remove = event.target.closest("[data-delete]");
  if (remove) {
    if (!(await confirmDelete((word) => t("profiles.delete_prompt", { word, name: remove.dataset.name })))) return;
    await api("/api/profiles/delete", { id: remove.dataset.delete });
    toast(t("profiles.deleted"));
    return renderProfiles();
  }
}));

$("profile-form").addEventListener("submit", guarded(async () => {
  const name = $("profile-new-name").value.trim();
  if (!name) return toast(t("profiles.need_name"));
  await useProfile(() => api("/api/profiles/create", { name, copy_lists: $("profile-copy").checked }));
}));

$("logout").addEventListener("click", guarded(async () => renderSettings(await api("/api/logout", {}))));
$("import-account").addEventListener("click", guarded(async (event) => {
  await runJob(await api("/api/import-account", {}), event.currentTarget);
  toast(t("settings.lists_imported"));
  await refreshSources();
}));

// The "+ YouMixer" bookmarklet: it runs inside YouTube and sends over the list on screen.
// This function is turned into text, so it can't use anything from outside itself;
// its messages travel inside, in the language YouMixer had when it was dragged.
function grabFromYouTube(origin, words) {
  const seen = new Set();
  const tracks = [];
  const text = (node) => (node?.textContent || "").trim();
  const add = (id, title, artist) => {
    if (id && !seen.has(id)) { seen.add(id); tracks.push([id, title, artist]); }
  };
  document.querySelectorAll("ytd-playlist-panel-video-renderer").forEach((el) => {
    const data = el.data || el.__data?.data || {};
    const href = el.querySelector("a#wc-endpoint, a#thumbnail")?.href;
    const id = data.videoId || (href ? new URL(href, location.href).searchParams.get("v") : null);
    add(id, data.title?.simpleText || text(el.querySelector("#video-title")),
      data.shortBylineText?.runs?.[0]?.text || text(el.querySelector("#byline")));
  });
  document.querySelectorAll("ytmusic-player-queue-item").forEach((el) => {
    const data = el.data || el.__data?.data || {};
    add(data.videoId, data.title?.runs?.[0]?.text || text(el.querySelector(".song-title")),
      data.shortBylineText?.runs?.[0]?.text || text(el.querySelector(".byline")).split(" • ")[0]);
  });
  if (!tracks.length) {
    alert(words.nothing);
    return;
  }
  const header = document.querySelector("ytd-playlist-panel-renderer:not([hidden]) #header-description h3, ytd-playlist-panel-renderer .title");
  const name = text(header) || (location.hostname.startsWith("music.") ? words.ytmQueue : words.ytMix);
  window.open(`${origin}/#import=${encodeURIComponent(JSON.stringify({ name, tracks }))}`, "_blank");
}

function updateBookmarklet() {
  const words = { nothing: t("bm.nothing"), ytmQueue: t("bm.ytm_queue"), ytMix: t("bm.yt_mix") };
  $("bookmarklet").href = "javascript:" + encodeURIComponent(`(${grabFromYouTube.toString()})(${JSON.stringify(location.origin)}, ${JSON.stringify(words)})`);
}

function setupBookmarklet() {
  updateBookmarklet();
  $("bookmarklet").addEventListener("click", (event) => {
    event.preventDefault();
    toast(t("bm.drag"));
  });
}

// Messages between tabs of the same browser (turning off gets there sooner this way)
const tabs = "BroadcastChannel" in window ? new BroadcastChannel("youmixer") : null;
tabs?.addEventListener("message", (event) => {
  if (event.data.type === "shutdown") setPower(false);
});

// Lists saved with the bookmarklet. They are announced through the periodic poll, so the news also
// reaches the app window or another browser, even when the bookmarklet's tab belongs to a different one.
let lastImportSeen = 0;

async function noticeImport(info) {
  if (!info || info.at <= lastImportSeen) return;
  lastImportSeen = info.at;
  if (state.profile && info.profile !== state.profile.id) return;
  await refreshSources();
  state.selected.add(info.source_id);
  renderSources();
  showPane("lists");
  toast(t("bm.saved_elsewhere", { name: info.name, count: info.count }));
}

// The tab the bookmarklet opens: it saves the list it was handed and closes itself
async function importFromHash() {
  if (!location.hash.startsWith("#import=")) return false;
  let payload;
  try {
    payload = JSON.parse(decodeURIComponent(location.hash.slice("#import=".length)));
  } catch {
    payload = null;
  }
  history.replaceState(null, "", location.pathname);
  if (!payload) return false;  // a mangled link: just open the app as usual
  const result = await api("/api/import-tracks", payload);
  document.body.innerHTML = `<p class="empty">${esc(t("bm.saved_close", { name: result.name, count: result.count }))}</p>`;
  window.close();
  return true;
}

function announceUpdate(update) {
  // Only once per new version, so the notice isn't repeated on every start
  if (update?.status !== "available") return;
  try {
    if (localStorage.getItem("youmixer-update-seen") === update.latest) return;
    localStorage.setItem("youmixer-update-seen", update.latest);
  } catch { /* no storage: it is announced every time */ }
  toast(t("update.toast", { version: update.latest }));
}

// First-run tour: three steps with a picture each. Shown once (the server remembers it), and again from Settings.
const TOUR_STEPS = 3;
let tourStep = 1;

function renderTour() {
  const image = $("welcome-image");
  const wanted = `/welcome/${i18n.lang}-${tourStep}.png`;
  image.onerror = () => {  // no picture in this language: use the English one
    image.onerror = null;
    image.src = `/welcome/en-${tourStep}.png`;
  };
  if (!image.src.endsWith(wanted)) image.src = wanted;
  $("welcome-step").textContent = t("welcome.step", { n: tourStep, total: TOUR_STEPS });
  $("welcome-heading").textContent = t(`welcome.s${tourStep}_title`);
  $("welcome-text").textContent = t(`welcome.s${tourStep}_text`);
  $("welcome-back").hidden = tourStep === 1;
  $("welcome-skip").hidden = tourStep === TOUR_STEPS;
  $("welcome-next").textContent = t(tourStep === TOUR_STEPS ? "welcome.start" : "welcome.next");
}

function openTour() {
  tourStep = 1;
  renderTour();
  if (!$("welcome").open) $("welcome").showModal();
}

async function closeTour() {
  $("welcome").close();
  if (state.settings && !state.settings.welcomed) {
    renderSettings(await api("/api/settings", { welcomed: true }));
  }
}

$("welcome-next").addEventListener("click", () => {
  if (tourStep < TOUR_STEPS) { tourStep += 1; renderTour(); } else guarded(closeTour)();
});
$("welcome-back").addEventListener("click", () => { tourStep -= 1; renderTour(); });
$("welcome-skip").addEventListener("click", guarded(closeTour));
$("welcome").addEventListener("cancel", (event) => { event.preventDefault(); guarded(closeTour)(); });  // Esc counts as skipping
$("show-welcome").addEventListener("click", () => { closeDrawer(); openTour(); });

// Start-up
guarded(async () => {
  navigator.serviceWorker?.register("/sw.js").catch(() => {});
  const info = await pingServer();
  await loadLanguage(info?.language || guessLanguage());
  renderWindowToggle();
  setPower(true);
  watchPower();
  if (!info) return setPower(false);
  lastImportSeen = info.last_import?.at || 0;
  if (await importFromHash()) return;
  setupBookmarklet();
  const data = await api("/api/bootstrap");
  state.sources = data.sources;
  state.reactions = data.reactions;
  $("genres").innerHTML = data.genres.map((g) =>
    `<label><input type="checkbox" value="${esc(g)}"><span data-i18n="genre.${esc(g)}">${esc(t(`genre.${g}`))}</span></label>`).join("");
  renderSources();
  renderSettings(data.settings);
  state.profile = data.profile;
  renderProfileKey();
  renderExplore();
  setSide(data.ui.side || SIDE_DEFAULT, false);
  state.shuffle = data.ui.shuffle ?? true;
  state.repeat = REPEAT_MODES.includes(data.ui.repeat) ? data.ui.repeat : "off";
  renderModes();
  renderToggle(false);
  applyQueue(data, false);
  showPane(state.queue.length && !state.selected.size ? "queue" : "lists");
  if (data.settings.welcomed) announceUpdate(data.settings.update); else openTour();
  if (data.auto_job) await watchAutoUpdate(data.auto_job);
})().finally(() => document.documentElement.classList.remove("i18n-pending"));
