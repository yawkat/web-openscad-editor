const HEADER_RE = /^(?:C)?OFF$/;

function normalizeColorComponent(value) {
    if (value > 1) {
        return value / 255;
    }
    return value;
}

function parseColor(tokens, cursor, available) {
    if (available < 3) {
        return null;
    }
    const r = Number(tokens[cursor]);
    const g = Number(tokens[cursor + 1]);
    const b = Number(tokens[cursor + 2]);
    if (![r, g, b].every(Number.isFinite)) {
        return null;
    }
    return [
        normalizeColorComponent(r),
        normalizeColorComponent(g),
        normalizeColorComponent(b),
    ];
}

function tokenizeOffLines(text) {
    const lines = [];
    for (const line of text.split(/\r?\n/)) {
        const uncommented = line.replace(/#.*/, "").trim();
        if (uncommented) {
            lines.push(uncommented.split(/\s+/));
        }
    }
    return lines;
}

/**
 * Parse OFF/COFF text into non-indexed triangle data.
 *
 * OpenSCAD writes face colors at the end of face records for colored models.
 * COFF vertex colors are also supported so the parser remains useful for
 * generic colored OFF files.
 */
export function parseOffMesh(text) {
    const lines = tokenizeOffLines(text);
    if (lines.length === 0) {
        throw new Error("Empty OFF file");
    }

    const firstLine = lines.shift();
    const header = firstLine.shift();
    if (!HEADER_RE.test(header)) {
        throw new Error(`Unsupported OFF header: ${header}`);
    }
    const hasVertexColors = header.includes("C");

    const countsLine = firstLine.length > 0 ? firstLine : lines.shift();
    if (!countsLine) {
        throw new Error("Missing OFF counts");
    }
    const vertexCount = Number(countsLine[0]);
    const faceCount = Number(countsLine[1]);
    if (!Number.isInteger(vertexCount) || vertexCount < 0) {
        throw new Error("Invalid OFF vertex count");
    }
    if (!Number.isInteger(faceCount) || faceCount < 0) {
        throw new Error("Invalid OFF face count");
    }

    const vertices = [];
    const vertexColors = [];
    for (let i = 0; i < vertexCount; i++) {
        const line = lines.shift();
        if (!line) {
            throw new Error(`Missing OFF vertex ${i}`);
        }
        const x = Number(line[0]);
        const y = Number(line[1]);
        const z = Number(line[2]);
        if (![x, y, z].every(Number.isFinite)) {
            throw new Error(`Invalid OFF vertex ${i}`);
        }
        vertices.push([x, y, z]);
        if (hasVertexColors) {
            const color = parseColor(line, 3, line.length - 3);
            if (!color) {
                throw new Error(`Invalid OFF color for vertex ${i}`);
            }
            vertexColors.push(color);
        }
    }

    const positions = [];
    const colors = [];
    let hasColors = false;

    for (let i = 0; i < faceCount; i++) {
        const line = lines.shift();
        if (!line) {
            throw new Error(`Missing OFF face ${i}`);
        }
        let cursor = 0;
        const points = Number(line[cursor++]);
        if (!Number.isInteger(points) || points < 3) {
            throw new Error(`Invalid OFF face ${i}`);
        }
        const indices = [];
        for (let j = 0; j < points; j++) {
            const index = Number(line[cursor++]);
            if (!Number.isInteger(index) || index < 0 || index >= vertexCount) {
                throw new Error(`Invalid OFF vertex index ${index} in face ${i}`);
            }
            indices.push(index);
        }

        const remainingFaceTokens = line.length - cursor;
        const faceColor = parseColor(line, cursor, remainingFaceTokens);
        if (faceColor) {
            hasColors = true;
        } else if (hasVertexColors) {
            hasColors = true;
        }

        for (let j = 1; j < points - 1; j++) {
            for (const index of [indices[0], indices[j], indices[j + 1]]) {
                positions.push(...vertices[index]);
                const color = faceColor || vertexColors[index] || [1, 1, 1];
                colors.push(...color);
            }
        }
    }

    return {
        positions: new Float32Array(positions),
        colors: hasColors ? new Float32Array(colors) : null,
    };
}

function triangleNormal(positions, offset) {
    const ax = positions[offset];
    const ay = positions[offset + 1];
    const az = positions[offset + 2];
    const bx = positions[offset + 3];
    const by = positions[offset + 4];
    const bz = positions[offset + 5];
    const cx = positions[offset + 6];
    const cy = positions[offset + 7];
    const cz = positions[offset + 8];

    const ux = bx - ax;
    const uy = by - ay;
    const uz = bz - az;
    const vx = cx - ax;
    const vy = cy - ay;
    const vz = cz - az;

    let nx = uy * vz - uz * vy;
    let ny = uz * vx - ux * vz;
    let nz = ux * vy - uy * vx;
    const length = Math.hypot(nx, ny, nz);
    if (length > 0) {
        nx /= length;
        ny /= length;
        nz /= length;
    }
    return [nx, ny, nz];
}

export function offMeshToBinaryStl(mesh) {
    const positions = mesh.positions;
    if (positions.length % 9 !== 0) {
        throw new Error("OFF mesh positions are not triangulated");
    }
    const triangleCount = positions.length / 9;
    const bytes = new ArrayBuffer(84 + triangleCount * 50);
    const view = new DataView(bytes);
    const header = new TextEncoder().encode("Generated from OFF by web-openscad-editor");
    new Uint8Array(bytes, 0, Math.min(header.length, 80)).set(header.slice(0, 80));
    view.setUint32(80, triangleCount, true);

    let cursor = 84;
    for (let i = 0; i < positions.length; i += 9) {
        const normal = triangleNormal(positions, i);
        for (const value of normal) {
            view.setFloat32(cursor, value, true);
            cursor += 4;
        }
        for (let j = 0; j < 9; j++) {
            view.setFloat32(cursor, positions[i + j], true);
            cursor += 4;
        }
        view.setUint16(cursor, 0, true);
        cursor += 2;
    }

    return new Uint8Array(bytes);
}
