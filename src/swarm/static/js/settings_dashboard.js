// Settings dashboard page logic (loaded via {% static %} from settings_dashboard.html).
// Server data arrives via Django json_script island #swarm-settings-data (not inline JS).
// Dynamic handlers use data-* + autoescape (not onclick JS strings): HTML entity
// decoding would otherwise reintroduce quotes into the handler source.
const settingsData = JSON.parse(document.getElementById("swarm-settings-data").textContent);

function toggleGroup(groupId) {
  const content = document.getElementById(`content-${groupId}`);
  const header = document.getElementById(`header-${groupId}`)
    || document.querySelector(`#group-${groupId} .group-header`);
  if (!content || !header) return;

  const expanded = content.classList.toggle('expanded');
  header.classList.toggle('expanded', expanded);
  header.setAttribute('aria-expanded', expanded ? 'true' : 'false');
}

function viewObject(groupId, settingName) {
  const setting = settingsData[groupId].settings[settingName];
  const modal = new bootstrap.Modal(document.getElementById('objectModal'));
  
  document.getElementById('objectContent').textContent = JSON.stringify(setting.value, null, 2);
  document.querySelector('#objectModal .modal-title').textContent = `${settingName} Configuration`;
  
  // Apply syntax highlighting if available
  if (window.Prism) {
    Prism.highlightElement(document.querySelector('#objectContent code'));
  }
  
  modal.show();
}

function copyObjectContent() {
  const content = document.getElementById('objectContent').textContent;
  navigator.clipboard.writeText(content);
  showToast('Object content copied to clipboard', 'success');
}

function copyEnvVar(envVar) {
  navigator.clipboard.writeText(envVar);
  showToast(`Environment variable "${envVar}" copied to clipboard`, 'success');
}

function exportSettings() {
  const data = {
    timestamp: new Date().toISOString(),
    settings: settingsData
  };
  
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `operating-swarm-settings-${new Date().toISOString().split('T')[0]}.json`;
  a.click();
  URL.revokeObjectURL(url);
  
  showToast('Settings exported successfully', 'success');
}

function refreshSettings() {
  window.location.reload();
}

function setAlertMessage(container, message, kind) {
  container.replaceChildren();
  const alert = document.createElement('div');
  alert.className = `alert alert-${kind}`;
  alert.textContent = message;
  container.appendChild(alert);
}

async function viewEnvironment() {
  const modal = new bootstrap.Modal(document.getElementById('envModal'));
  const content = document.getElementById('envContent');

  content.replaceChildren();
  const loading = document.createElement('div');
  loading.className = 'text-center';
  loading.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading environment variables...';
  content.appendChild(loading);
  modal.show();
  
  try {
    const response = await fetch('/settings/environment/');
    const data = await response.json();
    
    if (data.success) {
      content.replaceChildren();
      const summary = document.createElement('div');
      summary.className = 'env-summary';
      summary.textContent = `Found ${data.count} environment variables`;
      content.appendChild(summary);

      const grid = document.createElement('div');
      grid.className = 'env-grid';

      for (const [key, value] of Object.entries(data.environment_variables)) {
        const item = document.createElement('div');
        item.className = 'env-item';

        const keyEl = document.createElement('div');
        keyEl.className = 'env-key';
        keyEl.textContent = key;

        const valueEl = document.createElement('div');
        valueEl.className = 'env-value';
        const code = document.createElement('code');
        code.textContent = value;
        valueEl.appendChild(code);

        const copyBtn = document.createElement('button');
        copyBtn.type = 'button';
        copyBtn.className = 'btn btn-sm btn-outline-secondary';
        copyBtn.setAttribute('aria-label', 'Copy environment variable name');
        copyBtn.dataset.envVar = key;
        copyBtn.innerHTML = '<i class="fas fa-copy" aria-hidden="true"></i>';
        copyBtn.addEventListener('click', () => copyEnvVar(key));

        item.appendChild(keyEl);
        item.appendChild(valueEl);
        item.appendChild(copyBtn);
        grid.appendChild(item);
      }

      content.appendChild(grid);
    } else {
      setAlertMessage(content, `Error: ${data.error}`, 'danger');
    }
  } catch (error) {
    setAlertMessage(content, `Network error: ${error.message}`, 'danger');
  }
}

// Progress fill width comes from operator.css
// `.config-progress-fill[data-pct="N"]` rules (CSP: no element.style).

function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `alert alert-${type} position-fixed os-toast`;
  // textContent keeps the message XSS-safe; announce it for assistive tech.
  const assertive = type === 'danger' || type === 'error' || type === 'warning';
  toast.setAttribute('role', assertive ? 'alert' : 'status');
  toast.setAttribute('aria-live', assertive ? 'assertive' : 'polite');
  toast.setAttribute('aria-atomic', 'true');

  const text = document.createElement('span');
  text.textContent = message;
  toast.appendChild(text);

  const closeBtn = document.createElement('button');
  closeBtn.type = 'button';
  closeBtn.className = 'btn-close';
  closeBtn.setAttribute('aria-label', 'Close');
  closeBtn.addEventListener('click', () => toast.remove());
  toast.appendChild(closeBtn);

  document.body.appendChild(toast);
  
  setTimeout(() => {
    toast.remove();
  }, 5000);
}

function csrfToken() {
  return document.querySelector('#herdr-add-form [name=csrfmiddlewaretoken]')?.value
    || document.querySelector('.chat-retention-card [name=csrfmiddlewaretoken]')?.value
    || document.querySelector('[name=csrfmiddlewaretoken]')?.value
    || '';
}

async function postChatRetention(action, agentId) {
  const body = new URLSearchParams({ action });
  if (agentId) body.set('agent_id', agentId);
  const response = await fetch('/settings/chats/action/', {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'X-CSRFToken': csrfToken(),
    },
    body,
  });
  let data = {};
  try {
    data = await response.json();
  } catch {
    data = {};
  }
  if (!response.ok || !data.success) {
    showToast(data.error || 'Chat retention action failed', 'danger');
    return;
  }
  showToast('Chat files updated', 'success');
  window.location.reload();
}

function chatArchiveAll() {
  if (!window.confirm('Move all active agent chats to trash? You can restore them until you empty trash.')) {
    return;
  }
  postChatRetention('archive_all');
}

function chatEmptyTrash() {
  if (!window.confirm('Permanently delete every file in chat trash? This cannot be undone.')) {
    return;
  }
  postChatRetention('empty_trash');
}

function chatArchiveOne(agentId) {
  if (!agentId) return;
  postChatRetention('archive', agentId);
}

function chatRestoreOne(agentId) {
  if (!agentId) return;
  postChatRetention('restore', agentId);
}

function getCsrfToken() {
  const fromForm = csrfToken();
  if (fromForm) return fromForm;
  try {
    const match = document.cookie
      .split("; ")
      .find((row) => row.startsWith("csrftoken="));
    return match ? decodeURIComponent(match.split("=").slice(1).join("=")) : "";
  } catch {
    return "";
  }
}

function setHerdrRemoteStatus(message, kind) {
  const el = document.getElementById("herdr-remote-status");
  if (!el) return;
  el.textContent = message || "";
  el.className = kind ? `os-meta text-${kind}` : "os-meta";
}

async function refreshHerdrRemoteKind() {
  const status = document.getElementById("herdr-remote-status");
  if (!status) return;
  try {
    const response = await fetch("/v1/remotes/", {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    });
    if (!response.ok) {
      setHerdrRemoteStatus("Could not load remotes list.", "danger");
      return;
    }
    const body = await response.json();
    const rows = Array.isArray(body.data) ? body.data : [];
    const herdr = rows.find((row) => row && row.id === "herdr");
    if (!herdr) {
      setHerdrRemoteStatus(
        "Not configured — add local Herdr or SSH host + user.",
      );
      return;
    }
    const mode = herdr.herdr_mode || herdr.transport || "local";
    const loc =
      mode === "ssh" && herdr.ssh_host
        ? `SSH ${herdr.ssh_user || ""}@${herdr.ssh_host}`
        : herdr.base_url || "local Herdr (no SSH)";
    setHerdrRemoteStatus(
      `Configured kind=herdr · ${loc}. Remote Herdr is SSH-shaped, not HTTP.`,
      "success",
    );
  } catch {
    setHerdrRemoteStatus("Could not load remotes list.", "danger");
  }
}

function syncHerdrRemoteFormMode() {
  const mode = (document.getElementById("herdr-remote-mode")?.value || "local").trim();
  const localWrap = document.getElementById("herdr-remote-base-wrap");
  const sshIds = [
    "herdr-remote-ssh-host-wrap",
    "herdr-remote-ssh-user-wrap",
    "herdr-remote-ssh-ident-wrap",
  ];
  if (localWrap) localWrap.hidden = mode === "ssh";
  for (const id of sshIds) {
    const el = document.getElementById(id);
    if (el) el.hidden = mode !== "ssh";
  }
}

async function addHerdrRemoteKind() {
  const mode = (document.getElementById("herdr-remote-mode")?.value || "local").trim();
  const baseInput = document.getElementById("herdr-remote-base");
  const hostInput = document.getElementById("herdr-remote-ssh-host");
  const userInput = document.getElementById("herdr-remote-ssh-user");
  const identInput = document.getElementById("herdr-remote-ssh-ident");
  const base = (baseInput?.value || "").trim();
  const sshHost = (hostInput?.value || "").trim();
  const sshUser = (userInput?.value || "").trim();
  const sshIdentityEnv = (identInput?.value || "").trim();
  const payload = { herdr_mode: mode };
  if (mode === "local") {
    if (base) payload.base_url = base;
  } else {
    if (!sshHost || !sshUser) {
      setHerdrRemoteStatus("SSH host and user are required for remote Herdr.", "danger");
      return;
    }
    payload.ssh_host = sshHost;
    payload.ssh_user = sshUser;
    payload.ssh_agent = true;
    if (sshIdentityEnv) payload.ssh_identity_env = sshIdentityEnv;
  }
  const headers = {
    Accept: "application/json",
    "Content-Type": "application/json",
  };
  const csrf = getCsrfToken();
  if (csrf) headers["X-CSRFToken"] = csrf;
  const response = await fetch("/v1/remotes/herdr/", {
    method: "PATCH",
    headers,
    credentials: "same-origin",
    body: JSON.stringify(payload),
  });
  let body = {};
  try {
    body = await response.json();
  } catch {
    body = {};
  }
  if (!response.ok) {
    setHerdrRemoteStatus(body.error || `Add failed (${response.status}).`, "danger");
    return;
  }
  if (baseInput) baseInput.value = "";
  if (hostInput) hostInput.value = "";
  if (userInput) userInput.value = "";
  const loc =
    body.herdr_mode === "ssh" && body.ssh_host
      ? `SSH ${body.ssh_user || ""}@${body.ssh_host}`
      : body.base_url || base || "local Herdr (no SSH)";
  setHerdrRemoteStatus(
    `Added kind=herdr · ${loc}. Remote Herdr is SSH-shaped, not HTTP.`,
    "success",
  );
}

function setHerdrStatus(message, kind) {
  const el = document.getElementById("herdr-agent-status");
  if (!el) return;
  el.textContent = message || "";
  el.className = kind ? `os-meta mb-2 text-${kind}` : "os-meta mb-2";
}

function renderHerdrRows(agents) {
  const tbody = document.getElementById("herdr-agent-rows");
  if (!tbody) return;
  tbody.replaceChildren();
  if (!agents.length) {
    const tr = document.createElement("tr");
    tr.className = "herdr-empty-row";
    const td = document.createElement("td");
    td.colSpan = 3;
    td.textContent = "No Herdr agents yet. Add one to target localhost or a remote host.";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }
  for (const agent of agents) {
    const tr = document.createElement("tr");
    const nameTd = document.createElement("td");
    nameTd.textContent = agent.name || "";
    const remoteTd = document.createElement("td");
    remoteTd.textContent = agent.remote ? agent.remote : "localhost";
    const actionTd = document.createElement("td");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-sm btn-outline-danger";
    btn.dataset.action = "remove-herdr-agent";
    btn.dataset.herdrId = String(agent.id);
    btn.dataset.herdrName = agent.name || "";
    btn.textContent = "Remove";
    actionTd.appendChild(btn);
    tr.appendChild(nameTd);
    tr.appendChild(remoteTd);
    tr.appendChild(actionTd);
    tbody.appendChild(tr);
  }
}

async function refreshHerdrAgents() {
  const response = await fetch("/v1/herdr-agents/", {
    headers: { Accept: "application/json" },
    credentials: "same-origin",
  });
  if (!response.ok) {
    throw new Error(`List failed (${response.status})`);
  }
  const body = await response.json();
  renderHerdrRows(Array.isArray(body.data) ? body.data : []);
}

async function addHerdrMember(name, remote) {
  const headers = {
    Accept: "application/json",
    "Content-Type": "application/json",
  };
  const csrf = getCsrfToken();
  if (csrf) headers["X-CSRFToken"] = csrf;
  const response = await fetch("/v1/herdr-agents/", {
    method: "POST",
    headers,
    credentials: "same-origin",
    body: JSON.stringify({ name, remote: remote || "" }),
  });
  return response;
}

async function discoverHerdrAgents() {
  setHerdrStatus("Discovering live Herdr members…");
  const remote = (document.getElementById("herdr-remote")?.value || "").trim();
  const qs = remote ? `?remote=${encodeURIComponent(remote)}` : "";
  const response = await fetch(`/v1/herdr-agents/discover/${qs}`, {
    headers: { Accept: "application/json" },
    credentials: "same-origin",
  });
  const wrap = document.getElementById("herdr-discover-wrap");
  const list = document.getElementById("herdr-discover-list");
  if (!wrap || !list) return;
  if (!response.ok) {
    setHerdrStatus(`Discover failed (${response.status}).`, "danger");
    return;
  }
  const body = await response.json();
  const items = Array.isArray(body.data) ? body.data : [];
  list.replaceChildren();
  wrap.hidden = false;
  if (!items.length) {
    const empty = document.createElement("li");
    empty.textContent = body.herdr_available === false
      ? "herdr CLI not available here (cloud CI mocks it). On .30, live list comes from localhost sockets."
      : "No live Herdr agents or workspaces.";
    list.appendChild(empty);
    setHerdrStatus(empty.textContent);
    return;
  }
  for (const item of items) {
    const li = document.createElement("li");
    li.className = "d-flex align-items-center gap-2 mb-1";
    const label = document.createElement("span");
    const remoteLabel = item.remote ? item.remote : "localhost";
    label.textContent = `${item.name} · ${item.source || "agent"} · ${remoteLabel}`;
    li.appendChild(label);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-sm btn-outline-primary";
    btn.textContent = item.added ? "Added" : "Add as member";
    btn.disabled = Boolean(item.added);
    btn.dataset.herdrName = item.name || "";
    btn.dataset.herdrRemote = item.remote || "";
    btn.addEventListener("click", async () => {
      const res = await addHerdrMember(item.name, item.remote || "");
      if (res.status === 409 || res.ok) {
        btn.textContent = "Added";
        btn.disabled = true;
        setHerdrStatus(`Added ${item.name}.`, "success");
        await refreshHerdrAgents();
        return;
      }
      setHerdrStatus(`Add failed (${res.status}).`, "danger");
    });
    li.appendChild(btn);
    list.appendChild(li);
  }
  setHerdrStatus(`Found ${items.length} live Herdr member(s).`);
}

async function addHerdrAgent() {
  const nameInput = document.getElementById("herdr-name");
  const remoteInput = document.getElementById("herdr-remote");
  const name = (nameInput?.value || "").trim();
  const remote = (remoteInput?.value || "").trim();
  if (!name) {
    setHerdrStatus("Name is required.", "danger");
    return;
  }
  const response = await addHerdrMember(name, remote);
  if (response.status === 409) {
    setHerdrStatus(`Herdr agent "${name}" already exists.`, "danger");
    return;
  }
  if (!response.ok) {
    let detail = `Add failed (${response.status})`;
    try {
      const err = await response.json();
      detail = err.error || err.name?.[0] || detail;
    } catch {
      // keep status text
    }
    setHerdrStatus(detail, "danger");
    return;
  }
  if (nameInput) nameInput.value = "";
  if (remoteInput) remoteInput.value = "";
  setHerdrStatus(`Added ${name}.`, "success");
  await refreshHerdrAgents();
}

async function removeHerdrAgent(button) {
  const id = button?.dataset?.herdrId;
  const name = button?.dataset?.herdrName || id;
  if (!id) return;
  const headers = { Accept: "application/json" };
  const csrf = getCsrfToken();
  if (csrf) headers["X-CSRFToken"] = csrf;
  const response = await fetch(`/v1/herdr-agents/${encodeURIComponent(id)}/`, {
    method: "DELETE",
    headers,
    credentials: "same-origin",
  });
  if (!response.ok && response.status !== 204) {
    setHerdrStatus(`Remove failed (${response.status}).`, "danger");
    return;
  }
  setHerdrStatus(`Removed ${name}.`, "success");
  await refreshHerdrAgents();
}

const SETTINGS_DASHBOARD_ACTIONS = {
  'export-settings': exportSettings,
  'refresh-settings': refreshSettings,
  'view-environment': viewEnvironment,
  'copy-object-content': copyObjectContent,
  'chat-archive-all': chatArchiveAll,
  'chat-empty-trash': chatEmptyTrash,
  'add-herdr-agent': addHerdrAgent,
  'add-herdr-remote': addHerdrRemoteKind,
  'discover-herdr-agents': discoverHerdrAgents,
};

document.querySelector('.settings-page')?.addEventListener('click', (event) => {
  const btn = event.target.closest('[data-action]');
  if (!btn || !event.currentTarget.contains(btn) || btn.disabled) return;
  const action = btn.getAttribute('data-action');
  if (action === 'chat-archive-one') {
    chatArchiveOne(btn.getAttribute('data-agent-id') || '');
    return;
  }
  if (action === 'chat-restore-one') {
    chatRestoreOne(btn.getAttribute('data-agent-id') || '');
    return;
  }
  if (action === 'remove-herdr-agent') {
    event.preventDefault();
    removeHerdrAgent(btn);
    return;
  }
  if ((action === 'add-herdr-agent' || action === 'add-herdr-remote') && btn.type === 'submit') {
    // Form submit handler owns this; avoid double-fire from the click delegate.
    return;
  }
  const handler = SETTINGS_DASHBOARD_ACTIONS[action];
  if (typeof handler === 'function') handler();
});

document.getElementById('herdr-add-form')?.addEventListener('submit', (event) => {
  event.preventDefault();
  addHerdrAgent();
});

document.getElementById('herdr-remote-form')?.addEventListener('submit', (event) => {
  event.preventDefault();
  addHerdrRemoteKind();
});

document.getElementById('herdr-remote-mode')?.addEventListener('change', syncHerdrRemoteFormMode);
syncHerdrRemoteFormMode();

document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('.group-header[data-group-id]').forEach((header) => {
    const groupId = header.dataset.groupId;
    header.addEventListener('click', () => toggleGroup(groupId));
    header.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        toggleGroup(groupId);
      }
    });
  });

  document.querySelectorAll('.btn-view-object').forEach((btn) => {
    btn.addEventListener('click', () => viewObject(btn.dataset.groupId, btn.dataset.settingName));
  });
  document.querySelectorAll('.btn-copy-env').forEach((btn) => {
    btn.addEventListener('click', () => copyEnvVar(btn.dataset.envVar));
  });

  const firstGroup = document.querySelector('.settings-group');
  if (firstGroup) {
    const groupId = firstGroup.id.replace('group-', '');
    toggleGroup(groupId);
  }

  refreshHerdrRemoteKind();
});
