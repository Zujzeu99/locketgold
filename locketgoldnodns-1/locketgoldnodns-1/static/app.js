// ==================== STATE ====================
const state = {
    step: 1,
    master: null,
    customer: null,
    isLoading: false,
};

// ==================== DOM HELPERS ====================
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function show(el) {
    if (typeof el === 'string') el = $(el);
    if (el) { el.classList.remove('hidden'); el.classList.add('fade-in'); }
}

function hide(el) {
    if (typeof el === 'string') el = $(el);
    if (el) { el.classList.add('hidden'); el.classList.remove('fade-in'); }
}

// ==================== STEP MANAGEMENT ====================
function setStep(step) {
    state.step = step;
    // Update step dots
    $$('.step-dot').forEach((dot, i) => {
        const num = i + 1;
        dot.classList.remove('active', 'completed');
        if (num < step) dot.classList.add('completed');
        else if (num === step) dot.classList.add('active');
    });
    // Update step lines
    $$('.step-line').forEach((line, i) => {
        const num = i + 1;
        line.classList.remove('active', 'completed');
        if (num < step) line.classList.add('completed');
        else if (num === step) line.classList.add('active');
    });
    // Show/hide sections
    if (step >= 1) show('#section-master');
    if (step >= 2) show('#section-customer');
    else hide('#section-customer');
    if (step >= 3) show('#section-unlock');
    else hide('#section-unlock');
}

// ==================== LOADING OVERLAY ====================
function showLoading(text) {
    state.isLoading = true;
    const overlay = $('#loading-overlay');
    const loadingText = $('#loading-text');
    if (loadingText) loadingText.textContent = text || 'Đang xử lý...';
    overlay.classList.add('active');
}

function hideLoading() {
    state.isLoading = false;
    $('#loading-overlay').classList.remove('active');
}

// ==================== LOG ====================
function addLog(panel, message, type = '') {
    const logEl = $(panel);
    if (!logEl) return;
    const now = new Date();
    const time = now.toLocaleTimeString('vi-VN');
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    entry.innerHTML = `<span class="timestamp">[${time}]</span> ${message}`;
    logEl.appendChild(entry);
    logEl.scrollTop = logEl.scrollHeight;
}

// ==================== API CALLS ====================
async function apiCall(endpoint, data = null, method = 'POST') {
    const options = {
        method,
        headers: { 'Content-Type': 'application/json' },
    };
    if (data) options.body = JSON.stringify(data);

    const resp = await fetch(`/api/${endpoint}`, options);
    const json = await resp.json();
    return { ok: resp.ok, status: resp.status, data: json };
}

// ==================== CHECK MASTER ====================
async function checkMaster() {
    const input = $('#master-input');
    const username = input.value.trim();
    if (!username) {
        showStatusPanel('#master-status', 'error', 'Lỗi', 'Vui lòng nhập username Master');
        return;
    }

    const btn = $('#btn-check-master');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner spinner-dark"></span> Đang kiểm tra...';
    clearStatusPanel('#master-status');

    try {
        const { ok, data } = await apiCall('check-master', { username });

        if (ok && data.success) {
            state.master = data;
            const gold = data.gold;

            let html = `
                <div class="status-header success">✅ Master @${data.username} có Gold!</div>
                <div class="status-detail">
                    <span class="label">UID</span>
                    <span class="value">${data.uid}</span>
                </div>
                <div class="status-detail">
                    <span class="label">Sản phẩm</span>
                    <span class="value gold">${gold.product || 'N/A'}</span>
                </div>
                <div class="status-detail">
                    <span class="label">Hạn dùng</span>
                    <span class="value">${formatDate(gold.expires_date)}</span>
                </div>
                <div class="status-detail">
                    <span class="label">Còn lại</span>
                    <span class="value success">${gold.days_left} ngày</span>
                </div>
                <div class="status-detail">
                    <span class="label">Proxy Chain</span>
                    <span class="value gold">${data.proxy_stats ? data.proxy_stats.available + '/2500 slots' : 'Proxy Chain Mode'}</span>
                </div>
                <div class="status-detail">
                    <span class="label">Đã dùng</span>
                    <span class="value">${data.proxy_stats ? data.proxy_stats.total_customers + ' customers, ' + data.proxy_stats.total_proxies + ' proxies' : 'N/A'}</span>
                </div>
            `;
            showStatusPanelRaw('#master-status', 'success', html);
            setStep(2);
            $('#customer-input').focus();
        } else {
            showStatusPanel('#master-status', 'error', 'Không thành công', data.error || 'Không xác định');
        }
    } catch (err) {
        showStatusPanel('#master-status', 'error', 'Lỗi kết nối', err.message);
    }

    btn.disabled = false;
    btn.innerHTML = '🔍 Kiểm tra';
}

// ==================== CHECK CUSTOMER ====================
async function checkCustomer() {
    const input = $('#customer-input');
    const username = input.value.trim();
    if (!username) {
        showStatusPanel('#customer-status', 'error', 'Lỗi', 'Vui lòng nhập username cần nâng Gold');
        return;
    }

    const btn = $('#btn-check-customer');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner spinner-dark"></span> Đang kiểm tra...';
    clearStatusPanel('#customer-status');
    hide('#section-unlock');

    try {
        const { ok, data } = await apiCall('check-user', { username });

        if (ok && data.success) {
            state.customer = data;

            if (data.already_has_gold) {
                const gold = data.gold;
                let html = `
                    <div class="status-header warning">⚠️ @${data.username} đã có Gold!</div>
                    <div class="status-detail">
                        <span class="label">UID</span>
                        <span class="value">${data.uid}</span>
                    </div>
                    <div class="status-detail">
                        <span class="label">Sản phẩm</span>
                        <span class="value gold">${gold.product || 'N/A'}</span>
                    </div>
                    <div class="status-detail">
                        <span class="label">Hạn dùng</span>
                        <span class="value">${formatDate(gold.expires_date)}</span>
                    </div>
                    <div class="status-detail">
                        <span class="label">Còn lại</span>
                        <span class="value success">${gold.days_left} ngày</span>
                    </div>
                `;
                showStatusPanelRaw('#customer-status', 'warning', html);
            } else {
                let html = `
                    <div class="status-header info">ℹ️ @${data.username} chưa có Gold</div>
                    <div class="status-detail">
                        <span class="label">UID</span>
                        <span class="value">${data.uid}</span>
                    </div>
                    <div class="status-detail">
                        <span class="label">Trạng thái</span>
                        <span class="value error">Chưa có Gold</span>
                    </div>
                `;
                showStatusPanelRaw('#customer-status', 'info', html);
                setStep(3);
                $('#unlock-username').textContent = `@${data.username}`;
            }
        } else {
            showStatusPanel('#customer-status', 'error', 'Không tìm thấy', data.error || 'Không xác định');
        }
    } catch (err) {
        showStatusPanel('#customer-status', 'error', 'Lỗi kết nối', err.message);
    }

    btn.disabled = false;
    btn.innerHTML = '🔍 Kiểm tra';
}

// ==================== UNLOCK GOLD ====================
async function unlockGold() {
    if (!state.master || !state.customer) return;

    const btn = $('#btn-unlock');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner spinner-dark"></span> Đang kích hoạt Gold...';

    const logPanel = '#unlock-log';
    const log = $(logPanel);
    if (log) log.innerHTML = '';
    show('#unlock-log-container');

    addLog(logPanel, `Bắt đầu nâng Gold cho @${state.customer.username}...`);
    addLog(logPanel, `Master: @${state.master.username} (${state.master.uid.substring(0, 12)}...)`, 'warning');
    addLog(logPanel, `Customer UID: ${state.customer.uid}`, 'warning');
    addLog(logPanel, 'Đang gửi Alias request...', '');

    try {
        const { ok, data } = await apiCall('unlock', {
            customer_username: state.customer.username,
            master_uid: state.master.uid
        });

        if (data.success) {
            if (data.already_had_gold) {
                addLog(logPanel, `@${state.customer.username} đã có Gold từ trước!`, 'warning');
                showResult('warning', 'Đã có Gold!', data.message, data.gold);
            } else {
                addLog(logPanel, '✅ Alias thành công!', 'success');
                addLog(logPanel, `Xác minh Gold lần ${data.attempt || 1}...`, 'success');
                addLog(logPanel, `Hạn dùng: ${formatDate(data.gold?.expires_date)}`, 'success');
                showResult('success', 'Thành công!', data.message, data.gold);
                triggerConfetti();
            }
        } else {
            addLog(logPanel, `❌ Thất bại: ${data.error}`, 'error');
            showResult('error', 'Thất bại', data.error, null);
        }
    } catch (err) {
        addLog(logPanel, `❌ Lỗi kết nối: ${err.message}`, 'error');
        showResult('error', 'Lỗi kết nối', err.message, null);
    }

    btn.disabled = false;
    btn.innerHTML = '⚡ Kích hoạt Gold';
}

// ==================== RESULT DISPLAY ====================
function showResult(type, title, message, gold) {
    const container = $('#unlock-result');
    const iconEmoji = type === 'success' ? '✅' : type === 'warning' ? '⚠️' : '❌';

    let goldDetails = '';
    if (gold && gold.has_gold) {
        goldDetails = `
            <div style="margin-top: 16px; text-align: left;">
                <div class="status-detail">
                    <span class="label">Sản phẩm</span>
                    <span class="value gold">${gold.product || 'N/A'}</span>
                </div>
                <div class="status-detail">
                    <span class="label">Hạn dùng</span>
                    <span class="value">${formatDate(gold.expires_date)}</span>
                </div>
                <div class="status-detail">
                    <span class="label">Còn lại</span>
                    <span class="value success">${gold.days_left} ngày</span>
                </div>
            </div>
        `;
    }

    container.innerHTML = `
        <div class="result-card">
            <div class="result-icon ${type}">${iconEmoji}</div>
            <div class="result-title ${type}">${title}</div>
            <div class="result-message">${message}</div>
            ${goldDetails}
            <button class="btn btn-outline" style="margin-top: 16px;" onclick="resetCustomer()">
                🔄 Nâng Gold cho người khác
            </button>
        </div>
    `;
    show(container);
}

// ==================== RESET ====================
function resetCustomer() {
    state.customer = null;
    $('#customer-input').value = '';
    clearStatusPanel('#customer-status');
    hide('#section-unlock');
    hide('#unlock-result');
    hide('#unlock-log-container');
    setStep(2);
    $('#customer-input').focus();
}

function resetAll() {
    state.master = null;
    state.customer = null;
    $('#master-input').value = '';
    $('#customer-input').value = '';
    clearStatusPanel('#master-status');
    clearStatusPanel('#customer-status');
    hide('#section-customer');
    hide('#section-unlock');
    hide('#unlock-result');
    hide('#unlock-log-container');
    setStep(1);
    $('#master-input').focus();
}

// ==================== STATUS PANEL HELPERS ====================
function showStatusPanel(selector, type, title, message) {
    const el = $(selector);
    if (!el) return;
    const icon = type === 'success' ? '✅' : type === 'error' ? '❌' : type === 'warning' ? '⚠️' : 'ℹ️';
    el.innerHTML = `
        <div class="status-panel ${type}">
            <div class="status-header ${type}">${icon} ${title}</div>
            <div style="color: var(--text-secondary); font-size: 13px;">${message}</div>
        </div>
    `;
}

function showStatusPanelRaw(selector, type, html) {
    const el = $(selector);
    if (!el) return;
    el.innerHTML = `<div class="status-panel ${type}">${html}</div>`;
}

function clearStatusPanel(selector) {
    const el = $(selector);
    if (el) el.innerHTML = '';
}

// ==================== UTILITIES ====================
function formatDate(dateStr) {
    if (!dateStr) return 'N/A';
    try {
        const d = new Date(dateStr);
        return d.toLocaleDateString('vi-VN', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch {
        return dateStr;
    }
}

// ==================== CONFETTI ====================
function triggerConfetti() {
    const container = document.createElement('div');
    container.className = 'confetti-container';
    document.body.appendChild(container);

    const colors = ['#FFD700', '#F59E0B', '#10B981', '#3B82F6', '#EF4444', '#8B5CF6'];

    for (let i = 0; i < 60; i++) {
        const piece = document.createElement('div');
        piece.className = 'confetti-piece';
        piece.style.left = Math.random() * 100 + '%';
        piece.style.backgroundColor = colors[Math.floor(Math.random() * colors.length)];
        piece.style.animationDelay = Math.random() * 1.5 + 's';
        piece.style.animationDuration = (2 + Math.random() * 2) + 's';
        piece.style.borderRadius = Math.random() > 0.5 ? '50%' : '2px';
        piece.style.width = (4 + Math.random() * 8) + 'px';
        piece.style.height = (4 + Math.random() * 8) + 'px';
        container.appendChild(piece);
    }

    setTimeout(() => container.remove(), 5000);
}

// ==================== KEYBOARD ====================
function handleKeyPress(event, action) {
    if (event.key === 'Enter') {
        event.preventDefault();
        action();
    }
}

// ==================== INIT ====================
document.addEventListener('DOMContentLoaded', () => {
    setStep(1);
    $('#master-input').focus();
});
