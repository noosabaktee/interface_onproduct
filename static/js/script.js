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

function initZipUploadForm() {
    const form = document.querySelector("[data-zip-upload-form]");
    if (!form) {
        return;
    }

    const inputs = Array.from(form.querySelectorAll("[data-zip-input]"));
    const submitButton = form.querySelector("[data-zip-submit]");
    if (!inputs.length || !submitButton) {
        return;
    }

    const validateForm = () => {
        let allValid = true;

        inputs.forEach((input) => {
            const panel = input.closest(".upload-panel");
            const picker = panel ? panel.querySelector(".zip-picker") : null;
            const selectedFile = panel ? panel.querySelector("[data-selected-file]") : null;
            const error = panel ? panel.querySelector("[data-zip-error]") : null;
            const file = input.files && input.files[0];
            const hasFile = Boolean(file);
            const isZip = hasFile && file.name.toLowerCase().endsWith(".zip");

            if (selectedFile) {
                selectedFile.textContent = hasFile ? file.name : "Belum ada file dipilih";
            }

            if (picker) {
                picker.classList.toggle("is-ready", isZip);
                picker.classList.toggle("has-error", hasFile && !isZip);
            }

            if (error) {
                error.hidden = !hasFile || isZip;
            }

            input.setCustomValidity(hasFile && !isZip ? "File harus bertipe .zip." : "");
            if (!isZip) {
                allValid = false;
            }
        });

        submitButton.disabled = !allValid;
        return allValid;
    };

    inputs.forEach((input) => {
        input.addEventListener("change", validateForm);
    });

    form.addEventListener("submit", (event) => {
        if (!validateForm()) {
            event.preventDefault();
            return;
        }

        submitButton.disabled = true;
        submitButton.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Processing Upload';
    });

    validateForm();
}

function initCaseFileManager() {
    const uploadForm = document.querySelector("[data-case-upload-form]");
    if (uploadForm) {
        const input = uploadForm.querySelector("[data-case-file-input]");
        const label = uploadForm.querySelector(".case-upload-picker");
        const selected = uploadForm.querySelector("[data-case-selected-files]");
        const submit = uploadForm.querySelector("[data-case-upload-submit]");

        const updateUploadState = () => {
            const files = input && input.files ? Array.from(input.files) : [];
            if (label) {
                label.classList.toggle("is-ready", files.length > 0);
            }
            if (selected) {
                const visibleNames = files.slice(0, 3).map((file) => file.name).join(", ");
                const remaining = files.length > 3 ? ` +${files.length - 3} lainnya` : "";
                selected.textContent = files.length ? `${visibleNames}${remaining}` : "STL, konfigurasi, log, atau file custom";
            }
            if (submit) {
                submit.disabled = files.length === 0;
            }
        };

        if (input) {
            input.addEventListener("change", updateUploadState);
        }
        uploadForm.addEventListener("submit", () => {
            if (submit) {
                submit.disabled = true;
                submit.innerHTML = '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span> Uploading';
            }
        });
        updateUploadState();
    }

    document.querySelectorAll("[data-confirm-file-delete]").forEach((form) => {
        form.addEventListener("submit", (event) => {
            const filename = form.dataset.fileName || "file ini";
            if (!window.confirm(`Hapus ${filename} secara permanen dari case?`)) {
                event.preventDefault();
            }
        });
    });

    const clearForm = document.querySelector("[data-clear-case-form]");
    if (clearForm) {
        const confirmation = clearForm.querySelector("[data-clear-confirmation]");
        const submit = clearForm.querySelector("[data-clear-submit]");
        const updateClearState = () => {
            if (submit && confirmation) {
                submit.disabled = confirmation.value.trim().toUpperCase() !== "CLEAR";
            }
        };
        if (confirmation) {
            confirmation.addEventListener("input", updateClearState);
        }
        clearForm.addEventListener("submit", (event) => {
            const selectedMode = clearForm.querySelector('input[name="mode"]:checked');
            const modeLabel = selectedMode ? selectedMode.closest("label").querySelector("strong").textContent : "operasi ini";
            if (!window.confirm(`Jalankan “${modeLabel}” pada case aktif?`)) {
                event.preventDefault();
                return;
            }
            if (submit) {
                submit.disabled = true;
                submit.innerHTML = '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span> Processing';
            }
        });
        updateClearState();
    }

    const editorModal = document.getElementById("editCaseFileModal");
    if (editorModal) {
        const editorForm = editorModal.querySelector("[data-modal-text-editor-form]");
        const editor = editorModal.querySelector("[data-editor-content]");
        const title = editorModal.querySelector("[data-editor-file-title]");
        const pathLabel = editorModal.querySelector("[data-editor-file-path]");
        const loading = editorModal.querySelector("[data-editor-loading]");
        const error = editorModal.querySelector("[data-editor-error]");
        const download = editorModal.querySelector("[data-editor-download]");
        const save = editorModal.querySelector("[data-editor-save]");
        let editorRequestId = 0;

        const setEditorLoading = (filePath) => {
            title.textContent = filePath.split("/").pop() || filePath;
            pathLabel.textContent = filePath;
            editor.value = "";
            editor.disabled = true;
            editor.hidden = true;
            loading.hidden = false;
            error.hidden = true;
            error.textContent = "";
            save.disabled = true;
            editorForm.removeAttribute("action");
            download.removeAttribute("href");
            download.classList.add("disabled");
        };

        const setEditorError = (message) => {
            loading.hidden = true;
            editor.hidden = true;
            editor.disabled = true;
            error.textContent = message;
            error.hidden = false;
            save.disabled = true;
        };

        editorModal.addEventListener("show.bs.modal", (event) => {
            const trigger = event.relatedTarget;
            if (!trigger || !trigger.matches("[data-edit-file]")) {
                setEditorError("File yang akan diedit tidak ditemukan.");
                return;
            }

            const filePath = trigger.dataset.filePath || "File";
            const requestId = ++editorRequestId;
            setEditorLoading(filePath);

            fetch(trigger.dataset.readUrl, { headers: { Accept: "application/json" } })
                .then(async (response) => {
                    const payload = await response.json();
                    if (!response.ok) {
                        throw new Error(payload.error || "File gagal dibaca.");
                    }
                    return payload;
                })
                .then((payload) => {
                    if (requestId !== editorRequestId) {
                        return;
                    }
                    title.textContent = payload.path.split("/").pop() || payload.path;
                    pathLabel.textContent = payload.path;
                    editor.value = payload.content;
                    editor.disabled = false;
                    editor.hidden = false;
                    loading.hidden = true;
                    error.hidden = true;
                    editorForm.action = trigger.dataset.saveUrl;
                    download.href = trigger.dataset.downloadUrl;
                    download.classList.remove("disabled");
                    save.disabled = false;
                    window.setTimeout(() => editor.focus(), 150);
                })
                .catch((fetchError) => {
                    if (requestId === editorRequestId) {
                        setEditorError(fetchError.message || "File gagal dibaca.");
                    }
                });
        });

        editorModal.addEventListener("hidden.bs.modal", () => {
            editorRequestId += 1;
            editor.value = "";
            editor.disabled = true;
            editorForm.removeAttribute("action");
        });

        editorForm.addEventListener("submit", (event) => {
            if (!editorForm.hasAttribute("action") || editor.disabled) {
                event.preventDefault();
                return;
            }
            save.disabled = true;
            save.innerHTML = '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span> Saving';
        });

        editor.addEventListener("keydown", (event) => {
            if (event.key !== "Tab") {
                return;
            }
            event.preventDefault();
            const start = editor.selectionStart;
            const end = editor.selectionEnd;
            editor.setRangeText("    ", start, end, "end");
        });
    }
}

let activityChart = null;
let statusChart = null;

function renderDashboardCharts() {
    const activityCanvas = document.getElementById("activityChart");
    const statusCanvas = document.getElementById("statusChart");
    if (!window.Chart || (!activityCanvas && !statusCanvas)) {
        return;
    }

    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    const gridColor = isDark ? "#374151" : "#e5e7eb";
    const textColor = isDark ? "#9ca3af" : "#6b7280";

    if (activityCanvas) {
        if (activityChart) {
            activityChart.destroy();
        }
        activityChart = new Chart(activityCanvas.getContext("2d"), {
            type: "line",
            data: {
                labels: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                datasets: [{
                    label: "Simulations",
                    data: [12, 19, 15, 25, 22, 30, 28],
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
                        ticks: { color: textColor, stepSize: 10 },
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
                labels: ["Success", "Failed", "Running"],
                datasets: [{
                    data: [75, 15, 10],
                    backgroundColor: ["#10b981", "#f26522", "#008f4c"],
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
    initZipUploadForm();
    initCaseFileManager();
    renderDashboardCharts();
    window.addEventListener("resize", renderDashboardCharts);
});
