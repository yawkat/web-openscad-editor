import subprocess
import textwrap


def run_node(script: str):
    subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        text=True,
    )


def test_off_parser_triangulates_colored_faces():
    run_node(
        textwrap.dedent(
            """
            import assert from "node:assert/strict";
            import { parseOffMesh } from "./src/static/editor/off.js";

            const mesh = parseOffMesh(`
            OFF
            4 1 0
            0 0 0
            1 0 0
            1 1 0
            0 1 0
            4 0 1 2 3 255 128 0 1
            `);

            assert.equal(mesh.positions.length, 18);
            assert.equal(mesh.colors.length, 18);
            const firstColor = Array.from(mesh.colors.slice(0, 3));
            assert.equal(firstColor[0], 1);
            assert.ok(Math.abs(firstColor[1] - 128 / 255) < 1e-6);
            assert.equal(firstColor[2], 0);
            assert.deepEqual(Array.from(mesh.positions.slice(0, 9)), [
                0, 0, 0,
                1, 0, 0,
                1, 1, 0,
            ]);
            assert.deepEqual(Array.from(mesh.positions.slice(9, 18)), [
                0, 0, 0,
                1, 1, 0,
                0, 1, 0,
            ]);
            """
        )
    )


def test_off_parser_keeps_adjacent_uncolored_faces_uncolored():
    run_node(
        textwrap.dedent(
            """
            import assert from "node:assert/strict";
            import { parseOffMesh } from "./src/static/editor/off.js";

            const mesh = parseOffMesh(`
            OFF
            5 2 0
            0 0 0
            1 0 0
            0 1 0
            0 0 1
            1 1 1
            3 0 1 2
            3 2 3 4
            `);

            assert.equal(mesh.positions.length, 18);
            assert.equal(mesh.colors, null);
            """
        )
    )


def test_off_mesh_to_binary_stl():
    run_node(
        textwrap.dedent(
            """
            import assert from "node:assert/strict";
            import { offMeshToBinaryStl, parseOffMesh } from "./src/static/editor/off.js";

            const mesh = parseOffMesh(`
            OFF
            3 1 0
            0 0 0
            1 0 0
            0 1 0
            3 0 1 2 1 0 0
            `);
            const stl = offMeshToBinaryStl(mesh);
            const view = new DataView(stl.buffer, stl.byteOffset, stl.byteLength);

            assert.equal(stl.byteLength, 134);
            assert.equal(view.getUint32(80, true), 1);
            assert.equal(view.getFloat32(84, true), 0);
            assert.equal(view.getFloat32(88, true), 0);
            assert.equal(view.getFloat32(92, true), 1);
            assert.equal(view.getFloat32(96, true), 0);
            assert.equal(view.getFloat32(100, true), 0);
            assert.equal(view.getFloat32(104, true), 0);
            assert.equal(view.getFloat32(108, true), 1);
            assert.equal(view.getFloat32(112, true), 0);
            assert.equal(view.getFloat32(116, true), 0);
            assert.equal(view.getFloat32(120, true), 0);
            assert.equal(view.getFloat32(124, true), 1);
            assert.equal(view.getFloat32(128, true), 0);
            assert.equal(view.getUint16(132, true), 0);
            """
        )
    )
