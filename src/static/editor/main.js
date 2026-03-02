/**
 * Editor entry point.
 *
 * Reads model-specific configuration from the inline script, wires up
 * the customization controller and renderer, and attaches global hooks
 * needed by template-generated onclick handlers.
 */

import { getModelConfig } from "./modelConfig.js";
import { getDomRefs } from "./dom.js";
import { createCustomizationController } from "./customization.js";
import { createRenderer } from "./rendering.js";

const config = getModelConfig();
const dom = getDomRefs();

// The renderer is referenced in the customization callback, so we
// declare it first and assign after both are constructed.
let renderer;

const customization = createCustomizationController({
    defaultCustomization: config.defaultCustomization,
    additionalParamNames: config.additionalParamNames,
    onChanged() {
        renderer.triggerAutoRender();
    },
});

renderer = createRenderer({
    workerUrl: config.workerUrl,
    scadInputPath: config.scadInputPath,
    exportFilenamePrefix: config.exportFilenamePrefix,
    umamiTrackRender: config.umamiTrackRender,
    umamiTrackExport: config.umamiTrackExport,
    dom,
    getCustomization: customization.getCurrentCustomization,
    getAdditionalParamNames: customization.getAdditionalParamNames,
});

customization.attachInputListeners();

// Expose for template-generated onclick="setValueFromButton(...)" attributes.
window.setValueFromButton = (name, value) => customization.setValue(name, value);

// ── navigation & initial render ──────────────────────────────────────

navigation.addEventListener("navigate", (event) => {
    if (!event.canIntercept) {
        return;
    }

    const destination = new URL(event.destination.url);
    const current = new URL(window.location.href);
    const isSameDocument = destination.origin === current.origin &&
        destination.pathname === current.pathname &&
        destination.search === current.search;
    if (!isSameDocument) {
        return;
    }

    event.intercept({
        scroll: "manual",
        focusReset: "manual",
        handler: async () => {
            if (event.info && event.info.type === "customization-sync") {
                return;
            }

            customization.restoreFromHash(destination.hash);
            renderer.triggerAutoRender();
        },
    });
});

window.addEventListener("load", () => {
    customization.restoreFromHash(window.location.hash, { normalizeUrl: true });
    renderer.startRender();
});
