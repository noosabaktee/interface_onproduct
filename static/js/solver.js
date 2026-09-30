document.addEventListener('DOMContentLoaded', function () {
    'use strict';

    const root = document.querySelector('[data-simulation-terminal][data-task-key="solver"]');
    const meshingWarning = root.querySelector('[data-meshing-warning]');
    const safetyPanel = root.querySelector('[data-solver-safety-panel]');
    const safetySummary = root.querySelector('[data-safety-summary]');
    const safetyRows = {};

    safetyPanel.querySelectorAll('[data-safety-row]').forEach((row) => {
        safetyRows[row.dataset.safetyRow] = {
            value: row.querySelector('[data-safety-value]'),
            status: row.querySelector('[data-safety-status]')
        };
    });

    function formatLogValue(value) {
        if (value === null || value === undefined || Number.isNaN(value)) {
            return '-';
        }

        const absolute = Math.abs(value);
        if (value !== 0 && (absolute < 0.001 || absolute >= 10000)) {
            return value.toExponential(2);
        }
        return Number(value.toPrecision(4)).toString();
    }

    function setSafetyRow(key, valueText, statusText, statusClass) {
        const row = safetyRows[key];
        row.value.textContent = valueText || '-';
        row.status.textContent = statusText;
        row.status.className = `solver-safety-state is-${statusClass}`;
        return statusClass;
    }

    function thresholdStatus(value, limit) {
        if (value === null || value === undefined || Number.isNaN(value)) {
            return ['Menunggu', 'waiting'];
        }
        return value < limit ? ['Aman', 'safe'] : ['Lewat batas', 'danger'];
    }

    function extractSolverMetrics(lines) {
        const numberPattern = '[-+]?\\d*\\.?\\d+(?:[eE][-+]?\\d+)?';
        const courantPattern = new RegExp(`Courant Number mean:\\s*(${numberPattern})\\s+max:\\s*(${numberPattern})`, 'i');
        const residualPattern = new RegExp(`Solving for\\s+([^,\\s]+).*?Final residual\\s*=\\s*(${numberPattern})`, 'i');
        const continuityPattern = new RegExp(`time step continuity errors\\s*:\\s*sum local\\s*=\\s*(${numberPattern}),\\s*global\\s*=\\s*(${numberPattern})`, 'i');
        const metrics = {
            courantMean: null,
            courantMax: null,
            residualU: {},
            residualHH2O: {},
            residualPrgh: null,
            continuityLocal: null,
            continuityGlobal: null
        };

        (lines || []).forEach((line) => {
            const courant = line.match(courantPattern);
            if (courant) {
                metrics.courantMean = Number(courant[1]);
                metrics.courantMax = Number(courant[2]);
                return;
            }

            const residual = line.match(residualPattern);
            if (residual) {
                const field = residual[1];
                const finalResidual = Number(residual[2]);
                if (/^U[xyz]$/i.test(field) || field === 'U') {
                    metrics.residualU[field] = finalResidual;
                } else if (field === 'p_rgh') {
                    metrics.residualPrgh = finalResidual;
                } else if (['h', 'H2O', 'YH2O'].includes(field)) {
                    metrics.residualHH2O[field] = finalResidual;
                }
                return;
            }

            const continuity = line.match(continuityPattern);
            if (continuity) {
                metrics.continuityLocal = Number(continuity[1]);
                metrics.continuityGlobal = Number(continuity[2]);
            }
        });
        return metrics;
    }

    function updateSolverSafety(lines) {
        const metrics = extractSolverMetrics(lines);
        const rowStates = [];

        if (metrics.courantMax === null || Number.isNaN(metrics.courantMax)) {
            rowStates.push(setSafetyRow('courantMax', '-', 'Menunggu', 'waiting'));
        } else if (metrics.courantMax < 0.8) {
            rowStates.push(setSafetyRow('courantMax', formatLogValue(metrics.courantMax), 'Aman', 'safe'));
        } else if (metrics.courantMax < 1.0) {
            rowStates.push(setSafetyRow('courantMax', formatLogValue(metrics.courantMax), 'Waspada', 'warn'));
        } else {
            rowStates.push(setSafetyRow('courantMax', formatLogValue(metrics.courantMax), 'Lewat batas', 'danger'));
        }

        const [courantMeanText, courantMeanClass] = thresholdStatus(metrics.courantMean, 0.1);
        rowStates.push(setSafetyRow('courantMean', formatLogValue(metrics.courantMean), courantMeanText, courantMeanClass));

        const uValues = Object.values(metrics.residualU).filter((value) => !Number.isNaN(value));
        const maxU = uValues.length ? Math.max(...uValues) : null;
        const [residualUText, residualUClass] = thresholdStatus(maxU, 1e-6);
        rowStates.push(setSafetyRow('residualU', maxU === null ? '-' : `max ${formatLogValue(maxU)}`, residualUText, residualUClass));

        const [residualPrghText, residualPrghClass] = thresholdStatus(metrics.residualPrgh, 1e-5);
        rowStates.push(setSafetyRow('residualPrgh', formatLogValue(metrics.residualPrgh), residualPrghText, residualPrghClass));

        const hH2OValues = Object.values(metrics.residualHH2O).filter((value) => !Number.isNaN(value));
        const maxHH2O = hH2OValues.length ? Math.max(...hH2OValues) : null;
        const [residualHH2OText, residualHH2OClass] = thresholdStatus(maxHH2O, 1e-6);
        rowStates.push(setSafetyRow('residualHH2O', maxHH2O === null ? '-' : `max ${formatLogValue(maxHH2O)}`, residualHH2OText, residualHH2OClass));

        const hasContinuity = metrics.continuityLocal !== null && metrics.continuityGlobal !== null
            && !Number.isNaN(metrics.continuityLocal) && !Number.isNaN(metrics.continuityGlobal);
        const continuityMax = hasContinuity
            ? Math.max(Math.abs(metrics.continuityLocal), Math.abs(metrics.continuityGlobal))
            : null;
        const [continuityText, continuityClass] = thresholdStatus(continuityMax, 1e-5);
        const continuityValue = hasContinuity
            ? `local ${formatLogValue(metrics.continuityLocal)} / global ${formatLogValue(metrics.continuityGlobal)}`
            : '-';
        rowStates.push(setSafetyRow('continuity', continuityValue, continuityText, continuityClass));

        const knownStates = rowStates.filter((stateName) => stateName !== 'waiting');
        let summaryText = 'Menunggu log';
        let summaryClass = 'waiting';
        if (knownStates.includes('danger')) {
            summaryText = 'Ada batas terlewati';
            summaryClass = 'danger';
        } else if (knownStates.includes('warn')) {
            summaryText = 'Mendekati batas';
            summaryClass = 'warn';
        } else if (knownStates.length > 0) {
            summaryText = 'Dalam batas aman';
            summaryClass = 'safe';
        }

        safetySummary.className = `solver-safety-summary is-${summaryClass}`;
        safetySummary.innerHTML = `<span class="solver-safety-dot"></span>${summaryText}`;
    }

    function statusText(state) {
        if (state.running) {
            return 'Process is running...';
        }
        if (state.returncode === 0) {
            return 'Process completed successfully.';
        }
        if (state.resume_available || state.status === 'stopped') {
            return 'Solver stopped. Ready to resume from latest checkpoint.';
        }
        if (state.status === 'cancelled') {
            return 'Process cancelled.';
        }
        if (state.returncode !== null && state.returncode !== undefined) {
            return 'Process failed or cancelled.';
        }
        if (!state.meshing_ready) {
            return 'Meshing must be completed before running solver.';
        }
        return 'Waiting for processor setup and initial fields...';
    }

    window.createSimulationTerminal({
        root,
        canStart(state) {
            return state.meshing_ready || state.resume_available;
        },
        statusText,
        onState(state) {
            meshingWarning.classList.toggle('d-none', state.meshing_ready);
            updateSolverSafety(state.lines || []);
        }
    });
});
