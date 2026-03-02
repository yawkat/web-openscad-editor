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
        downloadStlButton: document.getElementById("download-stl"),
        autoRenderCheckbox: document.getElementById("auto-render"),
        renderError: document.getElementById("render-error"),
        renderErrorSummary: document.getElementById("render-error-summary"),
        renderErrorLog: document.getElementById("render-error-log"),
        renderErrorCopy: document.getElementById("render-error-copy"),
        modelViewer: document.getElementById("model"),
    };
}
