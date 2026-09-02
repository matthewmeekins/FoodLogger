const API_BASE = window.location.origin;
let _currentUser = null;
let _apiKeys = [];
let _lastCreatedKey = '';

function setStatus(id, message, type = null) {
    const el = document.getElementById(id);
    if (!el) return;
    if (!message) {
        el.textContent = '';
        el.className = 'status-message';
        return;
    }
    el.textContent = message;
    el.className = `status-message ${type || ''}`.trim();
}

async function requireAuth() {
    try {
        const meResp = await fetch(`${API_BASE}/auth/me`);
        if (meResp.status === 401) {
            window.location.href = '/login';
            return false;
        }
        if (!meResp.ok) {
            throw new Error('Unable to verify session');
        }
        const me = await meResp.json();
        _currentUser = me.user || null;
        if (!_currentUser) {
            window.location.href = '/login';
            return false;
        }
        document.getElementById('api-keys-current-user').textContent = _currentUser.display_name || _currentUser.username;
        return true;
    } catch {
        window.location.href = '/login';
        return false;
    }
}

async function logout() {
    try {
        await fetch(`${API_BASE}/auth/logout`, { method: 'POST' });
    } finally {
        window.location.href = '/login';
    }
}

function formatTimestamp(value) {
    if (!value) return '—';
    return value.replace('T', ' ').slice(0, 19);
}

function renderKeys() {
    const body = document.getElementById('keys-body');
    if (!body) return;

    if (_apiKeys.length === 0) {
        body.innerHTML = `<tr><td colspan="6">No API keys yet.</td></tr>`;
        return;
    }

    body.innerHTML = _apiKeys.map((k) => {
        const isRevoked = !!k.revoked_at;
        return `
        <tr>
            <td>${(k.label || 'Untitled').replace(/</g, '&lt;')}</td>
            <td><code>${k.key_prefix}…</code></td>
            <td>${formatTimestamp(k.created_at)}</td>
            <td>${formatTimestamp(k.last_used_at)}</td>
            <td>${isRevoked ? 'Revoked' : 'Active'}</td>
            <td>
                <button class="revoke-btn" ${isRevoked ? 'disabled' : ''} onclick="revokeKey(${k.id})">
                    ${isRevoked ? 'Revoked' : 'Revoke'}
                </button>
            </td>
        </tr>
    `;
    }).join('');
}

async function loadKeys() {
    setStatus('keys-status', 'Loading keys...', 'info');
    try {
        const response = await fetch(`${API_BASE}/auth/api-keys`);
        if (!response.ok) {
            throw new Error('Failed to load API keys');
        }
        const data = await response.json();
        _apiKeys = data.api_keys || [];
        renderKeys();
        setStatus('keys-status', '', null);
    } catch (error) {
        setStatus('keys-status', error.message, 'error');
    }
}

async function generateKey() {
    const labelInput = document.getElementById('new-key-label');
    const label = labelInput.value.trim();

    try {
        const response = await fetch(`${API_BASE}/auth/api-keys`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ label: label || null }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            setStatus('create-key-status', data.detail || 'Failed to create API key', 'error');
            return;
        }

        labelInput.value = '';
        _lastCreatedKey = data.key;
        document.getElementById('key-reveal-value').textContent = data.key;
        document.getElementById('key-reveal').style.display = 'flex';
        setStatus('create-key-status', 'API key created', 'success');
        await loadKeys();
    } catch {
        setStatus('create-key-status', 'Failed to create API key', 'error');
    }
}

async function copyKey() {
    if (!_lastCreatedKey) return;
    try {
        await navigator.clipboard.writeText(_lastCreatedKey);
        setStatus('create-key-status', 'Copied to clipboard', 'success');
    } catch {
        setStatus('create-key-status', 'Could not copy automatically — select and copy manually', 'error');
    }
}

async function revokeKey(keyId) {
    if (!confirm('Revoke this API key? Any client using it will stop working immediately.')) {
        return;
    }
    try {
        const response = await fetch(`${API_BASE}/auth/api-keys/${keyId}`, { method: 'DELETE' });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            setStatus('keys-status', data.detail || 'Failed to revoke key', 'error');
            return;
        }
        setStatus('keys-status', 'Key revoked', 'success');
        await loadKeys();
    } catch {
        setStatus('keys-status', 'Failed to revoke key', 'error');
    }
}

window.logout = logout;
window.generateKey = generateKey;
window.copyKey = copyKey;
window.revokeKey = revokeKey;

(async function init() {
    const ok = await requireAuth();
    if (!ok) return;
    await loadKeys();
})();
