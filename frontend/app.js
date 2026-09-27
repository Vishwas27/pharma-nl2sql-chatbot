/**
 * NovaPharma Commercial Analytics Assistant - Frontend Client Logic
 */

let state = {
    currentUser: null,
    users: [],
    conversationHistory: [],
    schemaData: null,
    activeChartInstances: {},
    settings: {
        provider: localStorage.getItem("nova_provider") || "gemini",
        apiKey: localStorage.getItem("nova_api_key") || ""
    }
};

// Recommended Starters by Role (Clear, plain-English business analytics questions)
const STARTERS_BY_ROLE = {
    exec: [
        "What is our gross revenue and pack units this quarter by product?",
        "What is our market share for Zenovax in the Docetaxel market?",
        "Rank our top 10 accounts by total volume this quarter",
        "Show 6-month monthly volume trend for all oncology products",
        "Give me a list of all products in our catalog"
    ],
    director: [
        "Compare territory volumes across my region this quarter",
        "What is our Docetaxel market share across territories in my region?",
        "What are the top 5 accounts in my region by pack units?",
        "Show monthly Zenovax volume trend for the last 6 months",
        "Give me a list of all products in our catalog"
    ],
    ram: [
        "What are my top 5 accounts by pack units this quarter?",
        "What is our market share for Zenovax in my territory?",
        "Show monthly volume trend for Carbotrel over the last 6 months",
        "What are my total sales in dollars?",
        "Give me a list of all medicines in our portfolio"
    ]
};

// Initialize Application
document.addEventListener("DOMContentLoaded", async () => {
    initTheme();
    setupEventListeners();
    await loadUsers();
    await loadSchemaData();
    checkExistingSession();
});

function initTheme() {
    const savedTheme = localStorage.getItem("nova_theme") || "theme-dark";
    document.body.className = savedTheme;
}

function checkExistingSession() {
    const savedUserId = sessionStorage.getItem("nova_active_user");
    if (savedUserId && state.users.length > 0) {
        const user = state.users.find(u => u.user_id === savedUserId);
        if (user) {
            loginUser(user);
            return;
        }
    }
    showLoginView();
}

function setupEventListeners() {
    // Theme toggle
    document.getElementById("theme-toggle-btn").addEventListener("click", () => {
        const isDark = document.body.classList.contains("theme-dark");
        const nextTheme = isDark ? "theme-light" : "theme-dark";
        document.body.className = nextTheme;
        localStorage.setItem("nova_theme", nextTheme);
    });

    // Login Persona Cards Quick-Select (1-Click Login & Select)
    document.querySelectorAll(".persona-card").forEach(card => {
        card.addEventListener("click", () => {
            const userId = card.getAttribute("data-user-id");
            document.querySelectorAll(".persona-card").forEach(c => c.classList.remove("selected"));
            card.classList.add("selected");
            const select = document.getElementById("login-user-select");
            if (select) select.value = userId;
            
            // Auto login directly on card click for seamless UX
            const user = state.users.find(u => u.user_id === userId);
            if (user) {
                loginUser(user);
            }
        });
    });

    // Dropdown change listener to sync selection
    const loginSelect = document.getElementById("login-user-select");
    if (loginSelect) {
        loginSelect.addEventListener("change", (e) => {
            const userId = e.target.value;
            document.querySelectorAll(".persona-card").forEach(c => {
                if (c.getAttribute("data-user-id") === userId) {
                    c.classList.add("selected");
                } else {
                    c.classList.remove("selected");
                }
            });
        });
    }

    // Login Submit button
    document.getElementById("btn-login-submit").addEventListener("click", () => {
        const select = document.getElementById("login-user-select");
        let userId = select.value;
        if (!userId) {
            const selectedCard = document.querySelector(".persona-card.selected");
            if (selectedCard) {
                userId = selectedCard.getAttribute("data-user-id");
            }
        }
        if (!userId && state.users.length > 0) {
            userId = state.users[0].user_id;
        }

        const user = state.users.find(u => u.user_id === userId);
        if (user) {
            loginUser(user);
        } else {
            alert("Please select a valid user persona.");
        }
    });

    // Switch Account / Sign Out
    document.getElementById("btn-switch-user").addEventListener("click", () => {
        signOut();
    });

    // Chat form submit
    document.getElementById("chat-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const input = document.getElementById("chat-input");
        const message = input.value.trim();
        if (!message) return;
        input.value = "";
        await sendMessage(message);
    });

    // Enter key auto-submit textarea (Shift+Enter for newline)
    document.getElementById("chat-input").addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            document.getElementById("chat-form").dispatchEvent(new Event("submit"));
        }
    });

    // Clear conversation
    document.getElementById("btn-clear-chat").addEventListener("click", () => {
        resetConversation();
    });

    // Modals
    document.getElementById("btn-open-schema").addEventListener("click", () => openModal("schema-modal"));
    document.getElementById("btn-open-rules").addEventListener("click", () => {
        openModal("schema-modal");
        switchTab("tab-metrics");
    });
    document.getElementById("btn-close-schema").addEventListener("click", () => closeModal("schema-modal"));
    
    document.getElementById("btn-open-logs").addEventListener("click", () => {
        openModal("logs-modal");
        loadLogs();
    });
    document.getElementById("btn-close-logs").addEventListener("click", () => closeModal("logs-modal"));
    document.getElementById("btn-refresh-logs").addEventListener("click", () => loadLogs());
    document.getElementById("btn-clear-logs").addEventListener("click", async () => {
        await fetch("/api/logs/clear", { method: "POST" });
        loadLogs();
    });

    document.getElementById("btn-open-settings").addEventListener("click", () => openSettingsModal());
    document.getElementById("btn-banner-open-settings").addEventListener("click", () => openSettingsModal());
    document.getElementById("btn-close-settings").addEventListener("click", () => closeModal("settings-modal"));

    // Save settings
    document.getElementById("btn-save-settings").addEventListener("click", () => {
        const provider = document.getElementById("provider-select").value;
        const apiKey = document.getElementById("api-key-input").value.trim();
        state.settings.provider = provider;
        state.settings.apiKey = apiKey;
        localStorage.setItem("nova_provider", provider);
        localStorage.setItem("nova_api_key", apiKey);
        closeModal("settings-modal");
        hideModelBanner();
        alert("AI Engine settings saved successfully!");
    });

    // Modal tabs
    document.querySelectorAll(".tab-btn").forEach(btn => {
        btn.addEventListener("click", (e) => {
            const targetTab = e.target.getAttribute("data-tab");
            switchTab(targetTab);
        });
    });
}

function openSettingsModal() {
    document.getElementById("provider-select").value = state.settings.provider;
    document.getElementById("api-key-input").value = state.settings.apiKey;
    openModal("settings-modal");
}

async function loadUsers() {
    try {
        const resp = await fetch("/api/users");
        if (!resp.ok) throw new Error("Failed to load users");
        state.users = await resp.json();

        const loginSelect = document.getElementById("login-user-select");
        loginSelect.innerHTML = '<option value="" disabled selected>Select any representative...</option>';

        state.users.forEach(u => {
            const opt = document.createElement("option");
            opt.value = u.user_id;
            const scopeDesc = u.role === "exec" ? "Global" : (u.role === "director" ? `${u.region_name} Region` : `${u.territory_name} Territory`);
            opt.textContent = `${u.full_name} (${u.role.toUpperCase()} — ${scopeDesc})`;
            loginSelect.appendChild(opt);
        });
    } catch (err) {
        console.error("Error loading users:", err);
    }
}

function showLoginView() {
    const loginEl = document.getElementById("login-view");
    const mainEl = document.getElementById("main-view");
    if (loginEl) loginEl.style.setProperty("display", "flex", "important");
    if (mainEl) mainEl.style.setProperty("display", "none", "important");
}

function loginUser(user) {
    if (!user) return;
    state.currentUser = user;
    sessionStorage.setItem("nova_active_user", user.user_id);

    // Update UI profile
    const nameEl = document.getElementById("active-user-name");
    const emailEl = document.getElementById("active-user-email");
    if (nameEl) nameEl.textContent = user.full_name;
    if (emailEl) emailEl.textContent = user.email;

    const badge = document.getElementById("role-badge");
    if (badge) {
        badge.className = `badge badge-${user.role}`;
        badge.textContent = user.role.toUpperCase();
    }

    const scopeEl = document.getElementById("user-scope");
    const wacEl = document.getElementById("user-wac-status");

    if (scopeEl && wacEl) {
        if (user.role === "exec") {
            scopeEl.textContent = "Global (All Regions)";
            wacEl.textContent = "Authorized";
            wacEl.className = "meta-value text-success";
        } else if (user.role === "director") {
            scopeEl.textContent = `${user.region_name} Region`;
            wacEl.textContent = "Restricted (Volume Only)";
            wacEl.className = "meta-value text-danger";
        } else {
            scopeEl.textContent = `${user.territory_name} Territory`;
            wacEl.textContent = "Restricted (Volume Only)";
            wacEl.className = "meta-value text-danger";
        }
    }

    const welcomeName = document.getElementById("welcome-user-name");
    if (welcomeName) welcomeName.textContent = user.full_name;

    renderStarters(user.role);
    resetConversation();

    // Transition Views cleanly
    const loginEl = document.getElementById("login-view");
    const mainEl = document.getElementById("main-view");
    if (loginEl) loginEl.style.setProperty("display", "none", "important");
    if (mainEl) mainEl.style.setProperty("display", "flex", "important");
}

function signOut() {
    sessionStorage.removeItem("nova_active_user");
    state.currentUser = null;
    showLoginView();
}

function renderStarters(role) {
    const container = document.getElementById("starters-container");
    if (!container) return;
    container.innerHTML = "";
    const list = STARTERS_BY_ROLE[role] || STARTERS_BY_ROLE.ram;

    list.forEach(promptText => {
        const chip = document.createElement("button");
        chip.className = "starter-chip";
        chip.textContent = promptText;
        chip.addEventListener("click", () => {
            document.getElementById("chat-input").value = promptText;
            document.getElementById("chat-form").dispatchEvent(new Event("submit"));
        });
        container.appendChild(chip);
    });
}

function resetConversation() {
    state.conversationHistory = [];
    const container = document.getElementById("chat-messages");
    container.innerHTML = `
        <div class="message-wrapper assistant-wrapper">
            <div class="avatar assistant-avatar">✨</div>
            <div class="message-bubble assistant-bubble">
                <div class="message-header">
                    <span class="sender-name">Pharma Analytics Bot</span>
                    <span class="timestamp">Just now</span>
                </div>
                <div class="message-body">
                    <p>Hello <strong>${state.currentUser ? state.currentUser.full_name : "User"}</strong>! What commercial analytics or portfolio questions can I assist you with today?</p>
                </div>
            </div>
        </div>
    `;
}

function showModelBanner(message) {
    const banner = document.getElementById("model-status-banner");
    const textEl = document.getElementById("model-alert-text");
    textEl.textContent = message || "Server not working, please put API key in Settings.";
    banner.style.display = "flex";
}

function hideModelBanner() {
    document.getElementById("model-status-banner").style.display = "none";
}

async function sendMessage(message) {
    if (!state.currentUser) return;

    // Append User Message to UI
    appendUserMessage(message);

    // Show Thinking indicator
    const thinkingId = appendThinkingIndicator();

    // Disable send button while processing
    const sendBtn = document.getElementById("send-btn");
    sendBtn.disabled = true;

    try {
        const payload = {
            user_id: state.currentUser.user_id,
            message: message,
            conversation_history: state.conversationHistory,
            api_provider: state.settings.provider,
            api_key: state.settings.apiKey || undefined
        };

        const resp = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (!resp.ok) {
            throw new Error(`Server status ${resp.status}`);
        }

        const data = await resp.json();
        removeElement(thinkingId);

        // If error returned (e.g. No API key or server error)
        if (!data.success || data.error) {
            showModelBanner(data.error || "Server not working, please put a valid API key in Settings.");
        } else {
            hideModelBanner();
        }

        // Update conversation history
        state.conversationHistory.push({ role: "user", content: message });
        state.conversationHistory.push({ 
            role: "assistant", 
            content: data.explanation, 
            sql: data.sql || null 
        });

        appendAssistantResponse(data);
    } catch (err) {
        removeElement(thinkingId);
        showModelBanner("Server not working, please put a valid API key in Settings.");
        appendAssistantResponse({
            success: false,
            explanation: "⚠️ Server not working, please put a valid API key in Settings.",
            security_notice: null,
            suggestions: ["Configure API Key in Settings"]
        });
    } finally {
        sendBtn.disabled = false;
        scrollToBottom();
    }
}

function appendUserMessage(text) {
    const container = document.getElementById("chat-messages");
    const div = document.createElement("div");
    div.className = "message-wrapper user-wrapper";
    div.innerHTML = `
        <div class="avatar user-avatar">👤</div>
        <div class="message-bubble user-bubble">
            <div class="message-header">
                <span class="sender-name">${state.currentUser.full_name}</span>
                <span class="timestamp">${getCurrentTime()}</span>
            </div>
            <div class="message-body">
                <p>${escapeHtml(text)}</p>
            </div>
        </div>
    `;
    container.appendChild(div);
    scrollToBottom();
}

function appendThinkingIndicator() {
    const container = document.getElementById("chat-messages");
    const id = `thinking-${Date.now()}`;
    const div = document.createElement("div");
    div.id = id;
    div.className = "message-wrapper assistant-wrapper";
    div.innerHTML = `
        <div class="avatar assistant-avatar">✨</div>
        <div class="message-bubble assistant-bubble thinking-bubble">
            <div class="dot-pulse">
                <span></span><span></span><span></span>
            </div>
            <span style="font-size: 0.8rem; color: var(--text-secondary);">Analyzing data and preparing insights...</span>
        </div>
    `;
    container.appendChild(div);
    scrollToBottom();
    return id;
}

function appendAssistantResponse(resp) {
    const container = document.getElementById("chat-messages");
    const div = document.createElement("div");
    div.className = "message-wrapper assistant-wrapper";

    const msgId = `msg-${Date.now()}`;
    let cardsHtml = "";

    // 1. Security Alert Box (If RBAC restriction triggered)
    if (resp.security_notice) {
        cardsHtml += `
            <div class="security-alert">
                <span>🛡️</span>
                <div>
                    <strong>Access Scoping Notice</strong>
                    <p style="margin-top: 3px;">${escapeHtml(resp.security_notice)}</p>
                </div>
            </div>
        `;
    }

    // 2. Visual Chart (If numerical metrics available)
    if (resp.data && resp.data.rows && resp.data.rows.length > 0 && resp.chart && resp.chart.chart_type !== "none" && resp.chart.chart_type !== "table") {
        const canvasId = `chart-${msgId}`;
        cardsHtml += `
            <div class="output-card">
                <div class="card-topbar">
                    <span class="card-title"><span>📈</span> Analytics Trend & Breakdown</span>
                    <span class="tag-metric">${resp.data.row_count} data points</span>
                </div>
                <div class="chart-wrapper">
                    <canvas id="${canvasId}"></canvas>
                </div>
            </div>
        `;
    }

    // 3. Tabular Data Presentation (Clean, human-readable)
    if (resp.data && resp.data.rows && resp.data.rows.length > 0) {
        const tableId = `table-${msgId}`;
        cardsHtml += `
            <div class="output-card">
                <div class="card-topbar">
                    <span class="card-title"><span>📋</span> Detailed Summary Data</span>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span class="tag-metric">${resp.data.row_count} Records</span>
                        <button class="btn-table-export" onclick="exportTableToCSV('${tableId}')">📥 Export CSV</button>
                    </div>
                </div>
                <div class="table-wrapper">
                    <table class="data-table" id="${tableId}">
                        <thead>
                            <tr>
                                ${resp.data.columns.map(c => `<th>${formatHeader(c)}</th>`).join('')}
                            </tr>
                        </thead>
                        <tbody>
                            ${resp.data.rows.slice(0, 50).map(row => `
                                <tr>
                                    ${resp.data.columns.map(c => `<td>${formatCellValue(row[c])}</td>`).join('')}
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }

    // 4. RAG Knowledge Layer Sources (Collapsible)
    let ragSourcesHtml = "";
    if (resp.rag_sources && resp.rag_sources.length > 0) {
        ragSourcesHtml = `
            <details class="rag-sources-accordion">
                <summary>
                    <span>📚 Knowledge Layer Context (${resp.rag_sources.length} sources retrieved)</span>
                </summary>
                <div class="rag-sources-list">
                    ${resp.rag_sources.map(src => `
                        <div class="rag-source-item">
                            <div class="rag-source-header">
                                <span class="rag-domain-badge">${escapeHtml(src.domain)}</span>
                                <span class="rag-source-file">${escapeHtml(src.source_file)}</span>
                            </div>
                            <div class="rag-source-title">${escapeHtml(src.title)}</div>
                            <div class="rag-source-snippet">${escapeHtml(src.text.slice(0, 220))}${src.text.length > 220 ? '...' : ''}</div>
                        </div>
                    `).join('')}
                </div>
            </details>
        `;
    }

    // 5. Multi-Agent Execution Trace (Collapsible)
    let tracesHtml = "";
    if (resp.traces && resp.traces.length > 0) {
        const totalTraceMs = resp.traces.reduce((acc, t) => acc + (t.latency_ms || 0), 0);
        tracesHtml = `
            <details class="trace-accordion">
                <summary>
                    <div class="trace-summary-left">
                        <span>🔍 Multi-Agent Execution Trace (${resp.traces.length} steps)</span>
                    </div>
                    <span class="trace-latency-badge">${totalTraceMs.toFixed(1)} ms</span>
                </summary>
                <div class="trace-timeline">
                    ${resp.traces.map(t => `
                        <div class="trace-item status-${t.status}">
                            <span class="trace-agent-tag">${escapeHtml(t.agent)}</span>
                            <div class="trace-body">
                                <span class="trace-action">${escapeHtml(t.action)}</span>
                                ${t.details ? `<span class="trace-details">${escapeHtml(t.details)}</span>` : ''}
                            </div>
                            <span class="trace-ms">${t.latency_ms}ms</span>
                        </div>
                    `).join('')}
                </div>
            </details>
        `;
    }

    // 6. Follow-up Suggestions
    let suggestionsHtml = "";
    if (resp.suggestions && resp.suggestions.length > 0) {
        suggestionsHtml = `
            <div class="suggestions-box">
                ${resp.suggestions.map(s => `
                    <button class="suggestion-pill" onclick="sendSuggestion('${escapeQuotes(s)}')">💡 ${escapeHtml(s)}</button>
                `).join('')}
            </div>
        `;
    }

    div.innerHTML = `
        <div class="avatar assistant-avatar">✨</div>
        <div class="message-bubble assistant-bubble">
            <div class="message-header">
                <span class="sender-name">Pharma Analytics Bot</span>
                <span class="timestamp">${getCurrentTime()}</span>
            </div>
            <div class="message-body">
                <p>${formatMarkdownText(resp.explanation)}</p>
                ${cardsHtml}
                ${ragSourcesHtml}
                ${tracesHtml}
                ${suggestionsHtml}
            </div>
        </div>
    `;

    container.appendChild(div);

    // Initialize Chart if rendered
    if (resp.data && resp.data.rows && resp.data.rows.length > 0 && resp.chart && resp.chart.chart_type !== "none" && resp.chart.chart_type !== "table") {
        const canvasId = `chart-${msgId}`;
        setTimeout(() => renderChart(canvasId, resp.data, resp.chart), 50);
    }

    scrollToBottom();
}

function renderChart(canvasId, data, chartConfig) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    const labels = data.rows.map(r => r[chartConfig.x_key] || "Item");
    const metricKey = (chartConfig.y_keys && chartConfig.y_keys[0]) || data.columns[1];
    const values = data.rows.map(r => r[metricKey] !== undefined ? r[metricKey] : 0);

    const isLight = document.body.classList.contains("theme-light");
    const textColor = isLight ? "#475569" : "#9ca3af";
    const gridColor = isLight ? "rgba(0,0,0,0.06)" : "rgba(255,255,255,0.06)";

    const chartType = chartConfig.chart_type === "line" ? "line" : "bar";

    new Chart(ctx, {
        type: chartType,
        data: {
            labels: labels,
            datasets: [{
                label: formatHeader(metricKey),
                data: values,
                backgroundColor: chartType === "line" ? "rgba(99, 102, 241, 0.2)" : "rgba(99, 102, 241, 0.75)",
                borderColor: "#6366f1",
                borderWidth: 2,
                borderRadius: 6,
                tension: 0.35,
                fill: chartType === "line"
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { labels: { color: textColor, font: { family: 'Plus Jakarta Sans', weight: '600' } } }
            },
            scales: {
                x: {
                    ticks: { color: textColor, font: { family: 'Plus Jakarta Sans', size: 11 } },
                    grid: { color: gridColor }
                },
                y: {
                    ticks: { color: textColor, font: { family: 'Plus Jakarta Sans', size: 11 } },
                    grid: { color: gridColor }
                }
            }
        }
    });
}

async function loadSchemaData() {
    try {
        const resp = await fetch("/api/schema");
        if (!resp.ok) return;
        state.schemaData = await resp.json();

        // Populate Products Table in modal
        const tbody = document.getElementById("products-table-body");
        tbody.innerHTML = "";
        state.schemaData.products.forEach(p => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td><strong>${p.drug_name}</strong></td>
                <td>${p.generic_name}</td>
                <td>${p.specialty}</td>
                <td>${p.market_category}</td>
                <td>${p.market_subcategory}</td>
            `;
            tbody.appendChild(tr);
        });

        document.getElementById("schema-ddl-code").textContent = state.schemaData.schema_ddl;
    } catch (e) {
        console.error("Failed to fetch schema metadata", e);
    }
}

// Utility Functions
function formatHeader(colName) {
    if (!colName) return "";
    return colName
        .replace(/_/g, " ")
        .replace(/\b\w/g, l => l.toUpperCase());
}

function switchTab(tabId) {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
    const activeBtn = document.querySelector(`[data-tab="${tabId}"]`);
    const activeContent = document.getElementById(tabId);
    if (activeBtn) activeBtn.classList.add("active");
    if (activeContent) activeContent.classList.add("active");
}

function openModal(id) {
    document.getElementById(id).classList.add("active");
}

function closeModal(id) {
    document.getElementById(id).classList.remove("active");
}

function sendSuggestion(text) {
    if (text.includes("Settings")) {
        openSettingsModal();
        return;
    }
    document.getElementById("chat-input").value = text;
    document.getElementById("chat-form").dispatchEvent(new Event("submit"));
}

function formatCellValue(val) {
    if (val === null || val === undefined) return '<span style="color:var(--text-muted)">—</span>';
    if (typeof val === "number") {
        return Number.isInteger(val) ? val.toLocaleString() : val.toFixed(2);
    }
    return escapeHtml(String(val));
}

function formatMarkdownText(text) {
    if (!text) return "";
    return escapeHtml(text).replace(/\n/g, "<br>");
}

function getCurrentTime() {
    const now = new Date();
    return now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function removeElement(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

function scrollToBottom() {
    const container = document.getElementById("chat-messages");
    container.scrollTop = container.scrollHeight;
}

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function escapeQuotes(str) {
    return String(str).replace(/'/g, "\\'").replace(/"/g, '\\"');
}

async function loadLogs() {
    const container = document.getElementById("logs-container");
    try {
        const resp = await fetch("/api/logs");
        if (!resp.ok) throw new Error("Failed to fetch logs");
        const logs = await resp.json();

        if (!logs || logs.length === 0) {
            container.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 24px;">No interaction logs recorded yet. Try asking a question in chat!</div>`;
            return;
        }

        container.innerHTML = logs.map(item => {
            const isError = item.status === "ERROR";
            const badgeClass = isError ? "log-badge-error" : "log-badge-success";

            let detailsHtml = `
                <div class="log-details-grid">
                    <div class="log-detail-item"><strong>Provider:</strong> ${escapeHtml(item.provider)}</div>
                    <div class="log-detail-item"><strong>Latency:</strong> ${item.latency_ms} ms</div>
                    <div class="log-detail-item"><strong>Rows:</strong> ${item.row_count}</div>
                </div>
            `;

            if (item.sql) {
                detailsHtml += `<div class="log-code-snippet"><strong>SQL:</strong>\n${escapeHtml(item.sql)}</div>`;
            }

            if (item.error) {
                detailsHtml += `<div class="log-error-detail"><strong>Error Message:</strong> ${escapeHtml(item.error)}</div>`;
            }

            return `
                <div class="log-card ${isError ? 'log-error' : ''}">
                    <div class="log-header">
                        <div class="log-meta-left">
                            <span class="${badgeClass}">${item.status}</span>
                            <span class="log-user-tag">${escapeHtml(item.user)}</span>
                        </div>
                        <span class="log-time">${escapeHtml(item.timestamp)}</span>
                    </div>
                    <div class="log-query-text"><strong>User Query:</strong> "${escapeHtml(item.question)}"</div>
                    ${detailsHtml}
                </div>
            `;
        }).join('');
    } catch (e) {
        container.innerHTML = `<div style="color: var(--danger); padding: 16px;">Error loading logs: ${e.message}</div>`;
    }
}

function exportTableToCSV(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return;

    const rows = Array.from(table.querySelectorAll("tr"));
    const csvContent = rows.map(r => {
        const cols = Array.from(r.querySelectorAll("th, td"));
        return cols.map(c => `"${c.innerText.replace(/"/g, '""')}"`).join(",");
    }).join("\n");

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `novapharma_export_${Date.now()}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

