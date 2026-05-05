document.querySelectorAll("[data-sync-target]").forEach((control) => {
    control.addEventListener("input", () => {
        const target = document.getElementById(control.dataset.syncTarget);
        if (!target) {
            return;
        }

        const value = Math.max(1, Math.min(16, Number(control.value || 1)));
        control.value = value;
        target.value = value;
    });
});

document.querySelectorAll("[data-terminal]").forEach((terminal) => {
    const taskKey = terminal.dataset.taskKey;
    const startButton = terminal.querySelector("[data-terminal-start]");
    const output = terminal.querySelector("[data-terminal-output]");
    let timer = null;

    const renderState = (state) => {
        output.textContent = state.lines.length
            ? state.lines.join("\n")
            : "Menunggu command dijalankan...";
        output.scrollTop = output.scrollHeight;
        startButton.disabled = state.running;
        startButton.innerHTML = state.running
            ? '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>Running'
            : `<i class="bi bi-terminal me-1"></i>${startButton.dataset.label}`;

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
        fetch(`/terminal/${taskKey}/start`, { method: "POST" })
            .then((response) => response.json())
            .then((state) => {
                renderState(state);
            })
            .catch(() => {
                output.textContent = "Gagal menjalankan command.";
            });
    });

    fetchLogs();
});
