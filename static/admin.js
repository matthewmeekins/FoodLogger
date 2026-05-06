const API_BASE = window.location.origin;
let _adminUser = null;
let _users = [];

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

async function requireAdmin() {
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
        _adminUser = me.user || null;
        if (!_adminUser || !_adminUser.is_admin) {
            window.location.href = '/';
            return false;
        }
        document.getElementById('admin-current-user').textContent = _adminUser.display_name || _adminUser.username;
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

function renderUsers() {
    const body = document.getElementById('admin-users-body');
    if (!body) return;
    body.innerHTML = _users.map((u) => `
        <tr>
            <td>${u.id}</td>
            <td>${u.username}</td>
            <td><input id="display-${u.id}" type="text" value="${(u.display_name || '').replace(/"/g, '&quot;')}"></td>
            <td>${u.is_admin ? 'yes' : 'no'}</td>
            <td><input id="active-${u.id}" type="checkbox" ${u.is_active ? 'checked' : ''}></td>
            <td><input id="password-${u.id}" type="password" placeholder="new password"></td>
            <td><button class="logout-btn" onclick="saveUser(${u.id})">Save</button></td>
        </tr>
    `).join('');
}

async function loadUsers() {
    setStatus('admin-users-status', 'Loading users...', 'info');
    try {
        const response = await fetch(`${API_BASE}/auth/users`);
        if (!response.ok) {
            throw new Error('Failed to load users');
        }
        const data = await response.json();
        _users = data.users || [];
        renderUsers();
        setStatus('admin-users-status', `Loaded ${_users.length} users`, 'success');
    } catch (error) {
        setStatus('admin-users-status', error.message, 'error');
    }
}

async function createUser() {
    const username = document.getElementById('new-username').value.trim();
    const displayName = document.getElementById('new-display-name').value.trim();
    const password = document.getElementById('new-password').value;
    const isAdmin = document.getElementById('new-is-admin').checked;

    if (!username || !password) {
        setStatus('admin-create-status', 'Username and password are required', 'error');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                username,
                password,
                display_name: displayName || null,
                is_admin: isAdmin,
            }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            setStatus('admin-create-status', data.detail || 'Failed to create user', 'error');
            return;
        }

        document.getElementById('new-username').value = '';
        document.getElementById('new-display-name').value = '';
        document.getElementById('new-password').value = '';
        document.getElementById('new-is-admin').checked = false;
        setStatus('admin-create-status', 'User created', 'success');
        await loadUsers();
    } catch {
        setStatus('admin-create-status', 'Failed to create user', 'error');
    }
}

async function saveUser(userId) {
    const displayName = document.getElementById(`display-${userId}`).value.trim();
    const isActive = document.getElementById(`active-${userId}`).checked;
    const password = document.getElementById(`password-${userId}`).value;

    const payload = {
        display_name: displayName || null,
        is_active: isActive,
    };
    if (password) {
        payload.password = password;
    }

    try {
        const response = await fetch(`${API_BASE}/auth/users/${userId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            setStatus('admin-users-status', data.detail || 'Failed to update user', 'error');
            return;
        }
        document.getElementById(`password-${userId}`).value = '';
        setStatus('admin-users-status', `Updated ${data.user.username}`, 'success');
        await loadUsers();
    } catch {
        setStatus('admin-users-status', 'Failed to update user', 'error');
    }
}

window.logout = logout;
window.createUser = createUser;
window.saveUser = saveUser;

(async function init() {
    const ok = await requireAdmin();
    if (!ok) return;
    await loadUsers();
})();
