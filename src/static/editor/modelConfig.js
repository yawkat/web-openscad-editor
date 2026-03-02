/**
 * Reads model-specific configuration from `window.__WOSE_MODEL__`.
 *
 * The inline script in the HTML template populates this object with all
 * Jinja2-derived values so that the external JS modules stay template-free.
 */

export function getModelConfig() {
    const cfg = window.__WOSE_MODEL__;
    if (!cfg || typeof cfg !== "object") {
        throw new Error("window.__WOSE_MODEL__ is missing or invalid");
    }
    return cfg;
}
