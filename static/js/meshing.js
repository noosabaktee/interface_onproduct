document.addEventListener('DOMContentLoaded', function () {
    'use strict';

    const root = document.querySelector('[data-simulation-terminal][data-task-key="meshing"]');

    function statusText(state) {
        if (state.running) {
            return 'Process is running...';
        }
        if (state.returncode === 0) {
            return 'Process completed successfully.';
        }
        if (state.resume_available || state.status === 'stopped') {
            return 'Meshing stopped. Ready to resume from the interrupted step.';
        }
        if (state.status === 'cancelled') {
            return 'Process cancelled.';
        }
        if (state.returncode !== null && state.returncode !== undefined) {
            return 'Process failed or cancelled.';
        }
        return 'Preparing mesh dictionaries and block generation...';
    }

    window.createSimulationTerminal({ root, statusText });
});
