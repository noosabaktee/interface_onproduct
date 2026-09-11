(function () {
    function initCaseTerminal() {
        const root = document.querySelector("[data-case-terminal]");
        if (!root) {
            return;
        }

        const screen = root.querySelector("[data-terminal-screen]");
        const output = root.querySelector("[data-terminal-output]");
        const form = root.querySelector("[data-terminal-form]");
        const input = root.querySelector("[data-terminal-input]");
        const prompt = root.querySelector("[data-terminal-prompt]");
        const submit = root.querySelector("[data-terminal-submit]");
        const stop = root.querySelector("[data-terminal-stop]");
        const clear = root.querySelector("[data-terminal-clear]");
        let pollTimer = null;
        let commandHistory = [];
        let historyIndex = 0;

        const render = (state) => {
            output.textContent = (state.lines && state.lines.length)
                ? state.lines.join("\n")
                : "Terminal siap.";
            prompt.textContent = state.prompt || "case:/ $";
            screen.scrollTop = screen.scrollHeight;

            const running = Boolean(state.running);
            root.classList.toggle("is-running", running);
            input.disabled = running;
            submit.disabled = running;
            stop.disabled = !running;

            if (state.error) {
                const message = document.createElement("div");
                message.className = "case-terminal-error";
                message.textContent = state.error;
                output.textContent += `${output.textContent ? "\n" : ""}${message.textContent}`;
                screen.scrollTop = screen.scrollHeight;
            }

            if (running && !pollTimer) {
                pollTimer = window.setInterval(fetchStatus, 1000);
            } else if (!running && pollTimer) {
                window.clearInterval(pollTimer);
                pollTimer = null;
            }

            if (!running) {
                input.focus();
            }
        };

        const requestJson = (url, options) => fetch(url, options).then(async (response) => {
            const payload = await response.json();
            if (!response.ok && !payload.error) {
                payload.error = "Request terminal gagal.";
            }
            return payload;
        });

        const fetchStatus = () => {
            requestJson(root.dataset.statusUrl).then(render).catch(() => {
                output.textContent += "\nError: status terminal gagal dibaca.";
            });
        };

        form.addEventListener("submit", (event) => {
            event.preventDefault();
            const command = input.value.trim();
            if (!command) {
                return;
            }

            commandHistory = commandHistory.filter((item) => item !== command);
            commandHistory.push(command);
            historyIndex = commandHistory.length;
            input.value = "";
            requestJson(root.dataset.runUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ command })
            }).then(render).catch(() => {
                output.textContent += "\nError: command gagal dikirim.";
                screen.scrollTop = screen.scrollHeight;
            });
        });

        stop.addEventListener("click", () => {
            requestJson(root.dataset.stopUrl, { method: "POST" }).then(render).catch(() => {
                output.textContent += "\nError: command gagal dihentikan.";
                screen.scrollTop = screen.scrollHeight;
            });
        });

        clear.addEventListener("click", () => {
            requestJson(root.dataset.runUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ command: "clear" })
            }).then(render);
            input.focus();
        });

        input.addEventListener("keydown", (event) => {
            if (event.key === "ArrowUp") {
                event.preventDefault();
                if (!commandHistory.length) {
                    return;
                }
                historyIndex = Math.max(0, historyIndex - 1);
                input.value = commandHistory[historyIndex] || "";
                input.setSelectionRange(input.value.length, input.value.length);
            }

            if (event.key === "ArrowDown") {
                event.preventDefault();
                if (!commandHistory.length) {
                    return;
                }
                historyIndex = Math.min(commandHistory.length, historyIndex + 1);
                input.value = commandHistory[historyIndex] || "";
                input.setSelectionRange(input.value.length, input.value.length);
            }
        });

        screen.addEventListener("click", () => {
            if (!input.disabled) {
                input.focus();
            }
        });

        fetchStatus();
    }

    document.addEventListener("DOMContentLoaded", initCaseTerminal);
}());
