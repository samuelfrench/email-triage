"use strict";

const state = {
    senders: [],
    filteredSenders: [],
    activeSender: null,
    messages: [],
    selected: new Set(),
    lastRunId: null,
};

const $ = (id) => document.getElementById(id);

async function api(path, opts = {}) {
    const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
    const res = await fetch(path, { ...opts, headers });
    if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new Error(`${res.status} ${res.statusText}: ${text}`);
    }
    return res.json();
}

function toast(message, kind = "info") {
    const el = $("toast");
    el.textContent = message;
    el.className = `toast ${kind}`;
    el.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => { el.hidden = true; }, 4000);
}

function fmtDate(iso) {
    if (!iso) return "";
    try {
        const d = new Date(iso);
        if (isNaN(d.getTime())) return iso.slice(0, 16);
        return d.toLocaleString();
    } catch { return iso; }
}

async function loadSenders() {
    try {
        const data = await api("/api/senders");
        state.senders = data.senders || [];
        $("totals").textContent = `${data.total_unread.toLocaleString()} unread • ${data.total_senders} senders`;
        $("generated-at").textContent = data.generated_at ? `cache ${fmtDate(data.generated_at)}` : "no cache";
        applyFilter();
    } catch (e) {
        toast(`Failed to load senders: ${e.message}`, "error");
    }
}

function applyFilter() {
    const q = ($("filter").value || "").toLowerCase().trim();
    state.filteredSenders = q
        ? state.senders.filter(s => s.email.includes(q) || (s.display || "").toLowerCase().includes(q))
        : state.senders;
    renderSenders();
}

function renderSenders() {
    const list = $("senders-list");
    list.innerHTML = "";
    for (const s of state.filteredSenders) {
        const li = document.createElement("li");
        li.className = "sender-row" + (s.is_self_sent ? " self-sent" : "") + (state.activeSender === s.email ? " active" : "");
        li.dataset.email = s.email;

        const sample = (s.sample_subjects || []).slice(0, 2).map(t => t.length > 64 ? t.slice(0, 64) + "…" : t).join(" · ");
        li.innerHTML = `
            <div class="rank">#${s.rank}</div>
            <div class="count">${s.count.toLocaleString()}</div>
            <div class="email">
                ${escapeHtml(s.email)}${s.is_self_sent ? '<span class="badge">self-sent</span>' : ""}
                ${sample ? `<small>${escapeHtml(sample)}</small>` : ""}
            </div>
        `;
        li.addEventListener("click", () => selectSender(s));
        list.appendChild(li);
    }
}

function escapeHtml(str) {
    return String(str || "").replace(/[&<>"']/g, ch => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[ch]));
}

async function selectSender(sender) {
    state.activeSender = sender.email;
    state.selected.clear();
    $("messages-empty").hidden = true;
    $("messages-content").hidden = false;
    $("messages-title").textContent = sender.email;
    $("messages-subtitle").innerHTML =
        `${sender.count.toLocaleString()} unread message${sender.count === 1 ? "" : "s"}`
        + (sender.is_self_sent ? ' <span class="badge" style="background:var(--warn-border);color:#1a1207;padding:0 6px;border-radius:3px;font-size:11px;">SELF-SENT — review carefully</span>' : "");
    $("messages-list").innerHTML = '<li class="muted" style="padding:16px">Loading messages…</li>';
    renderSenders();
    updateActionButtons(sender);

    try {
        const data = await api(`/api/sender/${encodeURIComponent(sender.email)}/messages`);
        state.messages = data.messages || [];
        renderMessages();
    } catch (e) {
        $("messages-list").innerHTML = `<li class="muted" style="padding:16px">Failed to load: ${escapeHtml(e.message)}</li>`;
    }
}

function updateActionButtons(sender) {
    const isSelf = sender && sender.is_self_sent;
    const markRead = $("action-mark-read");
    const markReviewed = $("action-mark-reviewed");
    const applyLow = $("action-apply-low");
    if (isSelf) {
        markRead.disabled = true;
        markRead.title = "Disabled for self-sent — use Mark Reviewed instead";
        applyLow.disabled = true;
        applyLow.title = "Disabled for self-sent — use Mark Reviewed instead";
    } else {
        markRead.disabled = false;
        markRead.title = "Remove the UNREAD label";
        applyLow.disabled = false;
        applyLow.title = "Apply LowPriority label without marking as read";
    }
    markReviewed.title = "Apply Triaged-Reviewed label and mark as read";
}

function renderMessages() {
    const list = $("messages-list");
    list.innerHTML = "";
    for (const m of state.messages) {
        const li = document.createElement("li");
        li.className = "message-row";
        li.dataset.messageId = m.message_id;
        li.innerHTML = `
            <input type="checkbox" data-id="${m.message_id}">
            <div>
                <div class="subject">${escapeHtml(m.subject || "(no subject)")}</div>
                <div class="snippet">${escapeHtml((m.snippet || "").slice(0, 200))}</div>
                <div class="meta-row">
                    ${escapeHtml(m.received_at || "")}
                    ${(m.label_ids || []).filter(l => !["INBOX","UNREAD","CATEGORY_PERSONAL"].includes(l))
                        .map(l => `<span class="label-pill">${escapeHtml(l)}</span>`).join("")}
                </div>
            </div>
        `;
        li.querySelector("input").addEventListener("change", (e) => {
            if (e.target.checked) state.selected.add(m.message_id);
            else state.selected.delete(m.message_id);
            updateSelectAllCheckbox();
        });
        list.appendChild(li);
    }
    $("select-all").checked = false;
}

function updateSelectAllCheckbox() {
    const total = state.messages.length;
    const sel = state.selected.size;
    $("select-all").checked = total > 0 && sel === total;
    $("select-all").indeterminate = sel > 0 && sel < total;
}

function showProgress(jobId, total) {
    let bar = document.getElementById("progress-bar");
    if (!bar) {
        bar = document.createElement("div");
        bar.id = "progress-bar";
        bar.className = "progress-bar";
        bar.innerHTML = `
            <div class="progress-meta">
                <span class="progress-label"></span>
                <span class="progress-count"></span>
            </div>
            <div class="progress-track"><div class="progress-fill"></div></div>
            <div class="progress-current muted"></div>
        `;
        document.querySelector(".pane-header .actions").after(bar);
    }
    bar.dataset.jobId = jobId;
    bar.dataset.total = total;
    bar.querySelector(".progress-fill").style.width = "0%";
    bar.querySelector(".progress-count").textContent = `0 / ${total}`;
    bar.hidden = false;
    return bar;
}

function updateProgress(bar, status) {
    const total = status.total || 0;
    const done = status.done || 0;
    const succ = status.succeeded || 0;
    const errs = (status.errors || []).length;
    const pct = total ? (done / total) * 100 : 0;
    bar.querySelector(".progress-fill").style.width = `${pct}%`;
    bar.querySelector(".progress-label").textContent =
        status.running
            ? `Working: ${status.action.replace(/_/g, " ")}…`
            : `Done • ${succ} ok${errs ? `, ${errs} errors` : ""}`;
    bar.querySelector(".progress-count").textContent =
        `${done.toLocaleString()} / ${total.toLocaleString()}`;
    bar.querySelector(".progress-current").textContent =
        status.running && status.current_message_id ? `current: ${status.current_message_id}` : "";
}

function hideProgress(bar) {
    if (bar) {
        bar.hidden = true;
    }
}

async function pollJob(jobId, bar, total) {
    while (true) {
        try {
            const status = await api(`/api/jobs/${jobId}`);
            updateProgress(bar, status);
            if (!status.running) return status;
        } catch (e) {
            updateProgress(bar, { total, done: total, succeeded: 0, errors: [{error: e.message}], running: false, action: "error" });
            throw e;
        }
        await new Promise(r => setTimeout(r, 600));
    }
}

async function bulkAction(endpoint, label = null) {
    if (!state.activeSender) return;
    if (state.selected.size === 0) {
        toast("Select at least one message first.", "error");
        return;
    }
    const ids = [...state.selected];
    const confirmMsg = `${ids.length} message${ids.length === 1 ? "" : "s"} from ${state.activeSender}. Continue?`;
    if (!confirm(confirmMsg)) return;

    const buttons = document.querySelectorAll("#messages-pane button");
    buttons.forEach(b => b.disabled = true);

    let bar = null;
    try {
        const body = { message_ids: ids, sender_email: state.activeSender };
        if (label) body.label_name = label;
        const res = await api(endpoint, { method: "POST", body: JSON.stringify(body) });
        state.lastRunId = res.run_id;

        bar = showProgress(res.job_id, res.total);
        const final = await pollJob(res.job_id, bar, res.total);

        // Visually mark processed rows for those that succeeded
        const errored = new Set((final.errors || []).map(e => e.message_id));
        for (const id of ids) {
            if (errored.has(id)) continue;
            const row = document.querySelector(`.message-row[data-message-id="${id}"]`);
            if (row) row.classList.add("processed");
            const cb = row?.querySelector('input[type="checkbox"]');
            if (cb) cb.checked = false;
        }
        state.selected.clear();
        updateSelectAllCheckbox();

        const errs = (final.errors || []).length;
        toast(
            `${final.succeeded} done${errs ? ` (${errs} errors)` : ""} • run ${final.run_id}`,
            errs ? "error" : "success"
        );
        await loadSenders();
        // Hide progress bar after a brief pause so user can see final state
        setTimeout(() => hideProgress(bar), 2500);
    } catch (e) {
        toast(`Failed: ${e.message}`, "error");
        if (bar) setTimeout(() => hideProgress(bar), 4000);
    } finally {
        buttons.forEach(b => b.disabled = false);
        const sender = state.senders.find(s => s.email === state.activeSender);
        if (sender) updateActionButtons(sender);
    }
}

async function refreshInbox() {
    if (!confirm("Re-fetch the entire unread inbox from Gmail? Takes a few minutes.")) return;
    $("refresh-overlay").hidden = false;
    try {
        await api("/api/refresh", { method: "POST" });
    } catch (e) {
        $("refresh-overlay").hidden = true;
        toast(`Refresh failed: ${e.message}`, "error");
        return;
    }

    const poll = async () => {
        try {
            const status = await api("/api/refresh/status");
            $("refresh-progress").textContent = (status.fetched || 0).toLocaleString();
            if (status.running) {
                setTimeout(poll, 1500);
            } else {
                $("refresh-overlay").hidden = true;
                if (status.error) {
                    toast(`Refresh failed: ${status.error}`, "error");
                } else {
                    toast("Inbox refreshed.", "success");
                    await loadSenders();
                }
            }
        } catch (e) {
            $("refresh-overlay").hidden = true;
            toast(`Status poll failed: ${e.message}`, "error");
        }
    };
    setTimeout(poll, 1000);
}

document.addEventListener("DOMContentLoaded", () => {
    $("filter").addEventListener("input", applyFilter);
    $("refresh-btn").addEventListener("click", refreshInbox);

    $("select-all").addEventListener("change", (e) => {
        if (e.target.checked) {
            state.messages.forEach(m => state.selected.add(m.message_id));
        } else {
            state.selected.clear();
        }
        document.querySelectorAll('#messages-list input[type="checkbox"]').forEach(cb => {
            cb.checked = e.target.checked;
        });
    });

    $("action-mark-read").addEventListener("click", () => bulkAction("/api/actions/mark-read"));
    $("action-mark-reviewed").addEventListener("click", () => bulkAction("/api/actions/mark-reviewed"));
    $("action-apply-low").addEventListener("click", () => bulkAction("/api/actions/apply-label", "LowPriority"));

    loadSenders();
});
