/**
 * Scope for user-supplied JavaScript expressions (display conditions,
 * export-file-stem).
 *
 * Parameter names may be dotted paths (CadQuery models use "lid.height" for a
 * field of a nested parameter model). Expressions see them as nested objects,
 * so they can be written as `lid.height > 5`.
 */

export function buildScope(customization) {
    const scope = {};
    for (const [name, value] of Object.entries(customization)) {
        const parts = name.split(".");
        let target = scope;
        for (const part of parts.slice(0, -1)) {
            if (typeof target[part] !== "object" || target[part] === null) {
                target[part] = {};
            }
            target = target[part];
        }
        target[parts[parts.length - 1]] = value;
    }
    return scope;
}

/**
 * Compile an expression into a function of the customization.
 *
 * @param {string} expression
 * @param {object} customization - provides the parameter names
 * @returns {function(object): *} evaluates the expression for a customization
 */
export function compileExpression(expression, customization) {
    const names = Object.keys(buildScope(customization));
    const fn = new Function(...names, "return " + expression);
    return (current) => {
        const scope = buildScope(current);
        return fn(...names.map((n) => scope[n]));
    };
}
