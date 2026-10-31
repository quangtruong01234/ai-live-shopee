// Trang host chế độ static (research R10; contracts/api.md §4).
// Nhận câu + PCM16 qua /ws/host, phát liền mạch bằng Web Audio, gửi ack để server đo mốc avatar_first_frame.
"use strict";

(() => {
  const CLOSE_REPLACED = 4000;
  // Đệm nhỏ trước câu đầu: chunk đầu tới rồi mới xếp lịch, tránh vấp tiếng khi mạng local chậm một nhịp.
  const LEAD_S = 0.05;

  const subtitle = document.getElementById("subtitle");
  const avatar = document.getElementById("avatar");
  const overlay = document.getElementById("start-overlay");
  const status = document.getElementById("host-status");

  let ctx = null;
  let ws = null;
  let nextTime = 0;
  let current = null; // câu đang nhận audio
  let sources = [];
  let timers = [];

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
      // Phụ đề và ack đi cùng lúc tiếng thật sự phát, không phải lúc nhận dữ liệu.
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
      // Câu không có audio: vẫn ack để server không chờ tới hết giờ.
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
    sources.forEach((s) => { try { s.stop(); } catch (_) { /* đã dừng */ } });
    sources = [];
    current = null;
    nextTime = 0;
    subtitle.textContent = "";
    avatar.classList.remove("speaking");
  }

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws/host`);
    ws.binaryType = "arraybuffer";
    ws.onopen = () => {
      setStatus("");
      send({ type: "ready" });
    };
    ws.onmessage = (ev) => {
      if (typeof ev.data !== "string") return onAudio(ev.data);
      const msg = JSON.parse(ev.data);
      if (msg.type === "sentence_start") onSentenceStart(msg);
      else if (msg.type === "sentence_end") onSentenceEnd(msg);
      else if (msg.type === "stop") stopAll();
    };
    ws.onclose = (ev) => {
      stopAll();
      if (ev.code === CLOSE_REPLACED) {
        // Một màn hình host khác đã nhận vai phát; không tự nối lại để tránh hai nơi giành nhau.
        setStatus("Đã có màn hình host khác. Tải lại trang nếu muốn phát ở đây.");
        return;
      }
      setStatus("Mất kết nối server, đang thử nối lại…");
      setTimeout(connect, 1000);
    };
  }

  document.getElementById("start-btn").addEventListener("click", async () => {
    ctx = new AudioContext();
    await ctx.resume();
    overlay.hidden = true;
    connect();
  });
})();
