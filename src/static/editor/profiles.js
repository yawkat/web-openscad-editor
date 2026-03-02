const STORAGE_KEY = "wose.profiles.v1";

/** @typedef {{ name: string, customization: object }} Profile */
/** @typedef {{ profiles: Record<string, Profile>, defaultProfileId: (string|null) }} ProfilesState */

export function loadProfilesState() {
    try {
        const raw = window.localStorage.getItem(STORAGE_KEY);
        if (!raw) {
            return { profiles: {}, defaultProfileId: null };
        }
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== "object") {
            return { profiles: {}, defaultProfileId: null };
        }
        const profiles = parsed.profiles && typeof parsed.profiles === "object" ? parsed.profiles : {};
        const defaultProfileId = typeof parsed.defaultProfileId === "string" ? parsed.defaultProfileId : null;
        return { profiles, defaultProfileId };
    } catch (e) {
        console.warn("Failed to load profiles from localStorage", e);
        return { profiles: {}, defaultProfileId: null };
    }
}

export function saveProfilesState(state) {
    try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (e) {
        console.warn("Failed to save profiles to localStorage", e);
    }
}

export function sanitizeCustomization(customization, defaultCustomization) {
    const result = {};
    if (!customization || typeof customization !== "object" || Array.isArray(customization)) {
        return result;
    }
    for (const k of Object.keys(defaultCustomization)) {
        if (k in customization) {
            result[k] = customization[k];
        }
    }
    return result;
}

export function createProfileId() {
    return "p_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
}

export function renderProfilesSelect(select, state) {
    const currentValue = select.value;
    select.textContent = "";

    const ids = Object.keys(state.profiles);
    ids.sort((a, b) => {
        const an = state.profiles[a]?.name ?? "";
        const bn = state.profiles[b]?.name ?? "";
        return an.localeCompare(bn);
    });

    for (const id of ids) {
        const profile = state.profiles[id];
        if (!profile) {
            continue;
        }
        const opt = document.createElement("option");
        opt.value = id;
        const isDefault = state.defaultProfileId === id;
        opt.textContent = profile.name + (isDefault ? " (default)" : "");
        select.appendChild(opt);
    }

    const hasDefault = state.defaultProfileId && state.profiles[state.defaultProfileId];
    if (!hasDefault) {
        state.defaultProfileId = null;
    }

    if (currentValue && state.profiles[currentValue]) {
        select.value = currentValue;
    } else if (state.defaultProfileId && state.profiles[state.defaultProfileId]) {
        select.value = state.defaultProfileId;
    } else {
        select.value = ids[0] ?? "";
    }
}
