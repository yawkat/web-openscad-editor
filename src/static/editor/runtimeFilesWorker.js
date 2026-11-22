/**
 * Helper worker that downloads and unpacks a CadQuery runtime file (see
 * runtimeFiles.js) while the CadQuery worker boots Pyodide. Running this in
 * its own worker keeps it from competing with Pyodide's synchronous startup
 * on the CadQuery worker's thread, and one helper per file lets them run in
 * parallel. The page starts the helpers on request of the CadQuery worker and
 * forwards the results; WebAssembly.Module objects can be posted between
 * workers.
 *
 * Message in: {task, url}. Message out: {result} or {error}.
 */

import { prepareRuntimeFile } from "./runtimeFiles.js";

self.addEventListener("message", async (event) => {
    try {
        self.postMessage({ result: await prepareRuntimeFile(event.data.task, event.data.url) });
    } catch (e) {
        self.postMessage({ error: String(e && e.stack ? e.stack : e) });
    }
});
