/**
 * Shared three.js helpers for the render workers: turn triangle meshes into
 * shaded GLB previews for <model-viewer>.
 */

import * as THREE from "https://esm.sh/three@0.160.0"
import {GLTFExporter} from "https://esm.sh/three@0.160.0/examples/jsm/exporters/GLTFExporter.js"

const DEFAULT_TOP_COLOR = new THREE.Color(0x63696f)
const DEFAULT_BOTTOM_COLOR = new THREE.Color(0xc4d0dd)

function applyDepthCueing(geometry, previewStyle) {
    const pos = geometry.getAttribute("position")
    if (!pos || pos.count < 3) {
        return
    }
    const baseColors = geometry.getAttribute("color")
    const useFaceColors = previewStyle === "colors"

    let minZ = Infinity
    let maxZ = -Infinity
    for (let i = 0; i < pos.count; i++) {
        const z = pos.getZ(i)
        if (z < minZ) minZ = z
        if (z > maxZ) maxZ = z
    }

    const range = maxZ - minZ
    if (!isFinite(range) || range <= 0) {
        return
    }

    const colors = new Float32Array(pos.count * 3)
    for (let i = 0; i < pos.count; i++) {
        const z = pos.getZ(i)
        const t = (z - minZ) / range
        const k = i * 3

        if (useFaceColors && baseColors) {
            const r = baseColors.getX(i)
            const g = baseColors.getY(i)
            const b = baseColors.getZ(i)
            // Keep the OpenSCAD color hue, but vary luminance with Z so
            // pockets and vertical surfaces remain readable. Colored
            // models need a narrower luminance range than the default
            // gray preview or saturated colors wash out.
            colors[k] = (r + (1 - r) * 0.08) * (1 - t) + (r * 0.78) * t
            colors[k + 1] = (g + (1 - g) * 0.08) * (1 - t) + (g * 0.78) * t
            colors[k + 2] = (b + (1 - b) * 0.08) * (1 - t) + (b * 0.78) * t
        } else {
            const c = DEFAULT_BOTTOM_COLOR.clone().lerp(DEFAULT_TOP_COLOR, t)
            colors[k] = c.r
            colors[k + 1] = c.g
            colors[k + 2] = c.b
        }
    }
    geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3))
}

async function geometryToGlb(geometry, previewStyle) {
    if (geometry.index) {
        // Keep vertex colors stable for per-face colored geometry.
        geometry = geometry.toNonIndexed()
    }
    if (!geometry.getAttribute("normal")) {
        geometry.computeVertexNormals()
    }

    const neutralLighting = previewStyle === "colors"
    const material = new THREE.MeshStandardMaterial({
        color: 0xc4d0dd,
        metalness: neutralLighting ? 0.0 : 0.8,
        roughness: neutralLighting ? 0.55 : 0.4,
        flatShading: true,
        vertexColors: true,
    })
    const mesh = new THREE.Mesh(geometry, material)
    // OpenSCAD uses mm; glTF uses meters.
    mesh.scale.setScalar(0.001)

    const scene = new THREE.Scene()
    scene.add(mesh)

    // Add a few basic lights so the exported GLB shades nicely even without an HDR environment.
    const lightA = new THREE.DirectionalLight(neutralLighting ? 0xffffff : 0xd6629e, neutralLighting ? 4 : 20) // top right
    lightA.position.set(1000, 1000, 1000) // north east, top
    lightA.lookAt(0, 0, 0)
    scene.add(lightA)

    const lightB = new THREE.DirectionalLight(neutralLighting ? 0xffffff : 0x5571a8, neutralLighting ? 2.5 : 20) // top left
    lightB.position.set(-1000, 1000, 1000) // north west, top
    lightB.lookAt(0, 0, 0)
    scene.add(lightB)

    const lightC = new THREE.DirectionalLight(neutralLighting ? 0xffffff : 0xbf86bb, neutralLighting ? 1 : 15) // bottom
    lightC.position.set(0, -1000, -1000) // south, bottom
    lightC.lookAt(0, 0, 0)
    scene.add(lightC)

    const lightD = new THREE.DirectionalLight(neutralLighting ? 0xffffff : 0xbf86bb, neutralLighting ? 1.5 : 15) // front
    lightD.position.set(0, -1000, 1000) // south, top
    lightD.lookAt(0, 0, 0)
    scene.add(lightD)

    return await new Promise((resolve, reject) => {
        const exporter = new GLTFExporter()
        exporter.parse(
            scene,
            (result) => {
                if (result instanceof ArrayBuffer) {
                    resolve(result)
                } else {
                    reject(new Error("Expected binary glTF (ArrayBuffer)"))
                }
            },
            (error) => reject(error),
            { binary: true },
        )
    })
}

/**
 * Build a GLB preview from non-indexed triangle data.
 *
 * @param {{positions: Float32Array, colors: Float32Array|null}} mesh
 * @param {string} previewStyle
 */
export async function meshToGlb(mesh, previewStyle) {
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute("position", new THREE.BufferAttribute(mesh.positions, 3))
    if (mesh.colors) {
        geometry.setAttribute("color", new THREE.BufferAttribute(mesh.colors, 3))
    }
    applyDepthCueing(geometry, previewStyle)
    return geometryToGlb(geometry, previewStyle)
}
