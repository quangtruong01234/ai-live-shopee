// Control page (FR-016: queue, dropped comments, current turn and errors; FR-018: latency table;
// FR-022: content upload; contracts/api.md §2–3). 004 FR-019: the "Show" area (state, mode, current and next
// segment, recent blocked sentences and errors, gap p95/max), refreshed from `GET /api/show` on show events.
// 004 FR-018: the "phân đoạn kế tiếp" picker offers only product/topic pairs listed in `available_topics` (US5 #2).
// 008 FR-017, FR-020: the read-only "Model LLM" area (008 contracts/api.md §3) and, in dev, the fault form with the
// per-entry modes.
// 007 FR-001, FR-005: the "Kiểm tra trước demo" button shows `GET /api/readiness` as a table plus the manual checks.
// 005 FR-011: in dev, the "Thử bằng tiếng có sẵn" form posts a WAV to `/api/debug/speak-audio` (005 contracts/api.md §1).
// Comment text is viewer data and script text is LLM output: assign both only through textContent, never innerHTML.
"use strict";

(() => {
  const MAX_ITEMS = 50;
  const ERROR_STEP_LABELS = { llm: "LLM", guard: "guard", tts: "TTS", render: "render (màn hình host)" };
  // Same wording as GuardReason.label in core/models.py.
  const GUARD_LABELS = {
    forbidden_claim: "khẳng định bị cấm",
    unknown_amount: "số tiền không có trong dữ liệu",
    unknown_percent: "phần trăm không có trong dữ liệu",
    link: "chứa link",
    platform_phrase: "cơ chế nền tảng shop không có",
    unsupported_claim: "khẳng định không có trong dữ liệu",
  };
  // Same wording as ShowState.label in core/models.py.
  const SHOW_STATE_LABELS = {
    idle: "chưa chạy",
    running: "đang chạy",
    paused: "tạm dừng",
    closing: "đang chào kết",
    ended: "đã kết thúc",
  };
  const SHOW_MODE_LABELS = { normal: "bình thường", fallback: "dự phòng" };
  // Same wording as Topic.label in core/models.py (opening/closing are never offered: the director owns them).
  const TOPIC_LABELS = {
    intro: "Giới thiệu chung",
    highlights: "Điểm nổi bật",
    specs: "Thông số",
    price: "Giá và phân loại",
    promotion: "Khuyến mãi",
    faq: "Câu hỏi thường gặp",
    call_to_action: "Kêu gọi mua",
  };
  const SHOW_RECENT = 10;
  // Same wording as DropReason.label in core/models.py.
  const DROP_LABELS = {
    empty: "không có nội dung",
    link: "chứa link",
    profanity: "từ ngữ không phù hợp",
    duplicate: "trùng",
    stale: "quá cũ",
    queue_full: "hàng đợi đầy",
    show_ended: "phiên đã kết thúc",
  };

  // Step keys of LatencySummary (director/latency.py), in display order; `total` goes last as the headline row.
  const LATENCY_STEPS = [
    ["queue_wait", "Chờ trong hàng đợi"],
    ["received_to_first_sentence", "Nhận comment → LLM ra câu đầu"],
    ["first_sentence_to_tts_first_chunk", "Câu đầu → TTS ra đoạn tiếng đầu"],
    ["floor_wait", "Chờ câu kịch bản đang nói xong"],
    ["tts_first_chunk_to_first_frame", "Đoạn tiếng đầu → avatar bắt đầu nói"],
    ["total", "Tổng: comment → avatar bắt đầu nói"],
  ];

  // 008 contracts/api.md §3: one label per AttemptReason value.
  const LLM_REASON_LABELS = {
    rate_limited: "hết hạn mức",
    overloaded: "quá tải / lỗi máy chủ",
    empty: "trả về rỗng",
    connection: "lỗi kết nối",
    timeout: "quá giờ chờ câu đầu",
    rejected: "bị từ chối (key/model)",
    wrong_platform: "sai nền tảng",
    blocked: "bị bộ lọc nội dung chặn",
    interrupted: "đứt giữa chừng",
  };
  // Same values as FAULT_STEPS / FAULT_MODES / ENTRY_FAULT_MODES in director/faults.py.
  const FAULT_STEPS = ["llm", "tts", "render"];
  const STEP_FAULT_MODES = { error: "lỗi", timeout: "quá giờ chờ" };
  const ENTRY_FAULT_MODES = ["rate_limited", "overloaded", "timeout", "empty", "wrong_platform", "interrupted"];
  // A past `retry_at` reads as ready without a new event (research R9), so the area re-renders on a timer.
  const LLM_TICK_MS = 1000;

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

  // 006: which output the show leaves through (OUTPUT_MODE) and whether the connection that plays is the right one.
  let outputMode = "meet";
  let hostConnected = false;
  let hostRole = null;

  function setHost(connected, role) {
    hostConnected = Boolean(connected);
    hostRole = hostConnected ? role || "host" : null;
    const obs = outputMode === "obs";
    // In obs mode a Chrome /host tab that got to play does not reach OBS, so it is not "connected" (contracts §8).
    const ok = obs ? hostRole === "obs" : hostConnected;
    let text = obs ? `OBS (${ok ? "đã nối" : "chưa nối"})` : `Meet — trang host (${ok ? "đã nối" : "chưa nối"})`;
    if (obs && hostRole === "host") text += ", /host trên Chrome đang phát thay";
    $("host-badge").textContent = text;
    $("host-badge").className = "badge " + (ok ? "ok" : "bad");
    $("host-warning-meet").hidden = obs;
    $("host-warning-obs").hidden = !obs;
    $("obs-url").textContent = `${location.protocol}//${location.host}/obs`;
    $("host-warning").hidden = ok;
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

  // ---------- 005: lip-synced character (contracts/api.md §5) ----------

  // ---------- 007: show watchdog banner (contracts/api.md §3) ----------

  const openAlerts = new Map(); // alert_id -> alert, in the order they opened

  function renderAlerts() {
    const banner = $("alert-banner");
    banner.replaceChildren();
    for (const alert of openAlerts.values()) {
      const row = document.createElement("div");
      row.className = `alert-row ${alert.level === "operator" ? "operator" : "warning"}`;
      const message = document.createElement("b");
      message.textContent = alert.message;
      const action = document.createElement("span");
      action.textContent = alert.action ? ` — ${alert.action}` : "";
      row.append(message, action);
      if (alert.text) {
        const said = document.createElement("div");
        said.className = "alert-text";
        said.textContent = `Câu đang kẹt: ${alert.text}`;
        row.append(said);
      }
      banner.append(row);
    }
    banner.hidden = openAlerts.size === 0;
  }

  function renderAvatarMode(mode) {
    const fellBack = Boolean(mode) && mode.configured === "livetalking" && mode.active !== mode.configured;
    $("avatar-warning").hidden = !fellBack;
    if (!fellBack) return;
    const turns = mode.consecutive_errors || 2;
    $("avatar-warning-text").textContent = `Nhân vật nhép miệng lỗi ${turns} lượt liền, đang dùng ảnh tĩnh.`;
  }

  function renderLipsyncHealth(health) {
    // Configured `static` has no fork: the status stays hidden.
    $("lipsync-status").hidden = !health;
    if (!health) return;
    const parts = [health.connected ? "đã nối" : "mất nối"];
    if (health.vram_used_mb != null) parts.push(`VRAM ${health.vram_used_mb} MB`);
    if (health.infer_fps != null) parts.push(`${Number(health.infer_fps).toFixed(1)} fps`);
    $("lipsync-badge").textContent = parts.join(" · ");
    $("lipsync-badge").className = "badge " + (health.connected ? "ok" : "bad");
    $("lipsync-badge").title = health.last_error ? `Lỗi gần nhất: ${health.last_error}` : "";
  }

  // ---------- 009: live scene ----------

  const scene = { enabled: false, highlight: null, error: null, issues: 0 };

  function renderScene() {
    const el = $("show-scene");
    el.hidden = !scene.enabled;
    if (!scene.enabled) return;
    const p = scene.highlight ? catalogProducts.get(scene.highlight) : null;
    const parts = [`Cảnh: ${p ? `đang làm nổi “${p.name}”` : scene.highlight ? scene.highlight : "không làm nổi món nào"}`];
    if (scene.issues) parts.push(`${scene.issues} chú ý (xem /api/scene)`);
    if (scene.error) parts.push(`lỗi gần nhất: ${scene.error}`);
    el.textContent = parts.join(" · ");
    el.classList.toggle("err", Boolean(scene.error));
  }

  async function loadScene() {
    try {
      const res = await fetch("/api/scene");
      if (!res.ok) return;
      const body = await res.json();
      scene.enabled = body.enabled;
      scene.highlight = body.highlight;
      scene.error = body.last_error;
      scene.issues = (body.issues || []).length;
      renderScene();
    } catch (_) {
      // The next `scene` event brings the highlight; the line stays hidden meanwhile.
    }
  }

  async function loadAvatar() {
    try {
      const res = await fetch("/api/avatar");
      if (!res.ok) return;
      const body = await res.json();
      renderAvatarMode(body.mode);
      renderLipsyncHealth(body.lipsync);
    } catch (_) {
      // The next `avatar_mode` / `lipsync_health` event over the WebSocket brings the same state.
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

  function fps(value) {
    return value == null ? "—" : value.toFixed(1);
  }

  function latencyRow(label, stats, cls, format = seconds) {
    const tr = document.createElement("tr");
    if (cls) tr.className = cls;
    const s = stats || { count: 0, median: null, p95: null, note: "chưa đủ mẫu" };
    const name = document.createElement("td");
    name.textContent = label;
    const count = document.createElement("td");
    count.textContent = String(s.count);
    const median = document.createElement("td");
    median.textContent = format(s.median);
    const p95 = document.createElement("td");
    if (s.p95 == null) {
      // p95 needs at least `min_samples` turns (research R12); the server sends the note text.
      p95.className = "note";
      p95.textContent = s.note || "chưa đủ mẫu";
    } else {
      p95.textContent = format(s.p95);
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
    // Lip-sync rates (005 FR-020): frames per second, not seconds; only turns rendered by the fork are counted.
    rows.push(latencyRow("fps tạo hình (khung/giây)", summary.render_fps, "rate", fps));
    rows.push(latencyRow("fps suy luận (khung/giây)", summary.infer_fps, "rate", fps));
    $("latency-rows").replaceChildren(...rows);
    renderLatencyTurns(summary.turns || []);
    $("latency-meta").textContent =
      `Đã xong ${summary.completed} lượt (host rảnh: ${summary.idle_completed}) · ` +
      `lỗi ${summary.errors} · bỏ qua ${summary.skipped} (lượt lỗi và bỏ qua không tính vào số liệu) · ` +
      `p95 cần ít nhất ${summary.min_samples} lượt.`;
  }

  const OUTCOME_LABELS = { completed: "xong", error: "lỗi", skipped: "bỏ qua" };

  function renderLatencyTurns(turns) {
    if (!turns.length) return;
    $("latency-turns").replaceChildren(
      ...turns.map((t) => {
        const tr = document.createElement("tr");
        tr.title = t.utterance_id;
        const cells = [
          t.utterance_id.slice(0, 8),
          OUTCOME_LABELS[t.outcome] || t.outcome,
          seconds(t.total_s),
          fps(t.render_fps),
          fps(t.infer_fps),
          // null = still image (no clip); an empty list = the fork rendered nothing for this turn.
          t.clips_used == null ? "ảnh tĩnh" : t.clips_used.join(", ") || "—",
          // 010 FR-010: mouth method the fork used; null on a still image or an older fork.
          t.mouth_method || "—",
        ];
        tr.append(
          ...cells.map((text) => {
            const td = document.createElement("td");
            td.textContent = text;
            return td;
          }),
        );
        return tr;
      }),
    );
  }

  async function loadLatency() {
    try {
      const res = await fetch("/api/latency");
      if (res.ok) renderLatency(await res.json());
    } catch (err) {
      // The next `latency` event over the WebSocket refreshes the table anyway.
    }
  }

  // product_id -> {name, is_primary}, for the picker's labels; refreshed with every catalog.
  let catalogProducts = new Map();

  function renderCatalog(catalog) {
    if (!catalog) return;
    catalogProducts = new Map((catalog.products || []).map((p) => [p.id, p]));
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

  function emptyItem(text) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = text;
    return li;
  }

  function segmentLabel(seg) {
    const what = seg.product_name || (seg.product_id ? seg.product_id : "chung");
    return `${what} · ${seg.topic_label || seg.topic}`;
  }

  function renderShowList(listId, items, render) {
    const list = $(listId);
    const recent = (items || []).slice(-SHOW_RECENT).reverse();
    if (recent.length === 0) {
      list.replaceChildren(emptyItem("Chưa có."));
      return;
    }
    list.replaceChildren(
      ...recent.map((item) => {
        const li = document.createElement("li");
        const time = document.createElement("span");
        time.className = "time";
        time.textContent = clock(item.at);
        li.appendChild(time);
        for (const [text, cls] of render(item)) {
          const span = document.createElement("span");
          if (cls) span.className = cls;
          span.textContent = text;
          li.appendChild(span);
        }
        return li;
      }),
    );
  }

  function option(value, text) {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = text;
    return opt;
  }

  let pickerTopics = {};
  let pickerKey = "";

  function fillNextTopics() {
    const select = $("next-topic");
    const keep = select.value;
    const topics = pickerTopics[$("next-product").value] || [];
    // An empty topic means "this product's next topic in rotation" (research R6).
    select.replaceChildren(
      option("", "Chủ đề kế tiếp theo lượt"),
      ...topics.map((t) => option(t, TOPIC_LABELS[t] || t)),
    );
    if (topics.includes(keep)) select.value = keep;
  }

  function renderNextPicker(show) {
    const open = Boolean(show) && ["running", "paused"].includes(show.state);
    const topics = (show && show.available_topics) || {};
    // Rebuild the options only when they change, so a refresh does not reset what the operator is picking.
    const key = JSON.stringify(topics) + JSON.stringify([...catalogProducts.keys()]);
    if (key !== pickerKey) {
      pickerKey = key;
      pickerTopics = topics;
      const select = $("next-product");
      const keep = select.value;
      const ids = Object.keys(topics).filter((pid) => topics[pid].length > 0);
      select.replaceChildren(
        ...ids.map((pid) => {
          const p = catalogProducts.get(pid);
          const name = p ? p.name : pid;
          return option(pid, p && p.is_primary ? `${name} (sản phẩm chính)` : name);
        }),
      );
      if (ids.includes(keep)) select.value = keep;
      fillNextTopics();
    }
    const usable = open && Boolean($("next-product").value);
    $("next-product").disabled = !usable;
    $("next-topic").disabled = !usable;
    $("next-btn").disabled = !usable;
  }

  function renderShow(show) {
    renderNextPicker(show);
    const active = Boolean(show) && ["running", "paused", "closing"].includes(show.state);
    $("show-start-btn").disabled = active;
    // Ending is only offered while it can still say the closing (FR-017); closing/ended need no second press.
    $("show-end-btn").disabled = !show || !["running", "paused"].includes(show.state);
    if (!show) {
      $("show-state").textContent = SHOW_STATE_LABELS.idle;
      $("show-state").className = "badge";
      $("show-mode").hidden = true;
      $("fallback-warning").hidden = true;
      $("show-current").textContent = "Show chưa bắt đầu.";
      $("show-sentence").textContent = "";
      $("show-next").textContent = "";
      $("show-stats").textContent = "";
      return;
    }
    $("show-state").textContent = SHOW_STATE_LABELS[show.state] || show.state;
    $("show-state").className = "badge " + (show.state === "running" ? "ok" : show.state === "ended" ? "" : "bad");
    $("show-mode").hidden = false;
    // R10: the operator must see at once that the host reads product text verbatim instead of a live script.
    $("fallback-warning").hidden = show.mode !== "fallback";
    $("show-mode").textContent = `chế độ ${SHOW_MODE_LABELS[show.mode] || show.mode}`;
    $("show-mode").className = "badge " + (show.mode === "normal" ? "ok" : "bad");
    const cur = show.current;
    $("show-current").textContent = cur ? `Đang nói: ${segmentLabel(cur)}` : "Đang chuẩn bị phân đoạn…";
    $("show-sentence").textContent = cur && cur.sentence ? `Câu ${cur.seq + 1}: ${cur.sentence}` : "";
    const next = show.next;
    $("show-next").textContent = next
      ? `Tiếp theo: ${segmentLabel(next)}${next.status === "ready" ? " (đã soạn xong)" : ""}`
      : "Tiếp theo: chưa có.";
    const stats = show.stats || {};
    const share = stats.primary_share == null ? "—" : `${Math.round(stats.primary_share * 100)}%`;
    $("show-stats").textContent =
      `Đã xong ${stats.segments || 0} phân đoạn · khoảng lặng giữa hai câu p95 ${seconds(stats.gap_p95_s)} s, ` +
      `lớn nhất ${seconds(stats.gap_max_s)} s · tỉ lệ sản phẩm chính ${share}`;
    renderShowList("show-blocked", show.recent_blocked, (b) => [
      [GUARD_LABELS[b.reason] || b.reason_label || b.reason, "reason"],
      [b.text, null],
    ]);
    renderShowList("show-errors", show.recent_errors, (e) => [
      [`Lỗi ở bước ${ERROR_STEP_LABELS[e.step] || e.step} (${e.kind})`, "err"],
      [e.message || "", null],
    ]);
  }

  // Show events only say what changed; the snapshot is the single source, so fetch it (coalesced) on each one.
  let showFetch = null;
  function refreshShow() {
    if (showFetch) return;
    showFetch = (async () => {
      try {
        const res = await fetch("/api/show");
        if (res.ok) renderShow(await res.json());
      } catch (err) {
        // The next show event retries.
      } finally {
        showFetch = null;
      }
    })();
  }

  // ---------- 008: model chain ----------

  let llmChain = null; // last ChainSnapshot, or null when the reply engine is not the chain

  function llmReason(reason) {
    return LLM_REASON_LABELS[reason] || reason || "không rõ";
  }

  // An entry rests only until its `retry_at`; after that the chain tries it again on the next turn (FR-019).
  function llmResting(entry, now) {
    return entry.status === "resting" && entry.retry_at != null && new Date(entry.retry_at).getTime() > now;
  }

  function llmCell(text) {
    const td = document.createElement("td");
    td.textContent = text;
    return td;
  }

  function renderLlmChain() {
    const chain = llmChain;
    $("llm-panel").hidden = !chain;
    renderFaultEntries();
    if (!chain) return;
    const now = Date.now();
    const entries = chain.entries || [];
    const last = entries.find((e) => e.label === chain.last_entry);
    $("llm-current").textContent = last
      ? `Đang nói bằng: ${last.label} (${last.model})`
      : "Đang nói bằng: chưa có lượt nào.";
    $("llm-rows").replaceChildren(
      ...entries.map((e) => {
        const tr = document.createElement("tr");
        const resting = llmResting(e, now);
        if (resting) tr.className = "resting";
        const status = resting ? `nghỉ tới ${clock(e.retry_at)} (${llmReason(e.reason)})` : "sẵn sàng";
        tr.append(
          llmCell(String(e.position)),
          llmCell(e.label),
          llmCell(e.model),
          llmCell(e.platform || "—"),
          llmCell(status),
        );
        return tr;
      }),
    );
    // US3 #2: why the entries before the speaking one are not used, and when they are tried again.
    const backup = Boolean(chain.using_backup) && Boolean(last);
    $("llm-backup-warning").hidden = !backup;
    if (backup) {
      $("llm-backup-reasons").replaceChildren(
        ...entries
          .filter((e) => e.position < last.position)
          .map((e) => {
            const li = document.createElement("li");
            li.textContent = llmResting(e, now)
              ? `${e.label}: ${llmReason(e.reason)}, thử lại lúc ${clock(e.retry_at)}`
              : `${e.label}: hết giờ nghỉ, thử lại ở lượt kế tiếp`;
            return li;
          }),
      );
    }
    $("llm-none-warning").hidden = entries.length === 0 || entries.some((e) => !llmResting(e, now));
  }

  // ---------- dev fault form ----------

  function renderFaultEntries() {
    const select = $("fault-entry");
    const labels = llmChain ? (llmChain.entries || []).map((e) => e.label) : [];
    const key = JSON.stringify(labels);
    if (select.dataset.key === key) return;
    select.dataset.key = key;
    const keep = select.value;
    select.replaceChildren(option("", "Cả bước (không theo mục)"), ...labels.map((l) => option(l, l)));
    if (labels.includes(keep)) select.value = keep;
    renderFaultModes();
  }

  function renderFaultModes() {
    const entry = $("fault-entry").value;
    const step = $("fault-step");
    // Entry faults exist only on the `llm` step (008 contracts/api.md §1).
    if (entry) step.value = "llm";
    step.disabled = Boolean(entry);
    const mode = $("fault-mode");
    const keep = mode.value;
    const modes = entry
      ? ENTRY_FAULT_MODES.map((m) => [m, LLM_REASON_LABELS[m] || m])
      : Object.entries(STEP_FAULT_MODES);
    mode.replaceChildren(...modes.map(([value, text]) => option(value, `${value} (${text})`)));
    if (modes.some(([value]) => value === keep)) mode.value = keep;
  }

  async function setupFaultPanel() {
    try {
      // The route is POST only and registered only in dev: 405 here means it exists, 404 means APP_ENV is not dev.
      const res = await fetch("/api/debug/fault");
      if (res.status !== 405) return;
    } catch (err) {
      return;
    }
    $("fault-step").replaceChildren(...FAULT_STEPS.map((s) => option(s, s)));
    renderFaultModes();
    $("fault-panel").hidden = false;
    // Same dev-only debug router as the fault route.
    $("speak-audio-panel").hidden = false;
  }

  function turnLabel(id) {
    const t = turns.get(id);
    return t ? `${t.author}: “${t.text}”` : id;
  }

  const handlers = {
    state(msg) {
      // Sent on every (re)connect: the open alerts are the whole truth, so a reloaded page shows the same banner.
      openAlerts.clear();
      for (const alert of msg.alerts || []) openAlerts.set(alert.alert_id, alert);
      renderAlerts();
      if (msg.session && msg.session.output_mode) outputMode = msg.session.output_mode;
      setHost(Boolean(msg.session && msg.session.host_connected), msg.session && msg.session.host_role);
      if (msg.session) setSession(msg.session.state);
      renderQueue(msg.queue || []);
      renderCatalog(msg.catalog);
      renderShow(msg.show || null);
      llmChain = msg.llm_chain || null;
      renderLlmChain();
    },
    llm_chain(msg) {
      llmChain = { entries: msg.entries, last_entry: msg.last_entry, using_backup: msg.using_backup };
      renderLlmChain();
    },
    show_state() {
      refreshShow();
    },
    segment_started() {
      refreshShow();
    },
    segment_finished() {
      refreshShow();
    },
    segment_next() {
      refreshShow();
    },
    show_stats() {
      refreshShow();
    },
    show_error() {
      refreshShow();
    },
    session_state(msg) {
      setSession(msg.state);
    },
    content_replaced(msg) {
      renderCatalog(msg);
      // A new catalog changes `available_topics`, which the next-segment picker reads from the snapshot.
      refreshShow();
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
      setHost(msg.connected, msg.role);
    },
    turn_started(msg) {
      turns.set(msg.utterance_id, { author: msg.author, text: msg.text });
      currentId = msg.utterance_id;
      $("turn-meta").textContent = `Đang trả lời ${msg.author}: “${msg.text}”`;
      $("turn-sentences").replaceChildren();
    },
    sentence(msg) {
      if (msg.segment_id) {
        $("show-sentence").textContent = `Đang nói: ${msg.text}`;
        return;
      }
      if (msg.utterance_id !== currentId) return;
      const li = document.createElement("li");
      li.textContent = msg.text;
      $("turn-sentences").appendChild(li);
    },
    guard_blocked(msg) {
      if (msg.segment_id) {
        // A scripted sentence: listed in the Show area with its text (FR-019).
        refreshShow();
        return;
      }
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
        // Same layout as a show error: the step and kind, then the engine's own message (003 contracts/events.md §2).
        const kind = msg.error_kind ? ` (${msg.error_kind})` : "";
        pushItem("errors", msg.ts, [
          [`Lỗi ở bước ${step}${kind}: ${msg.error_message || label}`, "err"],
          [msg.error_message ? label : "", null],
        ]);
        pushItem("history", msg.ts, [[`lỗi (${step}) · ${label}`, "err"]]);
      } else {
        pushItem("history", msg.ts, [[`${msg.outcome}${total} · ${label}`, null]]);
      }
      turns.delete(msg.utterance_id);
    },
    latency(msg) {
      renderLatency(msg);
    },
    alert(msg) {
      const alert = msg.alert;
      if (alert.state === "open") {
        openAlerts.set(alert.alert_id, alert);
      } else {
        // An auto-skip closes its alert within a moment of saying so; the history keeps what happened.
        const last = openAlerts.get(alert.alert_id) || alert;
        openAlerts.delete(alert.alert_id);
        const took = alert.seconds != null ? ` (${Math.round(alert.seconds)} giây)` : "";
        pushItem("history", msg.ts, [[`đã hết cảnh báo · ${last.message}${took}`, alert.level === "operator" ? "err" : null]]);
      }
      renderAlerts();
    },
    avatar_mode(msg) {
      renderAvatarMode(msg);
    },
    lipsync_health(msg) {
      renderLipsyncHealth(msg);
    },
    scene(msg) {
      scene.enabled = true;
      if (msg.kind === "highlight") scene.highlight = msg.product_id;
      else if (msg.kind === "error") scene.error = msg.message;
      else if (msg.kind === "rendered") return loadScene();
      renderScene();
    },
  };

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/control`);
    ws.onopen = () => {
      setServer(true);
      // The `state` message carries no latency; load the current summary once per (re)connect.
      loadLatency();
      // Nor the avatar mode: the `avatar_mode` event fires only on a change, so a fresh page asks once.
      loadAvatar();
      loadScene();
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
    const body = await sendControl("/api/pause");
    if (body) {
      $("control-msg").textContent = body.show_state
        ? "Host nói nốt câu đang nói rồi dừng show."
        : "Host nói nốt câu trả lời hiện tại rồi dừng.";
      if (body.show_state) refreshShow();
    }
  });
  $("resume-btn").addEventListener("click", async () => {
    const body = await sendControl("/api/resume");
    if (body) {
      $("control-msg").textContent = "";
      if (body.show_state) refreshShow();
    }
  });
  $("skip-btn").addEventListener("click", async () => {
    const body = await sendControl("/api/skip");
    if (!body) return;
    if (body.skipped_segment_id) {
      $("control-msg").textContent = "Đã bỏ qua phần còn lại của phân đoạn đang nói.";
      refreshShow();
    } else if (body.skipped_utterance_id) {
      $("control-msg").textContent = `Đã bỏ qua lượt ${turnLabel(body.skipped_utterance_id)}.`;
    } else {
      $("control-msg").textContent = "Host đang không nói, không có gì để bỏ qua.";
    }
  });

  $("show-end-btn").addEventListener("click", async () => {
    const body = await sendControl("/api/show/end");
    if (!body) return;
    $("show-msg").textContent =
      body.state === "closing" ? "Host nói nốt câu đang nói, chào kết rồi dừng show." : "Không có show đang chạy.";
    refreshShow();
  });

  $("next-product").addEventListener("change", fillNextTopics);

  $("next-btn").addEventListener("click", async () => {
    const body = { product_id: $("next-product").value };
    if ($("next-topic").value) body.topic = $("next-topic").value;
    $("next-msg").textContent = "Đang gửi…";
    try {
      const res = await fetch("/api/show/next", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const reply = await res.json();
      if (!res.ok) {
        $("next-msg").textContent = `Chưa chọn được: ${reply.message || res.status}`;
        return;
      }
      const p = catalogProducts.get(reply.product_id);
      const what = `${p ? p.name : reply.product_id} · ${TOPIC_LABELS[reply.topic] || reply.topic}`;
      $("next-msg").textContent = `Đã chọn: ${what}. Host nói xong phân đoạn hiện tại rồi chuyển sang.`;
      refreshShow();
    } catch (err) {
      $("next-msg").textContent = `Không gửi được: ${err}`;
    }
  });

  $("show-start-btn").addEventListener("click", async () => {
    $("show-msg").textContent = "Đang bắt đầu…";
    try {
      const res = await fetch("/api/show/start", { method: "POST" });
      const body = await res.json();
      if (!res.ok) {
        $("show-msg").textContent = `Chưa bắt đầu được: ${body.message || res.status}`;
        return;
      }
      $("show-msg").textContent = body.already_running ? "Show đang chạy rồi." : "Đã bắt đầu show, host chào mở đầu.";
      refreshShow();
    } catch (err) {
      $("show-msg").textContent = `Không gửi được: ${err}`;
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

  $("fault-entry").addEventListener("change", renderFaultModes);

  $("fault-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const body = { step: $("fault-step").value, mode: $("fault-mode").value, count: Number($("fault-count").value) };
    const entry = $("fault-entry").value;
    if (entry) body.entry = entry;
    $("fault-msg").textContent = "Đang gửi…";
    try {
      const res = await fetch("/api/debug/fault", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const reply = await res.json();
      if (!res.ok) {
        $("fault-msg").textContent = `Không tạo được lỗi: ${reply.message || res.status}`;
        return;
      }
      const where = reply.entry ? `mục ${reply.entry}` : `bước ${reply.step}`;
      $("fault-msg").textContent = `Đã hẹn ${reply.count} lỗi ${reply.mode} ở ${where}.`;
    } catch (err) {
      $("fault-msg").textContent = `Không gửi được: ${err}`;
    }
  });

  $("lipsync-enable-btn").addEventListener("click", async () => {
    $("avatar-msg").textContent = "Đang bật lại…";
    try {
      const res = await fetch("/api/avatar/lipsync", { method: "POST" });
      const body = await res.json();
      if (!res.ok) {
        $("avatar-msg").textContent = body.message || String(res.status);
        return;
      }
      $("avatar-msg").textContent = "";
      renderAvatarMode(body);
    } catch (err) {
      $("avatar-msg").textContent = `Không gửi được: ${err}`;
    }
  });

  $("speak-audio-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const file = $("speak-audio-file").files[0];
    if (!file) return;
    $("speak-audio-msg").textContent = "Đang phát…";
    try {
      // Raw body: the server reads the WAV bytes directly, so no multipart parser is needed.
      const res = await fetch("/api/debug/speak-audio", {
        method: "POST",
        headers: { "Content-Type": "audio/wav", "X-Filename": encodeURIComponent(file.name) },
        body: file,
      });
      const reply = await res.json();
      if (!res.ok) {
        $("speak-audio-msg").textContent = `Không phát được: ${reply.message || res.status}`;
        return;
      }
      const fmt = (v, digits) => (v === null || v === undefined ? "—" : Number(v).toFixed(digits));
      $("speak-audio-msg").textContent =
        `Dài ${fmt(reply.duration_s, 1)} s · khung đầu sau ${fmt(reply.first_frame_s, 2)} s` +
        ` · fps tạo hình ${fmt(reply.render_fps, 1)}`;
    } catch (err) {
      $("speak-audio-msg").textContent = `Không gửi được: ${err}`;
    }
  });

  // 007 FR-001, FR-005 (contracts/api.md §1): fail rows first catch the eye by colour, but the order stays the
  // server's so the table reads the same as the CLI.
  const READINESS_LABELS = { ok: "Đạt", warn: "Chú ý", fail: "Lỗi", unknown: "Chưa rõ" };

  function renderReadiness(result) {
    const verdict = $("readiness-verdict");
    verdict.hidden = false;
    verdict.textContent = result.ready ? "SẴN SÀNG" : "CHƯA SẴN SÀNG";
    verdict.className = `badge ${result.ready ? "ok" : "bad"}`;
    $("readiness-rows").replaceChildren(
      ...result.items.map((item) => {
        const tr = document.createElement("tr");
        tr.className = `check-${item.status}`;
        const status = document.createElement("td");
        const mark = document.createElement("span");
        mark.className = `check-mark ${item.status}`;
        mark.textContent = READINESS_LABELS[item.status] || item.status;
        status.append(mark);
        tr.append(llmCell(item.label), status, llmCell(item.message), llmCell(item.action || ""));
        return tr;
      }),
    );
    $("readiness-table").hidden = false;
    $("readiness-manual").replaceChildren(
      ...result.manual.map((task) => {
        const li = document.createElement("li");
        const box = document.createElement("input");
        box.type = "checkbox";
        const label = document.createElement("label");
        label.append(box, ` ${task}`);
        li.append(label);
        return li;
      }),
    );
    $("readiness-manual-box").hidden = result.manual.length === 0;
    $("readiness-msg").textContent = `Kiểm lúc ${clock(result.checked_at)}, mất ${result.duration_ms} ms.`;
  }

  $("readiness-btn").addEventListener("click", async () => {
    const btn = $("readiness-btn");
    btn.disabled = true;
    $("readiness-msg").textContent = "Đang kiểm…";
    try {
      const res = await fetch("/api/readiness");
      const body = await res.json();
      if (!res.ok) {
        $("readiness-msg").textContent = `Không kiểm được: ${body.message || res.status}`;
        return;
      }
      renderReadiness(body);
    } catch (err) {
      $("readiness-msg").textContent = `Không gửi được: ${err}`;
    } finally {
      btn.disabled = false;
    }
  });

  setInterval(renderLlmChain, LLM_TICK_MS);
  setupFaultPanel();
  connect();
})();
