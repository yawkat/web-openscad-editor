/**
 * Minimal zip reader for wheels and bundles, using the browser's native
 * DecompressionStream. Much faster than unpacking large archives in Python.
 */

const EOCD_SIGNATURE = 0x06054b50;
const CENTRAL_SIGNATURE = 0x02014b50;

async function inflateRaw(data) {
    const stream = new Blob([data]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
    return new Uint8Array(await new Response(stream).arrayBuffer());
}

/**
 * Read all file entries of a zip archive.
 *
 * @param {Uint8Array} bytes
 * @returns {Promise<Array<{name: string, data: Uint8Array}>>}
 */
export async function readZip(bytes) {
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    let eocd = bytes.length - 22;
    while (eocd >= 0 && view.getUint32(eocd, true) !== EOCD_SIGNATURE) {
        eocd--;
    }
    if (eocd < 0) {
        throw new Error("Not a zip file");
    }
    const count = view.getUint16(eocd + 10, true);
    let cursor = view.getUint32(eocd + 16, true);
    const decoder = new TextDecoder();
    const entries = [];
    for (let i = 0; i < count; i++) {
        if (view.getUint32(cursor, true) !== CENTRAL_SIGNATURE) {
            throw new Error("Corrupt zip central directory");
        }
        const method = view.getUint16(cursor + 10, true);
        const compressedSize = view.getUint32(cursor + 20, true);
        const nameLength = view.getUint16(cursor + 28, true);
        const extraLength = view.getUint16(cursor + 30, true);
        const commentLength = view.getUint16(cursor + 32, true);
        const localHeader = view.getUint32(cursor + 42, true);
        const name = decoder.decode(bytes.subarray(cursor + 46, cursor + 46 + nameLength));
        cursor += 46 + nameLength + extraLength + commentLength;
        if (name.endsWith("/")) {
            continue;
        }
        const localNameLength = view.getUint16(localHeader + 26, true);
        const localExtraLength = view.getUint16(localHeader + 28, true);
        const start = localHeader + 30 + localNameLength + localExtraLength;
        const raw = bytes.subarray(start, start + compressedSize);
        let data;
        if (method === 0) {
            data = raw;
        } else if (method === 8) {
            data = inflateRaw(raw);
        } else {
            throw new Error(`Unsupported zip compression method ${method} for ${name}`);
        }
        entries.push({ name, data });
    }
    return Promise.all(entries.map(async (e) => ({ name: e.name, data: await e.data })));
}
