// Control page (FR-016: queue, dropped comments, current turn and errors; FR-018: latency table;
// FR-022: content upload; contracts/api.md §2–3). 004 FR-019: the "Show" area (state, mode, current and next
// segment, recent blocked sentences and errors, gap p95/max), refreshed from `GET /api/show` on show events.
// 004 FR-018: the "phân đoạn kế tiếp" picker offers only product/topic pairs listed in `available_topics` (US5 #2).
// 008 FR-017, FR-020: the read-only "Model LLM" area (008 contracts/api.md §3) and, in dev, the fault form with the
// per-entry modes.
// 007 FR-001, FR-005: the "Kiểm tra trước demo" button shows `GET /api/readiness` as a table plus the manual checks.
// 012 US1: the "Ảnh sản phẩm" block uploads, previews and applies one product's picture (012 contracts/api.md §1).
// 012 US3: the same block shows the image in use (times, versions, size of uploads/) with "Về ảnh trước" and "Gỡ ảnh".
// 012 US4: "AI vừa nói" lists the scripted sentences just said; a product name opens that product's text from the
// file ("Nội dung sản phẩm"), live or staged (012 contracts/api.md §4).
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
  // Same wording as Topic.label in core/models.py. The picker never offers opening/closing (it reads only
  // `available_topics`; the director owns those two), but "AI vừa nói" labels them.
  const TOPIC_LABELS = {
    opening: "Chào mở màn",
    intro: "Giới thiệu chung",
    highlights: "Điểm nổi bật",
    specs: "Thông số",
    price: "Giá và phân loại",
    promotion: "Khuyến mãi",
    faq: "Câu hỏi thường gặp",
    call_to_action: "Kêu gọi mua",
    closing: "Chào kết",
  };
  // Same cap as SPOKEN_MAX in app/spoken.py.
  const SPOKEN_MAX = 100;
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

  const LIPSYNC_MODELS = { wav2lip: "Wav2Lip", ultralight: "Ultralight" };
  const LIPSYNC_TEACHERS = { musetalk: "MuseTalk", infinitetalk: "InfiniteTalk" };

  // Same text as `lipsync_label` in core/models.py (011 contracts/lipsync-selection.md §7).
  function lipsyncModelText(block) {
    if (!block || !block.model) return "Model: không rõ (fork cũ)";
    const parts = [LIPSYNC_MODELS[block.model] || block.model];
    if (block.teacher) parts.push(`thầy ${LIPSYNC_TEACHERS[block.teacher] || block.teacher}`);
    if (block.character_id) parts.push(block.character_id);
    return "Model: " + parts.join(" · ");
  }

  function renderLipsyncHealth(health) {
    // Configured `static` has no fork: the status stays hidden.
    $("lipsync-status").hidden = !health;
    const mismatch = Boolean(health && health.model_mismatch);
    $("lipsync-mismatch").hidden = !mismatch;
    $("lipsync-mismatch").textContent = mismatch
      ? "Model nhép miệng không khớp cấu hình: " + lipsyncModelText(health.lipsync) +
        ". Tắt fork rồi bật lại (scripts/livetalking/run.ps1), rồi bấm Kiểm tra trước demo."
      : "";
    if (!health) return;
    // The block comes with the fork's hello: before the first one there is nothing to name.
    $("lipsync-model").hidden = !health.connected;
    $("lipsync-model").textContent = lipsyncModelText(health.lipsync);
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

  // ---------- 012: product images ----------

  // Same states as ProductImageStatus.state (012 data-model §4).
  const IMAGE_STATE_LABELS = { kit: "ảnh bộ cảnh", upload: "ảnh tải lên", removed: "đã gỡ ảnh", none: "chưa có ảnh" };
  const images = { products: [], sceneEnabled: true, sceneUsable: true, catalogVersion: null, uploadsBytes: 0 };
  // The product being edited and the uploaded version waiting for "Áp dụng"; nothing here touches live.
  const pick = { pid: null, vid: null, previewOf: null, previewUrl: null };

  async function apiMessage(res) {
    try {
      const body = await res.json();
      return body.message || `HTTP ${res.status}`;
    } catch (_) {
      return `HTTP ${res.status}`;
    }
  }

  function refreshLiveStill() {
    const img = $("image-live");
    img.hidden = false;
    img.onerror = () => {
      img.hidden = true;
    };
    img.src = `/api/scene/still.png?t=${Date.now()}`;
  }

  function clearPreview(reason) {
    if (pick.previewUrl) URL.revokeObjectURL(pick.previewUrl);
    pick.previewUrl = null;
    pick.previewOf = null;
    $("image-preview").hidden = true;
    $("image-preview").removeAttribute("src");
    $("image-preview-empty").hidden = false;
    if (reason) $("image-msg").textContent = reason;
  }

  function resetCandidate() {
    pick.vid = null;
    clearPreview();
    $("image-file").value = "";
    $("image-rights").checked = false;
    $("image-bg-warning").hidden = true;
    $("image-upload-msg").textContent = "";
    updateImageButtons();
  }

  function updateImageButtons() {
    $("image-preview-btn").disabled = !pick.vid || !images.sceneEnabled || !images.sceneUsable;
    // FR-006: nothing goes live without the rights box ticked.
    $("image-apply-btn").disabled = !pick.vid || !$("image-rights").checked;
  }

  function imageItem(p) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "image-item" + (p.product_id === pick.pid ? " selected" : "");
    const thumb = document.createElement("div");
    thumb.className = "thumb";
    if (p.thumb_url) {
      const img = document.createElement("img");
      img.alt = "";
      img.src = p.thumb_url;
      thumb.append(img);
    } else {
      const none = document.createElement("span");
      none.className = "empty";
      none.textContent = p.state === "removed" ? "Đã gỡ: chỉ hiện thẻ tên/giá" : "Chưa có ảnh";
      thumb.append(none);
    }
    const name = document.createElement("div");
    name.className = "name";
    name.textContent = p.is_primary ? `${p.name} (chính)` : p.name;
    const state = document.createElement("div");
    state.className = "state";
    state.textContent = IMAGE_STATE_LABELS[p.state] || p.state;
    btn.append(thumb, name, state);
    for (const issue of p.issues || []) {
      const line = document.createElement("div");
      line.className = issue.level === "error" ? "state err" : "state";
      line.textContent = issue.message;
      btn.append(line);
    }
    btn.addEventListener("click", () => selectImageProduct(p.product_id));
    return btn;
  }

  function renderImages() {
    $("images-scene-off").hidden = images.sceneEnabled;
    const badge = $("images-badge");
    badge.hidden = !images.sceneEnabled || images.sceneUsable;
    badge.className = "badge bad";
    badge.textContent = "bộ cảnh chưa dùng được";
    const list = $("images-list");
    if (images.products.length === 0) {
      list.replaceChildren(emptyItem("File nội dung chưa có sản phẩm nào."));
    } else {
      list.replaceChildren(
        ...images.products.map((p) => {
          const li = document.createElement("li");
          li.append(imageItem(p));
          return li;
        }),
      );
    }
    const current = images.products.find((p) => p.product_id === pick.pid);
    $("image-editor").hidden = !current;
    if (current) {
      $("image-editor-title").textContent = `Đổi ảnh: ${current.name}`;
      renderCurrentImage(current);
    }
    updateImageButtons();
  }

  // ---------- 012 US3: the image in use, "Về ảnh trước", "Gỡ ảnh" (FR-016–FR-018) ----------

  function stamp(ts) {
    if (!ts) return "—";
    const d = new Date(ts);
    return Number.isNaN(d.getTime()) ? ts : d.toLocaleString("vi-VN", { hour12: false });
  }

  function sizeText(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function renderCurrentImage(p) {
    $("image-current-state").textContent = IMAGE_STATE_LABELS[p.state] || p.state;
    // Kit art and removed images have no upload record: the three times only describe an uploaded version.
    $("image-current-uploaded").textContent = stamp(p.uploaded_at);
    $("image-current-applied").textContent = stamp(p.applied_at);
    $("image-current-rights").textContent = stamp(p.rights_confirmed_at);
    // FR-016: one step back, locked when there is nothing before.
    $("image-revert-btn").disabled = !p.can_revert;
    $("image-remove-btn").disabled = p.state === "removed" || p.state === "none";
    const versions = p.versions || [];
    $("image-versions-count").textContent = String(versions.length);
    const list = $("image-versions");
    if (versions.length === 0) {
      list.replaceChildren(emptyItem("Chưa tải ảnh nào cho món này."));
    } else {
      list.replaceChildren(
        ...versions.map((v) => {
          const li = document.createElement("li");
          const inUse = v.version_id === p.version_id;
          li.className = inUse ? "active" : "";
          const name = v.source_name ? ` · ${v.source_name}` : "";
          const applied = v.applied_at ? ` · áp ${stamp(v.applied_at)}` : " · chưa áp";
          li.textContent = `${stamp(v.uploaded_at)}${name}${applied}${inUse ? " (đang dùng)" : ""}`;
          return li;
        }),
      );
    }
    $("image-uploads-size").textContent = sizeText(images.uploadsBytes);
  }

  async function changeImage(action, init) {
    const pid = pick.pid;
    if (!pid) return;
    const revert = $("image-revert-btn");
    const remove = $("image-remove-btn");
    revert.disabled = true;
    remove.disabled = true;
    $("image-msg").textContent = action === "revert" ? "Đang quay về ảnh trước…" : "Đang gỡ ảnh…";
    try {
      const res = await fetch(`/api/scene/images/${encodeURIComponent(pid)}/${action}`, { method: "POST", ...init });
      if (!res.ok) {
        $("image-msg").textContent = `Không đổi được, live giữ nguyên. ${await apiMessage(res)}`;
        return;
      }
      const body = await res.json();
      const what =
        action === "remove"
          ? "Đã gỡ ảnh; món chỉ còn thẻ tên/giá"
          : body.active === "kit"
            ? "Đã về ảnh bộ cảnh"
            : body.active === null
              ? "Đã về trạng thái không ảnh"
              : "Đã về ảnh trước";
      $("image-msg").textContent = body.scene_enabled
        ? `${what}; live đổi sau ${Math.round(body.to_frame_ms ?? 0)} ms.`
        : `${what}, nhưng cảnh đang tắt nên live chưa đổi.`;
      refreshLiveStill();
    } catch (err) {
      $("image-msg").textContent = `Không gửi được: ${err}`;
    } finally {
      // The list carries the new can_revert and state, which re-enable the right buttons.
      loadImages();
    }
  }

  $("image-revert-btn").addEventListener("click", () => changeImage("revert", {}));
  $("image-remove-btn").addEventListener("click", () => {
    const p = images.products.find((x) => x.product_id === pick.pid);
    if (!p) return;
    // FR-017: removing takes the picture off live, so it asks first; "Về ảnh trước" brings it back.
    const ok = confirm(`Gỡ ảnh của "${p.name}" khỏi live? Món vẫn còn thẻ tên/giá; bấm “Về ảnh trước” để lấy lại ảnh.`);
    if (!ok) return;
    changeImage("remove", {
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirm: true }),
    });
  });

  async function loadImages() {
    try {
      const res = await fetch("/api/scene/images");
      if (!res.ok) return;
      const body = await res.json();
      const catalogChanged = images.catalogVersion !== null && body.catalog_version !== images.catalogVersion;
      images.products = body.products || [];
      images.sceneEnabled = body.scene_enabled;
      images.sceneUsable = body.scene_usable;
      images.catalogVersion = body.catalog_version;
      images.uploadsBytes = body.uploads_bytes || 0;
      if (pick.pid && !images.products.some((p) => p.product_id === pick.pid)) {
        pick.pid = null;
        resetCandidate();
      } else if (catalogChanged && pick.previewOf) {
        clearPreview("Nội dung sản phẩm vừa đổi nên bản xem trước đã hủy; bấm “Xem trước” lại.");
      }
      renderImages();
    } catch (_) {
      // The next `image_changed` or reconnect reloads the list.
    }
  }

  function selectImageProduct(pid) {
    if (pick.pid !== pid) {
      pick.pid = pid;
      resetCandidate();
      $("image-msg").textContent = "";
    }
    renderImages();
    refreshLiveStill();
  }

  async function previewImage() {
    if (!pick.pid || !pick.vid) return;
    const of = { pid: pick.pid, vid: pick.vid };
    $("image-msg").textContent = "Đang dựng bản xem trước…";
    try {
      const q = new URLSearchParams({ product_id: of.pid, version_id: of.vid });
      const res = await fetch(`/api/scene/preview.png?${q}`);
      if (!res.ok) {
        $("image-msg").textContent = `Không xem trước được: ${await apiMessage(res)}`;
        return;
      }
      const blob = await res.blob();
      // The operator may have picked another product or file meanwhile.
      if (pick.pid !== of.pid || pick.vid !== of.vid) return;
      clearPreview();
      pick.previewUrl = URL.createObjectURL(blob);
      pick.previewOf = of;
      $("image-preview").src = pick.previewUrl;
      $("image-preview").hidden = false;
      $("image-preview-empty").hidden = true;
      $("image-msg").textContent = "Xem trước xong; live chưa đổi.";
      refreshLiveStill();
    } catch (err) {
      $("image-msg").textContent = `Không gửi được: ${err}`;
    }
  }

  $("image-file").addEventListener("change", async () => {
    const file = $("image-file").files[0];
    if (!file || !pick.pid) return;
    const pid = pick.pid;
    pick.vid = null;
    clearPreview();
    $("image-bg-warning").hidden = true;
    updateImageButtons();
    $("image-upload-msg").textContent = "Đang kiểm ảnh…";
    try {
      // Raw body like PUT /api/content (012 research R3); the name is only shown back, never used as a path.
      const res = await fetch(`/api/scene/uploads?product_id=${encodeURIComponent(pid)}`, {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream", "X-Filename": encodeURIComponent(file.name) },
        body: file,
      });
      if (!res.ok) {
        $("image-upload-msg").textContent = `Không nhận ảnh, live giữ ảnh cũ. ${await apiMessage(res)}`;
        return;
      }
      const body = await res.json();
      if (pick.pid !== pid) return;
      pick.vid = body.version_id;
      $("image-bg-warning").hidden = !(body.warnings || []).includes("has_background");
      $("image-upload-msg").textContent = `Đã nhận ảnh ${body.width}×${body.height}${body.reused ? " (trùng ảnh đã tải trước)" : ""}.`;
      updateImageButtons();
      loadImages();
      // FR-008: the operator sees the product on the desk before deciding.
      if (images.sceneEnabled && images.sceneUsable) previewImage();
    } catch (err) {
      $("image-upload-msg").textContent = `Không gửi được: ${err}`;
    }
  });

  $("image-rights").addEventListener("change", updateImageButtons);
  $("image-preview-btn").addEventListener("click", previewImage);
  $("image-cancel-btn").addEventListener("click", () => {
    resetCandidate();
    $("image-msg").textContent = "Đã hủy; live không đổi.";
  });

  $("image-apply-btn").addEventListener("click", async () => {
    if (!pick.pid || !pick.vid || !$("image-rights").checked) return;
    const btn = $("image-apply-btn");
    btn.disabled = true;
    $("image-msg").textContent = "Đang áp dụng…";
    try {
      const res = await fetch(`/api/scene/images/${encodeURIComponent(pick.pid)}/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ version_id: pick.vid, rights_confirmed: true }),
      });
      if (!res.ok) {
        $("image-msg").textContent = `Không áp dụng được, live giữ ảnh cũ. ${await apiMessage(res)}`;
        updateImageButtons();
        return;
      }
      const body = await res.json();
      resetCandidate();
      $("image-msg").textContent = body.scene_enabled
        ? `Đã áp dụng; ảnh lên live sau ${Math.round(body.to_frame_ms ?? 0)} ms.`
        : "Đã lưu ảnh, nhưng cảnh đang tắt, ảnh chưa hiện trên live.";
      refreshLiveStill();
      loadImages();
    } catch (err) {
      $("image-msg").textContent = `Không gửi được: ${err}`;
      updateImageButtons();
    }
  });

  // Another tab (or this one) changed a product's picture: the list follows, and a preview of the old state is void.
  function onImageChanged(msg) {
    if (pick.previewOf && pick.previewOf.pid === msg.product_id) {
      clearPreview("Ảnh của món này vừa đổi ở tab khác nên bản xem trước đã hủy.");
    }
    loadImages();
    if (pick.pid) refreshLiveStill();
  }

  // ---------- 012 US2: "Chuẩn bị bộ mới" ----------

  // Same values as StagedProductView.image (012 contracts/api.md §2).
  const STAGED_IMAGE_LABELS = {
    staged: "ảnh mới",
    reused_upload: "dùng lại ảnh cũ",
    reused_kit: "dùng lại ảnh cũ (bộ cảnh)",
    removed: "đã gỡ ảnh: chỉ hiện thẻ tên/giá",
    missing: "thiếu ảnh",
  };
  // The staged set as the server last sent it, the product being edited and its uploaded version not yet assigned.
  const staging = { view: null, pid: null, vid: null, previewUrl: null };

  function stagedProduct() {
    return staging.view && staging.view.products.find((p) => p.product_id === staging.pid);
  }

  function refreshStagingLive() {
    const img = $("staging-live");
    img.hidden = false;
    img.onerror = () => {
      img.hidden = true;
    };
    img.src = `/api/scene/still.png?t=${Date.now()}`;
  }

  function clearStagingPreview() {
    if (staging.previewUrl) URL.revokeObjectURL(staging.previewUrl);
    staging.previewUrl = null;
    $("staging-preview").hidden = true;
    $("staging-preview").removeAttribute("src");
    $("staging-preview-empty").hidden = false;
  }

  function resetStagingCandidate() {
    staging.vid = null;
    $("staging-image-file").value = "";
    $("staging-rights").checked = false;
    $("staging-bg-warning").hidden = true;
    $("staging-upload-msg").textContent = "";
    updateStagingButtons();
  }

  function updateStagingButtons() {
    // FR-006 as in US1: an image joins the set only with the rights box ticked.
    $("staging-assign-btn").disabled = !staging.vid || !$("staging-rights").checked;
    const current = stagedProduct();
    $("staging-unassign-btn").hidden = !current || current.image !== "staged";
    $("staging-preview-btn").disabled = !images.sceneEnabled || !images.sceneUsable;
  }

  function stagedItem(p) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "image-item" + (p.product_id === staging.pid ? " selected" : "");
    const thumb = document.createElement("div");
    thumb.className = "thumb";
    if (p.thumb_url) {
      const img = document.createElement("img");
      img.alt = "";
      img.src = p.thumb_url;
      thumb.append(img);
    } else {
      const none = document.createElement("span");
      none.className = "empty";
      none.textContent = p.image === "removed" ? "Đã gỡ ảnh" : "Chưa có ảnh";
      thumb.append(none);
    }
    const name = document.createElement("div");
    name.className = "name";
    name.textContent = p.is_primary ? `${p.name} (chính)` : p.name;
    const state = document.createElement("div");
    const lacking = p.image === "removed" || p.image === "missing";
    state.className = "state" + (lacking ? " warn" : p.image === "staged" ? " new" : "");
    state.textContent = STAGED_IMAGE_LABELS[p.image] || p.image;
    btn.append(thumb, name, state);
    btn.addEventListener("click", () => {
      if (staging.pid !== p.product_id) resetStagingCandidate();
      staging.pid = p.product_id;
      $("staging-editor-msg").textContent = "";
      renderStaging();
    });
    return btn;
  }

  function renderStaging() {
    const view = staging.view;
    $("staging-body").hidden = !view;
    if (!view) {
      $("staging-list").replaceChildren();
      $("staging-editor").hidden = true;
      clearStagingPreview();
      return;
    }
    const missing = view.missing.length;
    $("staging-meta").textContent =
      `File “${view.source_name}” · ${view.products.length} món · ` + (missing ? `${missing} món thiếu ảnh` : "đủ ảnh");
    $("staging-live-changed").hidden = !view.live_changed;
    $("staging-list").replaceChildren(
      ...view.products.map((p) => {
        const li = document.createElement("li");
        li.append(stagedItem(p));
        return li;
      }),
    );
    const current = stagedProduct();
    $("staging-editor").hidden = !current;
    if (current) $("staging-editor-title").textContent = `Ảnh cho bộ mới: ${current.name}`;
    if ($("staging-live").hidden) refreshStagingLive();
    updateStagingButtons();
  }

  function setStagingView(view) {
    const replaced = !view || !staging.view || view.staged_id !== staging.view.staged_id;
    staging.view = view;
    if (replaced) {
      staging.pid = null;
      resetStagingCandidate();
      clearStagingPreview();
      // A message about the previous set would be read as being about this one.
      $("staging-msg").textContent = "";
      $("staging-editor-msg").textContent = "";
    } else if (staging.pid && !view.products.some((p) => p.product_id === staging.pid)) {
      staging.pid = null;
    }
    renderStaging();
  }

  async function loadStaging() {
    try {
      const res = await fetch("/api/content/staging");
      if (res.status === 404) return setStagingView(null);
      if (!res.ok) return;
      setStagingView(await res.json());
    } catch (_) {
      // The next `staging` event or reconnect reloads it.
    }
  }

  function onStagingEvent(msg) {
    const mine = staging.view && staging.view.staged_id === msg.staged_id;
    if (mine && msg.action === "cancelled") $("staging-file-msg").textContent = "Bộ chuẩn bị đã bị hủy (ở tab khác).";
    if (msg.action === "applied") {
      loadImages();
      refreshLiveStill();
    }
    loadStaging();
  }

  function stagingPost(path, body) {
    return fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  }

  $("staging-file").addEventListener("change", async () => {
    const file = $("staging-file").files[0];
    if (!file) return;
    showContentIssues([], "staging-issues");
    $("staging-file-msg").textContent = "Đang đọc file…";
    try {
      // Same raw body as `PUT /api/content`, but nothing is installed (FR-013).
      const res = await fetch("/api/content/staging", {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream", "X-Filename": encodeURIComponent(file.name) },
        body: file,
      });
      const body = await res.json();
      if (!res.ok) {
        $("staging-file-msg").textContent = `Không đọc được file, live không đổi. ${body.message || res.status}`;
        showContentIssues(body.details || [], "staging-issues");
        return;
      }
      setStagingView(body);
      $("staging-file-msg").textContent = "Đã đọc file; live chưa đổi. Bấm từng món để gán ảnh.";
    } catch (err) {
      $("staging-file-msg").textContent = `Không gửi được: ${err}`;
    } finally {
      $("staging-file").value = "";
    }
  });

  $("staging-image-file").addEventListener("change", async () => {
    const file = $("staging-image-file").files[0];
    if (!file || !staging.pid) return;
    staging.vid = null;
    $("staging-bg-warning").hidden = true;
    updateStagingButtons();
    $("staging-upload-msg").textContent = "Đang kiểm ảnh…";
    try {
      const res = await fetch(`/api/scene/uploads?product_id=${encodeURIComponent(staging.pid)}`, {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream", "X-Filename": encodeURIComponent(file.name) },
        body: file,
      });
      if (!res.ok) {
        $("staging-upload-msg").textContent = `Không nhận ảnh. ${await apiMessage(res)}`;
        return;
      }
      const body = await res.json();
      staging.vid = body.version_id;
      $("staging-bg-warning").hidden = !(body.warnings || []).includes("has_background");
      const reused = body.reused ? " (trùng ảnh đã tải trước)" : "";
      $("staging-upload-msg").textContent = `Đã nhận ảnh ${body.width}×${body.height}${reused}. Tick xác nhận rồi bấm “Gán ảnh này”.`;
      updateStagingButtons();
    } catch (err) {
      $("staging-upload-msg").textContent = `Không gửi được: ${err}`;
    }
  });

  async function assignStaged(versionId) {
    const view = staging.view;
    if (!view || !staging.pid) return;
    const body = { staged_id: view.staged_id, version_id: versionId, rights_confirmed: versionId ? $("staging-rights").checked : false };
    $("staging-editor-msg").textContent = "Đang gán…";
    try {
      const res = await stagingPost(`/api/content/staging/images/${encodeURIComponent(staging.pid)}`, body);
      if (!res.ok) {
        $("staging-editor-msg").textContent = `Không gán được. ${await apiMessage(res)}`;
        if (res.status === 409) loadStaging();
        return;
      }
      setStagingView(await res.json());
      resetStagingCandidate();
      // The preview on screen no longer matches the set.
      clearStagingPreview();
      $("staging-editor-msg").textContent = versionId ? "Đã gán ảnh vào bộ mới; live chưa đổi." : "Đã bỏ ảnh đã gán.";
    } catch (err) {
      $("staging-editor-msg").textContent = `Không gửi được: ${err}`;
    }
  }

  $("staging-rights").addEventListener("change", updateStagingButtons);
  $("staging-assign-btn").addEventListener("click", () => {
    if (staging.vid && $("staging-rights").checked) assignStaged(staging.vid);
  });
  $("staging-unassign-btn").addEventListener("click", () => assignStaged(null));
  $("staging-close-btn").addEventListener("click", () => {
    staging.pid = null;
    resetStagingCandidate();
    renderStaging();
  });

  $("staging-preview-btn").addEventListener("click", async () => {
    if (!staging.view) return;
    $("staging-msg").textContent = "Đang dựng bản xem trước bộ mới…";
    try {
      const res = await fetch(`/api/scene/preview.png?target=staging&t=${Date.now()}`);
      if (!res.ok) {
        $("staging-msg").textContent = `Không xem trước được: ${await apiMessage(res)}`;
        return;
      }
      clearStagingPreview();
      staging.previewUrl = URL.createObjectURL(await res.blob());
      $("staging-preview").src = staging.previewUrl;
      $("staging-preview").hidden = false;
      $("staging-preview-empty").hidden = true;
      refreshStagingLive();
      $("staging-msg").textContent = "Xem trước xong; live chưa đổi.";
    } catch (err) {
      $("staging-msg").textContent = `Không gửi được: ${err}`;
    }
  });

  async function applyStaging(confirmMissing) {
    const view = staging.view;
    const res = await stagingPost("/api/content/staging/apply", { staged_id: view.staged_id, confirm_missing: confirmMissing });
    const body = await res.json();
    if (res.status === 409 && body.error === "missing_images" && !confirmMissing) {
      // FR-015: ask again, naming the products that would go live without a picture.
      const names = (body.details || []).map((p) => `• ${p.name}`).join("\n");
      const ok = window.confirm(`Còn món chưa có ảnh:\n${names}\nCác món này chỉ hiện thẻ tên/giá. Vẫn áp dụng bộ mới?`);
      if (!ok) {
        $("staging-msg").textContent = "Chưa áp dụng; live giữ bộ cũ.";
        return;
      }
      return applyStaging(true);
    }
    if (!res.ok) {
      $("staging-msg").textContent = `Không áp dụng được, live giữ bộ cũ. ${body.message || res.status}`;
      if (body.error === "staging_changed") loadStaging();
      return;
    }
    renderCatalog(body);
    setStagingView(null);
    loadImages();
    refreshLiveStill();
    const took = body.to_frame_ms != null ? ` sau ${Math.round(body.to_frame_ms)} ms` : "";
    const lacking = body.missing_images ? `, ${body.missing_images} món chưa có ảnh` : "";
    $("staging-file-msg").textContent = `Đã áp dụng bộ mới (phiên bản ${body.version}${lacking}); lên live${took}.`;
  }

  $("staging-apply-btn").addEventListener("click", async () => {
    if (!staging.view) return;
    const btn = $("staging-apply-btn");
    btn.disabled = true;
    $("staging-msg").textContent = "Đang áp dụng…";
    try {
      await applyStaging(false);
    } catch (err) {
      $("staging-msg").textContent = `Không gửi được: ${err}`;
    } finally {
      btn.disabled = false;
    }
  });

  $("staging-cancel-btn").addEventListener("click", async () => {
    if (!staging.view) return;
    if (!window.confirm("Hủy bộ chuẩn bị? Live không đổi; ảnh đã tải vẫn được giữ để dùng lại sau.")) return;
    try {
      const res = await fetch("/api/content/staging", { method: "DELETE" });
      if (!res.ok && res.status !== 404) {
        $("staging-msg").textContent = `Không hủy được: ${await apiMessage(res)}`;
        return;
      }
      setStagingView(null);
      $("staging-file-msg").textContent = "Đã hủy bộ chuẩn bị; ảnh đã tải vẫn còn.";
    } catch (err) {
      $("staging-msg").textContent = `Không gửi được: ${err}`;
    }
  });

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

  // ---------- 012 US4: "AI vừa nói" (FR-020, FR-021) ----------

  let spoken = []; // newest first, like `spoken` in `/api/state`
  let spokenShowState = null;

  function addSpoken(msg) {
    // Every scripted sentence is its own utterance: a repeat of an id is the same line, keep one row.
    if (spoken.some((s) => s.utterance_id === msg.utterance_id)) return;
    const p = msg.product_id ? catalogProducts.get(msg.product_id) : null;
    spoken.unshift({
      ts: msg.ts,
      utterance_id: msg.utterance_id,
      segment_id: msg.segment_id,
      text: msg.text,
      product_id: msg.product_id || null,
      // Looked up now, as the server does: a later file must not rename what was already said.
      product_name: p ? p.name : null,
      topic: msg.topic || null,
    });
    if (spoken.length > SPOKEN_MAX) spoken.length = SPOKEN_MAX;
    renderSpoken();
  }

  function renderSpoken() {
    $("spoken-count").textContent = String(spoken.length);
    const body = $("spoken-list");
    if (spoken.length === 0) {
      const tr = document.createElement("tr");
      tr.className = "empty";
      const td = document.createElement("td");
      td.colSpan = 4;
      td.textContent = "Chưa có câu nào.";
      tr.append(td);
      body.replaceChildren(tr);
      return;
    }
    body.replaceChildren(
      ...spoken.map((s) => {
        const tr = document.createElement("tr");
        const when = document.createElement("td");
        when.textContent = clock(s.ts);
        const what = document.createElement("td");
        if (s.product_id) {
          what.append(detailLink(s.product_name || s.product_id, s.product_id, "live"));
        } else {
          what.textContent = "Cả show";
        }
        const topic = document.createElement("td");
        topic.textContent = s.topic ? TOPIC_LABELS[s.topic] || s.topic : "—";
        const text = document.createElement("td");
        text.textContent = s.text;
        tr.append(when, what, topic, text);
        return tr;
      }),
    );
  }

  // ---------- 012 US4: "Nội dung sản phẩm" (FR-022, FR-023) ----------

  function detailLink(label, pid, source) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "link-btn";
    btn.textContent = label;
    btn.title = "Xem nội dung món này trong file";
    btn.addEventListener("click", () => openDetail(pid, source));
    return btn;
  }

  function money(amount) {
    return `${Number(amount).toLocaleString("vi-VN")}đ`;
  }

  function detailRows(pairs) {
    const dl = document.createElement("dl");
    for (const [key, value] of pairs) {
      const dt = document.createElement("dt");
      dt.textContent = key;
      const dd = document.createElement("dd");
      dd.textContent = value;
      dl.append(dt, dd);
    }
    return dl;
  }

  function detailList(items) {
    const ul = document.createElement("ul");
    ul.append(
      ...items.map((text) => {
        const li = document.createElement("li");
        li.textContent = text;
        return li;
      }),
    );
    return ul;
  }

  function detailSection(title, content) {
    const h = document.createElement("h3");
    h.textContent = title;
    return [h, content];
  }

  function renderDetail(d) {
    $("detail-name").textContent = d.name;
    const badge = $("detail-source");
    const staged = d.source === "staging";
    badge.className = staged ? "badge staging" : "badge ok";
    badge.textContent = staged ? "bộ chuẩn bị, chưa lên live" : "đang live";
    const parts = [
      detailRows([
        ["Mã món", d.id],
        ["Loại", d.is_primary ? "Sản phẩm chính" : "Sản phẩm phụ"],
        ["Giá", d.price !== null && d.price !== undefined ? money(d.price) : "theo phân loại"],
        ["Mô tả", d.description || "—"],
        ["Giới thiệu", d.intro || "—"],
      ]),
    ];
    if (d.variants.length) {
      parts.push(...detailSection("Phân loại", detailRows(d.variants.map((v) => [v.name, money(v.price)]))));
    }
    if (d.specs.length) parts.push(...detailSection("Thông số", detailRows(d.specs)));
    if (d.faq.length) parts.push(...detailSection("Câu hỏi thường gặp", detailRows(d.faq)));
    if (d.promotions.length) parts.push(...detailSection("Khuyến mãi", detailList(d.promotions)));
    if (d.forbidden_claims.length) {
      parts.push(...detailSection("Không được nói (câu nào có sẽ bị chặn)", detailList(d.forbidden_claims)));
    }
    $("detail-body").replaceChildren(...parts);
  }

  async function openDetail(pid, source) {
    const panel = $("product-detail");
    const url =
      source === "staging"
        ? `/api/content/staging/products/${encodeURIComponent(pid)}`
        : `/api/content/products/${encodeURIComponent(pid)}`;
    panel.hidden = false;
    $("detail-name").textContent = pid;
    $("detail-source").textContent = "";
    $("detail-body").textContent = "Đang tải…";
    panel.scrollIntoView({ block: "nearest" });
    try {
      const res = await fetch(url);
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        // A sentence about a product the newer file dropped: say so instead of an empty panel.
        const why =
          body.error === "unknown_product"
            ? "Món này không còn trong file đang dùng."
            : body.error === "no_staging"
              ? "Không còn bộ chuẩn bị nào (đã hủy hoặc đã áp dụng)."
              : `Lỗi: ${body.message || res.status}`;
        $("detail-body").textContent = why;
        return;
      }
      renderDetail(body);
    } catch (err) {
      $("detail-body").textContent = "Không tải được nội dung món, thử lại sau.";
    }
  }

  $("detail-close").addEventListener("click", () => {
    $("product-detail").hidden = true;
  });
  $("image-detail-btn").addEventListener("click", () => {
    if (pick.pid) openDetail(pick.pid, "live");
  });
  $("staging-detail-btn").addEventListener("click", () => {
    if (staging.pid) openDetail(staging.pid, "staging");
  });

  function renderCatalog(catalog) {
    if (!catalog) return;
    catalogProducts = new Map((catalog.products || []).map((p) => [p.id, p]));
    $("catalog-meta").textContent = `Phiên bản ${catalog.version}`;
    $("catalog-products").replaceChildren(
      ...(catalog.products || []).map((p) => {
        const li = document.createElement("li");
        li.append(detailLink(p.is_primary ? `${p.name} (sản phẩm chính)` : p.name, p.id, "live"));
        return li;
      }),
    );
  }

  function showContentIssues(issues, listId = "content-issues") {
    const list = $(listId);
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
      // 012 US4: the server's list is the whole truth on (re)connect.
      spoken = (msg.spoken || []).slice(0, SPOKEN_MAX);
      spokenShowState = msg.show ? msg.show.state : null;
      renderSpoken();
      llmChain = msg.llm_chain || null;
      // 012 US2: a reopened page picks up the staged set the server still holds.
      const stagedId = msg.staging ? msg.staging.staged_id : null;
      if (stagedId !== (staging.view ? staging.view.staged_id : null)) loadStaging();
      renderLlmChain();
    },
    llm_chain(msg) {
      llmChain = { entries: msg.entries, last_entry: msg.last_entry, using_backup: msg.using_backup };
      renderLlmChain();
    },
    show_state(msg) {
      // A new show starts its own list, as SpokenLog does; resuming a paused show keeps it.
      if (msg.state === "running" && [null, "idle", "ended"].includes(spokenShowState)) {
        spoken = [];
        renderSpoken();
      }
      spokenShowState = msg.state;
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
      // 012: the image list follows the new catalog; a running preview of the old one is cancelled there.
      loadImages();
      // The staged set compares against the live catalog (`live_changed`).
      if (staging.view) loadStaging();
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
        addSpoken(msg);
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
      else if (msg.kind === "image_changed") return onImageChanged(msg);
      else if (msg.kind === "staging") return onStagingEvent(msg);
      else if (msg.kind === "rendered") {
        if (pick.pid && !pick.previewOf) refreshLiveStill();
        if (staging.view) refreshStagingLive();
        return loadScene();
      }
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
      loadImages();
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
