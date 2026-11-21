/**
 * Unzip wheels and bundles in the browser with zip.js, which uses the native
 * DecompressionStream. Much faster than unpacking large archives in Python.
 */

import {
    configure,
    Uint8ArrayReader,
    Uint8ArrayWriter,
    ZipReader,
} from "https://cdn.jsdelivr.net/npm/@zip.js/zip.js@2.24.0/+esm";

// We already run in a worker, and zip.js's own workers would need extra files.
configure({ useWebWorkers: false });

/**
 * Read all file entries of a zip archive.
 *
 * @param {Uint8Array} bytes
 * @returns {Promise<Array<{name: string, data: Uint8Array}>>}
 */
export async function readZip(bytes) {
    const reader = new ZipReader(new Uint8ArrayReader(bytes));
    try {
        const entries = await reader.getEntries();
        return await Promise.all(
            entries
                .filter((entry) => !entry.directory)
                .map(async (entry) => ({
                    name: entry.filename,
                    data: await entry.getData(new Uint8ArrayWriter()),
                })),
        );
    } finally {
        await reader.close();
    }
}
