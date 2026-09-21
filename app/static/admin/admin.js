// OpsTranslate Control Center SPA Client

let currentTab = "overview";
let providersCache = [];

document.addEventListener("DOMContentLoaded", () => {
  initApp();
  startClock();
});

function startClock() {
  setInterval(() => {
    const el = document.getElementById("server-clock");
    if (el) {
      const now = new Date();
      el.textContent = now.toTimeString().split(" ")[0];
    }
  }, 1000);
}

async function apiFetch(url, options = {}) {
  options.headers = options.headers || {};
  const token = localStorage.getItem("admin_token");
  if (token) {
    options.headers["Authorization"] = `Bearer ${token}`;
  }
  options.headers["Content-Type"] = options.headers["Content-Type"] || "application/json";

  const res = await fetch(url, options);
  if (res.status === 401) {
    localStorage.removeItem("admin_token");
    showLogin();
    throw new Error("Session expired. Please log in again.");
  }
  return res;
}

async function initApp() {
  try {
    const res = await fetch("/api/admin/me", {
      headers: {
        Authorization: `Bearer ${localStorage.getItem("admin_token") || ""}`
      }
    });
    const data = await res.json();
    if (data.authenticated) {
      showApp(data.mode);
    } else {
      showLogin();
    }
  } catch (err) {
    showLogin();
  }
}

function showLogin() {
  document.getElementById("login-container").style.display = "flex";
  document.getElementById("app-container").style.display = "none";
}

function showApp(mode = "POLLING") {
  document.getElementById("login-container").style.display = "none";
  document.getElementById("app-container").style.display = "flex";
  document.getElementById("header-mode-badge").textContent = mode.toUpperCase();
  switchTab("overview");
}

async function handleLogin(e) {
  e.preventDefault();
  const pwdInput = document.getElementById("admin-password");
  const errEl = document.getElementById("login-error");
  const btn = document.getElementById("login-submit-btn");

  errEl.style.display = "none";
  btn.disabled = true;

  try {
    const res = await fetch("/api/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: pwdInput.value })
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Authentication failed.");
    }
    localStorage.setItem("admin_token", data.token);
    pwdInput.value = "";
    showApp();
    showToast("Authenticated successfully!", "success");
  } catch (err) {
    errEl.textContent = err.message;
    errEl.style.display = "block";
  } finally {
    btn.disabled = false;
  }
}

async function handleLogout() {
  try {
    await apiFetch("/api/admin/logout", { method: "POST" });
  } catch (e) {}
  localStorage.removeItem("admin_token");
  showLogin();
  showToast("Logged out.", "info");
}

function switchTab(tabName) {
  currentTab = tabName;
  document.querySelectorAll(".nav-item").forEach(el => {
    el.classList.toggle("active", el.dataset.tab === tabName);
  });
  document.querySelectorAll(".tab-pane").forEach(el => {
    el.classList.toggle("active", el.id === `tab-${tabName}`);
  });

  refreshCurrentView();
}

function refreshCurrentView() {
  if (currentTab === "overview") loadOverview();
  else if (currentTab === "providers") loadProviders();
  else if (currentTab === "users") loadUsers();
  else if (currentTab === "logs") loadLogs();
}

// ---- Overview -------------------------------------------------------------

async function loadOverview() {
  try {
    const res = await apiFetch("/api/admin/overview");
    const data = await res.json();

    document.getElementById("stat-provider-count").textContent = data.active_provider_count || 0;
    document.getElementById("nav-provider-count").textContent = data.active_provider_count || 0;
    document.getElementById("stat-today-spend").textContent = `$${data.today_spend_usd.toFixed(4)}`;

    const dbEl = document.getElementById("stat-db-status");
    if (!data.database_configured) {
      dbEl.textContent = "Unset";
      dbEl.style.color = "var(--text-muted)";
    } else {
      dbEl.textContent = data.database_online ? "Connected" : "Degraded";
      dbEl.style.color = data.database_online ? "var(--color-success)" : "var(--color-danger)";
    }

    const redisEl = document.getElementById("stat-redis-status");
    if (!data.redis_configured) {
      redisEl.textContent = "Memory";
      redisEl.style.color = "var(--text-muted)";
    } else {
      redisEl.textContent = data.redis_online ? "Online" : "Degraded";
      redisEl.style.color = data.redis_online ? "var(--color-success)" : "var(--color-danger)";
    }

    // Circuit breakers
    const bList = document.getElementById("overview-breakers-list");
    bList.innerHTML = "";
    const states = data.circuit_states || {};
    const names = Object.keys(states);
    if (names.length === 0) {
      bList.innerHTML = "<p class='text-muted'>No providers currently registered.</p>";
    } else {
      names.forEach(name => {
        const state = states[name] || "closed";
        const card = document.createElement("div");
        card.className = "breaker-card";
        card.innerHTML = `
          <span class="breaker-name">${escapeHtml(name)}</span>
          <span class="breaker-state-badge ${state}">
            <span class="status-dot ${state === 'closed' ? 'green' : state === 'open' ? 'red' : 'yellow'}"></span>
            ${state.toUpperCase()}
          </span>
        `;
        bList.appendChild(card);
      });
    }
  } catch (err) {
    showToast(err.message, "error");
  }
}

// ---- Providers ------------------------------------------------------------

async function loadProviders() {
  try {
    const res = await apiFetch("/api/admin/providers");
    const data = await res.json();
    providersCache = data.providers || [];
    renderProvidersTable(providersCache);
    document.getElementById("nav-provider-count").textContent = providersCache.length;
  } catch (err) {
    showToast(err.message, "error");
  }
}

function renderProvidersTable(providers) {
  const tbody = document.getElementById("providers-table-body");
  tbody.innerHTML = "";

  if (providers.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty-state">No providers configured yet.</td></tr>`;
    return;
  }

  providers.forEach(p => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><span class="priority-pill ${p.priority === 1 ? 'rank-1' : ''}">${p.priority}</span></td>
      <td><b>${escapeHtml(p.name)}</b></td>
      <td><span class="code-pill">${escapeHtml(p.model)}</span></td>
      <td style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(p.base_url)}</td>
      <td><span class="code-pill">${escapeHtml(p.api_key_masked || 'None')}</span></td>
      <td>${p.timeout_s}s</td>
      <td>
        <span class="breaker-state-badge ${p.breaker_state || 'closed'}">
          ${(p.breaker_state || 'closed').toUpperCase()}
        </span>
      </td>
      <td>
        <div class="table-actions">
          <button class="btn btn-sm btn-outline" onclick="openEditProviderModal(${p.id})">Edit</button>
          ${p.id ? `<button class="btn btn-sm btn-danger" onclick="deleteProvider(${p.id})">Delete</button>` : ''}
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function openAddProviderModal() {
  document.getElementById("modal-provider-title").textContent = "Add AI Provider";
  document.getElementById("p-id").value = "";
  document.getElementById("p-name").value = "";
  document.getElementById("p-base-url").value = "https://";
  document.getElementById("p-model").value = "gemini-3.1-flash-lite";
  document.getElementById("p-priority").value = "1";
  document.getElementById("p-timeout").value = "15";
  document.getElementById("p-api-key").value = "";
  document.getElementById("p-enabled").checked = true;
  document.getElementById("provider-test-result").style.display = "none";
  document.getElementById("provider-modal").style.display = "flex";
}

function openEditProviderModal(id) {
  const p = providersCache.find(item => item.id === id);
  if (!p) return;

  document.getElementById("modal-provider-title").textContent = `Edit Provider: ${p.name}`;
  document.getElementById("p-id").value = p.id || "";
  document.getElementById("p-name").value = p.name;
  document.getElementById("p-base-url").value = p.base_url;
  document.getElementById("p-model").value = p.model;
  document.getElementById("p-priority").value = p.priority;
  document.getElementById("p-timeout").value = p.timeout_s;
  document.getElementById("p-api-key").value = "";
  document.getElementById("p-enabled").checked = p.enabled;
  document.getElementById("provider-test-result").style.display = "none";
  document.getElementById("provider-modal").style.display = "flex";
}

function closeProviderModal() {
  document.getElementById("provider-modal").style.display = "none";
}

async function testCurrentProviderForm() {
  const baseUrl = document.getElementById("p-base-url").value.trim();
  const apiKey = document.getElementById("p-api-key").value.trim();
  const model = document.getElementById("p-model").value.trim();
  const timeout = parseFloat(document.getElementById("p-timeout").value) || 15;
  const resultBox = document.getElementById("provider-test-result");

  if (!baseUrl || !model) {
    showToast("Please enter Base URL and Model first.", "error");
    return;
  }

  resultBox.className = "test-result-box";
  resultBox.textContent = "Testing connection and latency...";
  resultBox.style.display = "block";

  try {
    const res = await apiFetch("/api/admin/providers/test", {
      method: "POST",
      body: JSON.stringify({
        base_url: baseUrl,
        api_key: apiKey,
        model: model,
        timeout_s: timeout
      })
    });
    const data = await res.json();
    if (data.ok) {
      resultBox.className = "test-result-box success";
      resultBox.textContent = `✓ Success! Status: ${data.status_code}, Latency: ${data.latency_ms}ms. Sample Output: "${data.sample_output}"`;
    } else {
      resultBox.className = "test-result-box error";
      resultBox.textContent = `✗ Failed! Status: ${data.status_code}, Latency: ${data.latency_ms}ms. Error: ${data.error}`;
    }
  } catch (err) {
    resultBox.className = "test-result-box error";
    resultBox.textContent = `✗ Test call failed: ${err.message}`;
  }
}

async function saveProvider(e) {
  e.preventDefault();
  const id = document.getElementById("p-id").value;
  const payload = {
    name: document.getElementById("p-name").value.trim(),
    base_url: document.getElementById("p-base-url").value.trim(),
    model: document.getElementById("p-model").value.trim(),
    priority: parseInt(document.getElementById("p-priority").value) || 1,
    timeout_s: parseFloat(document.getElementById("p-timeout").value) || 15,
    enabled: document.getElementById("p-enabled").checked,
  };
  const key = document.getElementById("p-api-key").value.trim();
  if (key) {
    payload.api_key = key;
  }

  try {
    let res;
    if (id) {
      res = await apiFetch(`/api/admin/providers/${id}`, {
        method: "PUT",
        body: JSON.stringify(payload)
      });
    } else {
      res = await apiFetch("/api/admin/providers", {
        method: "POST",
        body: JSON.stringify(payload)
      });
    }
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to save provider.");

    closeProviderModal();
    showToast("Provider saved and router reloaded!", "success");
    loadProviders();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function deleteProvider(id) {
  if (!confirm("Are you sure you want to delete this provider?")) return;
  try {
    const res = await apiFetch(`/api/admin/providers/${id}`, { method: "DELETE" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to delete.");
    showToast("Provider deleted and router reloaded.", "info");
    loadProviders();
  } catch (err) {
    showToast(err.message, "error");
  }
}

// ---- Staff Users ----------------------------------------------------------

async function loadUsers() {
  try {
    const res = await apiFetch("/api/admin/users");
    const data = await res.json();
    const tbody = document.getElementById("users-table-body");
    tbody.innerHTML = "";

    const users = data.users || [];
    if (users.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="empty-state">No staff users registered.</td></tr>`;
      return;
    }

    users.forEach(u => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><span class="code-pill">${u.user_id}</span></td>
        <td>${escapeHtml(u.display_name || '-')}</td>
        <td><span class="code-pill">${u.role.toUpperCase()}</span></td>
        <td>${u.daily_soft_cap} msgs</td>
        <td>
          <span class="status-dot ${u.active ? 'green' : 'red'}"></span>
          ${u.active ? 'Active' : 'Disabled'}
        </td>
        <td>${u.created_at || 'Seeded'}</td>
        <td>
          <button class="btn btn-sm btn-danger" onclick="deleteUser(${u.user_id})">Delete</button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    showToast(err.message, "error");
  }
}

function openAddUserModal() {
  document.getElementById("u-id").value = "";
  document.getElementById("u-name").value = "";
  document.getElementById("u-role").value = "staff";
  document.getElementById("u-cap").value = "200";
  document.getElementById("u-active").checked = true;
  document.getElementById("user-modal").style.display = "flex";
}

function closeUserModal() {
  document.getElementById("user-modal").style.display = "none";
}

async function saveUser(e) {
  e.preventDefault();
  const payload = {
    user_id: parseInt(document.getElementById("u-id").value),
    display_name: document.getElementById("u-name").value.trim(),
    role: document.getElementById("u-role").value,
    daily_soft_cap: parseInt(document.getElementById("u-cap").value) || 200,
    active: document.getElementById("u-active").checked
  };

  try {
    const res = await apiFetch("/api/admin/users", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to save user.");
    closeUserModal();
    showToast("Staff user saved!", "success");
    loadUsers();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function deleteUser(userId) {
  if (!confirm(`Remove user ${userId} from allowlist?`)) return;
  try {
    const res = await apiFetch(`/api/admin/users/${userId}`, { method: "DELETE" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to delete.");
    showToast("User removed from allowlist.", "info");
    loadUsers();
  } catch (err) {
    showToast(err.message, "error");
  }
}

// ---- Playground -----------------------------------------------------------

function loadSample(type) {
  const input = document.getElementById("play-input-text");
  if (type === 1) {
    input.value = "ဒီ ကစားသမားရဲ့ ID မှားနေတယ်၊ စစ်ပေးပါ";
  } else if (type === 2) {
    input.value = "ဒီ Customer က ပုံမှန်ကစားနေကျ fan တစ်ယောက်ပါ";
  } else if (type === 3) {
    input.value = "This Customer's registered phone number for withdrawals is about to hit its limit, please put the points back into their User Account.";
  }
}

async function runPlayground() {
  const text = document.getElementById("play-input-text").value.trim();
  const dst = document.getElementById("play-dst-lang").value;
  const btn = document.getElementById("play-run-btn");

  if (!text) {
    showToast("Please enter some text to translate.", "error");
    return;
  }

  btn.disabled = true;
  document.getElementById("play-empty-state").style.display = "none";
  document.getElementById("play-result-details").style.display = "none";

  try {
    const res = await apiFetch("/api/admin/playground", {
      method: "POST",
      body: JSON.stringify({ text, dst: dst || null })
    });
    const data = await res.json();

    if (!data.ok) {
      throw new Error(data.error || "Translation failed.");
    }

    document.getElementById("diag-src").textContent = data.src_lang;
    document.getElementById("diag-dst").textContent = data.dst_lang;
    document.getElementById("diag-provider").textContent = data.provider_used;
    document.getElementById("diag-latency").textContent = `${data.latency_ms} ms`;
    document.getElementById("diag-masked").textContent = data.masked_input;

    const tagsBox = document.getElementById("diag-policy-hits");
    tagsBox.innerHTML = "";
    if (data.policy_hits && data.policy_hits.length > 0) {
      data.policy_hits.forEach(h => {
        const span = document.createElement("span");
        span.className = "tag-hit";
        span.textContent = h;
        tagsBox.appendChild(span);
      });
    } else {
      tagsBox.innerHTML = "<span class='text-muted' style='font-size:0.8rem;'>No restricted gaming terms detected</span>";
    }

    document.getElementById("diag-final").textContent = data.final_output;
    document.getElementById("play-result-details").style.display = "block";
  } catch (err) {
    showToast(err.message, "error");
    document.getElementById("play-empty-state").style.display = "block";
  } finally {
    btn.disabled = false;
  }
}

// ---- Logs -----------------------------------------------------------------

async function loadLogs() {
  try {
    const res = await apiFetch("/api/admin/logs?limit=50");
    const data = await res.json();
    const tbody = document.getElementById("logs-table-body");
    tbody.innerHTML = "";

    const logs = data.logs || [];
    if (logs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="empty-state">No metadata logs available yet.</td></tr>`;
      return;
    }

    logs.forEach(l => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${l.created_at}</td>
        <td><span class="code-pill">${l.user_id}</span></td>
        <td>${l.char_len}</td>
        <td><b>${escapeHtml(l.provider)}</b></td>
        <td>${l.latency_ms} ms</td>
        <td><span class="status-dot green"></span> ${l.status}</td>
        <td><span class="code-pill">${escapeHtml(JSON.stringify(l.policy_hits || []))}</span></td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    showToast(err.message, "error");
  }
}

// ---- Utility Helpers ------------------------------------------------------

function showToast(msg, type = "info") {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${type === 'success' ? '✓' : type === 'error' ? '✗' : 'ℹ'}</span> <span>${escapeHtml(msg)}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(30px)";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
