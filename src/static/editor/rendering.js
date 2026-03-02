/**
 * Worker lifecycle, render orchestration, camera application, error
 * display and STL download.
 */

import { trackUmamiEvent } from "./analytics.js";

// ── camera helper ────────────────────────────────────────────────────

function applyCameraFromSummary(camera, modelViewer) {
    if (!camera) {
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

// ── renderer factory ─────────────────────────────────────────────────

/**
 * @param {object} opts
 * @param {string}   opts.workerUrl
 * @param {string}   opts.scadInputPath
 * @param {string}   opts.exportFilenamePrefix
 * @param {*}        opts.umamiTrackRender   - null or string[]
 * @param {*}        opts.umamiTrackExport   - null or string[]
 * @param {object}   opts.dom                - from getDomRefs()
 * @param {function} opts.getCustomization   - () => currentCustomization object
 * @param {function} opts.getAdditionalParamNames - () => string[]
 */
export function createRenderer({
    workerUrl,
    scadInputPath,
    exportFilenamePrefix,
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

    function setRendering(rendering) {
        isRendering = rendering;
        dom.renderButton.disabled = rendering;
        dom.downloadStlButton.disabled = rendering;
        if (rendering) {
            lastResult = null;
            dom.renderState.classList.remove("d-none");
        } else {
            dom.renderState.classList.add("d-none");
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
        setRendering(false);
    });

    worker.addEventListener("messageerror", (event) => {
        console.error("Worker message error", event);
        showRenderError(dom, {
            summary: "Worker message error",
            log: String(event && event.message ? event.message : event),
        });
        setRendering(false);
    });

    worker.addEventListener("message", (event) => {
        if (!event.data || typeof event.data !== "object") {
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
            const link = document.createElement("a");
            link.href = URL.createObjectURL(new Blob([lastResult.stl], { type: "application/octet-stream" }));
            link.download = exportFilenamePrefix + ".stl";
            document.body.appendChild(link);
            link.click();
            link.remove();
            if (umamiTrackExport !== null) {
                trackUmamiEvent("export-stl", umamiTrackExport, getCustomization());
            }
        }
    });

    return {
        startRender,
        triggerAutoRender,
    };
}
