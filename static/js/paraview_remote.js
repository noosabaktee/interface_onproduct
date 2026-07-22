(() => {
    const STATUS_META = {
        idle: { label: "Belum berjalan", icon: "bi-play-circle" },
        starting: { label: "Menyalakan server", icon: "bi-arrow-repeat" },
        waiting: { label: "Siap dikoneksi", icon: "bi-broadcast" },
        connected: { label: "Desktop terhubung", icon: "bi-link-45deg" },
        stopping: { label: "Menghentikan", icon: "bi-hourglass-split" },
        stopped: { label: "Server dihentikan", icon: "bi-stop-circle" },
        failed: { label: "Proses gagal", icon: "bi-exclamation-octagon" },
        checking: { label: "Memeriksa server", icon: "bi-arrow-repeat" },
        finalizing: { label: "Memeriksa hasil", icon: "bi-hourglass-split" },
        unreachable: { label: "Status tidak terjangkau", icon: "bi-wifi-off" },
    };

    function initRemoteParaview() {
        const panel = document.querySelector("[data-paraview-remote]");
        if (!panel) {
            return;
        }

        const statusUrl = panel.dataset.statusUrl;
        const startUrl = panel.dataset.startUrl;
        const stopUrl = panel.dataset.stopUrl;
        const csrfToken = panel.dataset.csrfToken;
        const startButton = panel.querySelector("[data-remote-start]");
        const stopButton = panel.querySelector("[data-remote-stop]");
        const statusBadge = panel.querySelector("[data-remote-status-badge]");
        const statusLabel = panel.querySelector("[data-remote-status-label]");
        const message = panel.querySelector("[data-remote-message]");
        const pid = panel.querySelector("[data-remote-pid]");
        const version = panel.querySelector("[data-remote-version]");
        const backend = panel.querySelector("[data-remote-backend]");
        const connectionUrl = panel.querySelector("[data-remote-connection-url]");
        const tunnelHost = panel.querySelector("[data-remote-tunnel-host]");
        const tunnelPort = panel.querySelector("[data-remote-tunnel-port]");
        const tunnelUrl = panel.querySelector("[data-remote-tunnel-url]");
        const sshCommand = panel.querySelector("[data-remote-ssh-command]");
        const casePath = panel.querySelector("[data-remote-case-path]");
        const hostWarning = panel.querySelector("[data-remote-host-warning]");
        const renderWarning = panel.querySelector("[data-remote-render-warning]");
        const renderWarningText = panel.querySelector("[data-remote-render-warning-text]");
        const terminal = panel.querySelector("[data-remote-terminal-output]");

        let pollTimer = null;
        let busy = false;
        let requestGeneration = 0;
        let currentState = { status: "checking", running: false, lines: [] };

        function normalizedStatus(state) {
            return STATUS_META[state.status] ? state.status : "idle";
        }

        function buttonMarkup(icon, label, spinning = false) {
            if (spinning) {
                return `<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>${label}`;
            }
            return `<i class="bi ${icon} me-1"></i>${label}`;
        }

        function renderTerminal(state) {
            if (!terminal) {
                return;
            }

            const wasNearBottom = terminal.scrollHeight - terminal.scrollTop - terminal.clientHeight < 56;
            const rawLines = Array.isArray(state.lines) ? state.lines : [];
            const serverLines = rawLines.map((line) => {
                if (/^Connection URL:/i.test(line)) {
                    return `[PVSERVER INTERNAL] ${line.replace(/^Connection URL:\s*/i, "")}`;
                }
                return line;
            });
            const displayLines = [];

            if (state.tunnel_connection_url) {
                displayLines.push(`[REMOTE/SSH] ParaView Desktop: ${state.tunnel_connection_url}`);
            }
            if (state.connection_url) {
                displayLines.push(`[DIRECT/UNENCRYPTED] ${state.connection_url}`);
            }
            if (state.case_path) {
                displayLines.push(`[REMOTE] Setelah connect, buka: ${state.case_path}`);
            }

            if (serverLines.length) {
                displayLines.push("", ...serverLines);
            } else if (state.status === "idle") {
                displayLines.push("", "[SYSTEM] Klik “Jalankan Server” untuk memulai sesi remote.");
            } else {
                displayLines.push("", "[SYSTEM] Menunggu output pvserver...");
            }

            if (state.error && !displayLines.some((line) => line.includes(state.error))) {
                displayLines.push(`[ERROR] ${state.error}`);
            }
            if (state.render_warning && !displayLines.some((line) => line.includes(state.render_warning))) {
                displayLines.push(`[WARNING] ${state.render_warning}`);
            }
            if (state.connection_error) {
                displayLines.push(`[UI WARNING] ${state.connection_error}`);
            }
            if (state.action_error) {
                displayLines.push(`[UI ERROR] ${state.action_error}`);
            }

            terminal.textContent = displayLines.join("\n");
            if (wasNearBottom || state.status === "starting") {
                terminal.scrollTop = terminal.scrollHeight;
            }
        }

        function renderState(state) {
            currentState = state;
            const status = normalizedStatus(state);
            const meta = STATUS_META[status];
            const running = Boolean(state.running);

            panel.dataset.remoteStatus = status;
            statusBadge.className = `remote-status-badge is-${status}`;
            statusLabel.textContent = meta.label;
            message.textContent = state.message || "Status pvserver diperbarui.";

            pid.textContent = state.pid || "—";
            version.textContent = state.server_version || "—";
            backend.textContent = state.render_backend || "—";

            if (state.connection_url) {
                connectionUrl.textContent = state.connection_url;
            }
            if (state.tunnel_host) {
                tunnelHost.textContent = state.tunnel_host;
            }
            if (state.public_port) {
                tunnelPort.textContent = state.public_port;
            }
            if (state.tunnel_connection_url) {
                tunnelUrl.textContent = state.tunnel_connection_url;
            }
            if (state.ssh_command) {
                sshCommand.textContent = state.ssh_command;
            }
            if (state.case_path) {
                casePath.textContent = state.case_path;
            }
            if (hostWarning) {
                hostWarning.hidden = Boolean(
                    state.public_host_configured && state.ssh_user_configured,
                );
            }
            if (renderWarning && renderWarningText) {
                renderWarning.hidden = !state.render_warning;
                renderWarningText.textContent = state.render_warning || "";
            }

            const starting = status === "starting";
            const stopping = status === "stopping";
            const controlsUnavailable = ["checking", "finalizing", "unreachable"].includes(status);
            startButton.disabled = busy || running || starting || stopping || controlsUnavailable;
            stopButton.hidden = !running && !stopping;
            stopButton.disabled = busy || stopping || controlsUnavailable;

            if (busy && !running) {
                startButton.innerHTML = buttonMarkup("", "Menyalakan...", true);
            } else if (running) {
                startButton.innerHTML = buttonMarkup("bi-check2-circle", "Server Berjalan");
            } else if (status === "failed" || status === "stopped") {
                startButton.innerHTML = buttonMarkup("bi-arrow-clockwise", "Jalankan Ulang");
            } else {
                startButton.innerHTML = buttonMarkup("bi-play-fill", "Jalankan Server");
            }

            if (busy && running) {
                stopButton.innerHTML = buttonMarkup("", "Menghentikan...", true);
            } else {
                stopButton.innerHTML = buttonMarkup("bi-stop-circle", "Stop Server");
            }

            renderTerminal(state);
        }

        function showNetworkError(error) {
            const state = {
                ...currentState,
                status: "unreachable",
                connection_error: error.message,
                message: "Status pvserver tidak dapat diperbarui. Kontrol dinonaktifkan sementara.",
            };
            renderState(state);
        }

        async function requestState(url, method = "GET", timeout = 12000) {
            const controller = new AbortController();
            const timeoutId = window.setTimeout(() => controller.abort(), timeout);

            try {
                const response = await fetch(url, {
                    method,
                    headers: {
                        Accept: "application/json",
                        ...(method === "POST" ? { "X-CSRF-Token": csrfToken } : {}),
                    },
                    signal: controller.signal,
                });
                const contentType = response.headers.get("content-type") || "";
                if (!contentType.includes("application/json")) {
                    throw new Error(
                        response.redirected
                            ? "Sesi login berakhir. Muat ulang halaman dan login kembali."
                            : `Respons server tidak valid (HTTP ${response.status}).`,
                    );
                }
                const data = await response.json();
                if (!response.ok) {
                    const requestError = new Error(
                        data.error || `Request gagal (HTTP ${response.status}).`,
                    );
                    requestError.isHttpError = true;
                    requestError.responseData = data;
                    throw requestError;
                }
                return data;
            } catch (error) {
                if (error.name === "AbortError") {
                    throw new Error("Request status melewati batas waktu.");
                }
                throw error;
            } finally {
                window.clearTimeout(timeoutId);
            }
        }

        function schedulePoll(delay) {
            window.clearTimeout(pollTimer);
            pollTimer = window.setTimeout(pollStatus, delay);
        }

        async function pollStatus() {
            if (document.hidden) {
                schedulePoll(2500);
                return;
            }
            if (busy) {
                schedulePoll(700);
                return;
            }

            const pollGeneration = requestGeneration;
            try {
                const state = await requestState(statusUrl, "GET", 8000);
                if (pollGeneration !== requestGeneration || busy) {
                    schedulePoll(500);
                    return;
                }
                renderState(state);
                schedulePoll(state.running ? 900 : 2200);
            } catch (error) {
                if (pollGeneration !== requestGeneration || busy) {
                    schedulePoll(500);
                    return;
                }
                showNetworkError(error);
                schedulePoll(3500);
            }
        }

        async function runAction(url, action) {
            if (busy) {
                return;
            }

            busy = true;
            requestGeneration += 1;
            const actionGeneration = requestGeneration;
            const stateBeforeAction = currentState;
            window.clearTimeout(pollTimer);
            const transitionalState = {
                ...currentState,
                status: action === "start" ? "starting" : "stopping",
                message: action === "start" ? "Menyiapkan pvserver..." : "Menghentikan pvserver...",
            };
            renderState(transitionalState);

            try {
                const state = await requestState(url, "POST", 15000);
                if (actionGeneration === requestGeneration) {
                    renderState(state);
                }
            } catch (error) {
                if (actionGeneration === requestGeneration) {
                    if (error.responseData && error.responseData.status) {
                        renderState(error.responseData);
                    } else if (error.isHttpError) {
                        renderState({
                            ...stateBeforeAction,
                            action_error: error.message,
                            message: error.message,
                        });
                    } else {
                        showNetworkError(error);
                    }
                }
            } finally {
                busy = false;
                renderState(currentState);
                if (action === "stop" && !currentState.running) {
                    startButton.focus();
                }
                schedulePoll(500);
            }
        }

        startButton.addEventListener("click", () => runAction(startUrl, "start"));
        stopButton.addEventListener("click", () => runAction(stopUrl, "stop"));

        panel.querySelectorAll("[data-remote-copy]").forEach((button) => {
            button.addEventListener("click", async () => {
                const key = button.dataset.remoteCopy;
                const sourceMap = {
                    connection: connectionUrl,
                    host: tunnelHost,
                    port: tunnelPort,
                    case: casePath,
                    ssh: sshCommand,
                    log: terminal,
                };
                const source = sourceMap[key];
                if (!source) {
                    return;
                }

                const value = source.textContent.trim();
                try {
                    await copyText(value);
                    showCopySuccess(button);
                } catch (error) {
                    message.textContent = "Gagal menyalin otomatis. Silakan blok dan salin teks secara manual.";
                }
            });
        });

        document.querySelectorAll("[data-remote-panel-focus]").forEach((button) => {
            button.addEventListener("click", () => {
                const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
                panel.focus({ preventScroll: true });
                panel.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
                panel.classList.add("is-highlighted");
                window.setTimeout(() => panel.classList.remove("is-highlighted"), 1200);
            });
        });

        document.addEventListener("visibilitychange", () => {
            if (!document.hidden) {
                schedulePoll(0);
            }
        });

        pollStatus();
    }

    async function copyText(value) {
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(value);
            return;
        }

        const textarea = document.createElement("textarea");
        textarea.value = value;
        textarea.setAttribute("readonly", "");
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        const copied = document.execCommand("copy");
        textarea.remove();
        if (!copied) {
            throw new Error("Copy command failed");
        }
    }

    function showCopySuccess(button) {
        const icon = button.querySelector("i");
        const label = button.querySelector("span");
        const previousIcon = icon ? icon.className : "";
        const previousLabel = label ? label.textContent : "";
        const previousAriaLabel = button.getAttribute("aria-label");

        button.classList.add("is-copied");
        button.setAttribute("aria-label", "Tersalin");
        if (icon) {
            icon.className = "bi bi-check2";
        }
        if (label) {
            label.textContent = "Tersalin";
        }

        window.setTimeout(() => {
            button.classList.remove("is-copied");
            if (icon) {
                icon.className = previousIcon;
            }
            if (label) {
                label.textContent = previousLabel;
            }
            if (previousAriaLabel) {
                button.setAttribute("aria-label", previousAriaLabel);
            } else {
                button.removeAttribute("aria-label");
            }
        }, 1400);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initRemoteParaview, { once: true });
    } else {
        initRemoteParaview();
    }
})();
