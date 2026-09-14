(function () {
    "use strict";

    function onReady(callback) {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", callback, { once: true });
        } else {
            callback();
        }
    }

    onReady(function () {
        var explorer = document.querySelector("[data-case-explorer]");
        if (!explorer) {
            return;
        }

        var buttons = Array.prototype.slice.call(explorer.querySelectorAll("[data-open-case-file]"));
        var editorForm = explorer.querySelector("#caseInlineEditor");
        var textarea = explorer.querySelector("[data-inline-content]");
        var saveButton = explorer.querySelector("[data-inline-save]");
        var lineNumbers = explorer.querySelector("[data-line-numbers]");
        var notice = explorer.querySelector("[data-inline-notice]");
        var welcome = explorer.querySelector("[data-editor-welcome]");
        var tabName = explorer.querySelector("[data-tab-name]");
        var dirtyIndicator = explorer.querySelector("[data-dirty-indicator]");
        var openPath = explorer.querySelector("[data-open-path]");
        var downloadLink = explorer.querySelector("[data-open-download]");
        var replaceButton = explorer.querySelector("[data-replace-file]");
        var deleteForm = explorer.querySelector("[data-confirm-file-delete]");
        var status = explorer.querySelector("[data-editor-status]");

        var currentButton = null;
        var currentPath = "";
        var currentSaveUrl = "";
        var currentContent = "";
        var currentEditable = false;
        var requestId = 0;

        function filename(path) {
            var parts = String(path || "").split("/");
            return parts[parts.length - 1] || "Untitled";
        }

        function setNotice(message, isError) {
            notice.textContent = message;
            notice.classList.toggle("is-error", Boolean(isError));
        }

        function isDirty() {
            return currentPath && textarea.value !== currentContent;
        }

        function updateDirtyState() {
            var dirty = isDirty();
            dirtyIndicator.hidden = !dirty;
            saveButton.disabled = !currentEditable || !dirty;
            if (currentPath && status) {
                var lines = textarea.value ? textarea.value.split("\n").length : 1;
                status.textContent = lines + " lines" + (currentEditable ? " - editable" : " - read-only");
            }
        }

        function updateLineNumbers() {
            var count = textarea.value ? textarea.value.split("\n").length : 1;
            var rows = [];
            for (var index = 1; index <= count; index += 1) {
                rows.push(index);
            }
            lineNumbers.textContent = rows.join("\n");
        }

        function syncGutterScroll() {
            lineNumbers.scrollTop = textarea.scrollTop;
        }

        function showWelcome() {
            editorForm.hidden = true;
            welcome.hidden = false;
            downloadLink.hidden = true;
            replaceButton.hidden = true;
            deleteForm.hidden = true;
            tabName.textContent = "Welcome";
            openPath.textContent = openPath.getAttribute("title") || "";
            currentButton = null;
            currentPath = "";
            currentSaveUrl = "";
            currentContent = "";
            currentEditable = false;
            textarea.value = "";
            updateLineNumbers();
            updateDirtyState();
        }

        function updateActionButtons(button) {
            downloadLink.href = button.dataset.downloadUrl || "#";
            downloadLink.hidden = false;

            var writable = button.dataset.writable === "true";
            replaceButton.hidden = !writable;
            deleteForm.hidden = !writable;

            if (writable) {
                replaceButton.dataset.filePath = button.dataset.filePath || "";
                replaceButton.dataset.replaceUrl = button.dataset.replaceUrl || "";
                deleteForm.action = button.dataset.deleteUrl || "#";
                deleteForm.dataset.fileName = button.dataset.filePath || "";
            }
        }

        function canLeaveCurrentFile() {
            return !isDirty() || window.confirm("Perubahan belum disimpan. Pindah file tanpa menyimpan?");
        }

        function openBinaryOrUnreadable(button) {
            currentButton = button;
            currentPath = button.dataset.filePath || "";
            currentSaveUrl = "";
            currentContent = "";
            currentEditable = false;
            textarea.value = "";
            editorForm.hidden = true;
            welcome.hidden = false;
            tabName.textContent = filename(currentPath);
            openPath.textContent = currentPath;
            updateActionButtons(button);
            setNotice("File ini tidak dapat dibuka sebagai teks. Gunakan Download atau Replace jika perlu.", !button.dataset.writable);
            updateLineNumbers();
            updateDirtyState();
        }

        function openFile(button) {
            if (button === currentButton) {
                return;
            }
            if (!canLeaveCurrentFile()) {
                return;
            }

            buttons.forEach(function (item) {
                item.classList.toggle("is-active", item === button);
                item.setAttribute("aria-current", item === button ? "true" : "false");
            });

            if (button.dataset.readable !== "true") {
                openBinaryOrUnreadable(button);
                return;
            }

            var localRequest = requestId + 1;
            requestId = localRequest;
            currentButton = button;
            currentPath = button.dataset.filePath || "";
            currentSaveUrl = button.dataset.saveUrl || "";
            currentEditable = button.dataset.editable === "true";
            tabName.textContent = filename(currentPath);
            openPath.textContent = currentPath;
            updateActionButtons(button);
            editorForm.hidden = true;
            welcome.hidden = false;
            textarea.readOnly = true;
            textarea.value = "";
            updateLineNumbers();
            updateDirtyState();
            setNotice("Membuka " + currentPath + "...");

            fetch(button.dataset.readUrl, {
                headers: { "Accept": "application/json" }
            }).then(function (response) {
                return response.json().then(function (payload) {
                    if (!response.ok) {
                        throw new Error(payload.error || "File gagal dibuka.");
                    }
                    return payload;
                });
            }).then(function (payload) {
                if (requestId !== localRequest) {
                    return;
                }
                currentContent = payload.content || "";
                textarea.value = currentContent;
                textarea.readOnly = !currentEditable;
                editorForm.action = currentSaveUrl;
                editorForm.hidden = false;
                welcome.hidden = true;
                updateLineNumbers();
                updateDirtyState();
                setNotice(currentEditable ? "Siap diedit." : "File ini read-only karena berada di luar 0, constant, atau system.");
                textarea.focus();
            }).catch(function (error) {
                if (requestId !== localRequest) {
                    return;
                }
                currentContent = "";
                textarea.value = "";
                editorForm.hidden = true;
                welcome.hidden = false;
                updateLineNumbers();
                updateDirtyState();
                setNotice(error.message || "File gagal dibuka.", true);
            });
        }

        function saveCurrentFile() {
            if (!currentEditable || !currentPath || !isDirty()) {
                return;
            }

            var formData = new FormData(editorForm);
            var snapshot = textarea.value;
            saveButton.disabled = true;
            textarea.readOnly = true;
            setNotice("Menyimpan " + currentPath + "...");

            fetch(currentSaveUrl, {
                method: "POST",
                headers: { "Accept": "application/json" },
                body: formData
            }).then(function (response) {
                return response.json().then(function (payload) {
                    if (!response.ok) {
                        throw new Error(payload.error || "File gagal disimpan.");
                    }
                    return payload;
                });
            }).then(function () {
                currentContent = snapshot;
                textarea.readOnly = !currentEditable;
                updateDirtyState();
                setNotice("Perubahan berhasil disimpan.");
            }).catch(function (error) {
                textarea.readOnly = false;
                updateDirtyState();
                setNotice(error.message || "File gagal disimpan.", true);
            });
        }

        buttons.forEach(function (button) {
            button.addEventListener("click", function () {
                openFile(button);
            });
        });

        textarea.addEventListener("input", function () {
            updateLineNumbers();
            updateDirtyState();
        });
        textarea.addEventListener("scroll", syncGutterScroll);
        textarea.addEventListener("keydown", function (event) {
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
                event.preventDefault();
                saveCurrentFile();
                return;
            }

            if (event.key === "Tab" && !textarea.readOnly) {
                event.preventDefault();
                textarea.setRangeText("    ", textarea.selectionStart, textarea.selectionEnd, "end");
                textarea.dispatchEvent(new Event("input", { bubbles: true }));
            }
        });

        editorForm.addEventListener("submit", function (event) {
            event.preventDefault();
            saveCurrentFile();
        });

        window.addEventListener("beforeunload", function (event) {
            if (!isDirty()) {
                return undefined;
            }
            event.preventDefault();
            event.returnValue = "";
            return "";
        });

        initUploadModal();
        updateLineNumbers();
        showWelcome();
    });

    function initUploadModal() {
        var form = document.querySelector("[data-explorer-upload]");
        if (!form) {
            return;
        }

        var mode = form.querySelector("[data-upload-mode]");
        var target = form.querySelector("[data-upload-target]");
        var folderInput = form.querySelector("[data-folder-picker]");
        var fileInput = form.querySelector("[data-file-picker]");
        var summary = form.querySelector("[data-upload-summary]");
        var submit = form.querySelector("[data-upload-submit]");
        var hint = form.querySelector("[data-upload-hint]");

        function activeInput() {
            return mode.value === "folder" ? folderInput : fileInput;
        }

        function selectedFiles() {
            return Array.prototype.slice.call(activeInput().files || []);
        }

        function sourceFolder(file) {
            var relativePath = file.webkitRelativePath || file.name || "";
            return relativePath.split("/")[0] || "";
        }

        function validateUpload() {
            var files = selectedFiles();
            var message = "";
            var valid = true;

            if (!files.length) {
                valid = false;
                message = mode.value === "folder" ? "Belum ada folder dipilih." : "Belum ada file dipilih.";
            } else if (mode.value === "folder") {
                var roots = files.map(sourceFolder).filter(Boolean);
                var firstRoot = roots[0] || "";
                var sameRoot = roots.every(function (root) {
                    return root === firstRoot;
                });
                if (!firstRoot || !sameRoot || firstRoot !== target.value) {
                    valid = false;
                    message = "Nama folder harus sama persis dengan tujuan: " + target.value + ".";
                } else {
                    message = files.length + " file dari folder " + firstRoot + " siap diupload.";
                }
            } else {
                message = files.length + " file siap diupload ke " + target.value + ".";
            }

            summary.textContent = message;
            submit.disabled = !valid;
            return valid;
        }

        function syncMode() {
            var folderMode = mode.value === "folder";
            folderInput.hidden = !folderMode;
            folderInput.disabled = !folderMode;
            folderInput.required = folderMode;
            fileInput.hidden = folderMode;
            fileInput.disabled = folderMode;
            fileInput.required = !folderMode;
            hint.textContent = folderMode
                ? "Nama folder harus sama persis dengan tujuan. Contoh: pilih folder constant untuk tujuan constant. Subfolder tetap dipertahankan."
                : "File akan disimpan langsung ke folder tujuan yang dipilih.";
            validateUpload();
        }

        form.addEventListener("formdata", function (event) {
            var data = event.formData;
            data.delete("files");
            selectedFiles().forEach(function (file) {
                var name = mode.value === "folder" ? (file.webkitRelativePath || file.name) : file.name;
                data.append("files", file, name);
            });
        });

        form.addEventListener("submit", function (event) {
            if (!validateUpload()) {
                event.preventDefault();
                return;
            }
            submit.disabled = true;
            submit.innerHTML = '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span> Uploading...';
        });

        mode.addEventListener("change", syncMode);
        target.addEventListener("change", validateUpload);
        folderInput.addEventListener("change", validateUpload);
        fileInput.addEventListener("change", validateUpload);
        syncMode();
    }
}());
