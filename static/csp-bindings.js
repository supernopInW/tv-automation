(() => {
    'use strict';

    const callGlobal = (name, args = []) => {
        const handler = window[name];
        if (typeof handler === 'function') {
            return handler(...args);
        }
        return undefined;
    };

    const actionHandlers = {
        'confirmResponsibilitySetup': () => callGlobal('confirmResponsibilitySetup'),
        'uploadExcelFile': () => callGlobal('uploadExcelFile'),
        'autoSelectThaiHolidays': () => callGlobal('autoSelectThaiHolidays'),
        'clearSelectedHolidays': () => callGlobal('clearSelectedHolidays'),
        'generateAutoMonthPlanFromWebUI': () => callGlobal('generateAutoMonthPlanFromWebUI'),
        'addNewRow': () => callGlobal('addNewRow'),
        'generateMonthScheduleOnWeb': () => callGlobal('generateMonthScheduleOnWeb'),
        'exportPlanToExcel': () => callGlobal('exportPlanToExcel'),
        'clearPlanTable': () => callGlobal('clearPlanTable'),
        'toggleAllRowsUseAllTambons': (element) => callGlobal('toggleAllRowsUseAllTambons', [element.dataset.value === 'true']),
        'openFileInput': () => document.getElementById('file-input')?.click(),
    };

    const dispatchAction = (element, event) => {
        const action = element.dataset.cspAction;
        if (!action) return;
        if (action === 'switchPlanCreationTab') {
            callGlobal('switchPlanCreationTab', [element.dataset.value]);
            return;
        }
        if (action === 'toggleHolidayDay') {
            callGlobal('toggleHolidayDay', [Number(element.dataset.day)]);
            return;
        }
        if (action === 'deleteRow') {
            callGlobal('deleteRow', [Number(element.dataset.rowIndex)]);
            return;
        }
        const handler = actionHandlers[action];
        if (handler) handler(element, event);
    };

    const dispatchChange = (element, event) => {
        const name = element.dataset.cspChange;
        if (!name) return;
        if (name === 'handleFileSelect') {
            callGlobal(name, [event]);
            return;
        }
        const rowIndex = element.dataset.rowIndex === undefined
            ? undefined
            : Number(element.dataset.rowIndex);
        if (name === 'syncSelectFulltext') {
            callGlobal(name, [element.dataset.targetId]);
        } else if (rowIndex !== undefined && Number.isInteger(rowIndex)) {
            callGlobal(name, [rowIndex]);
        } else {
            callGlobal(name, []);
        }
        const after = element.dataset.after;
        if (after) callGlobal(after, [element.dataset.targetId]);
    };

    document.addEventListener('click', (event) => {
        const element = event.target.closest('[data-csp-action]');
        if (!element) return;
        dispatchAction(element, event);
    });

    document.addEventListener('change', (event) => {
        const element = event.target.closest('[data-csp-change]');
        if (!element) return;
        dispatchChange(element, event);
    });

    document.addEventListener('dragover', (event) => {
        const element = event.target.closest('[data-csp-dragover]');
        if (element) event.preventDefault();
    });

    document.addEventListener('drop', (event) => {
        const element = event.target.closest('[data-csp-drop]');
        if (!element) return;
        event.preventDefault();
        callGlobal(element.dataset.cspDrop, [event]);
    });
})();
