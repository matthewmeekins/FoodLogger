// Get the API base URL (works for both localhost and network access)
        const API_BASE = window.location.origin;
    let _currentUser = null;
    let _selectedDailyDate = formatIsoDate(new Date());
    let _weeklyStartDate = null;
    const _weeklyDayEntryCache = {};
    const _entryMap = {};
    let _weeklyLoadRequestId = 0;
    let _dailyDatePickerInstance = null;
    let _weeklyDatePickerInstance = null;

        // Switch between tabs
        function switchTab(tabName, tabButton = null) {
            // Update tab buttons
            document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
            const activeButton = tabButton || document.querySelector(`.tab[onclick*="'${tabName}'"]`);
            if (activeButton) {
                activeButton.classList.add('active');
            }

            // Update tab content
            document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
            document.getElementById(`${tabName}-tab`).classList.add('active');

            // Load data for the tab
            if (tabName === 'daily') {
                loadTodayEntries();
            } else if (tabName === 'weekly') {
                loadWeekly();
            } else if (tabName === 'log') {
                loadFavorites();
            }
        }

        function formatIsoDate(date) {
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            return `${year}-${month}-${day}`;
        }

        function parseLocalDate(dateStr) {
            // Avoid UTC parsing of YYYY-MM-DD, which can shift labels by one day.
            return new Date(`${dateStr}T12:00:00`);
        }

        function formatEntryTime(timestamp) {
            if (!timestamp) {
                return '';
            }
            const normalized = /Z$|[+-]\d\d:\d\d$/.test(timestamp) ? timestamp : `${timestamp}Z`;
            const date = new Date(normalized);
            if (Number.isNaN(date.getTime())) {
                return '';
            }
            return date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
        }

        function getLocalDateAndTimeFromTimestamp(timestamp) {
            if (!timestamp) {
                return null;
            }
            const normalized = /Z$|[+-]\d\d:\d\d$/.test(timestamp) ? timestamp : `${timestamp}Z`;
            const date = new Date(normalized);
            if (Number.isNaN(date.getTime())) {
                return null;
            }

            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            const hours = String(date.getHours()).padStart(2, '0');
            const minutes = String(date.getMinutes()).padStart(2, '0');

            return {
                date: `${year}-${month}-${day}`,
                time: `${hours}:${minutes}`,
            };
        }

        function buildUtcIsoFromLocalDateTime(dateStr, timeStr) {
            if (!dateStr || !timeStr) {
                return null;
            }
            const localDate = new Date(`${dateStr}T${timeStr}:00`);
            if (Number.isNaN(localDate.getTime())) {
                return null;
            }
            return localDate.toISOString();
        }

        function formatNutrient(value) {
            const num = Number(value);
            if (!Number.isFinite(num)) {
                return '0';
            }
            return num.toLocaleString(undefined, {
                minimumFractionDigits: 0,
                maximumFractionDigits: 2,
            });
        }

        function formatQuantityLabel(entry) {
            const quantity = Number(entry.quantity_value);
            if (!Number.isFinite(quantity) || quantity <= 0) {
                return '';
            }
            return `Qty: ${Math.round(quantity)}`;
        }

        function renderEntryActions(entry, quantity, includeAddToToday = false) {
            const entryId = typeof entry === 'object' ? entry.id : entry;
            const entryJson = typeof entry === 'object' ? JSON.stringify(entry).replace(/'/g, '&#39;') : null;
            const editBtn = entryJson
                ? `<button class="icon-btn edit-icon-btn" title="Edit" aria-label="Edit" onclick="openEditModal(${entryJson})">✎</button>`
                : `<button class="icon-btn edit-icon-btn" title="Edit" aria-label="Edit" onclick="openEditModal(${entryId})">✎</button>`;
            const addToToday = includeAddToToday
                ? `<button class="icon-btn add-today-btn" title="Add to Today" aria-label="Add to Today" onclick="addToToday(${entryId}); event.stopPropagation();">⊕</button>`
                : '';

            return `
                <span class="quantity-controls"><button class="qty-btn" onclick="adjustQuantity(${entryId}, -1, ${quantity}); event.stopPropagation();">-</button><button class="qty-btn" onclick="adjustQuantity(${entryId}, 1, ${quantity}); event.stopPropagation();">+</button></span>
                ${addToToday}
                ${editBtn}
                <button class="icon-btn delete-icon-btn" title="Delete" aria-label="Delete" onclick="deleteEntry(${entryId})">✕</button>
            `;
        }

        function _syncDailyDatePicker() {
            const picker = document.getElementById('daily-date-picker');
            if (picker) {
                picker.value = _selectedDailyDate;
            }
            if (_dailyDatePickerInstance) {
                _dailyDatePickerInstance.setDate(_selectedDailyDate, false);
            }
        }

        function navigateDaily(direction) {
            const d = parseLocalDate(_selectedDailyDate);
            d.setDate(d.getDate() + direction);
            _selectedDailyDate = formatIsoDate(d);
            loadTodayEntries();
        }

        function onDailyDateChange(dateStr) {
            if (!dateStr) {
                return;
            }
            _selectedDailyDate = dateStr;
            loadTodayEntries();
        }

        function onWeeklyDateChange(dateStr) {
            if (!dateStr) {
                return;
            }
            loadWeekly(_getMondayOf(dateStr), { showLoading: false });
        }

        function openDatePicker(inputId) {
            if (inputId === 'daily-date-picker' && _dailyDatePickerInstance) {
                _dailyDatePickerInstance.open();
                return;
            }
            if (inputId === 'weekly-date-picker' && _weeklyDatePickerInstance) {
                _weeklyDatePickerInstance.open();
                return;
            }
            const input = document.getElementById(inputId);
            if (!input) {
                return;
            }
            if (typeof input.showPicker === 'function') {
                input.showPicker();
                return;
            }
            input.focus();
        }

        function setStatus(element, message, type = null) {
            if (!element) {
                return;
            }
            if (!message) {
                element.textContent = '';
                element.className = 'status-message';
                return;
            }
            element.textContent = message;
            element.className = `status-message ${type || ''}`.trim();
        }

        function showStatus(message, type = 'success') {
            setStatus(document.getElementById('log-status'), message, type);
        }

        function renderCurrentUser() {
            const userEl = document.getElementById('current-user');
            if (!userEl || !_currentUser) {
                return;
            }
            const display = _currentUser.display_name || _currentUser.username || 'User';
            userEl.textContent = display;

            const adminLink = document.getElementById('admin-link');
            if (adminLink) {
                adminLink.classList.toggle('hidden', !_currentUser.is_admin);
            }
        }

        function closeAccountMenu() {
            const menu = document.getElementById('account-menu');
            const toggle = document.getElementById('account-menu-toggle');
            if (!menu || !toggle) {
                return;
            }
            menu.classList.remove('open');
            toggle.setAttribute('aria-expanded', 'false');
        }

        function toggleAccountMenu(event) {
            event.stopPropagation();
            const menu = document.getElementById('account-menu');
            const toggle = document.getElementById('account-menu-toggle');
            if (!menu || !toggle) {
                return;
            }
            const nextState = !menu.classList.contains('open');
            menu.classList.toggle('open', nextState);
            toggle.setAttribute('aria-expanded', String(nextState));
        }

        function setupAccountMenu() {
            const menu = document.getElementById('account-menu');
            const shell = document.querySelector('.auth-shell');
            if (!menu || !shell) {
                return;
            }

            document.addEventListener('click', (event) => {
                if (!shell.contains(event.target)) {
                    closeAccountMenu();
                }
            });

            document.addEventListener('keydown', (event) => {
                if (event.key === 'Escape') {
                    closeAccountMenu();
                }
            });
        }

        function setupStyledDatePickers() {
            if (typeof window.flatpickr !== 'function') {
                return;
            }

            const dailyPickerEl = document.getElementById('daily-date-picker');
            if (dailyPickerEl) {
                _dailyDatePickerInstance = window.flatpickr(dailyPickerEl, {
                    dateFormat: 'Y-m-d',
                    defaultDate: _selectedDailyDate,
                    disableMobile: true,
                    onChange: (_dates, dateStr) => {
                        onDailyDateChange(dateStr);
                    },
                });
            }

            const weeklyPickerEl = document.getElementById('weekly-date-picker');
            if (weeklyPickerEl) {
                const initialWeekDate = _weeklyStartDate || _getMondayOf(formatIsoDate(new Date()));
                _weeklyDatePickerInstance = window.flatpickr(weeklyPickerEl, {
                    dateFormat: 'Y-m-d',
                    defaultDate: initialWeekDate,
                    disableMobile: true,
                    onChange: (_dates, dateStr) => {
                        onWeeklyDateChange(dateStr);
                    },
                });
            }
        }

        async function requireAuth() {
            try {
                const response = await fetch(`${API_BASE}/auth/me`);
                if (response.status === 401) {
                    window.location.href = '/login';
                    return false;
                }
                if (!response.ok) {
                    throw new Error('Unable to verify session');
                }
                const data = await response.json();
                _currentUser = data.user || null;
                renderCurrentUser();
                return true;
            } catch {
                window.location.href = '/login';
                return false;
            }
        }

        async function logout() {
            try {
                closeAccountMenu();
                await fetch(`${API_BASE}/auth/logout`, { method: 'POST' });
            } finally {
                window.location.href = '/login';
            }
        }

        function openPasswordModal() {
            const modal = document.getElementById('password-modal');
            if (!modal) return;
            closeAccountMenu();
            document.getElementById('current-password').value = '';
            document.getElementById('new-password').value = '';
            setStatus(document.getElementById('password-status'), '');
            modal.classList.add('active');
        }

        function closePasswordModal() {
            const modal = document.getElementById('password-modal');
            if (!modal) return;
            modal.classList.remove('active');
        }

        async function submitPasswordChange() {
            const status = document.getElementById('password-status');
            const currentPassword = document.getElementById('current-password').value;
            const newPassword = document.getElementById('new-password').value;

            if (!currentPassword || !newPassword) {
                setStatus(status, 'Both fields are required', 'error');
                return;
            }

            try {
                const response = await fetch(`${API_BASE}/auth/change-password`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        current_password: currentPassword,
                        new_password: newPassword,
                    }),
                });

                const data = await response.json().catch(() => ({}));
                if (!response.ok) {
                    setStatus(status, data.detail || 'Unable to update password', 'error');
                    return;
                }

                setStatus(status, 'Password updated successfully', 'success');
                setTimeout(() => {
                    closePasswordModal();
                }, 700);
            } catch {
                setStatus(status, 'Unable to update password', 'error');
            }
        }

        window.logout = logout;
        window.openPasswordModal = openPasswordModal;
        window.closePasswordModal = closePasswordModal;
        window.submitPasswordChange = submitPasswordChange;
        window.toggleAccountMenu = toggleAccountMenu;

        function showClarificationCard(pendingEntry) {
            const card = document.getElementById('clarification-card');
            const question = document.getElementById('clarification-question');
            const answer = document.getElementById('clarification-answer');

            document.getElementById('manual-card').style.display = 'none';
            card.style.display = 'block';
            card.dataset.pendingId = pendingEntry.pending_id;
            question.textContent = pendingEntry.question || 'Please provide more details.';
            answer.value = '';
            setStatus(document.getElementById('clarify-status'), '');
            answer.focus();
        }

        function showManualCard(data) {
            const clarification = document.getElementById('clarification-card');
            const card = document.getElementById('manual-card');
            const prompt = document.getElementById('manual-prompt');
            const caloriesInput = document.getElementById('manual-calories');

            clarification.style.display = 'none';
            card.style.display = 'block';
            card.dataset.pendingId = data.pending_id;
            prompt.textContent = data.manual_prompt || 'Please enter your calorie estimate.';
            caloriesInput.value = '';
            setStatus(document.getElementById('manual-status'), '');
            caloriesInput.focus();
        }

        // Log food entry
        async function logFood() {
            const input = document.getElementById('food-input');
            const button = document.getElementById('log-button');
            const text = input.value.trim();

            if (button.disabled) {
                return;
            }

            if (!text) {
                showStatus('Please enter what you ate', 'error');
                return;
            }

            button.disabled = true;
            button.textContent = 'Logging...';
            showStatus('Submitting entry...', 'info');

            try {
                const response = await fetch(`${API_BASE}/log`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'text/plain',
                    },
                    body: text
                });

                if (!response.ok) {
                    throw new Error('Failed to log food');
                }

                const data = await response.json();
                
                if (data.status === 'needs_clarification') {
                    document.getElementById('manual-card').style.display = 'none';
                    showClarificationCard(data.pending_entries[0]); // Assume one for now
                    showStatus('Need a bit more detail to finish this entry.', 'info');
                } else {
                    showStatus(`✓ Logged ${data.foods_logged} item(s) successfully!`, 'success');
                    input.value = '';
                    // Auto-switch to today tab after successful log
                    setTimeout(() => {
                        document.querySelectorAll('.tab')[1].click();
                    }, 1000);
                }

            } catch (error) {
                showStatus(`Error: ${error.message}`, 'error');
            } finally {
                button.disabled = false;
                button.textContent = 'Log Food';
            }
        }

        // Meal filter state
        let _todayEntries = [];
        let _activeMealFilter = 'all';
        let _todayTotalCalories = 0;

        function setMealFilter(meal) {
            _activeMealFilter = meal;
            // Update button active states
            document.querySelectorAll('.meal-filter-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.meal === meal);
            });
            renderTodayEntries();
        }

        function _buildEntryHtml(entry) {
            const calories = entry.calories ? `${entry.calories} cal` : '—';
            const quantityLabel = formatQuantityLabel(entry);
            const quantity = Number(entry.quantity_value) || 1;
            const quantityMarkup = quantityLabel ? `<div class="quantity-label">${quantityLabel}</div>` : '';
            const entryTime = formatEntryTime(entry.created_at);
            const foodLabel = entryTime ? `${entry.food_name} · ${entryTime}` : entry.food_name;
            const macros = entry.protein_g || entry.carbs_g || entry.fat_g ?
                `<div class="daily-entry-macros">P ${formatNutrient(entry.protein_g)}g · C ${formatNutrient(entry.carbs_g)}g · F ${formatNutrient(entry.fat_g)}g</div>` : '';

            return `
                <div class="weekly-entry-card">
                    <div class="weekly-entry-top">
                        <div class="detail-food">${foodLabel}</div>
                        <div class="detail-calories">${calories}</div>
                    </div>
                    ${macros}
                    <div class="weekly-entry-actions-bottom">
                        <div class="entry-qty-left">
                            ${quantityMarkup}
                            <span class="quantity-controls">
                                <button class="qty-btn" onclick="adjustQuantity(${entry.id}, -1, ${quantity}); event.stopPropagation();">-</button>
                                <button class="qty-btn" onclick="adjustQuantity(${entry.id}, 1, ${quantity}); event.stopPropagation();">+</button>
                            </span>
                        </div>
                        <div class="entry-icon-btns">
                            <button class="icon-btn edit-icon-btn" title="Edit" aria-label="Edit" onclick="openEditModal(${entry.id})">✎</button>
                            <button class="icon-btn delete-icon-btn" title="Delete" aria-label="Delete" onclick="deleteEntry(${entry.id})">✕</button>
                            <button class="icon-btn fav-icon-btn" onclick="saveEntryAsFavorite(${entry.id}); event.stopPropagation();" title="Save as favorite">&#9733;</button>
                        </div>
                    </div>
                </div>
                <div id="trace-${entry.id}" class="trace-panel"></div>
            `;
        }

        function renderTodayEntries() {
            const container = document.getElementById('daily-entries');
            const totalSection = document.getElementById('daily-total');

            const MEAL_ORDER = ['breakfast', 'lunch', 'dinner', 'snack'];

            if (_activeMealFilter === 'all') {
                // Group by meal in canonical order, then unspecified
                const groups = {};
                _todayEntries.forEach(entry => {
                    const meal = entry.meal ? entry.meal.toLowerCase() : 'unspecified';
                    if (!groups[meal]) groups[meal] = [];
                    groups[meal].push(entry);
                });

                const orderedMeals = [...MEAL_ORDER.filter(m => groups[m]), ...Object.keys(groups).filter(m => !MEAL_ORDER.includes(m) && groups[m])];

                if (orderedMeals.length === 0) {
                    container.innerHTML = `
                        <div class="empty-state">
                            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"></path>
                            </svg>
                            <p>No entries for this date</p>
                        </div>`;
                    totalSection.style.display = 'none';
                    return;
                }

                let html = '';
                orderedMeals.forEach(meal => {
                    const label = meal.charAt(0).toUpperCase() + meal.slice(1);
                    const saveMealBtn = meal !== 'unspecified'
                        ? `<button class="fav-btn" onclick="saveMealGroupAsFavorite('${meal}', event)">★ Save meal</button>`
                        : '';
                    html += `<div class="meal-group-header-row"><div class="meal-group-header ${meal === 'unspecified' ? '' : meal}">${label}</div>${saveMealBtn}</div>`;
                    groups[meal].forEach(entry => { html += _buildEntryHtml(entry); });
                });
                container.innerHTML = html;

            } else {
                // Filter to selected meal
                const filtered = _todayEntries.filter(e => (e.meal || '').toLowerCase() === _activeMealFilter);

                if (filtered.length === 0) {
                    container.innerHTML = `
                        <div class="empty-state">
                            <p>No ${_activeMealFilter} entries for this date</p>
                        </div>`;
                    totalSection.style.display = 'none';
                    return;
                }

                let html = '';
                filtered.forEach(entry => { html += _buildEntryHtml(entry); });
                container.innerHTML = html;

                // Show filtered calorie total
                const filteredCals = filtered.reduce((sum, e) => sum + (e.calories || 0), 0);
                if (filteredCals > 0) {
                    document.getElementById('daily-total-calories').textContent = filteredCals;
                    totalSection.style.display = 'block';
                } else {
                    totalSection.style.display = 'none';
                }
                return;
            }

            if (_todayTotalCalories > 0) {
                document.getElementById('daily-total-calories').textContent = _todayTotalCalories;
                totalSection.style.display = 'block';
            } else {
                totalSection.style.display = 'none';
            }
        }

        // ---------------------------------------------------------------------------
        // Favorites
        // ---------------------------------------------------------------------------

        let _allFavorites = [];

        async function loadFavorites() {
            try {
                const response = await fetch(`${API_BASE}/favorites`);
                const data = await response.json();
                _allFavorites = data.favorites || [];
                renderFavorites(_allFavorites);
            } catch {
                // Silently fail — favorites list is non-critical on load
            }
        }

        function filterFavorites() {
            const q = (document.getElementById('fav-search')?.value || '').toLowerCase().trim();
            const filtered = q ? _allFavorites.filter(f => f.name.toLowerCase().includes(q)) : _allFavorites;
            renderFavorites(filtered);
        }

        function renderFavorites(favorites) {
            const container = document.getElementById('fav-list');
            if (!container) return;

            if (favorites.length === 0) {
                container.innerHTML = `<div class="fav-empty">${_allFavorites.length === 0 ? 'No favorites saved yet.' : 'No matches.'}</div>`;
                return;
            }

            container.innerHTML = favorites.map(fav => {
                const meta = [
                    fav.item_count > 1 ? `${fav.item_count} items` : '1 item',
                    fav.total_calories ? `${fav.total_calories} cal` : '',
                    fav.total_protein_g ? `P ${formatNutrient(fav.total_protein_g)}g` : '',
                    fav.total_carbs_g ? `C ${formatNutrient(fav.total_carbs_g)}g` : '',
                    fav.total_fat_g ? `F ${formatNutrient(fav.total_fat_g)}g` : '',
                ].filter(Boolean).join(' · ');

                return `
                    <div class="fav-card">
                        <div class="fav-card-info">
                            <div class="fav-card-name">${fav.name}</div>
                            <div class="fav-card-meta">${meta}</div>
                        </div>
                        <div class="fav-card-actions">
                            <button class="icon-btn add-today-btn" title="Log" aria-label="Log" onclick="logFavorite(${fav.id}, '${fav.name.replace(/'/g, "\\'")}')">⊕</button>
                            <button class="icon-btn delete-icon-btn" onclick="deleteFavorite(${fav.id}, event)">✕</button>
                        </div>
                    </div>`;
            }).join('');
        }

        async function logFavorite(favId, favName) {
            try {
                const response = await fetch(`${API_BASE}/favorites/${favId}/log`, { method: 'POST' });
                if (!response.ok) throw new Error('Failed to log favorite');
                const data = await response.json();
                showStatus(`✓ Logged "${favName}" (${data.items_logged} item${data.items_logged !== 1 ? 's' : ''})`, 'success');
                loadTodayEntries();
                // Switch to Today tab
                setTimeout(() => { document.querySelectorAll('.tab')[1].click(); }, 800);
            } catch (error) {
                showStatus(error.message, 'error');
            }
        }

        async function deleteFavorite(favId, event) {
            event.stopPropagation();
            if (!confirm('Delete this favorite?')) return;
            try {
                const response = await fetch(`${API_BASE}/favorites/${favId}`, { method: 'DELETE' });
                if (!response.ok) throw new Error('Failed to delete favorite');
                await loadFavorites();
            } catch (error) {
                alert(error.message);
            }
        }

        async function saveEntryAsFavorite(entryId) {
            // Resolve from shared map so this works in both Daily and Weekly views.
            const entry = _entryMap[entryId] || _todayEntries.find(e => e.id === entryId);
            if (!entry) return;

            const name = prompt(`Save "${entry.food_name}" as a favorite. Enter a name:`, entry.food_name);
            if (!name || !name.trim()) return;

            const item = {
                food_name: entry.food_name,
                calories: entry.calories,
                meal: entry.meal,
                protein_g: entry.protein_g,
                carbs_g: entry.carbs_g,
                fat_g: entry.fat_g,
                reasoning: entry.reasoning,
                quantity_value: entry.quantity_value || 1,
                quantity_unit: entry.quantity_unit || null,
                per_unit_calories: entry.per_unit_calories || null,
                per_unit_protein_g: entry.per_unit_protein_g || null,
                per_unit_carbs_g: entry.per_unit_carbs_g || null,
                per_unit_fat_g: entry.per_unit_fat_g || null,
            };

            try {
                const response = await fetch(`${API_BASE}/favorites`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: name.trim(), items: [item] }),
                });
                if (!response.ok) throw new Error('Failed to save favorite');
                showStatus(`✓ Saved "${name.trim()}" as a favorite`, 'success');
                await loadFavorites();
            } catch (error) {
                showStatus(error.message, 'error');
            }
        }

        async function saveMealGroupAsFavorite(meal, event) {
            event.stopPropagation();
            const mealEntries = _todayEntries.filter(e => (e.meal || '').toLowerCase() === meal);
            if (mealEntries.length === 0) return;

            const defaultName = meal.charAt(0).toUpperCase() + meal.slice(1);
            const name = prompt(`Save all ${mealEntries.length} ${meal} items as a favorite. Enter a name:`, defaultName);
            if (!name || !name.trim()) return;

            const items = mealEntries.map(entry => ({
                food_name: entry.food_name,
                calories: entry.calories,
                meal: entry.meal,
                protein_g: entry.protein_g,
                carbs_g: entry.carbs_g,
                fat_g: entry.fat_g,
                reasoning: entry.reasoning,
                quantity_value: entry.quantity_value || 1,
                quantity_unit: entry.quantity_unit || null,
                per_unit_calories: entry.per_unit_calories || null,
                per_unit_protein_g: entry.per_unit_protein_g || null,
                per_unit_carbs_g: entry.per_unit_carbs_g || null,
                per_unit_fat_g: entry.per_unit_fat_g || null,
            }));

            try {
                const response = await fetch(`${API_BASE}/favorites`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: name.trim(), items }),
                });
                if (!response.ok) throw new Error('Failed to save favorite');
                showStatus(`✓ Saved "${name.trim()}" (${items.length} items) as a favorite`, 'success');
                await loadFavorites();
            } catch (error) {
                showStatus(error.message, 'error');
            }
        }

        // Load today's entries
        async function loadTodayEntries() {
            const container = document.getElementById('daily-entries');
            container.innerHTML = '<div class="empty-state"><p>Loading...</p></div>';
            _syncDailyDatePicker();

            try {
                const response = await fetch(`${API_BASE}/log/date/${encodeURIComponent(_selectedDailyDate)}`);
                const data = await response.json();

                _todayEntries = data.entries || [];
                _todayEntries.forEach(e => { _entryMap[e.id] = e; });
                _todayTotalCalories = data.total_calories || 0;
                renderTodayEntries();

            } catch (error) {
                container.innerHTML = `<div class="empty-state"><p>Error loading entries</p></div>`;
            }
        }


        async function toggleEntryTrace(entryId) {
            const panel = document.getElementById(`trace-${entryId}`);
            const toggle = document.getElementById(`trace-toggle-${entryId}`);
            if (!panel || !toggle) {
                return;
            }

            if (panel.classList.contains('visible')) {
                panel.classList.remove('visible');
                toggle.textContent = 'Details ▼';
                return;
            }

            if (!panel.dataset.loaded) {
                panel.innerHTML = '<div class="trace-block">Loading entry details...</div>';
                panel.classList.add('visible');
                toggle.textContent = 'Details ▲';

                try {
                    const response = await fetch(`${API_BASE}/log/${entryId}/details`);
                    if (!response.ok) {
                        throw new Error('Details not available');
                    }

                    const data = await response.json();
                    const lines = Array.isArray(data.lines) ? data.lines : [];
                    const title = data.title || 'Entry details';
                    const detailsHtml = lines.length > 0
                        ? `<ul class="trace-list">${lines.map(line => `<li>${line}</li>`).join('')}</ul>`
                        : '<div class="trace-block">No additional details available for this entry.</div>';

                    panel.innerHTML = `
                        <div class="trace-section-title">${title}</div>
                        ${detailsHtml}
                    `;
                    panel.dataset.loaded = '1';
                } catch (error) {
                    panel.innerHTML = '<div class="trace-block">Could not load entry details for this entry.</div>';
                }
            } else {
                panel.classList.add('visible');
                toggle.textContent = 'Details ▲';
            }
        }

        // Weekly view state
        function _getMondayOf(dateStr) {
            const d = new Date(dateStr + 'T12:00:00');
            const day = d.getDay(); // 0=Sun, 1=Mon...
            const diff = day === 0 ? -6 : 1 - day;
            d.setDate(d.getDate() + diff);
            return formatIsoDate(d);
        }

        function _weeklyDayElementId(dateStr) {
            return `weekly-day-${dateStr.replaceAll('-', '')}`;
        }

        function _getOpenWeeklyDayDate() {
            const openBody = document.querySelector('.weekly-day-body.open');
            return openBody?.dataset?.date || null;
        }

        function _setWeeklyNavLoading(isLoading) {
            const nav = document.querySelector('#weekly-tab .weekly-nav');
            if (!nav) {
                return;
            }
            nav.classList.toggle('is-loading', isLoading);
            nav.querySelectorAll('.secondary-btn, .nav-date-picker').forEach(el => {
                el.disabled = isLoading;
            });
        }

        function _renderWeeklyDayEntries(entries) {
            if (!entries || entries.length === 0) {
                return '<div class="weekly-day-empty">No entries for this day.</div>';
            }

            return entries.map(entry => {
                const calories = entry.calories ? `${entry.calories} cal` : '—';
                const quantityLabel = formatQuantityLabel(entry);
                const quantity = Number(entry.quantity_value) || 1;
                const quantityMarkup = quantityLabel ? `<div class="quantity-label">${quantityLabel}</div>` : '';
                const entryTime = formatEntryTime(entry.created_at);
                const foodLabel = entryTime ? `${entry.food_name} · ${entryTime}` : entry.food_name;

                return `
                    <div class="weekly-entry-card">
                        <div class="weekly-entry-top">
                            <div class="detail-food">${foodLabel}</div>
                            <div class="detail-calories">${calories}</div>
                        </div>
                        <div class="weekly-entry-actions-bottom">
                            <div class="entry-qty-left">
                                ${quantityMarkup}
                                <span class="quantity-controls">
                                    <button class="qty-btn" onclick="adjustQuantity(${entry.id}, -1, ${quantity}); event.stopPropagation();">-</button>
                                    <button class="qty-btn" onclick="adjustQuantity(${entry.id}, 1, ${quantity}); event.stopPropagation();">+</button>
                                </span>
                            </div>
                            <div class="entry-icon-btns">
                                <button class="icon-btn add-today-btn" title="Add to Today" aria-label="Add to Today" onclick="addToToday(${entry.id}); event.stopPropagation();">⊕</button>
                                <button class="icon-btn edit-icon-btn" title="Edit" aria-label="Edit" onclick="openEditModal(${entry.id})">✎</button>
                                <button class="icon-btn delete-icon-btn" title="Delete" aria-label="Delete" onclick="deleteEntry(${entry.id})">✕</button>
                                <button class="icon-btn fav-icon-btn" onclick="saveEntryAsFavorite(${entry.id}); event.stopPropagation();" title="Save as favorite">&#9733;</button>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
        }

        async function toggleWeeklyDay(dateStr) {
            const body = document.getElementById(_weeklyDayElementId(dateStr));
            if (!body) {
                return;
            }

            const isOpen = body.classList.contains('open');
            document.querySelectorAll('.weekly-day-body.open').forEach(panel => {
                panel.classList.remove('open');
            });
            if (isOpen) {
                return;
            }

            body.classList.add('open');
            if (_weeklyDayEntryCache[dateStr]) {
                body.innerHTML = _renderWeeklyDayEntries(_weeklyDayEntryCache[dateStr]);
                return;
            }

            body.innerHTML = '<div class="weekly-day-empty">Loading entries...</div>';

            try {
                const response = await fetch(`${API_BASE}/log/date/${encodeURIComponent(dateStr)}`);
                const data = await response.json();
                const entries = data.entries || [];
                entries.forEach(e => { _entryMap[e.id] = e; });
                _weeklyDayEntryCache[dateStr] = entries;
                body.innerHTML = _renderWeeklyDayEntries(entries);
            } catch (error) {
                body.innerHTML = '<div class="weekly-day-empty">Unable to load entries.</div>';
            }
        }

        function navigateWeek(direction) {
            if (!_weeklyStartDate) return;
            const d = new Date(_weeklyStartDate + 'T12:00:00');
            d.setDate(d.getDate() + direction * 7);
            _weeklyStartDate = formatIsoDate(d);
            loadWeekly(_weeklyStartDate, { showLoading: false });
        }

        async function loadWeekly(startDate, options = {}) {
            const { showLoading = true, preserveOpenDay = false } = options;
            const container = document.getElementById('weekly-content');
            const weeklyPicker = document.getElementById('weekly-date-picker');
            const prevWeekStart = _weeklyStartDate;
            const openDayDate = preserveOpenDay ? _getOpenWeeklyDayDate() : null;
            const requestId = ++_weeklyLoadRequestId;

            if (showLoading && container.dataset.loaded !== '1') {
                container.innerHTML = '<div class="empty-state"><p>Loading...</p></div>';
            }
            _setWeeklyNavLoading(true);

            if (!startDate) {
                // Default to current week Monday
                const today = new Date();
                startDate = _getMondayOf(formatIsoDate(today));
            }
            _weeklyStartDate = startDate;

            try {
                const response = await fetch(`${API_BASE}/log/weekly?start_date=${encodeURIComponent(startDate)}`);
                const data = await response.json();

                if (requestId !== _weeklyLoadRequestId) {
                    return;
                }

                // Reset cache only when week range changes.
                if (prevWeekStart && prevWeekStart !== data.start_date) {
                    Object.keys(_weeklyDayEntryCache).forEach(k => delete _weeklyDayEntryCache[k]);
                }
                if (weeklyPicker) {
                    weeklyPicker.value = data.start_date;
                }
                if (_weeklyDatePickerInstance) {
                    _weeklyDatePickerInstance.setDate(data.start_date, false);
                }

                // Compute max calories for chart scaling
                const calValues = data.days.map(d => d.total_calories || 0);
                const maxCal = Math.max(...calValues, 1);
                const todayStr = formatIsoDate(new Date());

                // --- Totals/averages grid ---
                const t = data.totals;
                const a = data.averages;
                const n = data.active_days;
                const avgNote = n > 0 ? `avg over ${n} day${n !== 1 ? 's' : ''}` : 'no data';

                const totalsHtml = `<div class="weekly-totals-grid">
                    <div class="weekly-stat-card">
                        <div class="stat-label">Total Calories</div>
                        <div class="stat-value">${t.calories || 0}</div>
                        <div class="stat-avg">${a.calories != null ? `${a.calories}/day` : ''} ${avgNote}</div>
                    </div>
                    <div class="weekly-stat-card">
                        <div class="stat-label">Protein</div>
                        <div class="stat-value">${formatNutrient(t.protein_g)}g</div>
                        <div class="stat-avg">${a.protein_g != null ? `${formatNutrient(a.protein_g)}g/day` : ''}</div>
                    </div>
                    <div class="weekly-stat-card">
                        <div class="stat-label">Carbs</div>
                        <div class="stat-value">${formatNutrient(t.carbs_g)}g</div>
                        <div class="stat-avg">${a.carbs_g != null ? `${formatNutrient(a.carbs_g)}g/day` : ''}</div>
                    </div>
                    <div class="weekly-stat-card">
                        <div class="stat-label">Fat</div>
                        <div class="stat-value">${formatNutrient(t.fat_g)}g</div>
                        <div class="stat-avg">${a.fat_g != null ? `${formatNutrient(a.fat_g)}g/day` : ''}</div>
                    </div>
                </div>`;

                // --- Bar chart ---
                const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
                let chartHtml = '<div class="weekly-chart">';
                data.days.forEach((day, i) => {
                    const cal = day.total_calories || 0;
                    const pct = cal > 0 ? Math.max(4, Math.round((cal / maxCal) * 100)) : 0;
                    const isToday = day.date === todayStr;
                    const barClass = cal === 0 ? 'empty' : (isToday ? 'today' : '');
                    const calLabel = cal > 0 ? `${cal}` : '';
                    chartHtml += `
                        <div class="weekly-bar-col">
                            <div class="weekly-bar-cal">${calLabel}</div>
                            <div class="weekly-bar ${barClass}" style="height:${pct}%"></div>
                            <div class="weekly-bar-label${isToday ? '" style="color:#ffd59f' : ''}">${DAY_LABELS[i]}</div>
                        </div>`;
                });
                chartHtml += '</div>';

                // --- Daily disclosure cards ---
                let disclosureHtml = '<div class="weekly-day-list">';
                data.days.forEach(day => {
                    const calories = day.total_calories || 0;
                    const macroText = `P ${formatNutrient(day.total_protein_g)}g · C ${formatNutrient(day.total_carbs_g)}g · F ${formatNutrient(day.total_fat_g)}g`;
                    const isToday = day.date === todayStr;
                    const todayChip = isToday ? '<span class="weekly-today-chip">Today</span>' : '';

                    disclosureHtml += `
                        <div class="weekly-day-card">
                            <button class="weekly-day-header" onclick="toggleWeeklyDay('${day.date}')">
                                <div class="weekly-day-title-wrap">
                                    <div class="weekly-day-title">${formatDate(day.date)} ${todayChip}</div>
                                    <div class="weekly-day-subtitle">${day.entry_count || 0} entries</div>
                                </div>
                                <div class="weekly-day-stat-wrap">
                                    <div class="weekly-day-calories">${calories} cal</div>
                                    <div class="weekly-day-macros">${macroText}</div>
                                </div>
                            </button>
                            <div id="${_weeklyDayElementId(day.date)}" class="weekly-day-body" data-date="${day.date}"></div>
                        </div>
                    `;
                });
                disclosureHtml += '</div>';

                container.innerHTML = totalsHtml + chartHtml + disclosureHtml;
                container.dataset.loaded = '1';

                if (preserveOpenDay && openDayDate && data.days.some(day => day.date === openDayDate)) {
                    await toggleWeeklyDay(openDayDate);
                }

            } catch (error) {
                if (container.dataset.loaded !== '1') {
                    container.innerHTML = `<div class="empty-state"><p>Error loading weekly summary</p></div>`;
                }
            } finally {
                if (requestId === _weeklyLoadRequestId) {
                    _setWeeklyNavLoading(false);
                }
            }
        }

        function refreshVisibleData() {
            if (document.getElementById('daily-tab')?.classList.contains('active')) {
                loadTodayEntries();
            }
            if (document.getElementById('weekly-tab')?.classList.contains('active')) {
                loadWeekly(_weeklyStartDate, { showLoading: false, preserveOpenDay: true });
            }
        }

        // Delete an entry
        async function deleteEntry(entryId) {
            if (!confirm('Delete this entry?')) {
                return;
            }

            try {
                const response = await fetch(`${API_BASE}/log/${entryId}`, {
                    method: 'DELETE'
                });

                if (!response.ok) {
                    throw new Error('Failed to delete entry');
                }

                // Remove from local caches immediately so open weekly panels update without hard reload.
                delete _entryMap[entryId];
                _todayEntries = _todayEntries.filter(e => e.id !== entryId);
                Object.keys(_weeklyDayEntryCache).forEach(dateStr => {
                    const before = _weeklyDayEntryCache[dateStr].length;
                    _weeklyDayEntryCache[dateStr] = _weeklyDayEntryCache[dateStr].filter(e => e.id !== entryId);
                    if (_weeklyDayEntryCache[dateStr].length !== before) {
                        const body = document.getElementById(_weeklyDayElementId(dateStr));
                        if (body && body.classList.contains('open')) {
                            body.innerHTML = _renderWeeklyDayEntries(_weeklyDayEntryCache[dateStr]);
                        }
                    }
                });

                refreshVisibleData();

            } catch (error) {
                alert(`Error: ${error.message}`);
            }
        }

        async function adjustQuantity(entryId, delta, currentQuantity) {
            const oldQuantity = Math.max(1, Number(currentQuantity));
            const nextQuantity = Math.max(1, Math.round((oldQuantity + delta) * 100) / 100);
            try {
                const response = await fetch(`${API_BASE}/log/${entryId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ quantity_value: nextQuantity })
                });

                if (!response.ok) {
                    throw new Error('Failed to update quantity');
                }

                // Invalidate weekly cache for this entry so it reloads fresh
                Object.keys(_weeklyDayEntryCache).forEach(dateStr => {
                    const idx = _weeklyDayEntryCache[dateStr].findIndex(e => e.id === entryId);
                    if (idx >= 0) {
                        delete _weeklyDayEntryCache[dateStr];
                    }
                });

                // Reload the active view from the server so displayed values are always accurate
                if (document.getElementById('daily-tab')?.classList.contains('active')) {
                    await loadTodayEntries();
                } else if (document.getElementById('weekly-tab')?.classList.contains('active')) {
                    await loadWeekly();
                }

            } catch (error) {
                showStatus(error.message, 'error');
            }
        }

        async function addToToday(entryId) {
            try {
                const response = await fetch(`${API_BASE}/log/${entryId}/add-to-today`, {
                    method: 'POST'
                });

                if (!response.ok) {
                    throw new Error('Failed to add entry to today');
                }

                refreshVisibleData();
                showStatus('Entry added to today', 'success');
            } catch (error) {
                showStatus(error.message, 'error');
            }
        }

        // Submit clarification answer
        async function submitClarification() {
            const card = document.getElementById('clarification-card');
            const answer = document.getElementById('clarification-answer');
            const status = document.getElementById('clarify-status');
            const button = document.getElementById('clarify-button');
            const pendingId = card.dataset.pendingId;
            const text = answer.value.trim();

            if (button.disabled) {
                return;
            }

            if (!text) {
                status.textContent = 'Please provide an answer';
                status.className = 'status-message error';
                return;
            }

            button.disabled = true;
            button.textContent = 'Submitting...';
            setStatus(status, 'Submitting clarification...', 'info');

            try {
                const response = await fetch(`${API_BASE}/clarify`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        pending_id: parseInt(pendingId),
                        answer: text
                    })
                });

                if (!response.ok) {
                    throw new Error('Failed to submit clarification');
                }

                const data = await response.json();

                if (data.status === 'resolved') {
                    status.textContent = '✓ Entry logged successfully!';
                    status.className = 'status-message success';
                    card.style.display = 'none';
                    document.getElementById('food-input').value = '';
                    setTimeout(() => {
                        document.querySelectorAll('.tab')[1].click();
                    }, 1000);
                } else if (data.status === 'needs_clarification') {
                    setStatus(status, data.message || 'More details are needed', 'info');
                    document.getElementById('clarification-question').textContent = data.question;
                } else if (data.status === 'unresolved') {
                    showManualCard(data);
                    showStatus('Automatic matching reached its limit. Please enter a manual estimate.', 'info');
                } else {
                    setStatus(status, 'Unexpected response from server', 'error');
                }

            } catch (error) {
                status.textContent = `Error: ${error.message}`;
                status.className = 'status-message error';
            } finally {
                button.disabled = false;
                button.textContent = 'Continue';
            }
        }

        async function submitManualEstimate() {
            const card = document.getElementById('manual-card');
            const status = document.getElementById('manual-status');
            const caloriesInput = document.getElementById('manual-calories');
            const button = document.getElementById('manual-button');
            const pendingId = parseInt(card.dataset.pendingId);
            const calories = parseInt(caloriesInput.value, 10);

            if (button.disabled) {
                return;
            }

            if (!calories || calories <= 0) {
                status.textContent = 'Please enter a valid calorie estimate';
                status.className = 'status-message error';
                return;
            }

            button.disabled = true;
            button.textContent = 'Saving...';
            setStatus(status, 'Saving manual estimate...', 'info');

            try {
                const response = await fetch(`${API_BASE}/manual-estimate`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        pending_id: pendingId,
                        calories: calories
                    })
                });

                if (!response.ok) {
                    throw new Error('Failed to save manual estimate');
                }

                const data = await response.json();
                status.textContent = `✓ Saved manual estimate (${data.calories} cal)`;
                status.className = 'status-message success';
                card.style.display = 'none';
                document.getElementById('food-input').value = '';
                setTimeout(() => {
                    document.querySelectorAll('.tab')[1].click();
                }, 1000);
            } catch (error) {
                status.textContent = `Error: ${error.message}`;
                status.className = 'status-message error';
            } finally {
                button.disabled = false;
                button.textContent = 'Save Estimate';
            }
        }

        // Helper: Format date nicely
        function formatDate(dateStr) {
            const date = parseLocalDate(dateStr);
            const today = new Date();
            const yesterday = new Date(today);
            yesterday.setDate(yesterday.getDate() - 1);

            if (date.toDateString() === today.toDateString()) {
                return 'Today';
            } else if (date.toDateString() === yesterday.toDateString()) {
                return 'Yesterday';
            } else {
                return date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
            }
        }

        // Allow Enter key to submit (with Shift+Enter for new line)
        document.getElementById('food-input').addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (e.repeat) {
                    return;
                }
                logFood();
            }
        });

        document.getElementById('clarification-answer').addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                if (e.repeat) {
                    return;
                }
                submitClarification();
            }
        });

        document.getElementById('manual-calories').addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                if (e.repeat) {
                    return;
                }
                submitManualEstimate();
            }
        });

        async function initApp() {
            const ok = await requireAuth();
            if (!ok) {
                return;
            }
            setupAccountMenu();
            setupStyledDatePickers();
            _syncDailyDatePicker();
            loadFavorites();
        }

        initApp();

let currentEditEntryId = null;

        function openEditModal(entryIdOrData) {
            const entry = (typeof entryIdOrData === 'object') ? entryIdOrData : _entryMap[entryIdOrData];
            if (!entry) {
                console.error('openEditModal: entry not found for id', entryIdOrData);
                return;
            }
            currentEditEntryId = entry.id;
            const dateTimeParts = getLocalDateAndTimeFromTimestamp(entry.created_at);
            document.getElementById('edit-food-name').value = entry.food_name || '';
            document.getElementById('edit-calories').value = entry.calories || '';
            document.getElementById('edit-quantity').value = entry.quantity_value || 1;
            document.getElementById('edit-meal').value = entry.meal || '';
            document.getElementById('edit-logged-date').value = entry.logged_date || dateTimeParts?.date || '';
            document.getElementById('edit-logged-time').value = dateTimeParts?.time || '';
            document.getElementById('edit-protein').value = entry.protein_g || '';
            document.getElementById('edit-carbs').value = entry.carbs_g || '';
            document.getElementById('edit-fat').value = entry.fat_g || '';
            document.getElementById('edit-modal').classList.add('active');
        }

        function closeEditModal() {
            document.getElementById('edit-modal').classList.remove('active');
            currentEditEntryId = null;
        }

        async function saveEdit() {
            if (!currentEditEntryId) return;

            const updateData = {};
            const foodName = document.getElementById('edit-food-name').value.trim();
            const calories = document.getElementById('edit-calories').value;
            const quantity = document.getElementById('edit-quantity').value;
            const meal = document.getElementById('edit-meal').value.trim();
            const loggedDate = document.getElementById('edit-logged-date').value;
            const loggedTime = document.getElementById('edit-logged-time').value;
            const protein = document.getElementById('edit-protein').value;
            const carbs = document.getElementById('edit-carbs').value;
            const fat = document.getElementById('edit-fat').value;

            const currentEntry = _entryMap[currentEditEntryId] || null;
            const effectiveDateForTime = loggedDate || currentEntry?.logged_date || '';

            if (foodName) updateData.food_name = foodName;
            if (calories) updateData.calories = parseInt(calories);
            if (quantity) updateData.quantity_value = parseFloat(quantity);
            if (meal) updateData.meal = meal;
            if (loggedDate) updateData.logged_date = loggedDate;

            if (loggedTime) {
                const createdAtIso = buildUtcIsoFromLocalDateTime(effectiveDateForTime, loggedTime);
                if (!createdAtIso) {
                    showStatus('Please enter a valid time', 'error');
                    return;
                }
                updateData.created_at = createdAtIso;
            }

            if (protein) updateData.protein_g = parseFloat(protein);
            if (carbs) updateData.carbs_g = parseFloat(carbs);
            if (fat) updateData.fat_g = parseFloat(fat);

            try {
                const response = await fetch(`${API_BASE}/log/${currentEditEntryId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(updateData)
                });

                if (response.ok) {
                    closeEditModal();
                    refreshVisibleData();
                    showStatus('Entry updated successfully', 'success');
                } else {
                    showStatus('Failed to update entry', 'error');
                }
            } catch (error) {
                showStatus('Error updating entry', 'error');
            }
        }

        // Close modal on background click
        document.getElementById('edit-modal').addEventListener('click', function(e) {
            if (e.target === this) {
                closeEditModal();
            }
        });

        document.getElementById('password-modal').addEventListener('click', function(e) {
            if (e.target === this) {
                closePasswordModal();
            }
        });

