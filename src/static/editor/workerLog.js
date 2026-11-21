/**
 * Log buffering for the render workers. Everything logged during a render is
 * kept (up to a limit) so it can be shown in the error log modal.
 */

const MAX_LOG_CHARS = 1024 * 1024
let currentLog = ""
let currentLogTruncated = false

function stringifyLogValue(v) {
    if (v instanceof Error) {
        return v && v.stack ? String(v.stack) : String(v)
    }
    if (typeof v === "string") {
        return v
    }
    if (v === null) {
        return "null"
    }
    if (v === undefined) {
        return "undefined"
    }
    try {
        return JSON.stringify(v)
    } catch (e) {
        return String(v)
    }
}

function appendLogLine(line) {
    if (!line) {
        line = ""
    }
    currentLog += String(line) + "\n"
    if (currentLog.length > MAX_LOG_CHARS) {
        currentLog = currentLog.slice(currentLog.length - MAX_LOG_CHARS)
        if (!currentLogTruncated) {
            currentLogTruncated = true
            currentLog = "[log truncated]\n" + currentLog
        }
    }
}

function logToConsoleAndBuffer(level, ...args) {
    const line = args.map(stringifyLogValue).join(" ")
    appendLogLine(line)
    const fn = console[level] || console.log
    fn.apply(console, args)
}

export function logInfo(...args) {
    logToConsoleAndBuffer("log", ...args)
}

export function logError(...args) {
    logToConsoleAndBuffer("error", ...args)
}

export function formatErrorForMessage(e) {
    if (e instanceof Error) {
        return String(e && e.message ? e.message : e)
    }
    if (typeof e === "string") {
        return e
    }
    if (!e || typeof e !== "object") {
        return String(e)
    }

    const message = typeof e.message === "string" ? e.message.trim() : ""
    if (message) {
        return message
    }
    if (typeof e.name === "string" && e.name) {
        if (typeof e.errno === "number") {
            return `${e.name} (errno ${e.errno})`
        }
        return e.name
    }
    if (typeof e.errno === "number") {
        return `Error (errno ${e.errno})`
    }
    try {
        return JSON.stringify(e)
    } catch (err) {
        return String(e)
    }
}

export function resetLog() {
    currentLog = ""
    currentLogTruncated = false
}

export function getLog() {
    return currentLog
}
