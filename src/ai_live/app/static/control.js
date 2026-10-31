// Control page (FR-016: queue, dropped comments, current turn and errors; FR-018: latency table;
// FR-022: content upload; contracts/api.md §2–3).
// Comment text is viewer data: assign it only through textContent, never innerHTML.
"use strict";

(() => {
  const MAX_ITEMS = 50;
  const ERROR_STEP_LABELS = { llm: "LLM", guard: "guard", tts: "TTS", render: "render (màn hình host)" };
  const GUARD_LABELS = { forbidden_claim: "khẳng định bị cấm", unknown_amount: "số tiền không có trong file" };
  // Same wording as DropReason.label in core/models.py.
  const DROP_LABELS = {
    empty: "không có nội dung",
    link: "chứa link",
    profanity: "từ ngữ không phù hợp",
    duplicate: "trùng",
    stale: "quá cũ",
    queue_full: "hàng đợi đầy",
  };

  // Step keys of LatencySummary (director/latency.py), in display order; `total` goes last as the headline row.
  const LATENCY_STEPS = [
    ["queue_wait", "Chờ trong hàng đợi"],
    ["received_to_first_sentence", "Nhận comment → LLM ra câu đầu"],
    ["first_sentence_to_tts_first_chunk", "Câu đầu → TTS ra đoạn tiếng đầu"],
    ["tts_first_chunk_to_first_frame", "Đoạn tiếng đầu → avatar bắt đầu nói"],
    ["total", "Tổng: comment → avatar bắt đầu nói"],
  ];

  const $ = (id) => document.getElementById(id);
  const turns = new Map(); // utterance_id -> {author, text}
  let currentId = null;

  function clock(ts) {
    const d = ts ? new Date(ts) : new Date();
    return d.toLocaleTimeString("vi-VN", { hour12: false });
  }

  function pushItem(listId, ts, parts) {
    const list = $(listId);
    const empty = list.querySelector(".empty");
    if (empty) empty.remove();
    const li = document.createElement("li");
    const time = document.createElement("span");
    time.className = "time";
    time.textContent = clock(ts);
    li.appendChild(time);
    for (const [text, cls] of parts) {
      const span = document.createElement("span");
      if (cls) span.className = cls;
      span.textContent = text;
      li.appendChild(span);
    }
    list.prepend(li);
    while (list.children.length > MAX_ITEMS) list.lastChild.remove();
  }

  function setHost(connected) {
    $("host-badge").textContent = connected ? "đã sẵn sàng" : "chưa mở";
    $("host-badge").className = "badge " + (connected ? "ok" : "bad");
    $("host-warning").hidden = connected;
  }

  function setSession(state) {
    const paused = state === "paused";
    $("session-badge").textContent = paused ? "tạm dừng" : "đang chạy";
    $("session-badge").className = "badge " + (paused ? "bad" : "ok");
    $("pause-btn").disabled = paused;
    $("resume-btn").disabled = !paused;
  }

  async function sendControl(path) {
    try {
      const res = await fetch(path, { method: "POST" });
      const body = await res.json();
      if (!res.ok) throw new Error(body.message || String(res.status));
      return body;
    } catch (err) {
      $("control-msg").textContent = `Lệnh lỗi: ${err.message || err}`;
      return null;
    }
  }

  function setServer(connected) {
    $("server-badge").textContent = connected ? "đang chạy" : "mất kết nối";
    $("server-badge").className = "badge " + (connected ? "ok" : "bad");
  }

  function renderQueue(queue) {
    const list = $("queue");
    $("queue-count").textContent = String(queue.length);
    if (queue.length === 0) {
      const li = document.createElement("li");
      li.className = "empty";
      li.textContent = "Hàng đợi trống.";
      list.replaceChildren(li);
      return;
    }
    // The server sends the queue already in `snapshot()` order, which is the answering order.
    list.replaceChildren(
      ...queue.map((item) => {
        const li = document.createElement("li");
        const prio = document.createElement("span");
        prio.className = `prio ${item.priority}`;
        prio.textContent = item.priority;
        const body = document.createElement("span");
        body.textContent = `${item.author}: ${item.text}`;
        li.append(prio, body);
        return li;
      }),
    );
  }

  function seconds(value) {
    return value == null ? "—" : value.toFixed(2);
  }

  function latencyRow(label, stats, cls) {
    const tr = document.createElement("tr");
    if (cls) tr.className = cls;
    const s = stats || { count: 0, median: null, p95: null, note: "chưa đủ mẫu" };
    const name = document.createElement("td");
    name.textContent = label;
    const count = document.createElement("td");
    count.textContent = String(s.count);
    const median = document.createElement("td");
    median.textContent = seconds(s.median);
    const p95 = document.createElement("td");
    if (s.p95 == null) {
      // p95 needs at least `min_samples` turns (research R12); the server sends the note text.
      p95.className = "note";
      p95.textContent = s.note || "chưa đủ mẫu";
    } else {
      p95.textContent = seconds(s.p95);
    }
    tr.append(name, count, median, p95);
    return tr;
  }

  function renderLatency(summary) {
    if (!summary || !summary.steps) return;
    const rows = LATENCY_STEPS.map(([key, label]) =>
      latencyRow(label, summary.steps[key], key === "total" ? "total" : null),
    );
    // Idle-only row: turns that waited < idle_threshold_s in the queue, i.e. pipeline speed without backlog.
    const idle = (summary.idle_steps || {}).total;
    rows.push(latencyRow(`Tổng, chỉ lượt host rảnh (chờ < ${summary.idle_threshold_s} s)`, idle, "idle"));
    $("latency-rows").replaceChildren(...rows);
    $("latency-meta").textContent =
      `Đã xong ${summary.completed} lượt (host rảnh: ${summary.idle_completed}) · ` +
      `lỗi ${summary.errors} · bỏ qua ${summary.skipped} (lượt lỗi và bỏ qua không tính vào số liệu) · ` +
      `p95 cần ít nhất ${summary.min_samples} lượt.`;
  }

  async function loadLatency() {
    try {
      const res = await fetch("/api/latency");
      if (res.ok) renderLatency(await res.json());
    } catch (err) {
      // The next `latency` event over the WebSocket refreshes the table anyway.
    }
  }

  function renderCatalog(catalog) {
    if (!catalog) return;
    $("catalog-meta").textContent = `Phiên bản ${catalog.version}`;
    $("catalog-products").replaceChildren(
      ...(catalog.products || []).map((p) => {
        const li = document.createElement("li");
        li.textContent = p.is_primary ? `${p.name} (sản phẩm chính)` : p.name;
        return li;
      }),
    );
  }

  function showContentIssues(issues) {
    const list = $("content-issues");
    list.hidden = issues.length === 0;
    list.replaceChildren(
      ...issues.map((issue) => {
        const li = document.createElement("li");
        li.className = "err";
        const where = [issue.product, issue.section].filter(Boolean).join(" › ");
        li.textContent = where ? `${where}: ${issue.message}` : issue.message;
        return li;
      }),
    );
  }

  function turnLabel(id) {
    const t = turns.get(id);
    return t ? `${t.author}: “${t.text}”` : id;
  }

  const handlers = {
    state(msg) {
      setHost(Boolean(msg.session && msg.session.host_connected));
      if (msg.session) setSession(msg.session.state);
      renderQueue(msg.queue || []);
      renderCatalog(msg.catalog);
    },
    session_state(msg) {
      setSession(msg.state);
    },
    content_replaced(msg) {
      renderCatalog(msg);
    },
    queue_changed(msg) {
      renderQueue(msg.queue || []);
    },
    comment_dropped(msg) {
      const why = DROP_LABELS[msg.reason] || msg.reason;
      pushItem("dropped", msg.ts, [
        [why, "reason"],
        [`${msg.author}: ${msg.text}`, null],
      ]);
    },
    host_connection(msg) {
      setHost(msg.connected);
    },
    turn_started(msg) {
      turns.set(msg.utterance_id, { author: msg.author, text: msg.text });
      currentId = msg.utterance_id;
      $("turn-meta").textContent = `Đang trả lời ${msg.author}: “${msg.text}”`;
      $("turn-sentences").replaceChildren();
    },
    sentence(msg) {
      if (msg.utterance_id !== currentId) return;
      const li = document.createElement("li");
      li.textContent = msg.text;
      $("turn-sentences").appendChild(li);
    },
    guard_blocked(msg) {
      const why = GUARD_LABELS[msg.reason] || msg.reason;
      pushItem("blocked", msg.ts, [[`Chặn (${why}) khi trả lời ${turnLabel(msg.utterance_id)}`, null]]);
    },
    turn_finished(msg) {
      const label = turnLabel(msg.utterance_id);
      if (msg.utterance_id === currentId) {
        $("turn-meta").textContent = `Đã xong (${msg.outcome}): ${label}`;
      }
      const total = msg.total_s == null ? "" : ` · ${msg.total_s.toFixed(2)} s tới lúc bắt đầu nói`;
      if (msg.outcome === "error") {
        const step = ERROR_STEP_LABELS[msg.error_step] || msg.error_step;
        pushItem("errors", msg.ts, [[`Lỗi ở bước ${step}: ${label}`, "err"]]);
        pushItem("history", msg.ts, [[`lỗi (${step}) · ${label}`, "err"]]);
      } else {
        pushItem("history", msg.ts, [[`${msg.outcome}${total} · ${label}`, null]]);
      }
      turns.delete(msg.utterance_id);
    },
    latency(msg) {
      renderLatency(msg);
    },
  };

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/control`);
    ws.onopen = () => {
      setServer(true);
      // The `state` message carries no latency; load the current summary once per (re)connect.
      loadLatency();
    };
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      const handle = handlers[msg.type];
      if (handle) handle(msg);
    };
    ws.onclose = () => {
      setServer(false);
      setTimeout(connect, 1000);
    };
  }

  $("comment-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const author = $("author").value;
    const text = $("text").value;
    $("form-msg").textContent = "Đang gửi…";
    try {
      const res = await fetch("/api/comments", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ author, text }),
      });
      const body = await res.json();
      if (!res.ok) {
        $("form-msg").textContent = `Lỗi: ${body.message || res.status}`;
        return;
      }
      $("form-msg").textContent =
        body.status === "waiting"
          ? `Đã vào hàng đợi (${body.priority}).`
          : `Bị loại: ${DROP_LABELS[body.drop_reason] || body.drop_reason}`;
      $("text").value = "";
      $("text").focus();
    } catch (err) {
      $("form-msg").textContent = `Không gửi được: ${err}`;
    }
  });

  // The badge follows the `session_state` event, so every open control page shows the same state.
  $("pause-btn").addEventListener("click", async () => {
    if (await sendControl("/api/pause")) $("control-msg").textContent = "Host nói nốt câu trả lời hiện tại rồi dừng.";
  });
  $("resume-btn").addEventListener("click", async () => {
    if (await sendControl("/api/resume")) $("control-msg").textContent = "";
  });
  $("skip-btn").addEventListener("click", async () => {
    const body = await sendControl("/api/skip");
    if (body) {
      $("control-msg").textContent = body.skipped_utterance_id
        ? `Đã bỏ qua lượt ${turnLabel(body.skipped_utterance_id)}.`
        : "Host đang không nói, không có gì để bỏ qua.";
    }
  });

  $("content-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const file = $("content-file").files[0];
    if (!file) return;
    showContentIssues([]);
    $("content-msg").textContent = "Đang kiểm tra file…";
    try {
      // Raw body, not multipart (contracts/api.md §2); the name is only shown in issue messages.
      const res = await fetch("/api/content", {
        method: "PUT",
        headers: { "Content-Type": "application/octet-stream", "X-Filename": encodeURIComponent(file.name) },
        body: file,
      });
      const body = await res.json();
      if (!res.ok) {
        $("content-msg").textContent = `Không nạp được, host vẫn dùng nội dung cũ. ${body.message || res.status}`;
        showContentIssues(body.details || []);
        return;
      }
      renderCatalog(body);
      $("content-msg").textContent = `Đã nạp phiên bản ${body.version}. Lượt đang nói dùng nội dung cũ, lượt sau dùng nội dung mới.`;
      $("content-file").value = "";
    } catch (err) {
      $("content-msg").textContent = `Không gửi được: ${err}`;
    }
  });

  connect();
})();
