// Get the API base URL (works for both localhost and network access)
        const API_BASE = window.location.origin;
        let selectedSummaryDate = null;

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
            if (tabName === 'today') {
                loadTodayEntries();
            } else if (tabName === 'summary') {
                loadSummary();
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
            const unit = (entry.quantity_unit || '').trim();
            return `Qty: ${formatNutrient(quantity)}${unit ? ` ${unit}` : ''}`;
        }

        function initializeSummaryDateRange() {
            const endInput = document.getElementById('summary-end');
            const startInput = document.getElementById('summary-start');
            const today = new Date();
            const weekAgo = new Date();
            weekAgo.setDate(today.getDate() - 6);

            endInput.value = formatIsoDate(today);
            startInput.value = formatIsoDate(weekAgo);
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
            const mealClass = entry.meal ? entry.meal.toLowerCase() : '';
            const mealBadge = entry.meal ? `<span class="meal-badge ${mealClass}">${entry.meal}</span>` : '';
            const calories = entry.calories ? `<span class="calories">${entry.calories} cal</span>` : '';
            const quantityLabel = formatQuantityLabel(entry);
            const quantity = Number(entry.quantity_value) || 1;
            const quantityMarkup = quantityLabel ? `<span class="quantity-label">${quantityLabel}</span>` : '';
            const quantityControls = `<span class="quantity-controls"><button class="qty-btn" onclick="adjustQuantity(${entry.id}, -1, ${quantity}); event.stopPropagation();">-</button><button class="qty-btn" onclick="adjustQuantity(${entry.id}, 1, ${quantity}); event.stopPropagation();">+</button></span>`;
            const confidence = entry.confidence_level ? `<span class="confidence ${entry.confidence_level}">${entry.confidence_level}</span>` : '';
            const source = entry.source ? `<span class="source">${entry.source}</span>` : '';
            const entryTime = formatEntryTime(entry.created_at);
            const timeLine = entryTime ? `<div class="entry-time">${entryTime}</div>` : '';
            const macros = entry.protein_g || entry.carbs_g || entry.fat_g ?
                `<div class="macros">Macros: Protein ${formatNutrient(entry.protein_g)}g | Carbs ${formatNutrient(entry.carbs_g)}g | Fat ${formatNutrient(entry.fat_g)}g</div>` : '';
            const assumptions = entry.assumptions && entry.assumptions.length > 0 ?
                `<div class="assumptions-toggle" onclick="toggleAssumptions(this)">Why this estimate? ▼</div>
                 <div class="assumptions-panel" style="display: none;">
                     <ul>${entry.assumptions.map(a => `<li>${a}</li>`).join('')}</ul>
                 </div>` : '';

            return `
                <div class="food-item">
                    <div class="food-main">
                        <div class="food-details" onclick="toggleEntryTrace(${entry.id})">
                            <div class="food-name">
                                ${entry.food_name}
                                ${mealBadge}
                                ${confidence}
                                ${source}
                            </div>
                            <div class="food-meta">
                                ${timeLine}
                                ${calories}
                                ${quantityMarkup}
                                ${macros}
                                ${assumptions}
                            </div>
                            <div class="trace-toggle" id="trace-toggle-${entry.id}">Details ▼</div>
                        </div>
                        <div class="food-item-info">
                            ${quantityControls}
                            <button class="fav-btn" onclick="saveEntryAsFavorite(${entry.id}); event.stopPropagation();" title="Save as favorite">&#9733;</button>
                            <button class="edit-btn" onclick="openEditModal(${entry.id})">Edit</button>
                            <button class="delete-btn" onclick="deleteEntry(${entry.id})">Delete</button>
                        </div>
                    </div>
                </div>
                <div id="trace-${entry.id}" class="trace-panel"></div>
            `;
        }

        function renderTodayEntries() {
            const container = document.getElementById('today-entries');
            const totalSection = document.getElementById('today-total');

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
                            <p>No entries yet today</p>
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
                            <p>No ${_activeMealFilter} entries today</p>
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
                    document.getElementById('total-calories').textContent = filteredCals;
                    totalSection.style.display = 'block';
                } else {
                    totalSection.style.display = 'none';
                }
                return;
            }

            if (_todayTotalCalories > 0) {
                document.getElementById('total-calories').textContent = _todayTotalCalories;
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
                            <button class="fav-log-btn" onclick="logFavorite(${fav.id}, '${fav.name.replace(/'/g, "\\'")}')">Log</button>
                            <button class="fav-del-btn" onclick="deleteFavorite(${fav.id}, event)">✕</button>
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
            // Find entry in loaded today entries
            const entry = _todayEntries.find(e => e.id === entryId);
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
            const container = document.getElementById('today-entries');
            container.innerHTML = '<div class="empty-state"><p>Loading...</p></div>';

            try {
                const response = await fetch(`${API_BASE}/log/today`);
                const data = await response.json();

                _todayEntries = data.entries || [];
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
        let _weeklyStartDate = null;

        function _getMondayOf(dateStr) {
            const d = new Date(dateStr + 'T12:00:00');
            const day = d.getDay(); // 0=Sun, 1=Mon...
            const diff = day === 0 ? -6 : 1 - day;
            d.setDate(d.getDate() + diff);
            return formatIsoDate(d);
        }

        function navigateWeek(direction) {
            if (!_weeklyStartDate) return;
            const d = new Date(_weeklyStartDate + 'T12:00:00');
            d.setDate(d.getDate() + direction * 7);
            _weeklyStartDate = formatIsoDate(d);
            loadWeekly(_weeklyStartDate);
        }

        async function loadWeekly(startDate) {
            const container = document.getElementById('weekly-content');
            const rangeLabel = document.getElementById('weekly-range-label');
            container.innerHTML = '<div class="empty-state"><p>Loading...</p></div>';

            if (!startDate) {
                // Default to current week Monday
                const today = new Date();
                startDate = _getMondayOf(formatIsoDate(today));
            }
            _weeklyStartDate = startDate;

            try {
                const response = await fetch(`${API_BASE}/log/weekly?start_date=${encodeURIComponent(startDate)}`);
                const data = await response.json();

                // Update range label
                const startLabel = formatDate(data.start_date);
                const endLabel = formatDate(data.end_date);
                rangeLabel.textContent = `${startLabel} – ${endLabel}`;

                // Compute max calories for chart scaling
                const calValues = data.days.map(d => d.total_calories || 0);
                const maxCal = Math.max(...calValues, 1);
                const todayStr = formatIsoDate(new Date());

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

                // --- Per-day table ---
                let tableHtml = `
                    <table class="weekly-stats-table">
                        <thead><tr>
                            <th>Date</th><th>Calories</th><th>Protein</th><th>Carbs</th><th>Fat</th><th>Items</th>
                        </tr></thead><tbody>`;
                data.days.forEach(day => {
                    const isToday = day.date === todayStr;
                    const rowClass = isToday ? ' class="today-row"' : '';
                    const cal = day.total_calories != null ? day.total_calories : '—';
                    const prot = day.total_protein_g != null ? `${formatNutrient(day.total_protein_g)}g` : '—';
                    const carb = day.total_carbs_g != null ? `${formatNutrient(day.total_carbs_g)}g` : '—';
                    const fat = day.total_fat_g != null ? `${formatNutrient(day.total_fat_g)}g` : '—';
                    const count = day.entry_count || 0;
                    const calDisplay = cal !== '—' ? `${cal}` : '—';
                    tableHtml += `<tr${rowClass}>
                        <td>${formatDate(day.date)}</td>
                        <td class="cal-cell">${calDisplay}</td>
                        <td>${prot}</td><td>${carb}</td><td>${fat}</td>
                        <td>${count > 0 ? count : '—'}</td>
                    </tr>`;
                });
                tableHtml += '</tbody></table>';

                // --- Totals/averages grid ---
                const t = data.totals;
                const a = data.averages;
                const n = data.active_days;
                const avgNote = n > 0 ? `avg over ${n} day${n !== 1 ? 's' : ''}` : 'no data';

                let totalsHtml = `<div class="weekly-totals-grid">
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

                // --- Meal frequency ---
                const mealFreq = data.meal_frequency || {};
                const MEAL_ORDER = ['breakfast', 'lunch', 'dinner', 'snack'];
                const freqKeys = [...MEAL_ORDER.filter(m => mealFreq[m]), ...Object.keys(mealFreq).filter(m => !MEAL_ORDER.includes(m))];
                let mealHtml = '';
                if (freqKeys.length > 0) {
                    mealHtml = '<div class="meal-freq-row">' + freqKeys.map(m =>
                        `<div class="meal-freq-chip"><span class="meal-badge ${m}">${m}</span><span class="chip-count">${mealFreq[m]}x</span></div>`
                    ).join('') + '</div>';
                }

                container.innerHTML = chartHtml + tableHtml + totalsHtml + mealHtml;

            } catch (error) {
                container.innerHTML = `<div class="empty-state"><p>Error loading weekly summary</p></div>`;
            }
        }

        // Load 7-day summary
        async function loadSummary() {
            const container = document.getElementById('summary-content');
            const startInput = document.getElementById('summary-start');
            const endInput = document.getElementById('summary-end');
            
            container.innerHTML = '<div class="empty-state"><p>Loading...</p></div>';

            try {
                let query = '';
                if (startInput.value && endInput.value) {
                    query = `?start_date=${encodeURIComponent(startInput.value)}&end_date=${encodeURIComponent(endInput.value)}`;
                }

                const response = await fetch(`${API_BASE}/log/summary${query}`);
                const data = await response.json();

                if (!data.summary || data.summary.length === 0) {
                    container.innerHTML = `
                        <div class="empty-state">
                            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path>
                            </svg>
                            <p>No data available</p>
                        </div>
                    `;
                    return;
                }

                let html = '';
                data.summary.forEach(day => {
                    const calories = day.total_calories || '—';
                    const caloriesText = calories !== '—' ? `${calories} cal` : 'No data';
                    const hasMacros = day.total_protein_g || day.total_carbs_g || day.total_fat_g;
                    const macroLine = hasMacros
                        ? `<div class="summary-macros">P ${formatNutrient(day.total_protein_g)}g · C ${formatNutrient(day.total_carbs_g)}g · F ${formatNutrient(day.total_fat_g)}g</div>`
                        : '';

                    html += `
                        <div class="summary-day" onclick="loadDateDetails('${day.date}')">
                            <div class="summary-date">${formatDate(day.date)}</div>
                            <div class="summary-stats">
                                <div class="summary-calories">${caloriesText}</div>
                                ${macroLine}
                                <div class="summary-count">${day.entry_count} entries</div>
                            </div>
                        </div>
                    `;
                });

                container.innerHTML = html;

            } catch (error) {
                container.innerHTML = `<div class="empty-state"><p>Error loading summary</p></div>`;
            }
        }

        async function loadDateDetails(dateStr) {
            const details = document.getElementById('summary-date-details');
            selectedSummaryDate = dateStr;
            details.style.display = 'block';
            details.innerHTML = '<div class="empty-state"><p>Loading date details...</p></div>';

            try {
                const response = await fetch(`${API_BASE}/log/date/${encodeURIComponent(dateStr)}`);
                const data = await response.json();

                if (!data.entries || data.entries.length === 0) {
                    details.innerHTML = `<div class="empty-state"><p>No entries found for ${formatDate(dateStr)}</p></div>`;
                    return;
                }

                const rows = data.entries.map(entry => {
                    const calories = entry.calories ? `${entry.calories} cal` : '—';
                    const quantityLabel = formatQuantityLabel(entry);
                    const quantity = Number(entry.quantity_value) || 1;
                    const quantityMarkup = quantityLabel ? `<div class="quantity-label">${quantityLabel}</div>` : '';
                    const entryTime = formatEntryTime(entry.created_at);
                    const foodLabel = entryTime ? `${entry.food_name} · ${entryTime}` : entry.food_name;
                    return `
                        <div class="detail-item">
                            <div>
                                <div class="detail-food">${foodLabel}</div>
                                ${quantityMarkup}
                            </div>
                            <div class="detail-actions">
                                <div class="detail-calories">${calories}</div>
                                <span class="quantity-controls"><button class="qty-btn" onclick="adjustQuantity(${entry.id}, -1, ${quantity}); event.stopPropagation();">-</button><button class="qty-btn" onclick="adjustQuantity(${entry.id}, 1, ${quantity}); event.stopPropagation();">+</button></span>
                                <button class="add-today-btn" onclick="addToToday(${entry.id}); event.stopPropagation();">Add to Today</button>
                                <button class="edit-btn" onclick="openEditModal(${entry.id})">Edit</button>
                                <button class="delete-btn" onclick="deleteEntry(${entry.id})">Delete</button>
                            </div>
                        </div>
                    `;
                }).join('');

                details.innerHTML = `
                    <h3 class="section-title">${formatDate(dateStr)} Details</h3>
                    ${rows}
                    <div class="total-section" style="margin-top: 12px;">
                        <span class="total-label">Total Calories</span>
                        <span class="total-value">${data.total_calories}</span>
                    </div>
                `;
            } catch (error) {
                details.innerHTML = '<div class="empty-state"><p>Error loading date details</p></div>';
            }
        }

        function applySummaryRange() {
            const details = document.getElementById('summary-date-details');
            details.style.display = 'none';
            loadSummary();
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

                // Reload today's entries
                loadTodayEntries();
                loadSummary();
                if (selectedSummaryDate) {
                    loadDateDetails(selectedSummaryDate);
                }

            } catch (error) {
                alert(`Error: ${error.message}`);
            }
        }

        async function adjustQuantity(entryId, delta, currentQuantity) {
            const nextQuantity = Math.max(1, Math.round((Number(currentQuantity) + delta) * 100) / 100);
            try {
                const response = await fetch(`${API_BASE}/log/${entryId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ quantity_value: nextQuantity })
                });

                if (!response.ok) {
                    throw new Error('Failed to update quantity');
                }

                loadTodayEntries();
                loadSummary();
                if (selectedSummaryDate) {
                    loadDateDetails(selectedSummaryDate);
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

                loadTodayEntries();
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

        initializeSummaryDateRange();
        loadFavorites();

let currentEditEntryId = null;

        function openEditModal(entryId) {
            currentEditEntryId = entryId;
            
            // Fetch current entry data
            fetch(`${API_BASE}/log/today`)
                .then(r => r.json())
                .then(data => {
                    const entry = data.entries.find(e => e.id === entryId);
                    if (entry) {
                        document.getElementById('edit-food-name').value = entry.food_name || '';
                        document.getElementById('edit-calories').value = entry.calories || '';
                        document.getElementById('edit-quantity').value = entry.quantity_value || 1;
                        document.getElementById('edit-meal').value = entry.meal || '';
                        document.getElementById('edit-protein').value = entry.protein_g || '';
                        document.getElementById('edit-carbs').value = entry.carbs_g || '';
                        document.getElementById('edit-fat').value = entry.fat_g || '';
                        document.getElementById('edit-modal').classList.add('active');
                    }
                });
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
            const protein = document.getElementById('edit-protein').value;
            const carbs = document.getElementById('edit-carbs').value;
            const fat = document.getElementById('edit-fat').value;

            if (foodName) updateData.food_name = foodName;
            if (calories) updateData.calories = parseInt(calories);
            if (quantity) updateData.quantity_value = parseFloat(quantity);
            if (meal) updateData.meal = meal;
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
                    loadTodayEntries();
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

