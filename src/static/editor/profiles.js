const STORAGE_KEY = "wose.profiles.v1";

function resolveStorageKey(scopeKey) {
    if (!scopeKey) {
        return STORAGE_KEY;
    }
    return `${STORAGE_KEY}:${String(scopeKey)}`;
}

export function loadProfilesState(scopeKey = "") {
    try {
        const raw = window.localStorage.getItem(resolveStorageKey(scopeKey));
        if (!raw) {
            return { profiles: {} };
        }
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== "object") {
            return { profiles: {} };
        }
        const profilesRaw = parsed.profiles && typeof parsed.profiles === "object" ? parsed.profiles : {};
        const profiles = {};
        for (const [id, profile] of Object.entries(profilesRaw)) {
            if (!profile || typeof profile !== "object") {
                continue;
            }
            profiles[id] = {
                name: typeof profile.name === "string" ? profile.name : "Profile",
                customization: profile.customization && typeof profile.customization === "object" && !Array.isArray(profile.customization)
                    ? profile.customization
                    : {},
                applyByDefault: !!profile.applyByDefault,
            };
        }

        return { profiles };
    } catch (e) {
        console.warn("Failed to load profiles from localStorage", e);
        return { profiles: {} };
    }
}

export function saveProfilesState(state, scopeKey = "") {
    try {
        const normalizedProfiles = {};
        for (const [id, profile] of Object.entries(state.profiles || {})) {
            if (!profile || typeof profile !== "object") {
                continue;
            }
            normalizedProfiles[id] = {
                name: typeof profile.name === "string" ? profile.name : "Profile",
                customization: profile.customization && typeof profile.customization === "object" && !Array.isArray(profile.customization)
                    ? profile.customization
                    : {},
                applyByDefault: !!profile.applyByDefault,
            };
        }
        window.localStorage.setItem(resolveStorageKey(scopeKey), JSON.stringify({
            profiles: normalizedProfiles,
        }));
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
