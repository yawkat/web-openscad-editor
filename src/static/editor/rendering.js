/**
 * Worker lifecycle, render orchestration, camera application, error
 * display and STL download.
 */

import { trackUmamiEvent } from "./analytics.js";
import { compileExpression } from "./scope.js";

// ── camera helper ────────────────────────────────────────────────────

function applyCameraFromSummary(camera, modelViewer) {
    if (!camera) {
        // No camera information (e.g. CadQuery models): let model-viewer
        // frame the model automatically.
        modelViewer.removeAttribute("camera-orbit");
        modelViewer.removeAttribute("camera-target");
        return;
    }
    const rotation = camera.rotation;
    const distance = camera.distance;
    const translation = camera.translation;

    let theta = 25, phi = 55, radius = "auto";
    if (Array.isArray(rotation) && rotation.length === 3) {
        phi = rotation[0];
        theta = rotation[2];
    }
    if (typeof distance === "number") {
        radius = (distance * 0.001) + "m";
    }

    let target = "auto auto auto";
    if (Array.isArray(translation) && translation.length === 3) {
        const tx = translation[0] * 0.001;
        const ty = translation[2] * 0.001;
        const tz = -translation[1] * 0.001;
        target = tx + "m " + ty + "m " + tz + "m";
    }

    modelViewer.setAttribute("camera-orbit", theta + "deg " + phi + "deg " + radius);
    modelViewer.setAttribute("camera-target", target);
}

// ── error helpers ────────────────────────────────────────────────────

function setRenderErrorVisible(dom, visible) {
    if (visible) {
        dom.renderError.classList.remove("d-none");
    } else {
        dom.renderError.classList.add("d-none");
    }
}

function clearRenderError(dom) {
    dom.renderErrorSummary.textContent = "";
    dom.renderErrorLog.textContent = "";
    setRenderErrorVisible(dom, false);
}

function showRenderError(dom, { summary, log }) {
    dom.renderErrorSummary.textContent = summary || "Render failed";
    dom.renderErrorLog.textContent = log || "";
    setRenderErrorVisible(dom, true);
}

function setProgress(dom, message) {
    if (!dom.renderProgress) {
        return;
    }
    dom.renderProgress.textContent = message || "";
    dom.renderProgress.classList.toggle("d-none", !message);
}

// ── export file naming ───────────────────────────────────────────────

function evaluateExportFileStem(exportFileStem, customization) {
    if (exportFileStem === null) {
        return "";
    }
    if (exportFileStem.js != null) {
        try {
            const evaluated = compileExpression(String(exportFileStem.js), customization)(customization);
            return evaluated == null ? "" : String(evaluated);
        } catch (e) {
            console.warn("Failed to evaluate export-file-stem expression", e);
            if (exportFileStem.fixed != null) {
                return String(exportFileStem.fixed);
            }
            return "";
        }
    }
    if (exportFileStem.fixed != null) {
        return String(exportFileStem.fixed);
    }
    return "";
}

function downloadBytes(bytes, filename, mimeType) {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([bytes], { type: mimeType }));
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
}

// ── renderer factory ─────────────────────────────────────────────────

/**
 * @param {object} opts
 * @param {string}   opts.workerUrl
 * @param {string}   opts.scadInputPath
 * @param {string}   opts.previewStyle
 * @param {*}        opts.exportFileStem     - null or {fixed?: string, js?: string}
 * @param {*}        opts.umamiTrackRender   - null or string[]
 * @param {*}        opts.umamiTrackExport   - null or string[]
 * @param {object}   opts.dom                - from getDomRefs()
 * @param {function} opts.getCustomization   - () => currentCustomization object
 * @param {function} opts.getAdditionalParamNames - () => string[]
 */
export function createRenderer({
    workerUrl,
    scadInputPath,
    previewStyle,
    exportFileStem,
    umamiTrackRender,
    umamiTrackExport,
    dom,
    getCustomization,
    getAdditionalParamNames,
}) {
    const worker = new Worker(workerUrl, { type: "module" });

    let isRendering = false;
    let isDirty = false;
    let lastResult = null;
    let isInitialRender = true;
    let isExporting = false;

    function setExporting(exporting) {
        isExporting = exporting;
        if (dom.downloadStepButton) {
            dom.downloadStepButton.disabled = exporting || isRendering;
        }
        if (dom.downloadStepState) {
            dom.downloadStepState.classList.toggle("d-none", !exporting);
        }
    }

    function exportFilename(extension) {
        return evaluateExportFileStem(exportFileStem, getCustomization()) + "." + extension;
    }

    function setRendering(rendering) {
        isRendering = rendering;
        dom.renderButton.disabled = rendering;
        dom.downloadStlButton.disabled = rendering;
        if (dom.downloadStepButton) {
            dom.downloadStepButton.disabled = rendering || isExporting;
        }
        if (rendering) {
            lastResult = null;
            dom.renderState.classList.remove("d-none");
            dom.modelViewer.classList.add("is-outdated");
            dom.modelViewer.setAttribute("aria-busy", "true");
            if (dom.modelLoadingOverlay) {
                dom.modelLoadingOverlay.classList.remove("d-none");
            }
        } else {
            setProgress(dom, "");
            dom.renderState.classList.add("d-none");
            dom.modelViewer.classList.remove("is-outdated");
            dom.modelViewer.setAttribute("aria-busy", "false");
            if (dom.modelLoadingOverlay) {
                dom.modelLoadingOverlay.classList.add("d-none");
            }
            if (isDirty) {
                isDirty = false;
                startRender();
            }
        }
    }

    // ── worker event handlers ───────────────────────────────────────

    worker.addEventListener("error", (event) => {
        console.error("Worker script error", event);
        showRenderError(dom, {
            summary: "Worker crashed while rendering",
            log: String(event && event.message ? event.message : event),
        });
        setExporting(false);
        setRendering(false);
    });

    worker.addEventListener("messageerror", (event) => {
        console.error("Worker message error", event);
        showRenderError(dom, {
            summary: "Worker message error",
            log: String(event && event.message ? event.message : event),
        });
        setExporting(false);
        setRendering(false);
    });

    worker.addEventListener("message", (event) => {
        if (!event.data || typeof event.data !== "object") {
            return;
        }
        if (event.data.type === "progress") {
            // The CadQuery runtime starts loading before the first render
            // starts, so show progress regardless of the render state. It is
            // cleared when the render finishes.
            setProgress(dom, event.data.message);
            return;
        }
        if (event.data.type === "export-ok") {
            setExporting(false);
            downloadBytes(event.data.bytes, exportFilename(event.data.format), "application/octet-stream");
            if (umamiTrackExport !== null) {
                trackUmamiEvent("export-" + event.data.format, umamiTrackExport, getCustomization());
            }
            return;
        }
        if (event.data.type === "export-error") {
            setExporting(false);
            console.error("Export error", event.data);
            showRenderError(dom, {
                summary: "Export failed: " + (event.data.error || "unknown error"),
                log: event.data.log || "",
            });
            return;
        }
        if (event.data.type === "ok") {
            lastResult = event.data;
            dom.modelViewer.src = URL.createObjectURL(new Blob([event.data.glb], { type: "model/gltf-binary" }));
            applyCameraFromSummary(event.data.camera, dom.modelViewer);
            clearRenderError(dom);
            setRendering(false);
            if (!isInitialRender && umamiTrackRender !== null) {
                trackUmamiEvent("render", umamiTrackRender, getCustomization());
            }
            isInitialRender = false;
        }
        if (event.data.type === "error") {
            console.error("Worker error", event.data);
            const summary = event.data && event.data.error ? String(event.data.error) : "Render failed";
            const parts = [];
            if (event.data && event.data.log) {
                parts.push(String(event.data.log));
            }
            if (event.data && event.data.stack) {
                const stack = String(event.data.stack);
                if (stack.trim()) {
                    parts.push("\n---\n" + stack);
                }
            }
            showRenderError(dom, { summary, log: parts.join("\n") });
            setRendering(false);
        }
    });

    // ── render control ──────────────────────────────────────────────

    function startRender() {
        clearRenderError(dom);
        setRendering(true);
        const currentCustomization = getCustomization();
        const additionalParamNames = getAdditionalParamNames();
        const normalParams = {};
        const additionalParams = {};
        for (const field in currentCustomization) {
            if (additionalParamNames.includes(field)) {
                additionalParams[field] = currentCustomization[field];
            } else {
                normalParams[field] = currentCustomization[field];
            }
        }
        worker.postMessage({
            type: "render",
            input: scadInputPath,
            previewStyle: previewStyle || "shaded",
            normalParams: normalParams,
            additionalParams: additionalParams,
        });
    }

    function triggerAutoRender() {
        if (!dom.autoRenderCheckbox.checked) {
            return;
        }
        if (isRendering) {
            isDirty = true;
        } else {
            startRender();
        }
    }

    // ── UI event handlers ───────────────────────────────────────────

    dom.renderErrorCopy.addEventListener("click", async () => {
        const text = dom.renderErrorLog.textContent || "";
        try {
            await navigator.clipboard.writeText(text);
        } catch (e) {
            console.warn("Failed to copy log to clipboard", e);
        }
    });

    dom.renderButton.addEventListener("click", function () {
        if (!this.disabled) {
            startRender();
        }
    });

    dom.downloadStlButton.addEventListener("click", function () {
        if (lastResult != null) {
            downloadBytes(lastResult.stl, exportFilename("stl"), "application/octet-stream");
            if (umamiTrackExport !== null) {
                trackUmamiEvent("export-stl", umamiTrackExport, getCustomization());
            }
        }
    });

    if (dom.downloadStepButton) {
        // STEP files are generated on demand from the last render, since
        // exporting is slower than tessellating.
        dom.downloadStepButton.addEventListener("click", function () {
            if (lastResult != null && !isExporting) {
                setExporting(true);
                worker.postMessage({ type: "export", format: "step" });
            }
        });
    }

    return {
        startRender,
        triggerAutoRender,
    };
}
