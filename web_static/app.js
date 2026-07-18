/* ==========================================================================
   NurClipper Frontend v2.0
   Features: SPA Navigation, SSE Logs, Scheduler, Inline Edit, Toast System
   ========================================================================== */

document.addEventListener("DOMContentLoaded", () => {

    // ==========================================
    // STATE
    // ==========================================
    let videos = [];
    let moments = [];
    let schedules = [];
    let selectedVideoId = null;
    let config = {};
    let logFilter = "all";
    let logSSE = null;

    // Track status analisa sebelumnya untuk deteksi perubahan
    const prevAnalisisStatus = {};  // { videoId: "processing" | "success" | ... }

    // State progress bar aktif
    let activeProgress = {};  // { type: 'download'|'potong', pct, label }

    // ==========================================
    // DOM REFS
    // ==========================================
    const sidebar          = document.getElementById("sidebar");
    const btnSidebarToggle = document.getElementById("btnSidebarToggle");
    const logPanel         = document.getElementById("logPanel");
    const logBody          = document.getElementById("logBody");
    const btnToggleLog     = document.getElementById("btnToggleLog");
    const logToggleIcon    = document.getElementById("logToggleIcon");
    const btnClearLog      = document.getElementById("btnClearLog");
    const autoScroll       = document.getElementById("autoScroll");
    const toastContainer   = document.getElementById("toastContainer");
    const confirmDialog    = document.getElementById("confirmDialog");
    const confirmTitle     = document.getElementById("confirmTitle");
    const confirmMessage   = document.getElementById("confirmMessage");
    const confirmOk        = document.getElementById("confirmOk");
    const confirmCancel    = document.getElementById("confirmCancel");

    // ==========================================
    // TOAST SYSTEM
    // ==========================================
    function toast(type, title, msg = "", duration = 3500) {
        const icons = { success: "fa-circle-check", error: "fa-circle-exclamation",
                        info: "fa-circle-info", warning: "fa-triangle-exclamation" };
        const el = document.createElement("div");
        el.className = `toast ${type}`;
        el.innerHTML = `
            <i class="fa-solid ${icons[type] || icons.info} toast-icon"></i>
            <div class="toast-body">
                <div class="toast-title">${title}</div>
                ${msg ? `<div class="toast-msg">${msg}</div>` : ""}
            </div>`;
        toastContainer.appendChild(el);
        setTimeout(() => {
            el.classList.add("removing");
            setTimeout(() => el.remove(), 300);
        }, duration);
    }

    // ==========================================
    // PROGRESS BAR SYSTEM
    // ==========================================
    function showProgress(type, pct, label, sublabel = "") {
        let el = document.getElementById(`progressBar_${type}`);
        if (!el) {
            el = document.createElement("div");
            el.id = `progressBar_${type}`;
            el.className = "progress-bar-wrap";
            // Sisipkan di atas pipeline stepper jika detail terbuka
            const pipelineSection = document.querySelector(".pipeline-section");
            if (pipelineSection) {
                pipelineSection.insertAdjacentElement("afterend", el);
            }
        }
        const color = type === "download" ? "var(--info)" : "var(--accent)";
        const icon  = type === "download" ? "fa-download" : "fa-scissors";
        el.innerHTML = `
            <div class="pb-header">
                <span class="pb-label">
                    <i class="fa-solid ${icon}"></i> ${label}
                </span>
                <span class="pb-pct">${parseFloat(pct).toFixed(1)}%</span>
            </div>
            <div class="pb-track">
                <div class="pb-fill" style="width:${pct}%; background:${color};"></div>
            </div>
            ${sublabel ? `<div class="pb-sub">${sublabel}</div>` : ""}
        `;
        el.classList.remove("hidden");
    }

    function hideProgress(type) {
        const el = document.getElementById(`progressBar_${type}`);
        if (el) {
            // Tunjukkan 100% sebentar lalu hilang
            el.querySelector(".pb-fill").style.width = "100%";
            el.querySelector(".pb-pct").textContent = "100%";
            setTimeout(() => el.remove(), 1200);
        }
    }

    // ==========================================
    // CONFIRM DIALOG
    // ==========================================
    function confirm(title, message) {
        return new Promise(resolve => {
            confirmTitle.textContent = title;
            confirmMessage.textContent = message;
            confirmDialog.classList.remove("hidden");
            const ok = () => { cleanup(); resolve(true); };
            const cancel = () => { cleanup(); resolve(false); };
            const cleanup = () => {
                confirmDialog.classList.add("hidden");
                confirmOk.removeEventListener("click", ok);
                confirmCancel.removeEventListener("click", cancel);
            };
            confirmOk.addEventListener("click", ok);
            confirmCancel.addEventListener("click", cancel);
        });
    }

    // ==========================================
    // LOG CONSOLE
    // ==========================================
    function appendLog(text, type = null) {
        const line = document.createElement("div");
        line.className = "log-line";

        // Auto-detect type
        let detectedType = type;
        if (!detectedType) {
            if (/❌|error|gagal|failed/i.test(text)) detectedType = "error";
            else if (/🎉|sukses|berhasil|success/i.test(text)) detectedType = "success";
            else if (/⚡|memulai|running|processing/i.test(text)) detectedType = "warn";
            else if (/⚙️|sistem|info|queue/i.test(text)) detectedType = "info";
            else detectedType = "default";
        }

        line.dataset.type = detectedType;
        line.classList.add(`log-${detectedType}`);

        const ts = new Date().toLocaleTimeString("id-ID", { hour12: false });
        line.innerHTML = `<span class="log-ts">[${ts}]</span>${text}`;

        // Apply filter
        if (logFilter !== "all" && detectedType !== logFilter) {
            line.classList.add("hidden");
        }

        logBody.appendChild(line);
        if (autoScroll.checked) logBody.scrollTop = logBody.scrollHeight;
    }

    function setupSSE() {
        if (logSSE) logSSE.close();
        logSSE = new EventSource("/api/logs/stream");
        logSSE.onmessage = (e) => {
            if (e.data === "ping") return;
            try {
                const d = JSON.parse(e.data);

                // ── Parse PROGRESS_DOWNLOAD ──────────────────────────────
                // Format: PROGRESS_DOWNLOAD|pct|speed|eta|total
                if (d.text.startsWith("PROGRESS_DOWNLOAD|")) {
                    const parts = d.text.split("|");
                    const pct   = parseFloat(parts[1]) || 0;
                    const speed = parts[2] || "—";
                    const eta   = parts[3] || "—";
                    const total = parts[4] || "—";
                    if (pct >= 100) {
                        hideProgress("download");
                    } else {
                        showProgress(
                            "download",
                            pct,
                            "Mengunduh Video Master",
                            `${speed}/s &nbsp;·&nbsp; ETA: ${eta} &nbsp;·&nbsp; Ukuran: ${total}`
                        );
                    }
                    return; // Jangan tampilkan di log console
                }

                // ── Parse PROGRESS_POTONG ────────────────────────────────
                // Format: PROGRESS_POTONG|urutan|total|pct|moment_id|judul
                if (d.text.startsWith("PROGRESS_POTONG|")) {
                    const parts   = d.text.split("|");
                    const urutan  = parseInt(parts[1]) || 1;
                    const total   = parseInt(parts[2]) || 1;
                    const pct     = parseFloat(parts[3]) || 0;
                    const judul   = parts[5] || `Momen ${urutan}`;
                    if (pct >= 100) {
                        if (urutan >= total) {
                            hideProgress("potong");
                        } else {
                            showProgress("potong", 0,
                                `Memotong Momen ${urutan + 1}/${total}`,
                                "Memulai..."
                            );
                        }
                    } else {
                        showProgress(
                            "potong",
                            pct,
                            `Memotong Momen ${urutan}/${total}`,
                            judul
                        );
                    }
                    return; // Jangan tampilkan di log console
                }

                // ── Log biasa ────────────────────────────────────────────
                appendLog(d.text);

                // Auto-refresh UI saat ada perubahan status (berhasil/gagal)
                if (d.video_id && d.video_id === selectedVideoId) {
                    if (/TAHAP ANALISA.*exit code: 0|Data analisis.*berhasil disimpan/i.test(d.text)) {
                        setTimeout(() => fetchMoments(selectedVideoId), 800);
                    }
                    if (/exit code: [1-9]|❌|Gagal|gagal|ERROR|error|failed/i.test(d.text)) {
                        setTimeout(() => fetchVideos(false), 500);
                    }
                    if (/🏁|SUKSES|sukses|selesai dengan sukses/i.test(d.text)) {
                        setTimeout(() => fetchVideos(false), 500);
                    }
                }
            } catch {}
        };
        logSSE.onerror = () => {
            logSSE.close();
            setTimeout(() => setupSSE(), 3000);
        };
    }

    btnClearLog.addEventListener("click", () => {
        logBody.innerHTML = '<div class="log-line log-info">[Sistem] Log dibersihkan.</div>';
    });

    btnToggleLog.addEventListener("click", () => {
        if (logPanel.classList.contains("expanded")) {
            logPanel.classList.remove("expanded");
            logToggleIcon.className = "fa-solid fa-chevron-up";
        } else if (logPanel.classList.contains("collapsed")) {
            logPanel.classList.remove("collapsed");
            logToggleIcon.className = "fa-solid fa-chevron-up";
        } else {
            logPanel.classList.add("expanded");
            logToggleIcon.className = "fa-solid fa-chevron-down";
        }
    });

    document.querySelectorAll(".lf-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".lf-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            logFilter = btn.dataset.filter;
            document.querySelectorAll(".log-line").forEach(line => {
                if (logFilter === "all" || line.dataset.type === logFilter) {
                    line.classList.remove("hidden");
                } else {
                    line.classList.add("hidden");
                }
            });
        });
    });

    // ==========================================
    // SIDEBAR & NAVIGATION
    // ==========================================
    btnSidebarToggle.addEventListener("click", () => {
        sidebar.classList.toggle("collapsed");
        const isCollapsed = sidebar.classList.contains("collapsed");
        logPanel.style.left = isCollapsed ? "60px" : "var(--sidebar-w)";
    });

    const pageTitles = {
        dashboard: { icon: "fa-gauge-high", label: "Dashboard" },
        queue:     { icon: "fa-list-check",  label: "Antrean Video" },
        schedule:  { icon: "fa-calendar-days", label: "Jadwal Upload" },
        settings:  { icon: "fa-sliders",     label: "Pengaturan" }
    };

    function navigateTo(page) {
        document.querySelectorAll(".nav-item").forEach(n => {
            n.classList.toggle("active", n.dataset.page === page);
        });
        document.querySelectorAll(".page").forEach(p => {
            p.classList.toggle("active", p.id === `page-${page}`);
            p.classList.toggle("hidden", p.id !== `page-${page}`);
        });
        const pt = pageTitles[page];
        document.getElementById("pageTitle").innerHTML =
            `<i class="fa-solid ${pt.icon}"></i><span>${pt.label}</span>`;

        if (page === "schedule") { fetchSchedules(); populateScheduleVideoSelect(); }
        if (page === "settings") fetchConfig();
        if (page === "queue")    { fetchVideos(); }
    }

    document.querySelectorAll(".nav-item").forEach(item => {
        item.addEventListener("click", (e) => {
            e.preventDefault();
            navigateTo(item.dataset.page);
        });
    });


    // ==========================================
    // STATS & VIDEO LIST
    // ==========================================
    async function fetchVideos(showSync = false) {
        const syncEl = document.getElementById("syncIndicator");
        if (showSync && syncEl) syncEl.classList.remove("hidden");
        try {
            const res = await fetch("/api/videos");
            if (!res.ok) throw new Error();
            videos = await res.json();
            updateStats();
            renderVideoList();
            renderVideoListFull();
            document.getElementById("navBadgeQueue").textContent = videos.length;
            if (selectedVideoId) {
                const v = videos.find(v => v.id === selectedVideoId);
                if (v) {
                    updatePipelineUI(v);

                    // Auto-refresh momen jika status analisa baru saja berubah jadi 'success'
                    const prev = prevAnalisisStatus[selectedVideoId];
                    const curr = v.status_analisis;
                    if (prev === "processing" && curr === "success") {
                        toast("success", "Analisa selesai!", "Memuat daftar momen...");
                        fetchMoments(selectedVideoId);
                    }
                    prevAnalisisStatus[selectedVideoId] = curr;
                }
            }
        } catch (e) {
            console.error("fetchVideos error", e);
            toast("error", "Gagal memuat data video");
        } finally {
            if (showSync && syncEl) syncEl.classList.add("hidden");
        }
    }

    function updateStats() {
        let processing = 0, completed = 0, failed = 0;
        videos.forEach(v => {
            const stages = [v.status_analisis, v.status_download, v.status_potong, v.status_upload, v.status_facebook];
            if (stages.includes("processing")) processing++;
            if (v.status_upload === "success") completed++;
            if (stages.includes("failed")) failed++;
        });
        document.getElementById("statTotal").textContent = videos.length;
        document.getElementById("statProcessing").textContent = processing;
        document.getElementById("statCompleted").textContent = completed;
        document.getElementById("statFailed").textContent = failed;
    }

    function extractYtId(url) {
        const m = url.match(/(?:v=|youtu\.be\/|\/shorts\/)([a-zA-Z0-9_-]{11})/);
        return m ? m[1] : url.split("/").pop().split("?")[0];
    }

    function buildVideoRowHTML(v) {
        const ytId = extractYtId(v.url);
        const thumb = `https://img.youtube.com/vi/${ytId}/hqdefault.jpg`;
        const isActive = selectedVideoId === v.id ? "active" : "";
        const title = escAttr(v.judul_video || v.url);
        const channel = escHtml(v.channel_video || "—");
        const displayTitle = escHtml(v.judul_video || v.url);
        return `
        <div class="video-row ${isActive}" data-id="${v.id}">
            <img class="vr-thumb" src="${thumb}" alt="" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2280%22 height=%2246%22><rect fill=%22%23222%22 width=%2280%22 height=%2246%22/></svg>'">
            <div class="vr-info">
                <div class="vr-channel">${channel}</div>
                <div class="vr-title" title="${title}">${displayTitle}</div>
                <div class="vr-stages">
                    <span class="sbadge ${v.status_analisis}">🔍 ${v.status_analisis}</span>
                    <span class="sbadge ${v.status_download}">📥 ${v.status_download}</span>
                    <span class="sbadge ${v.status_potong}">✂️ ${v.status_potong}</span>
                    <span class="sbadge ${v.status_upload}">📤 ${v.status_upload}</span>
                    <span class="sbadge ${v.status_facebook}">📘 ${v.status_facebook}</span>
                </div>
            </div>
            <button class="vr-del" data-id="${v.id}" title="Hapus"><i class="fa-solid fa-trash-can"></i></button>
        </div>`;
    }

    function bindVideoRowEvents(container) {
        container.querySelectorAll(".video-row").forEach(row => {
            row.addEventListener("click", (e) => {
                if (e.target.closest(".vr-del")) return;
                selectVideo(parseInt(row.dataset.id));
                navigateTo("dashboard");
            });
        });
        container.querySelectorAll(".vr-del").forEach(btn => {
            btn.addEventListener("click", (e) => {
                e.stopPropagation();
                deleteVideo(parseInt(btn.dataset.id));
            });
        });
    }

    function renderVideoList() {
        const list = document.getElementById("videoList");
        const empty = document.getElementById("emptyQueue");
        const search = document.getElementById("searchQueue")?.value.toLowerCase() || "";
        const filtered = videos.filter(v =>
            (v.judul_video || v.url).toLowerCase().includes(search) ||
            (v.channel_video || "").toLowerCase().includes(search)
        );
        if (filtered.length === 0) {
            list.innerHTML = "";
            empty.classList.remove("hidden");
        } else {
            empty.classList.add("hidden");
            list.innerHTML = filtered.map(buildVideoRowHTML).join("");
            bindVideoRowEvents(list);
        }
    }

    function renderVideoListFull() {
        const list = document.getElementById("videoListFull");
        if (!list) return;
        const search = document.getElementById("searchQueueFull")?.value.toLowerCase() || "";
        const filtered = videos.filter(v =>
            (v.judul_video || v.url).toLowerCase().includes(search) ||
            (v.channel_video || "").toLowerCase().includes(search)
        );
        if (filtered.length === 0) {
            list.innerHTML = `<div class="empty-state"><i class="fa-solid fa-film"></i><p>Tidak ada video</p></div>`;
        } else {
            list.innerHTML = filtered.map(buildVideoRowHTML).join("");
            bindVideoRowEvents(list);
        }
    }

    document.getElementById("searchQueue")?.addEventListener("input", renderVideoList);
    document.getElementById("searchQueueFull")?.addEventListener("input", renderVideoListFull);

    // ==========================================
    // ADD VIDEO
    // ==========================================
    document.getElementById("addVideoForm").addEventListener("submit", async (e) => {
        e.preventDefault();
        const raw = document.getElementById("ytUrls").value.trim();
        if (!raw) return;
        const urls = raw.split(/\r?\n/).map(u => u.trim()).filter(Boolean);
        let ok = 0;
        for (const url of urls) {
            try {
                const res = await fetch("/api/videos", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ url })
                });
                if (res.ok) { ok++; }
                else {
                    const err = await res.json();
                    toast("warning", "Gagal menambahkan", err.detail || url);
                }
            } catch { toast("error", "Koneksi gagal", url); }
        }
        if (ok > 0) {
            toast("success", `${ok} link ditambahkan`, "Berhasil masuk ke antrean");
            document.getElementById("ytUrls").value = "";
            fetchVideos(true);
        }
    });

    // ==========================================
    // DELETE VIDEO
    // ==========================================
    async function deleteVideo(vidId) {
        const v = videos.find(v => v.id === vidId);
        if (!v) return;
        const ok = await confirm("Hapus Video?",
            `"${v.judul_video || v.url}" beserta semua momen dan klip terkait akan dihapus permanen.`);
        if (!ok) return;
        try {
            const res = await fetch(`/api/videos/${vidId}`, { method: "DELETE" });
            if (!res.ok) throw new Error();
            toast("success", "Video dihapus");
            if (selectedVideoId === vidId) { selectedVideoId = null; hideDetail(); }
            fetchVideos(true);
        } catch { toast("error", "Gagal menghapus video"); }
    }

    // ==========================================
    // CLEANUP
    // ==========================================
    async function doCleanup() {
        const ok = await confirm("Bersihkan Semua Sesi?",
            "Ini akan menghapus SEMUA data database, video podcast, dan klip. Tindakan tidak dapat dibatalkan.");
        if (!ok) return;
        // Feedback langsung biar user tau proses berjalan
        toast("info", "Membersihkan sesi...", "Mohon tunggu");
        try {
            const res = await fetch("/api/cleanup", { method: "POST" });
            if (!res.ok) throw new Error(await res.text());
            // Kosongkan state lokal langsung tanpa nunggu fetch ulang
            videos = [];
            moments = [];
            selectedVideoId = null;
            hideDetail();
            updateStats();
            renderVideoList();
            renderVideoListFull();
            if (document.getElementById("momentsList")) {
                document.getElementById("momentsList").innerHTML = '<div class="empty-state"><i class="fa-solid fa-wand-magic-sparkles"></i><p>Belum ada momen</p></div>';
            }
            toast("success", "Sesi dibersihkan", "Semua data berhasil dihapus");
            // Refresh dari server sebagai backup
            fetchVideos(true);
        } catch (e) {
            toast("error", "Gagal membersihkan sesi", String(e));
        }
    }

    document.getElementById("btnCleanup").addEventListener("click", doCleanup);
    document.getElementById("btnCleanupSettings")?.addEventListener("click", doCleanup);


    // ==========================================
    // DETAIL PANEL
    // ==========================================
    function selectVideo(vidId) {
        selectedVideoId = vidId;
        document.querySelectorAll(".video-row").forEach(r => {
            r.classList.toggle("active", parseInt(r.dataset.id) === vidId);
        });
        const v = videos.find(v => v.id === vidId);
        if (!v) return;

        // Catat status analisa saat ini sebagai baseline untuk deteksi perubahan
        prevAnalisisStatus[vidId] = v.status_analisis;

        const ytId = extractYtId(v.url);
        document.getElementById("detailThumb").src = `https://img.youtube.com/vi/${ytId}/hqdefault.jpg`;
        document.getElementById("detailLink").href = v.url;
        document.getElementById("detailTitle").textContent = v.judul_video || v.url;
        document.getElementById("detailChannel").textContent = v.channel_video || "Unknown Channel";

        updatePipelineUI(v);
        closePreview();
        fetchMoments(vidId);

        document.getElementById("detailEmpty").classList.add("hidden");
        document.getElementById("detailContent").classList.remove("hidden");
    }

    function hideDetail() {
        document.getElementById("detailEmpty").classList.remove("hidden");
        document.getElementById("detailContent").classList.add("hidden");
    }

    function updatePipelineUI(v) {
        const stages = ["analisa", "download", "potong", "upload", "facebook"];
        const statusMap = {
            analisa:  v.status_analisis,
            download: v.status_download,
            potong:   v.status_potong,
            upload:   v.status_upload,
            facebook: v.status_facebook
        };

        const anyProcessing = Object.values(statusMap).includes("processing");

        stages.forEach((s, i) => {
            const stepEl = document.getElementById(`ps${s.charAt(0).toUpperCase() + s.slice(1)}`);
            const btnEl  = document.getElementById(`btn${s.charAt(0).toUpperCase() + s.slice(1)}`);
            const dbadge = document.getElementById(`dbadge${s.charAt(0).toUpperCase() + s.slice(1)}`);
            const status = statusMap[s];

            if (stepEl) {
                stepEl.className = `ps-step ${status || "pending"}`;
                if (status === "processing") {
                    stepEl.querySelector(".ps-icon").innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
                } else {
                    const icons = { analisa: "fa-magnifying-glass", download: "fa-download",
                                    potong: "fa-scissors", upload: "fa-cloud-arrow-up", facebook: "fa-facebook" };
                    const brands = { facebook: "fa-brands" };
                    const prefix = brands[s] ? `${brands[s]} ` : "fa-solid ";
                    stepEl.querySelector(".ps-icon").innerHTML = `<i class="${prefix}${icons[s]}"></i>`;
                }
            }

            if (btnEl) btnEl.disabled = (status === "processing");

            if (dbadge) {
                dbadge.className = `dbadge ${status || "pending"}`;
                const labels = { analisa: "🔍 Analisa", download: "📥 Download",
                                 potong: "✂️ Potong", upload: "📤 Upload", facebook: "📘 Facebook" };
                dbadge.textContent = `${labels[s]}: ${status || "pending"}`;
            }

            if (i < stages.length - 1) {
                const line = document.getElementById(`psLine${i + 1}`);
                if (line) {
                    line.className = "ps-line";
                    if (status === "success") line.classList.add("done");
                    else if (status === "processing") line.classList.add("active");
                }
            }
        });

        document.getElementById("btnRunAll").disabled = anyProcessing;
    }

    // ==========================================
    // PIPELINE TRIGGERS
    // ==========================================
    async function triggerStage(vidId, stage) {
        try {
            const res = await fetch(`/api/process/${vidId}/${stage}`, { method: "POST" });
            if (!res.ok) throw new Error();
            toast("info", `Tahap '${stage}' dimulai`, "Masuk ke antrean latar belakang");
            fetchVideos(false);
        } catch { toast("error", "Gagal memicu pipeline"); }
    }

    function handlePipelineClick(stage) {
        if (!selectedVideoId) {
            toast("warning", "Pilih video dulu", "Klik baris video dari antrean");
            return;
        }
        triggerStage(selectedVideoId, stage);
    }

    document.getElementById("btnRunAll").addEventListener("click", () => {
        handlePipelineClick("all");
    });

    document.getElementById("btnAnalisa").addEventListener("click", () => {
        handlePipelineClick("analisa");
    });

    document.getElementById("btnDownload").addEventListener("click", () => {
        handlePipelineClick("download");
    });

    document.getElementById("btnPotong").addEventListener("click", async () => {
        if (!selectedVideoId) {
            toast("warning", "Pilih video dulu", "Klik baris video dari antrean");
            return;
        }

        let targetMoments = moments;
        if (targetMoments.length === 0) {
            try {
                const res = await fetch(`/api/moments/${selectedVideoId}`);
                if (res.ok) targetMoments = await res.json();
            } catch {}
        }

        const sel = targetMoments.filter(m => m.is_selected === 1);
        if (sel.length === 0) {
            toast("warning", "Pilih minimal 1 momen", "Centang momen yang ingin dipotong");
            return;
        }
        triggerStage(selectedVideoId, "potong");
    });

    document.getElementById("btnUpload").addEventListener("click", () => {
        handlePipelineClick("upload");
    });

    document.getElementById("btnFacebook").addEventListener("click", () => {
        handlePipelineClick("facebook");
    });

    document.getElementById("btnResetStatus").addEventListener("click", async () => {
        if (!selectedVideoId) return;
        const ok = await confirm("Reset Status Video?",
            "Semua status tahap akan di-reset ke 'pending' agar tombol bisa digunakan kembali.");
        if (!ok) return;
        try {
            const res = await fetch(`/api/reset/${selectedVideoId}`, { method: "POST" });
            if (!res.ok) throw new Error();
            toast("success", "Status di-reset", "Semua tahap kembali ke 'pending'");
            fetchVideos(false);
        } catch { toast("error", "Gagal mereset status"); }
    });

    // ==========================================
    // VIDEO PREVIEW
    // ==========================================
    function playPreview(videoId, momentId, title) {
        const src = `/clips/${videoId}_${momentId}.mp4`;
        document.getElementById("videoSrc").src = src;
        document.getElementById("previewCaption").textContent = title;
        const player = document.getElementById("previewPlayer");
        player.classList.remove("hidden");
        const videoEl = document.getElementById("videoEl");
        videoEl.load();
        videoEl.play().catch(() => {});
        player.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    function closePreview() {
        const videoEl = document.getElementById("videoEl");
        videoEl.pause();
        document.getElementById("videoSrc").src = "";
        document.getElementById("previewPlayer").classList.add("hidden");
    }

    document.getElementById("btnClosePreview").addEventListener("click", closePreview);

    // ==========================================
    // MOMENTS
    // ==========================================
    async function fetchMoments(vidId) {
        const list = document.getElementById("momentsList");
        list.innerHTML = `<div class="empty-state"><i class="fa-solid fa-spinner fa-spin"></i><p>Memuat momen...</p></div>`;
        try {
            const res = await fetch(`/api/moments/${vidId}`);
            if (!res.ok) throw new Error();
            moments = await res.json();
            document.getElementById("momentsCount").textContent = `${moments.length} momen`;
            renderMoments();
        } catch {
            list.innerHTML = `<div class="empty-state"><i class="fa-solid fa-triangle-exclamation"></i><p>Gagal memuat momen</p></div>`;
        }
    }

    function renderMoments(filter = "") {
        const list = document.getElementById("momentsList");
        const selectAll = document.getElementById("selectAll");

        const filtered = filter
            ? moments.filter(m => m.judul_menarik.toLowerCase().includes(filter) ||
                                  m.deskripsi_pendek?.toLowerCase().includes(filter))
            : moments;

        if (filtered.length === 0) {
            list.innerHTML = `<div class="empty-state">
                <i class="fa-solid fa-wand-magic-sparkles"></i>
                <p>Belum ada momen</p>
                <span>Jalankan Analisa Gemini terlebih dahulu</span>
            </div>`;
            if (selectAll) selectAll.disabled = true;
            return;
        }

        if (selectAll) {
            selectAll.disabled = false;
            selectAll.checked = filtered.every(m => m.is_selected === 1);
        }

        list.innerHTML = filtered.map(m => {
            const unsel = m.is_selected === 0 ? "unselected" : "";
            let statusHtml = `<span class="mi-status">⏳ Antrean</span>`;
            if (m.is_uploaded === 1) statusHtml = `<span class="mi-status uploaded"><i class="fa-solid fa-circle-check"></i> Sudah Diupload</span>`;
            else if (m.has_clip)     statusHtml = `<span class="mi-status clipped"><i class="fa-solid fa-scissors"></i> Sudah Dipotong</span>`;
            const fbBadge = m.is_uploaded_fb === 1 ? `<span class="mi-status uploaded"><i class="fa-brands fa-facebook"></i> FB Uploaded</span>` : "";

            const previewBtn = m.has_clip
                ? `<button class="btn btn-xs btn-accent btn-play" data-id="${m.id}" data-title="${escHtml(m.judul_menarik)}">
                       <i class="fa-solid fa-circle-play"></i> Putar
                   </button>`
                : `<span style="font-size:10.5px;color:var(--text-3)"><i class="fa-solid fa-ban"></i> Belum dipotong</span>`;

            return `
            <div class="moment-item ${unsel}" data-mid="${m.id}">
                <div class="mi-header">
                    <label class="chk-label" style="flex:1;min-width:0">
                        <input type="checkbox" class="chk-moment" data-id="${m.id}" ${m.is_selected ? "checked" : ""}>
                        <span class="chk-box"></span>
                        <input type="text" class="mi-title inline-edit" data-field="judul_menarik" data-id="${m.id}"
                               value="${escHtml(m.judul_menarik)}" placeholder="Judul momen">
                    </label>
                    <input type="text" class="mi-time inline-edit" data-field="waktu_start" data-id="${m.id}"
                           value="${m.waktu_start}" placeholder="00:00:00" title="Waktu mulai (hh:mm:ss)">
                </div>
                <input type="text" class="mi-desc inline-edit" data-field="deskripsi_pendek" data-id="${m.id}"
                       value="${escHtml(m.deskripsi_pendek || "")}" placeholder="Deskripsi singkat...">
                <input type="text" class="mi-tags inline-edit" data-field="hashtag_terbaik" data-id="${m.id}"
                       value="${escHtml(m.hashtag_terbaik || "")}" placeholder="#hashtag #viral">
                <div class="mi-footer">
                    ${statusHtml}
                    ${fbBadge}
                    ${previewBtn}
                </div>
            </div>`;
        }).join("");

        // Bind events
        list.querySelectorAll(".chk-moment").forEach(chk => {
            chk.addEventListener("change", () => {
                const mid = parseInt(chk.dataset.id);
                const val = chk.checked ? 1 : 0;
                chk.closest(".moment-item").classList.toggle("unselected", !chk.checked);
                saveMoment(mid, "is_selected", val);
            });
        });

        list.querySelectorAll(".inline-edit").forEach(inp => {
            inp.addEventListener("focusout", () => {
                saveMoment(parseInt(inp.dataset.id), inp.dataset.field, inp.value.trim());
            });
        });

        list.querySelectorAll(".btn-play").forEach(btn => {
            btn.addEventListener("click", () => {
                playPreview(selectedVideoId, parseInt(btn.dataset.id), btn.dataset.title);
            });
        });
    }

    function escHtml(str) {
        return (str || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
    }

    function escAttr(str) {
        return (str || "").replace(/&/g,"&amp;").replace(/"/g,"&quot;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    }

    async function saveMoment(momentId, field, value) {
        const m = moments.find(m => m.id === momentId);
        if (!m) return;
        m[field] = value;
        try {
            await fetch(`/api/moments/${momentId}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    waktu_start: m.waktu_start,
                    judul_menarik: m.judul_menarik,
                    hashtag_terbaik: m.hashtag_terbaik,
                    deskripsi_pendek: m.deskripsi_pendek,
                    is_selected: parseInt(m.is_selected)
                })
            });
        } catch { toast("error", "Gagal menyimpan perubahan momen"); }
    }

    document.getElementById("selectAll").addEventListener("change", (e) => {
        const val = e.target.checked ? 1 : 0;
        document.querySelectorAll(".chk-moment").forEach(chk => {
            chk.checked = e.target.checked;
            chk.closest(".moment-item").classList.toggle("unselected", !e.target.checked);
        });
        moments.reduce((promise, m) => {
            m.is_selected = val;
            return promise.then(() => new Promise(r => setTimeout(r, 50))).then(() => saveMoment(m.id, "is_selected", val));
        }, Promise.resolve());
    });

    document.getElementById("searchMoment").addEventListener("input", (e) => {
        renderMoments(e.target.value.toLowerCase());
    });


    // ==========================================
    // SCHEDULE PAGE
    // ==========================================
    async function fetchSchedules() {
        try {
            const res = await fetch("/api/schedules");
            if (!res.ok) throw new Error();
            schedules = await res.json();
            renderSchedules();
            document.getElementById("navBadgeSchedule").textContent =
                schedules.filter(s => s.status === "pending").length;
            document.getElementById("statScheduled").textContent =
                schedules.filter(s => s.status === "pending").length;
        } catch { console.error("fetchSchedules error"); toast("error", "Gagal memuat jadwal"); }
    }

    function renderSchedules() {
        const list = document.getElementById("scheduleList");
        if (!list) return;
        if (schedules.length === 0) {
            list.innerHTML = `<div class="empty-state">
                <i class="fa-solid fa-calendar-xmark"></i>
                <p>Belum ada jadwal</p>
                <span>Buat jadwal baru di form sebelah kiri</span>
            </div>`;
            return;
        }

        const stageLabels = { all: "⚡ All-in-One", analisa: "🔍 Analisa",
                              download: "📥 Download", potong: "✂️ Potong", upload: "📤 Upload" };
        const repeatLabels = { once: "Sekali", daily: "Harian", weekly: "Mingguan" };

        list.innerHTML = schedules.map(s => `
        <div class="schedule-item">
            <div class="sched-icon"><i class="fa-solid fa-calendar-days"></i></div>
            <div class="sched-info">
                <div class="sched-title">${s.judul_video || `Video ID ${s.video_id}`}</div>
                <div class="sched-meta">
                    <span><i class="fa-solid fa-bolt"></i> ${stageLabels[s.stage] || s.stage}</span>
                    <span><i class="fa-solid fa-clock"></i> ${s.scheduled_at}</span>
                    <span><i class="fa-solid fa-repeat"></i> ${repeatLabels[s.repeat] || s.repeat}</span>
                </div>
            </div>
            <span class="sched-badge ${s.status}">${s.status === "done" ? "Selesai" : "Menunggu"}</span>
            <button class="sched-del" data-id="${s.id}" title="Hapus Jadwal">
                <i class="fa-solid fa-trash-can"></i>
            </button>
        </div>`).join("");

        list.querySelectorAll(".sched-del").forEach(btn => {
            btn.addEventListener("click", async () => {
                const ok = await confirm("Hapus Jadwal?", "Jadwal ini akan dihapus permanen.");
                if (!ok) return;
                try {
                    await fetch(`/api/schedules/${btn.dataset.id}`, { method: "DELETE" });
                    toast("success", "Jadwal dihapus");
                    fetchSchedules();
                } catch { toast("error", "Gagal menghapus jadwal"); }
            });
        });
    }

    function populateScheduleVideoSelect() {
        const sel = document.getElementById("schedVideoId");
        if (!sel) return;
        sel.innerHTML = `<option value="">— Pilih video dari database —</option>` +
            videos.map(v => `<option value="${v.id}">${v.judul_video || v.url}</option>`).join("");
    }

    document.getElementById("scheduleForm")?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const videoId = parseInt(document.getElementById("schedVideoId").value);
        const stage   = document.getElementById("schedStage").value;
        const dtVal   = document.getElementById("schedDateTime").value;
        const repeat  = document.getElementById("schedRepeat").value;

        if (!videoId || !dtVal) { toast("warning", "Lengkapi semua field"); return; }

        // Convert datetime-local to "YYYY-MM-DD HH:MM"
        const scheduled_at = dtVal.replace("T", " ").slice(0, 16);

        try {
            const res = await fetch("/api/schedules", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ video_id: videoId, stage, scheduled_at, repeat })
            });
            if (!res.ok) throw new Error();
            toast("success", "Jadwal disimpan", `${stage} pada ${scheduled_at}`);
            e.target.reset();
            fetchSchedules();
        } catch { toast("error", "Gagal menyimpan jadwal"); }
    });

    document.getElementById("btnRefreshSchedules")?.addEventListener("click", fetchSchedules);

    // ==========================================
    // SETTINGS PAGE
    // ==========================================
    async function fetchConfig() {
        try {
            const res = await fetch("/api/config");
            if (!res.ok) throw new Error();
            config = await res.json();

            // Update YouTube auth status everywhere
            const connected = config.has_youtube_auth;
            const authBtn = document.getElementById("btnYoutubeAuth");
            const authText = document.getElementById("youtubeAuthText");
            const authDot = document.getElementById("authDot");

            if (connected) {
                authBtn.classList.add("connected");
                authText.textContent = "YouTube Terhubung";
                authDot.classList.add("connected");
            } else {
                authBtn.classList.remove("connected");
                authText.textContent = "Hubungkan YouTube";
                authDot.classList.remove("connected");
            }

            // Settings form
            const gk = document.getElementById("geminiKey");
            if (gk) gk.value = config.gemini_key || "";
            const ec = document.getElementById("enableCaption");
            if (ec) ec.checked = config.enable_caption;
            const wm = document.getElementById("whisperModel");
            if (wm) wm.value = config.whisper_model || "base";
            const fn = document.getElementById("fontName");
            if (fn) fn.value = config.font_name || "Cooper Black";
            const fs = document.getElementById("fontSize");
            if (fs) fs.value = config.font_size || "6";

            const fpid = document.getElementById("fbPageId");
            if (fpid) fpid.value = config.fb_page_id || "";
            const fpt = document.getElementById("fbPageToken");
            if (fpt) fpt.value = config.fb_page_token || "";
            const fpv = document.getElementById("fbPrivacy");
            if (fpv) fpv.value = config.fb_privacy || "PUBLIC";

            // OAuth indicator in settings
            const oauthInd = document.getElementById("oauthIndicator");
            const oauthText = document.getElementById("oauthStatusText");
            if (oauthInd && oauthText) {
                oauthInd.querySelector(".dot").className = `dot ${connected ? "dot-green" : "dot-red"}`;
                oauthText.textContent = connected ? "Terhubung ke YouTube" : "Belum terhubung";
            }
        } catch { console.error("fetchConfig error"); toast("error", "Gagal memuat pengaturan"); }
    }

    document.getElementById("settingsForm")?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const key = document.getElementById("geminiKey").value.trim();
        if (!key) { toast("warning", "API Key tidak boleh kosong"); return; }
        try {
            const res = await fetch("/api/config", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    gemini_key: key,
                    enable_caption: document.getElementById("enableCaption").checked,
                    font_name: document.getElementById("fontName").value.trim() || "Cooper Black",
                    font_size: document.getElementById("fontSize").value.trim() || "6",
                    whisper_model: document.getElementById("whisperModel").value,
                    fb_page_id: document.getElementById("fbPageId").value.trim(),
                    fb_page_token: document.getElementById("fbPageToken").value.trim(),
                    fb_privacy: document.getElementById("fbPrivacy").value
                })
            });
            if (!res.ok) throw new Error();
            toast("success", "Pengaturan disimpan");
            fetchConfig();
        } catch { toast("error", "Gagal menyimpan pengaturan"); }
    });

    document.getElementById("toggleKey")?.addEventListener("click", () => {
        const inp = document.getElementById("geminiKey");
        const icon = document.querySelector("#toggleKey i");
        if (inp.type === "password") {
            inp.type = "text";
            icon.className = "fa-solid fa-eye-slash";
        } else {
            inp.type = "password";
            icon.className = "fa-solid fa-eye";
        }
    });

    document.getElementById("toggleFbToken")?.addEventListener("click", () => {
        const inp = document.getElementById("fbPageToken");
        const icon = document.querySelector("#toggleFbToken i");
        if (inp.type === "password") {
            inp.type = "text";
            icon.className = "fa-solid fa-eye-slash";
        } else {
            inp.type = "password";
            icon.className = "fa-solid fa-eye";
        }
    });

    async function triggerYoutubeAuth() {
        toast("info", "Membuka login Google...", "Periksa jendela browser baru di server");
        try {
            const res = await fetch("/api/youtube-auth", { method: "POST" });
            if (!res.ok) throw new Error();
            const d = await res.json();
            toast("info", "Login dipicu", d.message);
            setTimeout(fetchConfig, 6000);
        } catch { toast("error", "Gagal memicu autentikasi YouTube"); }
    }

    document.getElementById("btnYoutubeAuth").addEventListener("click", triggerYoutubeAuth);
    document.getElementById("btnYoutubeAuthSettings")?.addEventListener("click", triggerYoutubeAuth);

    // ==========================================
    // THEME SWITCHER
    // ==========================================
    // Load tema dari localStorage saat init
    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);

    // Update active state pada theme option buttons
    function updateThemeButtons(theme) {
        document.querySelectorAll('.theme-option').forEach(opt => {
            if (opt.dataset.theme === theme) {
                opt.classList.add('active');
            } else {
                opt.classList.remove('active');
            }
        });
    }

    // Set initial active state
    updateThemeButtons(savedTheme);

    // Event listener untuk theme option buttons
    document.querySelectorAll('.theme-option').forEach(option => {
        option.addEventListener('click', () => {
            const theme = option.dataset.theme;
            document.documentElement.setAttribute('data-theme', theme);
            localStorage.setItem('theme', theme);
            updateThemeButtons(theme);
            toast('success', 'Tema diubah', `Tema ${theme === 'dark' ? 'gelap' : 'terang'} diterapkan`);
        });
    });

    // ==========================================
    // INIT
    // ==========================================
    function init() {
        fetchConfig();
        fetchVideos(true);
        fetchSchedules();
        setupSSE();
    }

    init();
});
