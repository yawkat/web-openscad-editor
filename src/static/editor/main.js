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
import {
    loadProfilesState,
    saveProfilesState,
    sanitizeCustomization,
    createProfileId,
    renderProfilesSelect,
} from "./profiles.js";

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

function getBareHash() {
    const h = window.location.hash;
    return !h || h === "#" ? "" : h;
}

function isBareEditorLoad() {
    return getBareHash() === "";
}

function initProfilesUi() {
    const select = dom.profileSelect;
    if (!select) {
        return;
    }
    let state = loadProfilesState();
    renderProfilesSelect(select, state);

    function getSelectedId() {
        return select.value || "";
    }

    function getSelectedProfile() {
        const id = getSelectedId();
        return id && state.profiles[id] ? state.profiles[id] : null;
    }

    function syncButtons() {
        const hasSelection = !!getSelectedProfile();
        if (dom.profileSaveButton) dom.profileSaveButton.disabled = !hasSelection;
        if (dom.profileDeleteButton) dom.profileDeleteButton.disabled = !hasSelection;
        if (dom.profileSetDefaultButton) dom.profileSetDefaultButton.disabled = !hasSelection;
    }

    function rerender() {
        state = loadProfilesState();
        renderProfilesSelect(select, state);
        syncButtons();
    }

    if (isBareEditorLoad() && state.defaultProfileId && state.profiles[state.defaultProfileId]) {
        const prof = state.profiles[state.defaultProfileId];
        const sanitized = sanitizeCustomization(prof.customization, config.defaultCustomization);
        customization.applyCustomization(sanitized);
    }

    select.addEventListener("change", () => {
        const prof = getSelectedProfile();
        if (prof) {
            const sanitized = sanitizeCustomization(prof.customization, config.defaultCustomization);
            customization.applyCustomization(sanitized);
        }
        syncButtons();
    });

    if (dom.profileNewButton) {
        dom.profileNewButton.addEventListener("click", () => {
            const nameRaw = window.prompt("Profile name:");
            if (nameRaw === null) {
                return;
            }
            const name = nameRaw.trim();
            if (!name) {
                return;
            }
            const id = createProfileId();
            const state2 = loadProfilesState();
            state2.profiles[id] = {
                name: name.slice(0, 120),
                customization: sanitizeCustomization(customization.getCurrentCustomization(), config.defaultCustomization),
            };
            saveProfilesState(state2);
            rerender();
            select.value = id;
            syncButtons();
        });
    }

    if (dom.profileSaveButton) {
        dom.profileSaveButton.addEventListener("click", () => {
            const id = getSelectedId();
            if (!id || !state.profiles[id]) {
                return;
            }
            const state2 = loadProfilesState();
            const existing = state2.profiles[id];
            if (!existing) {
                return;
            }
            existing.customization = sanitizeCustomization(customization.getCurrentCustomization(), config.defaultCustomization);
            saveProfilesState(state2);
            rerender();
        });
    }

    if (dom.profileDeleteButton) {
        dom.profileDeleteButton.addEventListener("click", () => {
            const id = getSelectedId();
            if (!id || !state.profiles[id]) {
                return;
            }
            const state2 = loadProfilesState();
            delete state2.profiles[id];
            if (state2.defaultProfileId === id) {
                state2.defaultProfileId = null;
            }
            saveProfilesState(state2);
            rerender();
        });
    }

    if (dom.profileSetDefaultButton) {
        dom.profileSetDefaultButton.addEventListener("click", () => {
            const id = getSelectedId();
            if (!id || !state.profiles[id]) {
                return;
            }
            const state2 = loadProfilesState();
            state2.defaultProfileId = id;
            saveProfilesState(state2);
            rerender();
        });
    }

    syncButtons();
}

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
    initProfilesUi();
    renderer.startRender();
});
