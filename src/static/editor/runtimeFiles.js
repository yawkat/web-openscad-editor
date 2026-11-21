/**
 * Download and unpack the CadQuery runtime files: the OCP.wasm wheel (whose
 * 156 MB OpenCascade library is compiled with compileStreaming while it is
 * still being decompressed) and the precompiled site-packages bundle.
 *
 * Runs in a helper worker (see runtimeFilesWorker.js), or in the CadQuery
 * worker itself as a fallback.
 */

import {
    configure,
    Uint8ArrayReader,
    Uint8ArrayWriter,
    ZipReader,
} from "https://cdn.jsdelivr.net/npm/@zip.js/zip.js@2.24.0/+esm";

import { readZip } from "./zip.js";

configure({ useWebWorkers: false });

/**
 * @param {string} url - URL of the OCP.wasm wheel
 * @returns {Promise<{module: WebAssembly.Module, libraryName: string, files: Array<{name: string, data: Uint8Array}>}>}
 */
async function compileOcp(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`Failed to fetch ${url}: ${response.status} ${response.statusText}`);
    }
    const reader = new ZipReader(new Uint8ArrayReader(new Uint8Array(await response.arrayBuffer())));
    try {
        const entries = (await reader.getEntries()).filter((e) => !e.directory);
        const library = entries.find((e) => e.filename.endsWith(".so"));
        if (!library) {
            throw new Error("The OCP wheel does not contain a shared library");
        }
        const { readable, writable } = new TransformStream();
        const modulePromise = WebAssembly.compileStreaming(
            new Response(readable, { headers: { "Content-Type": "application/wasm" } }),
        );
        const [module, files] = await Promise.all([
            modulePromise,
            Promise.all(
                entries
                    .filter((e) => e !== library)
                    .map(async (e) => ({ name: e.filename, data: await e.getData(new Uint8ArrayWriter()) })),
            ),
            library.getData(writable),
        ]);
        return { module, libraryName: library.filename, files };
    } finally {
        await reader.close();
    }
}

async function fetchZip(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`Failed to fetch ${url}: ${response.status} ${response.statusText}`);
    }
    return readZip(new Uint8Array(await response.arrayBuffer()));
}

/**
 * Prepare one kind of runtime file.
 *
 * @param {"ocp" | "site-packages"} task
 * @param {string} url
 */
export function prepareRuntimeFile(task, url) {
    if (task === "ocp") {
        return compileOcp(url);
    }
    if (task === "site-packages") {
        return fetchZip(url);
    }
    throw new Error(`Unknown task ${task}`);
}
