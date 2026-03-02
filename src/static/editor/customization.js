/**
 * Customization state management, URL-hash synchronization, input
 * synchronization, and modification indicators.
 *
 * The controller owns `defaultCustomization` (immutable after init) and
 * `currentCustomization` (mutable working copy).  All external access goes
 * through the returned API so that side effects (URL update, indicator
 * refresh, auto-render trigger) happen consistently.
 */

const DEBUG_CUSTOMIZATION_HASH = false;

// ── helpers ──────────────────────────────────────────────────────────

function jsonEqual(a, b) {
    if (a === undefined && b === undefined) {
        return true;
    }
    return JSON.stringify(a) === JSON.stringify(b);
}

function base64EncodeUtf8(text) {
    const bytes = new TextEncoder().encode(text);
    let binary = "";
    for (const b of bytes) {
        binary += String.fromCharCode(b);
    }
    return btoa(binary);
}

function base64DecodeUtf8(text) {
    const binary = atob(text);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
    }
    return new TextDecoder().decode(bytes);
}

// ── controller factory ───────────────────────────────────────────────

/**
 * @param {object} opts
 * @param {object}   opts.defaultCustomization  - initial parameter values
 * @param {string[]} opts.additionalParamNames  - names of "additional" params
 * @param {function} opts.onChanged             - called after any value change
 */
export function createCustomizationController({ defaultCustomization, additionalParamNames, onChanged }) {
    // Deep-clone so mutations never leak back to the frozen default.
    const currentCustomization = JSON.parse(JSON.stringify(defaultCustomization));

    // ── conditional display predicates ──────────────────────────────
    const conditionalElements = [];
    for (const elem of document.querySelectorAll("[data-display-condition]")) {
        const js = elem.dataset.displayCondition;
        conditionalElements.push({
            element: elem,
            predicate: new Function(...Object.keys(currentCustomization), "return " + js),
        });
    }

    // ── private helpers ─────────────────────────────────────────────

    function computeChangedCustomization() {
        const changed = {};
        for (const [k, defaultValue] of Object.entries(defaultCustomization)) {
            if (!jsonEqual(currentCustomization[k], defaultValue)) {
                changed[k] = currentCustomization[k];
            }
        }
        return changed;
    }

    function resetCurrentCustomizationToDefault() {
        for (const [k, v] of Object.entries(defaultCustomization)) {
            currentCustomization[k] = JSON.parse(JSON.stringify(v));
        }
    }

    function isParamModified(name) {
        if (!(name in defaultCustomization)) {
            return false;
        }
        const defaultValue = defaultCustomization[name];
        const currentValue = currentCustomization[name];
        if (Array.isArray(defaultValue)) {
            const maxLen = Math.max(defaultValue.length, Array.isArray(currentValue) ? currentValue.length : 0);
            for (let i = 0; i < maxLen; i++) {
                if (!jsonEqual(currentValue?.[i], defaultValue?.[i])) {
                    return true;
                }
            }
            return false;
        }
        return !jsonEqual(currentValue, defaultValue);
    }

    function updateUrlFromCustomization() {
        const changed = computeChangedCustomization();
        const json = Object.keys(changed).length === 0 ? "" : JSON.stringify(changed);
        const hash = json === "" ? "" : encodeURIComponent(base64EncodeUtf8(json));
        const url = new URL(window.location.href);
        url.hash = hash === "" ? "" : "#" + hash;

        if (url.href === window.location.href) {
            return;
        }

        if (DEBUG_CUSTOMIZATION_HASH) {
            console.log("updateUrlFromCustomization", { changed, hash: url.hash });
        }

        navigation.navigate(url.href, {
            history: "replace",
            state: navigation.currentEntry.getState() ?? null,
            info: { type: "customization-sync" },
        });
    }

    function syncCustomizationIndicators() {
        for (const group of document.querySelectorAll(".customizer-group")) {
            const name = group.getAttribute("attr-name");
            if (!name) {
                continue;
            }
            const modified = isParamModified(name);
            group.classList.toggle("is-modified", modified);
            const btn = group.querySelector(".customizer-reset");
            if (btn) {
                btn.disabled = !modified;
            }
        }
        for (const elem of conditionalElements) {
            elem.element.style.display = elem.predicate(...Object.values(currentCustomization)) ? "" : "none";
        }
    }

    function applyCustomizationToInputs() {
        for (const input of document.querySelectorAll(".customizer")) {
            const name = input.getAttribute("attr-name");
            const index = input.getAttribute("attr-index");
            const value = index !== null ? currentCustomization?.[name]?.[index] : currentCustomization?.[name];
            if (value === undefined) {
                continue;
            }

            if (input.type === "checkbox") {
                input.checked = !!value;
            } else if (input.type === "select-one") {
                let found = false;
                for (const option of input.options) {
                    try {
                        if (jsonEqual(JSON.parse(option.value), value)) {
                            input.value = option.value;
                            found = true;
                            break;
                        }
                    } catch (e) {
                        // Ignore unparsable option values.
                    }
                }
                if (!found) {
                    if (DEBUG_CUSTOMIZATION_HASH) {
                        console.warn("No matching <option> for value", { name, value });
                    }
                    input.value = JSON.stringify(value);
                }
            } else {
                input.value = String(value);
            }
        }

        syncCustomizationIndicators();
    }

    // ── public API ──────────────────────────────────────────────────

    function restoreFromHash(hashString, { normalizeUrl = false } = {}) {
        resetCurrentCustomizationToDefault();
        if (!hashString || hashString.length <= 1) {
            applyCustomizationToInputs();
            if (normalizeUrl) {
                updateUrlFromCustomization();
            }
            return;
        }

        let customizationFromUrl;
        try {
            customizationFromUrl = JSON.parse(base64DecodeUtf8(decodeURIComponent(hashString.slice(1))));
        } catch (e) {
            console.warn("Failed to parse customization from URL hash", e);
            applyCustomizationToInputs();
            if (normalizeUrl) {
                updateUrlFromCustomization();
            }
            return;
        }

        if (!customizationFromUrl || typeof customizationFromUrl !== "object" || Array.isArray(customizationFromUrl)) {
            applyCustomizationToInputs();
            if (normalizeUrl) {
                updateUrlFromCustomization();
            }
            return;
        }

        for (const [k, v] of Object.entries(customizationFromUrl)) {
            if (k in defaultCustomization) {
                currentCustomization[k] = v;
            }
        }

        applyCustomizationToInputs();
        if (normalizeUrl) {
            updateUrlFromCustomization();
        }
    }

    function setValue(name, value) {
        currentCustomization[name] = value;
        applyCustomizationToInputs();
        updateUrlFromCustomization();
        onChanged();
    }

    function attachInputListeners() {
        for (const input of document.querySelectorAll(".customizer")) {
            const name = input.getAttribute("attr-name");
            const index = input.getAttribute("attr-index");
            input.addEventListener("change", function () {
                let value;
                if (this.type === "checkbox") {
                    value = this.checked;
                } else if (this.type === "select-one") {
                    value = JSON.parse(this.value);
                } else if (this.type === "number") {
                    value = this.valueAsNumber;
                } else {
                    value = this.value;
                }
                if (index !== null) {
                    currentCustomization[name][index] = value;
                } else {
                    currentCustomization[name] = value;
                }

                updateUrlFromCustomization();
                syncCustomizationIndicators();
                onChanged();
            });
        }

        for (const btn of document.querySelectorAll(".customizer-reset")) {
            btn.addEventListener("click", () => {
                const name = btn.getAttribute("attr-name");
                if (!name || !(name in defaultCustomization)) {
                    return;
                }
                setValue(name, JSON.parse(JSON.stringify(defaultCustomization[name])));
            });
        }
    }

    function getCurrentCustomization() {
        return currentCustomization;
    }

    function getAdditionalParamNames() {
        return additionalParamNames;
    }

    return {
        restoreFromHash,
        setValue,
        attachInputListeners,
        getCurrentCustomization,
        getAdditionalParamNames,
    };
}
