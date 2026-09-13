/**
 * LLM-rotry Dashboard Application Logic
 */

(function () {
    'use strict';

    // Application State
    const state = {
        isStaticMode: false,
        liveKeys: [],
        staticKeys: JSON.parse(JSON.stringify(window.MOCK_KEYS || [])),
        stagedKeys: [],
        selectedIds: new Set(),
        searchQuery: '',
        filterKeyType: 'all',
        filterStatus: 'all'
    };

    // DOM Elements
    const elements = {
        modeSwitch: document.getElementById('modeSwitch'),
        modeBadge: document.getElementById('modeBadge'),
        modeText: document.getElementById('modeText'),
        btnRefresh: document.getElementById('btnRefresh'),
        btnOpenAddModal: document.getElementById('btnOpenAddModal'),
        btnOpenCleanupModal: document.getElementById('btnOpenCleanupModal'),
        keysGrid: document.getElementById('keysGrid'),
        searchInput: document.getElementById('searchInput'),
        filterKeyType: document.getElementById('filterKeyType'),
        filterStatus: document.getElementById('filterStatus'),
        bulkActions: document.getElementById('bulkActions'),
        selectedCount: document.getElementById('selectedCount'),
        btnBulkDelete: document.getElementById('btnBulkDelete'),
        
        // Stats
        statTotalKeys: document.getElementById('statTotalKeys'),
        statActiveRatio: document.getElementById('statActiveRatio'),
        statApiKeys: document.getElementById('statApiKeys'),
        statLlmKeys: document.getElementById('statLlmKeys'),
        statTotalRpm: document.getElementById('statTotalRpm'),

        // Staging
        stagingSection: document.getElementById('stagingSection'),
        stagedCountBadge: document.getElementById('stagedCountBadge'),
        finalizeCount: document.getElementById('finalizeCount'),
        stagedItemsList: document.getElementById('stagedItemsList'),
        btnClearStaging: document.getElementById('btnClearStaging'),
        btnFinalizeStaging: document.getElementById('btnFinalizeStaging'),

        // Add Modal
        addKeyModal: document.getElementById('addKeyModal'),
        addKeyForm: document.getElementById('addKeyForm'),
        closeAddModal: document.getElementById('closeAddModal'),
        btnCancelAdd: document.getElementById('btnCancelAdd'),
        btnStageKey: document.getElementById('btnStageKey'),
        addKeyType: document.getElementById('addKeyType'),
        tokenLimitsBox: document.getElementById('tokenLimitsBox'),
        tokenNotice: document.getElementById('tokenNotice'),

        // Edit Modal
        editKeyModal: document.getElementById('editKeyModal'),
        editKeyForm: document.getElementById('editKeyForm'),
        closeEditModal: document.getElementById('closeEditModal'),
        btnCancelEdit: document.getElementById('btnCancelEdit'),
        editTokenBox: document.getElementById('editTokenBox'),

        // Cleanup Modal
        cleanupModal: document.getElementById('cleanupModal'),
        closeCleanupModal: document.getElementById('closeCleanupModal'),
        btnCancelCleanup: document.getElementById('btnCancelCleanup'),
        btnConfirmCleanup: document.getElementById('btnConfirmCleanup'),

        toastContainer: document.getElementById('toastContainer')
    };

    // Initialize application
    function init() {
        // Check URL param or localStorage for static mode
        const urlParams = new URLSearchParams(window.location.search);
        const staticParam = urlParams.get('static');
        
        if (staticParam === 'true' || localStorage.getItem('llm_rotry_static') === 'true') {
            setMode(true);
        } else {
            setMode(false);
        }

        bindEvents();
        loadData();
    }

    // Toggle between Live and Static mode
    function setMode(isStatic) {
        state.isStaticMode = isStatic;
        elements.modeSwitch.checked = isStatic;
        localStorage.setItem('llm_rotry_static', isStatic ? 'true' : 'false');

        if (isStatic) {
            elements.modeBadge.className = 'mode-badge static';
            elements.modeText.textContent = 'Static / Dummy';
            showToast('Switched to Static / Dummy Mode', 'info');
        } else {
            elements.modeBadge.className = 'mode-badge live';
            elements.modeText.textContent = 'Live Backend';
            showToast('Switched to Live Backend Mode', 'info');
        }
        render();
    }

    // Event Bindings
    function bindEvents() {
        elements.modeSwitch.addEventListener('change', (e) => {
            setMode(e.target.checked);
            loadData();
        });

        elements.btnRefresh.addEventListener('click', () => {
            loadData();
            showToast('Data refreshed', 'info');
        });

        // Add Modal Open / Close
        elements.btnOpenAddModal.addEventListener('click', () => openModal(elements.addKeyModal));
        elements.closeAddModal.addEventListener('click', () => closeModal(elements.addKeyModal));
        elements.btnCancelAdd.addEventListener('click', () => closeModal(elements.addKeyModal));

        // Form Key Type Switch (dim token inputs for API Call)
        elements.addKeyType.addEventListener('change', (e) => {
            const isApi = e.target.value === 'api_call';
            if (isApi) {
                elements.tokenLimitsBox.classList.add('disabled-box');
                elements.tokenNotice.textContent = '⚡ Generic API keys only track request limits (RPM / RPD). Token limits (TPM / TPD) are disabled.';
            } else {
                elements.tokenLimitsBox.classList.remove('disabled-box');
                elements.tokenNotice.textContent = '🧠 Token limits (TPM / TPD) are tracked and enforced for LLM models.';
            }
        });

        // Add Key: Stage Key
        elements.btnStageKey.addEventListener('click', handleStageKey);

        // Add Key: Direct Submit
        elements.addKeyForm.addEventListener('submit', handleDirectSubmit);

        // Staging Queue Controls
        elements.btnClearStaging.addEventListener('click', () => {
            state.stagedKeys = [];
            renderStagingQueue();
            showToast('Staged queue cleared', 'info');
        });

        elements.btnFinalizeStaging.addEventListener('click', handleFinalizeStaging);

        // Edit Modal Open / Close
        elements.closeEditModal.addEventListener('click', () => closeModal(elements.editKeyModal));
        elements.btnCancelEdit.addEventListener('click', () => closeModal(elements.editKeyModal));
        elements.editKeyForm.addEventListener('submit', handleEditSubmit);

        // Cleanup Modal Open / Close
        elements.btnOpenCleanupModal.addEventListener('click', () => openModal(elements.cleanupModal));
        elements.closeCleanupModal.addEventListener('click', () => closeModal(elements.cleanupModal));
        elements.btnCancelCleanup.addEventListener('click', () => closeModal(elements.cleanupModal));
        elements.btnConfirmCleanup.addEventListener('click', handleCleanupAll);

        // Search & Filter
        elements.searchInput.addEventListener('input', (e) => {
            state.searchQuery = e.target.value.toLowerCase().trim();
            renderKeys();
        });

        elements.filterKeyType.addEventListener('change', (e) => {
            state.filterKeyType = e.target.value;
            renderKeys();
        });

        elements.filterStatus.addEventListener('change', (e) => {
            state.filterStatus = e.target.value;
            renderKeys();
        });

        // Bulk Delete
        elements.btnBulkDelete.addEventListener('click', handleBulkDelete);
    }

    // Modal Helpers
    function openModal(modal) {
        modal.classList.add('open');
    }
    function closeModal(modal) {
        modal.classList.remove('open');
    }

    // Load Data
    async function loadData() {
        if (state.isStaticMode) {
            render();
            return;
        }

        try {
            const res = await fetch('/keys');
            if (!res.ok) throw new Error(`HTTP error ${res.status}`);
            const data = await res.json();
            state.liveKeys = data;
            render();
        } catch (err) {
            console.error('Error fetching keys:', err);
            showToast(`Error connecting to backend: ${err.message}. Consider switching to Static Mode.`, 'error');
            state.liveKeys = [];
            render();
        }
    }

    // Active dataset
    function getKeys() {
        return state.isStaticMode ? state.staticKeys : state.liveKeys;
    }

    // Main Render function
    function render() {
        renderStats();
        renderStagingQueue();
        renderKeys();
        renderBulkBar();
    }

    // Render Stats
    function renderStats() {
        const keys = getKeys();
        const total = keys.length;
        const active = keys.filter(k => k.status === 'active').length;
        const apiCount = keys.filter(k => k.key_type === 'api_call').length;
        const llmCount = keys.filter(k => k.key_type === 'llm_call').length;

        let totalRpm = 0;
        keys.forEach(k => {
            const rpm = typeof k.rpm === 'object' && k.rpm !== null ? k.rpm?.rpm : k.rpm;
            if (rpm) {
                totalRpm += Number(rpm);
            }
        });

        elements.statTotalKeys.textContent = total;
        elements.statActiveRatio.textContent = `${active} of ${total} active in rotation`;
        elements.statApiKeys.textContent = apiCount;
        elements.statLlmKeys.textContent = llmCount;
        elements.statTotalRpm.textContent = totalRpm.toLocaleString();
    }

    // Render Staging Queue
    function renderStagingQueue() {
        const count = state.stagedKeys.length;
        if (count === 0) {
            elements.stagingSection.style.display = 'none';
            return;
        }

        elements.stagingSection.style.display = 'block';
        elements.stagedCountBadge.textContent = count;
        elements.finalizeCount.textContent = count;

        elements.stagedItemsList.innerHTML = state.stagedKeys.map((item, index) => `
            <div class="staged-item-chip">
                <span class="staged-item-type ${item.key_type === 'api_call' ? 'type-api' : 'type-llm'}">
                    ${item.key_type === 'api_call' ? 'API' : 'LLM'}
                </span>
                <strong>${escapeHtml(item.provider)}</strong>
                <span style="color: var(--text-muted);">(${escapeHtml(item.account_name)})</span>
                <button class="staged-remove-btn" onclick="window.llmRotry.removeStaged(${index})" title="Remove staged key">
                    &times;
                </button>
            </div>
        `).join('');
    }

    // Filter Keys
    function getFilteredKeys() {
        const keys = getKeys();
        return keys.filter(key => {
            // Search query matches provider, account, url, or id
            if (state.searchQuery) {
                const matchProvider = (key.provider || '').toLowerCase().includes(state.searchQuery);
                const matchAccount = (key.account_name || '').toLowerCase().includes(state.searchQuery);
                const matchUrl = (key.api_url || '').toLowerCase().includes(state.searchQuery);
                const matchId = (key.id || '').toLowerCase().includes(state.searchQuery);
                if (!matchProvider && !matchAccount && !matchUrl && !matchId) return false;
            }

            // Key Type filter
            if (state.filterKeyType !== 'all' && key.key_type !== state.filterKeyType) {
                return false;
            }

            // Status filter
            if (state.filterStatus !== 'all' && key.status !== state.filterStatus) {
                return false;
            }

            return true;
        });
    }

    // Render Keys Grid
    function renderKeys() {
        const filtered = getFilteredKeys();

        if (filtered.length === 0) {
            elements.keysGrid.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">📭</div>
                    <h3>No keys found</h3>
                    <p style="margin-top: 0.5rem; font-size: 0.85rem;">
                        ${getKeys().length === 0 
                            ? 'Get started by adding your first API or LLM key above.' 
                            : 'No keys match your active search or filter criteria.'}
                    </p>
                </div>
            `;
            return;
        }

        elements.keysGrid.innerHTML = filtered.map(key => {
            const isApi = key.key_type === 'api_call';
            const isChecked = state.selectedIds.has(key.id);

            // Rate Limits Display Helper
            const formatLimit = (v, unit) => {
                const num = (typeof v === 'object' && v !== null) ? (v.rpm ?? v.rpd ?? v.tpm ?? v.tpd) : v;
                return (num != null && num !== '') ? `${Number(num).toLocaleString()} ${unit}` : 'Unlimited';
            };

            const rpmVal = formatLimit(key.rpm, '/min');
            const rpdVal = formatLimit(key.rpd, '/day');
            const rpmonVal = formatLimit(key.rpmon, '/mo');
            const tpmVal = formatLimit(key.tpm, '/min');
            const tpdVal = formatLimit(key.tpd, '/day');
            const tpmonVal = formatLimit(key.tpmon, '/mo');

            return `
            <div class="key-card" data-id="${key.id}">
                <div class="key-card-header">
                    <div class="key-title-group">
                        <input type="checkbox" class="key-select-check" 
                            ${isChecked ? 'checked' : ''} 
                            onchange="window.llmRotry.toggleSelect('${key.id}')"
                        >
                        <div class="provider-avatar">
                            ${(key.provider || 'K').slice(0, 2).toUpperCase()}
                        </div>
                        <div>
                            <div class="provider-name">${escapeHtml(key.provider)}</div>
                            <div class="account-badge">${escapeHtml(key.account_name)}</div>
                        </div>
                    </div>

                    <div class="key-badges">
                        <span class="staged-item-type ${isApi ? 'type-api' : 'type-llm'}">
                            ${isApi ? 'API Key' : 'LLM Key'}
                        </span>
                        <span class="status-badge status-${key.status}">
                            ${key.status}
                        </span>
                    </div>
                </div>

                <!-- API URL & Masked Key Details -->
                <div class="key-details">
                    <div class="key-detail-row">
                        <span class="detail-label">Endpoint:</span>
                        <span class="detail-value" title="${escapeHtml(key.api_url)}">${escapeHtml(key.api_url)}</span>
                    </div>
                    <div class="key-detail-row">
                        <span class="detail-label">API Key:</span>
                        <span class="detail-value" title="${escapeHtml(key.api_key)}">
                            ${maskKey(key.api_key)}
                        </span>
                        <button class="copy-btn" onclick="window.llmRotry.copyText('${escapeHtml(key.api_key)}')">
                            📋 Copy
                        </button>
                    </div>
                </div>

                <!-- Rate Limits Block -->
                <div class="rate-limits-container">
                    <div class="limits-title">
                        <span>Configured Limits</span>
                        <span>${isApi ? 'Request-based only' : 'Tokens + Requests'}</span>
                    </div>
                    <div class="limits-pill-group">
                        <div class="limit-pill">
                            <span class="limit-pill-name">RPM (Req/Min)</span>
                            <span class="limit-pill-val">${rpmVal}</span>
                        </div>
                        <div class="limit-pill">
                            <span class="limit-pill-name">RPD (Req/Day)</span>
                            <span class="limit-pill-val">${rpdVal}</span>
                        </div>
                        <div class="limit-pill">
                            <span class="limit-pill-name">RPMon (Req/Month)</span>
                            <span class="limit-pill-val">${rpmonVal}</span>
                        </div>
                        ${!isApi ? `
                        <div class="limit-pill">
                            <span class="limit-pill-name">TPM (Tok/Min)</span>
                            <span class="limit-pill-val">${tpmVal}</span>
                        </div>
                        <div class="limit-pill">
                            <span class="limit-pill-name">TPD (Tok/Day)</span>
                            <span class="limit-pill-val">${tpdVal}</span>
                        </div>
                        <div class="limit-pill">
                            <span class="limit-pill-name">TPMon (Tok/Month)</span>
                            <span class="limit-pill-val">${tpmonVal}</span>
                        </div>
                        ` : ''}
                    </div>
                </div>

                <!-- Card Footer Actions -->
                <div class="key-card-footer">
                    <button class="btn btn-sm ${key.status === 'active' ? 'btn-secondary' : 'btn-success'}" 
                        onclick="window.llmRotry.toggleKeyStatus('${key.id}', '${key.status}')">
                        ${key.status === 'active' ? 'Deactivate' : 'Activate'}
                    </button>
                    <div class="card-actions-group">
                        <button class="btn btn-secondary btn-sm" onclick="window.llmRotry.openEditModal('${key.id}')">
                            ✏️ Edit
                        </button>
                        <button class="btn btn-danger btn-sm" onclick="window.llmRotry.deleteSingleKey('${key.id}')">
                            🗑️ Delete
                        </button>
                    </div>
                </div>
            </div>
            `;
        }).join('');
    }

    // Render Bulk Bar
    function renderBulkBar() {
        const count = state.selectedIds.size;
        if (count > 0) {
            elements.bulkActions.style.display = 'flex';
            elements.selectedCount.textContent = count;
        } else {
            elements.bulkActions.style.display = 'none';
        }
    }

    // Form extraction helper
    function getFormData() {
        const key_type = elements.addKeyType.value;
        const provider = document.getElementById('addProvider').value.trim();
        const account_name = document.getElementById('addAccountName').value.trim();
        const status = document.getElementById('addStatus').value;
        const api_url = document.getElementById('addApiUrl').value.trim();
        const api_key = document.getElementById('addApiKey').value.trim();

        if (!provider || !account_name || !api_url || !api_key) {
            showToast('Please fill out all required fields (*)', 'error');
            return null;
        }

        const data = {
            id: 'k-' + Math.random().toString(36).substring(2, 10),
            key_type,
            provider,
            account_name,
            status,
            api_url,
            api_key,
            reg_date: new Date().toISOString()
        };

        // RPM
        const rpm = document.getElementById('addRpm').value;
        if (rpm) data.rpm = parseInt(rpm, 10);

        // RPD
        const rpd = document.getElementById('addRpd').value;
        if (rpd) data.rpd = parseInt(rpd, 10);

        // RPMon
        const rpmon = document.getElementById('addRpmon').value;
        if (rpmon) data.rpmon = parseInt(rpmon, 10);

        // If LLM call, include TPM, TPD and TPMon
        if (key_type === 'llm_call') {
            const tpm = document.getElementById('addTpm').value;
            if (tpm) data.tpm = parseInt(tpm, 10);

            const tpd = document.getElementById('addTpd').value;
            if (tpd) data.tpd = parseInt(tpd, 10);

            const tpmon = document.getElementById('addTpmon').value;
            if (tpmon) data.tpmon = parseInt(tpmon, 10);
        }

        return data;
    }

    // Handle Staging a key
    function handleStageKey() {
        const data = getFormData();
        if (!data) return;

        state.stagedKeys.push(data);
        elements.addKeyForm.reset();
        elements.addKeyType.dispatchEvent(new Event('change'));
        closeModal(elements.addKeyModal);
        renderStagingQueue();
        showToast(`Key queued in staging. Total staged: ${state.stagedKeys.length}`, 'success');
    }

    // Handle Direct Submission
    async function handleDirectSubmit(e) {
        e.preventDefault();
        const data = getFormData();
        if (!data) return;

        if (state.isStaticMode) {
            state.staticKeys.unshift(data);
            elements.addKeyForm.reset();
            closeModal(elements.addKeyModal);
            render();
            showToast(`Key for ${data.provider} registered (Static Mode)!`, 'success');
            return;
        }

        try {
            const res = await fetch('/keys/new_reg', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail ? JSON.stringify(err.detail) : `HTTP ${res.status}`);
            }
            elements.addKeyForm.reset();
            closeModal(elements.addKeyModal);
            await loadData();
            showToast(`Key for ${data.provider} registered successfully!`, 'success');
        } catch (err) {
            console.error('Error creating key:', err);
            showToast(`Registration failed: ${err.message}`, 'error');
        }
    }

    // Finalize all staged keys
    async function handleFinalizeStaging() {
        if (state.stagedKeys.length === 0) return;

        const count = state.stagedKeys.length;

        if (state.isStaticMode) {
            state.staticKeys.unshift(...state.stagedKeys);
            state.stagedKeys = [];
            render();
            showToast(`Successfully finalized and registered ${count} keys (Static Mode)!`, 'success');
            return;
        }

        try {
            const res = await fetch('/keys/new_reg', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(state.stagedKeys)
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail ? JSON.stringify(err.detail) : `HTTP ${res.status}`);
            }
            state.stagedKeys = [];
            await loadData();
            showToast(`Successfully registered all ${count} staged keys!`, 'success');
        } catch (err) {
            console.error('Error finalizing keys:', err);
            showToast(`Failed to finalize keys: ${err.message}`, 'error');
        }
    }

    // Open Edit Modal
    function openEditModal(keyId) {
        const keys = getKeys();
        const key = keys.find(k => k.id === keyId);
        if (!key) return;

        document.getElementById('editKeyId').value = key.id;
        document.getElementById('editKeyType').value = key.key_type;
        document.getElementById('editProvider').value = key.provider || '';
        document.getElementById('editAccountName').value = key.account_name || '';
        document.getElementById('editStatus').value = key.status || 'active';
        document.getElementById('editApiUrl').value = key.api_url || '';
        document.getElementById('editApiKey').value = key.api_key || '';

        const getRawLimit = (v) => {
            if (v == null) return '';
            if (typeof v === 'object') return (v.rpm ?? v.rpd ?? v.tpm ?? v.tpd ?? '');
            return v;
        };

        // RPM, RPD, RPMon
        document.getElementById('editRpm').value = getRawLimit(key.rpm);
        document.getElementById('editRpd').value = getRawLimit(key.rpd);
        document.getElementById('editRpmon').value = getRawLimit(key.rpmon);

        // Token limits
        const isApi = key.key_type === 'api_call';
        if (isApi) {
            elements.editTokenBox.style.display = 'none';
        } else {
            elements.editTokenBox.style.display = 'block';
            document.getElementById('editTpm').value = getRawLimit(key.tpm);
            document.getElementById('editTpd').value = getRawLimit(key.tpd);
            document.getElementById('editTpmon').value = getRawLimit(key.tpmon);
        }

        openModal(elements.editKeyModal);
    }

    // Handle Edit Submit
    async function handleEditSubmit(e) {
        e.preventDefault();
        const keyId = document.getElementById('editKeyId').value;
        const keyType = document.getElementById('editKeyType').value;

        const updates = {
            provider: document.getElementById('editProvider').value.trim(),
            account_name: document.getElementById('editAccountName').value.trim(),
            status: document.getElementById('editStatus').value,
            api_url: document.getElementById('editApiUrl').value.trim(),
            api_key: document.getElementById('editApiKey').value.trim()
        };

        const rpm = document.getElementById('editRpm').value;
        if (rpm !== '') updates.rpm = parseInt(rpm, 10);

        const rpd = document.getElementById('editRpd').value;
        if (rpd !== '') updates.rpd = parseInt(rpd, 10);

        const rpmon = document.getElementById('editRpmon').value;
        if (rpmon !== '') updates.rpmon = parseInt(rpmon, 10);

        if (keyType === 'llm_call') {
            const tpm = document.getElementById('editTpm').value;
            if (tpm !== '') updates.tpm = parseInt(tpm, 10);

            const tpd = document.getElementById('editTpd').value;
            if (tpd !== '') updates.tpd = parseInt(tpd, 10);

            const tpmon = document.getElementById('editTpmon').value;
            if (tpmon !== '') updates.tpmon = parseInt(tpmon, 10);
        }

        if (state.isStaticMode) {
            const idx = state.staticKeys.findIndex(k => k.id === keyId);
            if (idx !== -1) {
                state.staticKeys[idx] = { ...state.staticKeys[idx], ...updates };
                closeModal(elements.editKeyModal);
                render();
                showToast('Key updated (Static Mode)', 'success');
            }
            return;
        }

        try {
            const res = await fetch(`/keys/${keyId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updates)
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail ? JSON.stringify(err.detail) : `HTTP ${res.status}`);
            }
            closeModal(elements.editKeyModal);
            await loadData();
            showToast('Key updated successfully!', 'success');
        } catch (err) {
            console.error('Error updating key:', err);
            showToast(`Update failed: ${err.message}`, 'error');
        }
    }

    // Toggle Key Status (Active / Inactive)
    async function toggleKeyStatus(keyId, currentStatus) {
        const newStatus = currentStatus === 'active' ? 'inactive' : 'active';
        const endpoint = newStatus === 'active' ? 'activate' : 'deactivate';

        if (state.isStaticMode) {
            const key = state.staticKeys.find(k => k.id === keyId);
            if (key) {
                key.status = newStatus;
                render();
                showToast(`Key status changed to ${newStatus} (Static Mode)`, 'info');
            }
            return;
        }

        try {
            const res = await fetch(`/keys/${keyId}/${endpoint}`, { method: 'POST' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            await loadData();
            showToast(`Key status updated to ${newStatus}`, 'info');
        } catch (err) {
            console.error('Error updating status:', err);
            showToast(`Failed to update status: ${err.message}`, 'error');
        }
    }

    // Delete Single Key
    async function deleteSingleKey(keyId) {
        if (!confirm('Are you sure you want to delete this key?')) return;

        if (state.isStaticMode) {
            state.staticKeys = state.staticKeys.filter(k => k.id !== keyId);
            state.selectedIds.delete(keyId);
            render();
            showToast('Key deleted (Static Mode)', 'info');
            return;
        }

        try {
            const res = await fetch(`/keys/${keyId}`, { method: 'DELETE' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            state.selectedIds.delete(keyId);
            await loadData();
            showToast('Key deleted', 'info');
        } catch (err) {
            console.error('Error deleting key:', err);
            showToast(`Delete failed: ${err.message}`, 'error');
        }
    }

    // Toggle Checkbox Selection
    function toggleSelect(keyId) {
        if (state.selectedIds.has(keyId)) {
            state.selectedIds.delete(keyId);
        } else {
            state.selectedIds.add(keyId);
        }
        renderBulkBar();
    }

    // Bulk Delete
    async function handleBulkDelete() {
        const ids = Array.from(state.selectedIds);
        if (ids.length === 0) return;
        if (!confirm(`Are you sure you want to delete ${ids.length} selected key(s)?`)) return;

        if (state.isStaticMode) {
            state.staticKeys = state.staticKeys.filter(k => !state.selectedIds.has(k.id));
            state.selectedIds.clear();
            render();
            showToast(`Deleted ${ids.length} keys (Static Mode)`, 'info');
            return;
        }

        try {
            const res = await fetch('/keys/bulk-delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ids })
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const result = await res.json();
            state.selectedIds.clear();
            await loadData();
            showToast(`Deleted ${result.deleted} keys successfully`, 'info');
        } catch (err) {
            console.error('Error bulk deleting:', err);
            showToast(`Bulk delete failed: ${err.message}`, 'error');
        }
    }

    // Cleanup All Keys
    async function handleCleanupAll() {
        if (state.isStaticMode) {
            state.staticKeys = [];
            state.selectedIds.clear();
            closeModal(elements.cleanupModal);
            render();
            showToast('All static keys cleared (Static Mode)', 'info');
            return;
        }

        try {
            const res = await fetch('/keys?confirm=true', { method: 'DELETE' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const result = await res.json();
            state.selectedIds.clear();
            closeModal(elements.cleanupModal);
            await loadData();
            showToast(`Cleaned up all keys (${result.deleted} removed)`, 'info');
        } catch (err) {
            console.error('Error cleaning up keys:', err);
            showToast(`Cleanup failed: ${err.message}`, 'error');
        }
    }

    // Toast notifications
    function showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        let icon = 'ℹ️';
        if (type === 'success') icon = '✅';
        if (type === 'error') icon = '❌';

        toast.innerHTML = `<span>${icon}</span><span>${escapeHtml(message)}</span>`;
        elements.toastContainer.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(10px)';
            toast.style.transition = 'all 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 3500);
    }

    // String Utilities
    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function maskKey(key) {
        if (!key) return '';
        if (key.length <= 10) return '••••••••';
        return key.slice(0, 7) + '••••••••' + key.slice(-4);
    }

    function copyText(text) {
        if (navigator.clipboard) {
            navigator.clipboard.writeText(text).then(() => {
                showToast('API Key copied to clipboard!', 'success');
            }).catch(() => {
                fallbackCopy(text);
            });
        } else {
            fallbackCopy(text);
        }
    }

    function fallbackCopy(text) {
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        showToast('API Key copied to clipboard!', 'success');
    }

    // Expose functions for inline HTML event handlers
    window.llmRotry = {
        removeStaged: (index) => {
            state.stagedKeys.splice(index, 1);
            renderStagingQueue();
        },
        toggleSelect,
        toggleKeyStatus,
        openEditModal,
        deleteSingleKey,
        copyText
    };

    // Run on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
