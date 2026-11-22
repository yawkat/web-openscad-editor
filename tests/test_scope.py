import subprocess
import textwrap


def run_node(script: str):
    subprocess.run(["node", "--input-type=module", "-e", script], check=True, text=True)


def test_scope_and_expressions():
    run_node(
        textwrap.dedent(
            """
            import assert from "node:assert/strict";
            import { buildScope, compileExpression } from "./src/static/editor/scope.js";

            assert.deepEqual(buildScope({ a: 1, "lid.show": true, "lid.size.x": 2 }), {
                a: 1,
                lid: { show: true, size: { x: 2 } },
            });

            const custom = { width: 3, "lid.show": true, "lid.height": 4 };
            const predicate = compileExpression("lid.show && width > 2", custom);
            assert.equal(predicate(custom), true);
            assert.equal(predicate({ ...custom, "lid.show": false }), false);
            assert.equal(compileExpression("'box-' + lid.height", custom)(custom), "box-4");
            """
        )
    )
