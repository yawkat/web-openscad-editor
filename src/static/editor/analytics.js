/**
 * Umami analytics integration.
 *
 * trackUmamiEvent sends a custom event to Umami when the global `umami`
 * object is available.  `paramNames` controls which customization values
 * are included in the event data:
 *   - null          -> tracking disabled, no event fired
 *   - []            -> event fired with no parameter data
 *   - ["a", "b"]    -> event fired with values for parameters a and b
 */

export function trackUmamiEvent(eventName, paramNames, currentCustomization) {
    if (typeof umami === "undefined" || paramNames === null) {
        return;
    }
    const eventData = {};
    if (Array.isArray(paramNames)) {
        for (const paramName of paramNames) {
            if (paramName in currentCustomization) {
                eventData[paramName] = currentCustomization[paramName];
            }
        }
    }
    umami.track(eventName, eventData);
}
