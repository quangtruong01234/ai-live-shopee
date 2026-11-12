// Host page (001 research R10, contracts/api.md §4; 005 contracts/api.md §3–§4).
// `static`: sentences + PCM16 arrive over /ws/host and play gaplessly through Web Audio; acks let the server time
// avatar_first_frame. `livetalking`: picture and voice come from the LiveTalking fork over WebRTC (POST /offer);
// this page only reports the fork's `sessionid` and shows the subtitles the server sends. The Web Audio path stays
// ready because a fallback to the still image sends sentences the `static` way.
"use strict";

(() => {
  const CLOSE_REPLACED = 4000;
  // Small lead before the first sentence: schedule once the first chunk is here so a slow local hop does not stutter.
  const LEAD_S = 0.05;
  const REOFFER_DELAY_MS = 2000;

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

  function setStatus(text) {
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
    try {
      lipsyncSession = await offer();
      setStatus("");
    } catch (_) {
      lipsyncSession = null;
      // The server fails the turn and falls back to the still image; this text tells the operator why.
      setStatus("Chưa nối được phần nhép miệng (LiveTalking).");
      scheduleReoffer();
    }
    refreshPicture();
    send({ type: "lipsync_session", session: lipsyncSession });
  }

  function scheduleReoffer() {
    if (reofferTimer !== null) return;
    reofferTimer = setTimeout(() => {
      reofferTimer = null;
      startLipsync();
    }, REOFFER_DELAY_MS);
  }

  // ---------- Server link ----------

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws/host`);
    ws.binaryType = "arraybuffer";
    ws.onopen = () => {
      // Keep the lip-sync warning: only the server link came back.
      if (config.mode !== "livetalking" || lipsyncSession !== null) setStatus("");
      const ready = { type: "ready" };
      // A static page sends no session at all, so it never clears one (static_renderer handle_message).
      if (config.mode === "livetalking") ready.lipsync_session = lipsyncSession;
      send(ready);
    };
    ws.onmessage = (ev) => {
      if (typeof ev.data !== "string") return onAudio(ev.data);
      const msg = JSON.parse(ev.data);
      if (msg.type === "sentence_start") onSentenceStart(msg);
      else if (msg.type === "sentence_end") onSentenceEnd(msg);
      else if (msg.type === "subtitle") onSubtitle(msg);
      else if (msg.type === "subtitle_clear") onSubtitleClear(msg);
      else if (msg.type === "mode") onMode(msg);
      else if (msg.type === "stop") stopAll();
    };
    ws.onclose = (ev) => {
      stopAll();
      if (ev.code === CLOSE_REPLACED) {
        // Another host page took over playback; do not reconnect, or the two would keep taking it from each other.
        setStatus("Đã có màn hình host khác. Tải lại trang nếu muốn phát ở đây.");
        return;
      }
      setStatus("Mất kết nối server, đang thử nối lại…");
      setTimeout(connect, 1000);
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
  }

  ["playing", "pause", "emptied", "waiting"].forEach((name) => video.addEventListener(name, updateLabel));

  document.getElementById("start-btn").addEventListener("click", async () => {
    // The click unlocks sound for both Web Audio (fallback) and the WebRTC <video> (Chrome autoplay policy).
    ctx = new AudioContext();
    await ctx.resume();
    overlay.hidden = true;
    await loadConfig();
    if (config.mode === "livetalking") {
      setStatus("Đang nối phần nhép miệng…");
      // Before the socket opens, so `ready` already carries the session (its own report is a no-op while closed).
      await startLipsync();
    }
    connect();
  });
})();
