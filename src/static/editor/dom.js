/**
 * Central DOM element lookup.
 *
 * Gathering every getElementById / querySelector call in one place makes it
 * easy to see which elements the editor JS depends on.
 */

export function getDomRefs() {
    return {
        renderButton: document.getElementById("render"),
        renderState: document.getElementById("render-state"),
        renderProgress: document.getElementById("render-progress"),
        downloadStlButton: document.getElementById("download-stl"),
        // Only present for CadQuery models.
        downloadStepButton: document.getElementById("download-step"),
        downloadStepState: document.getElementById("download-step-state"),
        autoRenderCheckbox: document.getElementById("auto-render"),
        profilesList: document.getElementById("profiles-list"),
        renderError: document.getElementById("render-error"),
        renderErrorSummary: document.getElementById("render-error-summary"),
        renderErrorLog: document.getElementById("render-error-log"),
        renderErrorCopy: document.getElementById("render-error-copy"),
        modelViewer: document.getElementById("model"),
        modelLoadingOverlay: document.getElementById("model-loading-overlay"),
        modelLoadingBox: document.getElementById("model-loading-box"),
        modelLoadingSpinner: document.getElementById("model-loading-spinner"),
        modelLoadingBar: document.getElementById("model-loading-bar"),
    };
}
