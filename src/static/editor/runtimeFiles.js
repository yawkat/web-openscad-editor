/**
 * Download and unpack the CadQuery runtime files. Each is a zstd-compressed
 * tar archive (see cadquery_build.py): OCP.wasm, whose OpenCascade library is
 * compiled to a WebAssembly.Module here, and the precompiled site-packages
 * bundles.
 *
 * Runs in a helper worker (see runtimeFilesWorker.js), or in the CadQuery
 * worker itself as a fallback.
 */

import { ZSTDDecoder } from "https://cdn.jsdelivr.net/npm/zstddec@0.3.4/dist/zstddec.mjs";
import { parseTar } from "https://cdn.jsdelivr.net/npm/nanotar@0.3.0/dist/index.mjs";

const decoder = new ZSTDDecoder();

/**
 * @param {string} url
 * @returns {Promise<Array<{name: string, data: Uint8Array}>>}
 */
async function fetchBundle(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`Failed to fetch ${url}: ${response.status} ${response.statusText}`);
    }
    const [compressed] = await Promise.all([response.arrayBuffer(), decoder.init()]);
    let tar = decoder.decode(new Uint8Array(compressed));
    if (tar.byteOffset !== 0 || tar.byteLength !== tar.buffer.byteLength) {
        // parseTar reads the whole underlying buffer.
        tar = tar.slice();
    }
    return parseTar(tar)
        .filter((entry) => entry.type === "file")
        .map((entry) => ({ name: entry.name, data: entry.data || new Uint8Array(0) }));
}

/**
 * @param {string} url - URL of the OCP.wasm bundle
 * @returns {Promise<{module: WebAssembly.Module, libraryName: string, files: Array<{name: string, data: Uint8Array}>}>}
 */
async function compileOcp(url) {
    const entries = await fetchBundle(url);
    const library = entries.find((e) => e.name.endsWith(".so"));
    if (!library) {
        throw new Error("The OCP bundle does not contain a shared library");
    }
    const module = await WebAssembly.compile(library.data);
    return {
        module,
        libraryName: library.name,
        // Copies, so that posting them doesn't copy the library's whole buffer.
        files: entries.filter((e) => e !== library).map((e) => ({ name: e.name, data: e.data.slice() })),
    };
}

/**
 * Prepare one runtime file.
 *
 * @param {string} task - "ocp", or the name of a site-packages bundle
 * @param {string} url
 */
export function prepareRuntimeFile(task, url) {
    return task === "ocp" ? compileOcp(url) : fetchBundle(url);
}
