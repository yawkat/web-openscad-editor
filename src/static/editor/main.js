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
    const list = dom.profilesList;
    if (!list) {
        return;
    }
    let state = loadProfilesState(config.scadInputPath);

    function sortedProfileIds(profiles) {
        return Object.keys(profiles).sort((a, b) => a.localeCompare(b));
    }

    function createIconButton(icon, title, btnClass = "btn-outline-secondary") {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = `btn btn-sm ${btnClass}`;
        btn.title = title;
        btn.ariaLabel = title;
        btn.textContent = icon;
        return btn;
    }

    function createTextButton(text, title, btnClass = "btn-outline-primary") {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = `btn btn-sm ${btnClass}`;
        btn.title = title;
        btn.ariaLabel = title;
        btn.textContent = text;
        return btn;
    }

    function nextProfileName(profiles) {
        let max = 0;
        for (const profile of Object.values(profiles)) {
            const m = /^Profile #(\d+)$/.exec(profile?.name ?? "");
            if (m) {
                max = Math.max(max, Number(m[1]));
            }
        }
        return `Profile #${max + 1}`;
    }

    function reloadStateAndRender() {
        const openDetails = new Set(
            Array.from(list.querySelectorAll("details[data-profile-id][open]"))
                .map((d) => d.getAttribute("data-profile-id"))
                .filter((v) => !!v),
        );
        state = loadProfilesState(config.scadInputPath);
        renderList(openDetails);
    }

    function applyProfile(id, reset) {
        const profile = state.profiles[id];
        if (!profile) {
            return;
        }
        const sanitized = sanitizeCustomization(profile.customization, config.defaultCustomization);
        customization.applyCustomization(sanitized, { reset });
    }

    function deleteProfileOption(id, optionName) {
        const state2 = loadProfilesState(config.scadInputPath);
        const profile = state2.profiles[id];
        if (!profile || !profile.customization || !(optionName in profile.customization)) {
            return;
        }
        delete profile.customization[optionName];
        saveProfilesState(state2, config.scadInputPath);
        reloadStateAndRender();
    }

    function createProfileRow(id, profile, openDetails) {
        const row = document.createElement("div");
        row.className = "list-group-item";

        const top = document.createElement("div");
        top.className = "d-flex align-items-center justify-content-between gap-2 flex-wrap";

        const title = document.createElement("div");
        title.className = "fw-semibold d-flex align-items-center gap-2";
        const nameText = document.createElement("span");
        nameText.textContent = profile.name;
        const editLink = document.createElement("button");
        editLink.type = "button";
        editLink.className = "btn btn-link btn-sm p-0";
        editLink.textContent = "✏️";
        editLink.title = "Rename";
        editLink.ariaLabel = "Rename";
        title.appendChild(nameText);
        title.appendChild(editLink);
        top.appendChild(title);

        const actions = document.createElement("div");
        actions.className = "btn-group btn-group-sm";

        editLink.addEventListener("click", () => {
            const nameRaw = window.prompt("Profile name:", profile.name);
            if (nameRaw === null) {
                return;
            }
            const name = nameRaw.trim();
            if (!name) {
                return;
            }
            const state2 = loadProfilesState(config.scadInputPath);
            const existing = state2.profiles[id];
            if (!existing) {
                return;
            }
            existing.name = name.slice(0, 120);
            saveProfilesState(state2, config.scadInputPath);
            reloadStateAndRender();
        });

        const storeBtn = createIconButton("⇄", "Store current settings");
        storeBtn.addEventListener("click", () => {
            const state2 = loadProfilesState(config.scadInputPath);
            const existing = state2.profiles[id];
            if (!existing) {
                return;
            }
            existing.customization = sanitizeCustomization(customization.getCurrentCustomization(), config.defaultCustomization);
            saveProfilesState(state2, config.scadInputPath);
            reloadStateAndRender();
        });

        const applyBtn = createTextButton("Apply", "Apply profile", "btn-outline-primary");
        applyBtn.addEventListener("click", () => applyProfile(id, false));

        const applyResetBtn = createTextButton("Clean Apply", "Apply profile after reset", "btn-outline-primary");
        applyResetBtn.addEventListener("click", () => applyProfile(id, true));

        const deleteBtn = createIconButton("✕", "Delete profile", "btn-outline-danger");
        deleteBtn.addEventListener("click", () => {
            const state2 = loadProfilesState(config.scadInputPath);
            if (!(id in state2.profiles)) {
                return;
            }
            delete state2.profiles[id];
            saveProfilesState(state2, config.scadInputPath);
            reloadStateAndRender();
        });

        const defaultWrap = document.createElement("label");
        defaultWrap.className = "form-check-label d-flex align-items-center gap-2 mt-2 small";
        const defaultCheckbox = document.createElement("input");
        defaultCheckbox.type = "checkbox";
        defaultCheckbox.className = "form-check-input mt-0";
        defaultCheckbox.checked = !!state.profiles[id]?.applyByDefault;
        defaultCheckbox.addEventListener("change", () => {
            const state2 = loadProfilesState(config.scadInputPath);
            const profile2 = state2.profiles[id];
            if (!profile2) {
                return;
            }
            profile2.applyByDefault = defaultCheckbox.checked;
            saveProfilesState(state2, config.scadInputPath);
            reloadStateAndRender();
        });
        const defaultLabelText = document.createElement("span");
        defaultLabelText.textContent = "Apply by default";
        defaultWrap.appendChild(defaultCheckbox);
        defaultWrap.appendChild(defaultLabelText);

        actions.appendChild(storeBtn);
        actions.appendChild(applyBtn);
        actions.appendChild(applyResetBtn);
        actions.appendChild(deleteBtn);
        top.appendChild(actions);
        row.appendChild(top);
        row.appendChild(defaultWrap);

        const details = document.createElement("details");
        details.className = "mt-2";
        details.dataset.profileId = id;
        details.open = openDetails.has(id);
        const summary = document.createElement("summary");
        const options = Object.entries(profile.customization ?? {}).sort((a, b) => a[0].localeCompare(b[0]));
        summary.textContent = `Options (${options.length})`;
        details.appendChild(summary);

        if (options.length === 0) {
            const empty = document.createElement("div");
            empty.className = "text-muted small mt-2";
            empty.textContent = "No options saved in this profile.";
            details.appendChild(empty);
        } else {
            const ul = document.createElement("ul");
            ul.className = "list-group list-group-flush mt-2";
            for (const [optionName, optionValue] of options) {
                const li = document.createElement("li");
                li.className = "list-group-item px-0 d-flex align-items-center justify-content-between gap-2";

                const text = document.createElement("div");
                text.className = "small";
                text.textContent = `${optionName}: ${JSON.stringify(optionValue)}`;

                const deleteOptionBtn = createIconButton("✕", `Delete option ${optionName}`, "btn-outline-danger");
                deleteOptionBtn.addEventListener("click", () => deleteProfileOption(id, optionName));

                li.appendChild(text);
                li.appendChild(deleteOptionBtn);
                ul.appendChild(li);
            }
            details.appendChild(ul);
        }

        row.appendChild(details);
        return row;
    }

    function renderList(openDetails = new Set()) {
        list.textContent = "";

        for (const id of sortedProfileIds(state.profiles)) {
            const profile = state.profiles[id];
            if (!profile) {
                continue;
            }
            list.appendChild(createProfileRow(id, profile, openDetails));
        }

        const addRow = document.createElement("button");
        addRow.type = "button";
        addRow.className = "list-group-item list-group-item-action d-flex align-items-center gap-2";
        const plus = document.createElement("span");
        plus.textContent = "➕";
        const text = document.createElement("span");
        text.textContent = "Create profile from current settings";
        addRow.appendChild(plus);
        addRow.appendChild(text);
        addRow.addEventListener("click", () => {
            const id = createProfileId();
            const state2 = loadProfilesState(config.scadInputPath);
            state2.profiles[id] = {
                name: nextProfileName(state2.profiles),
                customization: customization.getChangedCustomization(),
                applyByDefault: false,
            };
            saveProfilesState(state2, config.scadInputPath);
            reloadStateAndRender();
        });
        list.appendChild(addRow);
    }

    if (isBareEditorLoad()) {
        const merged = {};
        for (const id of sortedProfileIds(state.profiles)) {
            const profile = state.profiles[id];
            if (!profile || !profile.applyByDefault) {
                continue;
            }
            Object.assign(merged, sanitizeCustomization(profile.customization, config.defaultCustomization));
        }
        customization.applyCustomization(merged, { reset: true });
    }

    renderList();
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
