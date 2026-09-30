(function () {
    'use strict';

    function createSimulationTerminal(options) {
        const root = options.root;
        if (!root) {
            return null;
        }

        const startButton = root.querySelector('[data-terminal-start]');
        const cancelButton = root.querySelector('[data-terminal-cancel]');
        const downloadButton = root.querySelector('[data-terminal-download]');
        const terminalOutput = root.querySelector('[data-terminal-output]');
        const progressBar = root.querySelector('[data-progress-bar]');
        const progressValue = root.querySelector('[data-progress-value]');
        const progressElement = progressBar.closest('[role="progressbar"]');
        const statusLabel = root.querySelector('[data-status-label]');
        const config = root.dataset;

        let pollingInterval = null;
        let currentState = {
            running: false,
            status: 'idle',
            resume_available: false,
            meshing_ready: true
        };

        function setMainButton(html, disabled, variant) {
            startButton.innerHTML = html;
            startButton.disabled = disabled;
            startButton.className = `btn btn-outline-${variant} shadow-sm`;
        }

        function canStart(state) {
            return !options.canStart || options.canStart(state);
        }

        function renderMainButton(state, otherState) {
            if (otherState && otherState.running) {
                setMainButton(`Cannot start while ${config.otherTaskLabel} is running`, true, 'secondary');
                return;
            }

            if (!canStart(state)) {
                setMainButton(`<i class="bi bi-play-fill me-1"></i> ${config.actionLabel}`, true, 'secondary');
                return;
            }

            if (state.running) {
                setMainButton(
                    '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>Stop',
                    false,
                    'danger'
                );
                return;
            }

            if (state.resume_available || state.status === 'stopped') {
                setMainButton('<i class="bi bi-play-fill me-1"></i>Resume', false, 'primary');
                return;
            }

            setMainButton(`<i class="bi bi-play-fill me-1"></i> ${config.actionLabel}`, false, 'primary');
        }

        function updateUI(state) {
            currentState = state;
            cancelButton.hidden = !state.running;
            statusLabel.textContent = options.statusText(state);

            if (state.progress !== undefined) {
                const progress = Math.max(0, Math.min(100, Number(state.progress) || 0));
                progressBar.style.width = `${progress}%`;
                progressValue.textContent = `${progress}%`;
                progressElement.setAttribute('aria-valuenow', progress);
            }

            if (state.lines && state.lines.length > 0) {
                terminalOutput.textContent = state.lines.join('\n');
                terminalOutput.scrollTop = terminalOutput.scrollHeight;
                downloadButton.hidden = false;
            } else {
                downloadButton.hidden = true;
            }

            if (options.onState) {
                options.onState(state);
            }
        }

        async function requestJson(url, requestOptions) {
            const response = await fetch(url, requestOptions);
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.error || 'Request gagal diproses.');
            }
            return data;
        }

        function syncPolling(state, otherState) {
            const shouldPoll = state.running || (otherState && otherState.running);
            if (shouldPoll && !pollingInterval) {
                pollingInterval = window.setInterval(pollState, 1000);
            } else if (!shouldPoll && pollingInterval) {
                window.clearInterval(pollingInterval);
                pollingInterval = null;
            }
        }

        async function pollState() {
            try {
                const [state, otherState] = await Promise.all([
                    requestJson(config.logsUrl),
                    requestJson(config.otherLogsUrl)
                ]);
                updateUI(state);
                renderMainButton(state, otherState);
                syncPolling(state, otherState);
            } catch (error) {
                console.error(error);
            }
        }

        startButton.addEventListener('click', async function () {
            if (!currentState.running && !canStart(currentState)) {
                return;
            }

            try {
                await requestJson(currentState.running ? config.stopUrl : config.startUrl, { method: 'POST' });
                await pollState();
            } catch (error) {
                window.alert(error.message);
            }
        });

        cancelButton.addEventListener('click', async function () {
            try {
                const data = await requestJson(config.cancelUrl, { method: 'POST' });
                if (data.message) {
                    window.alert(data.message);
                }
                await pollState();
            } catch (error) {
                window.alert(error.message);
            }
        });

        downloadButton.addEventListener('click', function () {
            window.location.href = config.downloadUrl;
        });

        window.addEventListener('beforeunload', function () {
            if (pollingInterval) {
                window.clearInterval(pollingInterval);
            }
        });

        pollState();
        return { poll: pollState };
    }

    window.createSimulationTerminal = createSimulationTerminal;
})();
