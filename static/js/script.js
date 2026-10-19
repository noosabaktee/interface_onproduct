function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    const icon = document.getElementById("themeIcon");
    if (icon) {
        icon.className = theme === "dark" ? "bi bi-sun-fill text-warning" : "bi bi-moon-fill";
    }
}

function initThemeToggle() {
    const savedTheme = localStorage.getItem("theme") || "light";
    applyTheme(savedTheme);

    const toggle = document.querySelector("[data-theme-toggle]");
    if (!toggle) {
        return;
    }

    toggle.addEventListener("click", () => {
        const currentTheme = document.documentElement.getAttribute("data-theme") || "light";
        const nextTheme = currentTheme === "dark" ? "light" : "dark";
        localStorage.setItem("theme", nextTheme);
        applyTheme(nextTheme);
        renderDashboardCharts();
    });
}

function initSynchronizedInputs() {
    document.querySelectorAll("[data-sync-target]").forEach((control) => {
        const syncTarget = document.getElementById(control.dataset.syncTarget);
        if (!syncTarget) {
            return;
        }

        const syncValue = () => {
            const processorGrid = document.getElementById("core-grid");
            const min = Number(control.min || syncTarget.min || 1);
            const max = Number(control.max || syncTarget.max || (processorGrid && processorGrid.dataset.maxCores) || 32);
            let value = Number(control.value || syncTarget.value || min);
            if (Number.isNaN(value)) {
                value = min;
            }
            value = Math.max(min, Math.min(max, value));
            control.value = value;
            syncTarget.value = value;
            updateCoreVisuals(value);
        };

        control.addEventListener("input", syncValue);
        syncTarget.addEventListener("input", syncValue);
        syncValue();
    });
}

function updateCoreVisuals(activeCount) {
    const grid = document.getElementById("core-grid");
    if (!grid) {
        return;
    }

    const configuredMax = Number(grid.dataset.maxCores || grid.children.length || 32);
    const maxCores = Number.isFinite(configuredMax) && configuredMax > 0 ? configuredMax : 32;
    const activeCores = Math.max(0, Math.min(maxCores, Number(activeCount) || 0));
    grid.innerHTML = "";
    for (let i = 0; i < maxCores; i += 1) {
        const box = document.createElement("div");
        box.className = `core-box${i < activeCores ? "" : " inactive"}`;
        box.innerHTML = '<i class="bi bi-cpu-fill"></i>';
        grid.appendChild(box);
    }
}

function initTerminalBlocks() {
    document.querySelectorAll("[data-terminal]").forEach((terminal) => {
        const taskKey = terminal.dataset.taskKey;
        const startButton = terminal.querySelector("[data-terminal-start]");
        const output = terminal.querySelector("[data-terminal-output]");
        if (!taskKey || !startButton || !output) {
            return;
        }

        let timer = null;
        let currentState = { running: false, status: "idle", resume_available: false };

        const defaultLogs = {
            meshing: [
                "[SYSTEM] Initializing OpenFOAM Environment...",
                "[INFO] Waiting for user command...",
                "> blockMesh",
                "> surfaceFeatureExtract",
                "> snappyHexMesh -overwrite",
                "_"
            ],
            solver: [
                "[SYSTEM] Initializing OpenFOAM Solver...",
                "[INFO] Preparing parallel decomposition...",
                "> decomposePar",
                "> mpirun -np [configured] sprayFoam -parallel",
                "_"
            ]
        };

        const renderState = (state) => {
            currentState = state;
            output.textContent = state.lines.length ? state.lines.join("\n") : (defaultLogs[taskKey] || ["Menunggu command dijalankan..."]).join("\n");
            output.scrollTop = output.scrollHeight;
            startButton.disabled = false;
            if (state.running) {
                startButton.className = "btn btn-outline-danger shadow-sm";
                startButton.innerHTML = '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>Stop';
            } else {
                startButton.className = "btn btn-outline-primary shadow-sm";
                startButton.innerHTML = state.resume_available || state.status === "stopped"
                    ? '<i class="bi bi-play-fill me-1"></i>Resume'
                    : `<i class="bi bi-play-fill me-1"></i>${startButton.dataset.label}`;
            }

            if (state.running && !timer) {
                timer = setInterval(fetchLogs, 700);
            } else if (!state.running && timer) {
                clearInterval(timer);
                timer = null;
            }
        };

        const fetchLogs = () => {
            fetch(`/terminal/${taskKey}/logs`)
                .then((response) => response.json())
                .then(renderState)
                .catch(() => {
                    output.textContent = "Gagal mengambil log terminal.";
                });
        };

        startButton.dataset.label = startButton.textContent.trim();
        startButton.addEventListener("click", () => {
            const endpoint = currentState.running ? "stop" : "start";
            fetch(`/terminal/${taskKey}/${endpoint}`, { method: "POST" })
                .then((response) => response.json())
                .then((state) => renderState(state))
                .catch(() => {
                    output.textContent = "Gagal menjalankan command.";
                });
        });

        fetchLogs();
    });
}


function renderDashboardCharts() {
    const activityCanvas = document.getElementById("activityChart");
    const statusCanvas = document.getElementById("statusChart");
    if (!window.Chart || (!activityCanvas && !statusCanvas)) {
        return;
    }

    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    const gridColor = isDark ? "#374151" : "#e5e7eb";
    const textColor = isDark ? "#9ca3af" : "#6b7280";
    const chartDataElement = document.getElementById("dashboardChartData");
    let dashboardData = {
        activity: { labels: [], values: [] },
        status_breakdown: { labels: [], values: [] },
    };
    if (chartDataElement) {
        try {
            dashboardData = JSON.parse(chartDataElement.textContent);
        } catch (error) {
            console.error("Dashboard chart data tidak valid.", error);
        }
    }

    if (activityCanvas) {
        if (activityChart) {
            activityChart.destroy();
        }
        activityChart = new Chart(activityCanvas.getContext("2d"), {
            type: "line",
            data: {
                labels: dashboardData.activity.labels,
                datasets: [{
                    label: "Simulations",
                    data: dashboardData.activity.values,
                    borderColor: "#008f4c",
                    backgroundColor: "rgba(0, 143, 76, 0.15)",
                    borderWidth: 3,
                    pointBackgroundColor: "#ffffff",
                    pointBorderColor: "#008f4c",
                    pointBorderWidth: 2,
                    pointRadius: 4,
                    tension: 0.4,
                    fill: true
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: { color: textColor, stepSize: 1, precision: 0 },
                        grid: { color: gridColor, drawBorder: false }
                    },
                    x: {
                        ticks: { color: textColor },
                        grid: { display: false, drawBorder: false }
                    }
                }
            }
        });
    }

    if (statusCanvas) {
        if (statusChart) {
            statusChart.destroy();
        }
        statusChart = new Chart(statusCanvas.getContext("2d"), {
            type: "doughnut",
            data: {
                labels: dashboardData.status_breakdown.labels,
                datasets: [{
                    data: dashboardData.status_breakdown.values,
                    backgroundColor: [
                        "#10b981",
                        "#ef4444",
                        "#008f4c",
                        "#f59e0b",
                        "#6b7280",
                    ],
                    borderWidth: 0,
                    hoverOffset: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "75%",
                plugins: { legend: { display: false } }
            }
        });
    }
}

document.addEventListener("DOMContentLoaded", () => {
    initThemeToggle();
    initSynchronizedInputs();
    initTerminalBlocks();
    renderDashboardCharts();
    window.addEventListener("resize", renderDashboardCharts);
});
