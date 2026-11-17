// Host page (001 research R10, contracts/api.md §4; 005 contracts/api.md §3–§4).
// `static`: sentences + PCM16 arrive over /ws/host and play gaplessly through Web Audio; acks let the server time
// avatar_first_frame. `livetalking`: picture and voice come from the LiveTalking fork over WebRTC (POST /offer);
// this page only reports the fork's `sessionid` and shows the subtitles the server sends. The Web Audio path stays
// ready because a fallback to the still image sends sentences the `static` way.
"use strict";

(() => {
  const CLOSE_REPLACED = 4000;
  const CLOSE_YIELDED = 4001; // 006: an OBS source took playback from this /host page
  // 006 `/obs`: the OBS Browser Source. It starts on load (OBS's browser allows sound without a click), shows only the
  // picture and the AI label, and reloads itself after the app comes back (research R6).
  const OBS = document.body.classList.contains("obs");
  const RECONNECT_MS = 1000;
  // Small lead before the first sentence: schedule once the first chunk is here so a slow local hop does not stutter.
  const LEAD_S = 0.05;
  const REOFFER_DELAY_MS = 2000;
  const HEARTBEAT_MS = 1000; // 007 `host_status`: what the viewer's screen really does, for the show watchdog

  const subtitle = document.getElementById("subtitle");
  const avatar = document.getElementById("avatar");
  const video = document.getElementById("video");
  const label = document.getElementById("ai-label");
  const overlay = document.getElementById("start-overlay");
  const status = document.getElementById("host-status");

  let ctx = null;
  let ws = null;
  let nextTime = 0;
  let current = null; // sentence whose audio is arriving
  let sources = [];
  let timers = [];

  let config = { mode: "static" };
  // Picture shown now: differs from `config.mode` after a fallback to the still image (`mode` message, FR-022).
  let active = "static";
  let pc = null;
  let lipsyncSession = null;
  let subtitleKey = null; // `${utterance_id}:${seq}` of the subtitle shown in livetalking mode
  let reofferTimer = null;
  let sceneVersion = 0; // newest scene still asked for (009 contracts/api.md §5)
  let heartbeat = null;
  let released = false; // lost playback for good (4000/4001): nothing may reconnect or re-offer
  let lostServer = false; // `/obs` only: the socket dropped once, so the next successful open reloads the page

  function setStatus(text) {
    // OBS captures the whole page: an operator message there would go out to the viewers.
    if (OBS) return;
    status.textContent = text;
    status.hidden = !text;
  }

  function send(msg) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
  }

  function later(atCtxTime, fn) {
    const delayMs = Math.max(0, (atCtxTime - ctx.currentTime) * 1000);
    timers.push(setTimeout(fn, delayMs));
  }

  // ---------- static: Web Audio playback ----------

  function onSentenceStart(msg) {
    current = { id: msg.utterance_id, seq: msg.seq, text: msg.text, rate: msg.sample_rate, startAt: null };
  }

  function onAudio(buffer) {
    if (!current) return;
    const pcm = new Int16Array(buffer);
    if (!pcm.length) return;
    const audio = ctx.createBuffer(1, pcm.length, current.rate);
    const data = audio.getChannelData(0);
    for (let i = 0; i < pcm.length; i++) data[i] = pcm[i] / 32768;
    const src = ctx.createBufferSource();
    src.buffer = audio;
    src.connect(ctx.destination);
    const at = Math.max(nextTime, ctx.currentTime + LEAD_S);
    src.start(at);
    sources.push(src);
    src.onended = () => { sources = sources.filter((s) => s !== src); };
    nextTime = at + audio.duration;
    if (current.startAt === null) {
      current.startAt = at;
      const sentence = current;
      // Subtitle and ack go out when the sound really starts, not when the data arrives.
      later(at, () => {
        subtitle.textContent = sentence.text;
        avatar.classList.add("speaking");
        send({ type: "playback_started", utterance_id: sentence.id, seq: sentence.seq });
      });
    }
  }

  function onSentenceEnd(msg) {
    const sentence = current;
    current = null;
    if (!sentence || sentence.id !== msg.utterance_id || sentence.seq !== msg.seq) return;
    if (sentence.startAt === null) {
      // A sentence without audio: ack anyway so the server does not wait for its timeout.
      subtitle.textContent = sentence.text;
      send({ type: "playback_started", utterance_id: sentence.id, seq: sentence.seq });
      send({ type: "sentence_played", utterance_id: sentence.id, seq: sentence.seq });
      return;
    }
    const endAt = nextTime;
    later(endAt, () => {
      send({ type: "sentence_played", utterance_id: sentence.id, seq: sentence.seq });
      if (ctx.currentTime >= nextTime - 0.01) avatar.classList.remove("speaking");
    });
  }

  function stopAll() {
    timers.forEach(clearTimeout);
    timers = [];
    sources.forEach((s) => { try { s.stop(); } catch (_) { /* already stopped */ } });
    sources = [];
    current = null;
    nextTime = 0;
    subtitle.textContent = "";
    subtitleKey = null;
    avatar.classList.remove("speaking");
  }

  // ---------- livetalking: subtitles timed by the fork's acks ----------

  function onSubtitle(msg) {
    subtitleKey = `${msg.utterance_id}:${msg.seq}`;
    subtitle.textContent = msg.text;
  }

  function onSubtitleClear(msg) {
    // With LIVETALKING_LEAD_S the next sentence's subtitle may already be up; clear only the matching one.
    if (subtitleKey !== `${msg.utterance_id}:${msg.seq}`) return;
    subtitleKey = null;
    subtitle.textContent = "";
  }

  // ---------- livetalking: WebRTC from the fork ----------

  function showVideo(on) {
    video.hidden = !on;
    avatar.hidden = on;
    // A stream that arrived while the video was hidden and muted (fork restarted during a fallback) never
    // autoplays; the "Bắt đầu" click is the user activation that lets this unmuted play() start.
    if (on && video.paused && video.srcObject) video.play().catch(() => {});
    updateLabel();
  }

  function refreshPicture() {
    showVideo(active === "livetalking" && lipsyncSession !== null);
  }

  // ---------- 009: live scene on the still image ----------

  function applyScene(scene) {
    if (!scene || !scene.enabled) return;
    document.querySelector(".stage").classList.add("scene-on");
    // The scene draws the sentence into the frame; a second copy on top would cover the product cards (FR-018).
    if (scene.subtitles) subtitle.classList.add("in-frame");
    if (scene.version) onScene({ version: scene.version });
  }

  function onScene(msg) {
    const version = Number(msg.version);
    if (!(version > sceneVersion)) return;
    sceneVersion = version;
    // Swap only once the new picture is decoded, so the stage never flashes empty between two scenes.
    const next = new Image();
    next.onload = () => {
      if (version === sceneVersion) avatar.src = next.src;
    };
    next.src = `/api/scene/still.png?v=${version}`;
  }

  function onMode(msg) {
    if (msg.mode !== "static" && msg.mode !== "livetalking") return;
    active = msg.mode;
    // Muted on the still image so a leftover fork sound never plays over the Web Audio sentences.
    video.muted = active !== "livetalking";
    subtitleKey = null;
    subtitle.textContent = "";
    if (active === "livetalking" && (lipsyncSession === null || !pc || pc.connectionState !== "connected")) {
      // The WebRTC link may have died with the fork; a fresh /offer also reports the new session to the server.
      startLipsync();
      return;
    }
    refreshPicture();
  }

  function updateLabel() {
    // The fork composites the AI label into every frame; the CSS label hides only while those frames are playing,
    // so the label is on screen at every moment (Article I, FR-018).
    const framesPlaying = !video.hidden && !video.paused && video.readyState >= 2;
    label.hidden = framesPlaying;
  }

  function waitIceGathering(peer) {
    if (peer.iceGatheringState === "complete") return Promise.resolve();
    return new Promise((resolve) => {
      const check = () => {
        if (peer.iceGatheringState === "complete") {
          peer.removeEventListener("icegatheringstatechange", check);
          resolve();
        }
      };
      peer.addEventListener("icegatheringstatechange", check);
    });
  }

  async function offer() {
    if (pc) pc.close();
    const peer = new RTCPeerConnection();
    pc = peer;
    peer.addTransceiver("video", { direction: "recvonly" });
    peer.addTransceiver("audio", { direction: "recvonly" });
    peer.ontrack = (ev) => {
      if (ev.track.kind === "video") video.srcObject = ev.streams[0];
    };
    peer.onconnectionstatechange = () => {
      if (peer !== pc) return;
      if (peer.connectionState === "failed" || peer.connectionState === "disconnected") scheduleReoffer();
    };
    const local = await peer.createOffer();
    await peer.setLocalDescription(local);
    await waitIceGathering(peer);
    const resp = await fetch(`${config.livetalking_url}/offer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sdp: peer.localDescription.sdp, type: peer.localDescription.type }),
    });
    if (!resp.ok) throw new Error(`/offer ${resp.status}`);
    const answer = await resp.json();
    await peer.setRemoteDescription({ sdp: answer.sdp, type: answer.type });
    // Upstream's id is a UUID string; a refusal (`{code: -1}`, a second session) already threw at setRemoteDescription.
    return typeof answer.sessionid === "string" && answer.sessionid ? answer.sessionid : null;
  }

  async function startLipsync() {
    if (released) return;
    try {
      lipsyncSession = await offer();
      if (released) return releasePeer();
      setStatus("");
    } catch (_) {
      lipsyncSession = null;
      // An offer cut short by releasePlayback() (its peer was closed) is not a fork problem.
      if (released) return;
      // The server fails the turn and falls back to the still image; this text tells the operator why.
      setStatus("Chưa nối được phần nhép miệng (LiveTalking).");
      scheduleReoffer();
    }
    refreshPicture();
    send({ type: "lipsync_session", session: lipsyncSession });
  }

  function scheduleReoffer() {
    if (released || reofferTimer !== null) return;
    reofferTimer = setTimeout(() => {
      reofferTimer = null;
      startLipsync();
    }, REOFFER_DELAY_MS);
  }

  // ---------- 007: heartbeat for the show watchdog (contracts/api.md §4) ----------

  async function decodedFrames() {
    // Only the lip-sync picture moves; the still image has no frame count, so the frozen rule does not apply to it.
    if (!pc || active !== "livetalking" || video.hidden) return null;
    try {
      const stats = await pc.getStats();
      for (const report of stats.values()) {
        if (report.type === "inbound-rtp" && report.kind === "video") return report.framesDecoded ?? null;
      }
    } catch (_) {
      // A peer closed mid-call: unknown, not frozen.
    }
    return null;
  }

  async function sendHostStatus() {
    const onVideo = active === "livetalking" && !video.hidden;
    send({
      type: "host_status",
      frames: await decodedFrames(),
      audio: ctx ? ctx.state : null,
      // The <video> carries the voice only in lip-sync; on the still image it is muted on purpose.
      video_muted: onVideo ? video.muted : null,
      video_paused: onVideo ? video.paused : null,
      visible: document.visibilityState === "visible",
    });
  }

  function startHeartbeat() {
    stopHeartbeat();
    heartbeat = setInterval(sendHostStatus, HEARTBEAT_MS);
  }

  function stopHeartbeat() {
    if (heartbeat !== null) clearInterval(heartbeat);
    heartbeat = null;
  }

  // ---------- 006: giving playback away ----------

  function releasePeer() {
    if (reofferTimer !== null) clearTimeout(reofferTimer);
    reofferTimer = null;
    // Closing the peer lets the fork drop this session, so the page that now plays gets the lip-sync picture and
    // the fork never speaks twice (research R5).
    if (pc) pc.close();
    pc = null;
    lipsyncSession = null;
  }

  function releasePlayback() {
    released = true;
    stopHeartbeat();
    stopAll();
    releasePeer();
    video.muted = true;
    video.pause();
    video.srcObject = null;
    if (ctx) ctx.suspend().catch(() => {});
    // Back to the still image with the AI label, never a blank stage (Article I).
    showVideo(false);
  }

  // ---------- Server link ----------

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws/host?role=${OBS ? "obs" : "host"}`);
    ws.binaryType = "arraybuffer";
    ws.onopen = () => {
      if (lostServer) {
        // The app restarted: its scene versions count from zero again, so only a fresh page matches it (R6).
        location.reload();
        return;
      }
      // Keep the lip-sync warning: only the server link came back.
      if (config.mode !== "livetalking" || lipsyncSession !== null) setStatus("");
      const ready = { type: "ready" };
      // A static page sends no session at all, so it never clears one (static_renderer handle_message).
      if (config.mode === "livetalking") ready.lipsync_session = lipsyncSession;
      send(ready);
      startHeartbeat();
    };
    ws.onmessage = (ev) => {
      if (typeof ev.data !== "string") return onAudio(ev.data);
      const msg = JSON.parse(ev.data);
      if (msg.type === "sentence_start") onSentenceStart(msg);
      else if (msg.type === "sentence_end") onSentenceEnd(msg);
      else if (msg.type === "subtitle") onSubtitle(msg);
      else if (msg.type === "subtitle_clear") onSubtitleClear(msg);
      else if (msg.type === "mode") onMode(msg);
      else if (msg.type === "scene") onScene(msg);
      else if (msg.type === "stop") stopAll();
    };
    ws.onclose = (ev) => {
      if (ev.code === CLOSE_REPLACED || ev.code === CLOSE_YIELDED) {
        // Another page took over playback; do not reconnect, or the two would keep taking it from each other.
        releasePlayback();
        if (ev.code === CLOSE_YIELDED) setStatus("Đang phát qua OBS, xem trong cửa sổ OBS. Tải lại trang nếu muốn phát ở đây.");
        else setStatus("Đã có màn hình host khác. Tải lại trang nếu muốn phát ở đây.");
        return;
      }
      stopHeartbeat();
      stopAll();
      if (OBS) lostServer = true;
      setStatus("Mất kết nối server, đang thử nối lại…");
      setTimeout(connect, RECONNECT_MS);
    };
  }

  async function loadConfig() {
    try {
      const resp = await fetch("/api/host-config");
      if (resp.ok) config = await resp.json();
    } catch (_) {
      // Keep `static`: the still image still works without the config.
    }
    // A page reloaded after a fallback starts on the still image; it still offers, so switching back is quick.
    active = config.active || config.mode;
    video.muted = active !== "livetalking";
    applyScene(config.scene);
  }

  // A page left for another URL may sit in the back/forward cache with its socket still open; the server would only
  // see the host gone after the ping timeout (~40 s in the 007 T035 check), so the operator's banner came late.
  window.addEventListener("pagehide", () => {
    if (ws && ws.readyState <= WebSocket.OPEN) ws.close(1001, "pagehide");
  });

  ["playing", "pause", "emptied", "waiting"].forEach((name) => video.addEventListener(name, updateLabel));

  async function start() {
    ctx = new AudioContext();
    if (OBS) {
      // No click in OBS: OBS's browser lets sound play on its own. A plain Chrome tab leaves the context suspended
      // without a click, and that resume() would never settle, so it is not awaited (the heartbeat reports it, Q32).
      ctx.resume().catch(() => {});
    } else {
      await ctx.resume();
    }
    overlay.hidden = true;
    await loadConfig();
    if (config.mode === "livetalking") {
      setStatus("Đang nối phần nhép miệng…");
      // Before the socket opens, so `ready` already carries the session (its own report is a no-op while closed).
      await startLipsync();
    }
    connect();
  }

  if (OBS) {
    overlay.hidden = true;
    start();
  } else {
    // The click unlocks sound for both Web Audio (fallback) and the WebRTC <video> (Chrome autoplay policy).
    document.getElementById("start-btn").addEventListener("click", start);
  }
})();
