const THREE_URL = "three";
const ORBIT_CONTROLS_URL = "three/addons/controls/OrbitControls.js";

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-copy-value]").forEach((button) => {
        button.addEventListener("click", () => copyValue(button));
    });

    const viewer = document.querySelector("[data-paraview-viewer]");
    if (viewer) {
        initParaviewViewer(viewer).catch((error) => {
            const status = viewer.querySelector("[data-paraview-status]");
            setStatus(status, `Viewer gagal dimuat: ${error.message}`, "error");
        });
    }
});

async function initParaviewViewer(viewer) {
    const mount = viewer.querySelector("[data-paraview-scene]");
    const status = viewer.querySelector("[data-paraview-status]");
    if (!mount) {
        return;
    }

    setStatus(status, "Loading 3D engine...", "loading");
    const THREE = await import(THREE_URL);
    const { OrbitControls } = await import(ORBIT_CONTROLS_URL);

    const state = createScene(THREE, OrbitControls, mount);
    bindSurfaceButtons(viewer, state, status);

    const defaultSurface = viewer.querySelector("[data-surface-url].active")
        || viewer.querySelector("[data-surface-url]");

    if (defaultSurface) {
        await loadSurface(defaultSurface, state, status);
    } else {
        setStatus(status, "Surface VTP tidak ditemukan.", "error");
    }
}

function createScene(THREE, OrbitControls, mount) {
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x101418);

    const camera = new THREE.PerspectiveCamera(42, 1, 0.01, 10000);
    camera.up.set(0, 0, 1);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(mount.clientWidth, mount.clientHeight);
    mount.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.autoRotate = true;
    controls.autoRotateSpeed = 0.7;

    const ambient = new THREE.HemisphereLight(0xf3fff8, 0x1f2937, 1.35);
    scene.add(ambient);

    const keyLight = new THREE.DirectionalLight(0xffffff, 2.2);
    keyLight.position.set(3, -5, 5);
    scene.add(keyLight);

    const rimLight = new THREE.DirectionalLight(0xf26522, 0.75);
    rimLight.position.set(-4, 4, 3);
    scene.add(rimLight);

    const state = {
        THREE,
        scene,
        camera,
        renderer,
        controls,
        mount,
        mesh: null,
        axes: null,
    };

    const resize = () => {
        const width = Math.max(1, mount.clientWidth);
        const height = Math.max(1, mount.clientHeight);
        renderer.setSize(width, height, false);
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
    };

    if (window.ResizeObserver) {
        new ResizeObserver(resize).observe(mount);
    }
    window.addEventListener("resize", resize);
    resize();

    const animate = () => {
        requestAnimationFrame(animate);
        controls.update();
        renderer.render(scene, camera);
    };
    animate();

    return state;
}

function bindSurfaceButtons(viewer, state, status) {
    viewer.querySelectorAll("[data-surface-url]").forEach((button) => {
        button.addEventListener("click", () => {
            viewer.querySelectorAll("[data-surface-url]").forEach((item) => item.classList.remove("active"));
            button.classList.add("active");
            loadSurface(button, state, status).catch((error) => {
                setStatus(status, `Surface gagal dimuat: ${error.message}`, "error");
            });
        });
    });
}

async function loadSurface(button, state, status) {
    const surfaceUrl = button.dataset.surfaceUrl;
    const surfaceName = button.dataset.surfaceName || "surface";
    if (!surfaceUrl) {
        return;
    }

    setStatus(status, `Loading ${surfaceName}...`, "loading");

    const response = await fetch(surfaceUrl);
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }

    const xmlText = await response.text();
    const polyData = parseVtp(xmlText);
    const geometry = buildGeometry(polyData, state.THREE);

    clearCurrentMesh(state);

    const material = new state.THREE.MeshStandardMaterial({
        color: 0x50d890,
        metalness: 0.08,
        roughness: 0.62,
        side: state.THREE.DoubleSide,
    });

    const mesh = new state.THREE.Mesh(geometry, material);
    state.scene.add(mesh);
    state.mesh = mesh;

    fitCameraToMesh(state, mesh);

    setStatus(
        status,
        `${surfaceName} | ${formatNumber(polyData.numberOfPoints)} points | ${formatNumber(polyData.numberOfPolys)} polys`,
        "ready",
    );
}

function parseVtp(xmlText) {
    const parser = new DOMParser();
    const xml = parser.parseFromString(xmlText, "application/xml");
    if (xml.querySelector("parsererror")) {
        throw new Error("format VTP tidak valid");
    }

    const vtkFile = xml.querySelector("VTKFile");
    const headerBytes = vtkFile && vtkFile.getAttribute("header_type") === "UInt64" ? 8 : 4;
    const piece = xml.querySelector("Piece");
    const points = xml.querySelector("Points DataArray");
    const connectivity = Array.from(xml.querySelectorAll("Polys DataArray"))
        .find((item) => item.getAttribute("Name") === "connectivity");
    const offsets = Array.from(xml.querySelectorAll("Polys DataArray"))
        .find((item) => item.getAttribute("Name") === "offsets");

    if (!piece || !points || !connectivity || !offsets) {
        throw new Error("Points atau Polys tidak lengkap");
    }

    return {
        numberOfPoints: Number(piece.getAttribute("NumberOfPoints") || 0),
        numberOfPolys: Number(piece.getAttribute("NumberOfPolys") || 0),
        positions: decodeDataArray(points, Float32Array, headerBytes),
        connectivity: decodeDataArray(connectivity, Int32Array, headerBytes),
        offsets: decodeDataArray(offsets, Int32Array, headerBytes),
    };
}

function decodeDataArray(element, TypedArray, headerBytes) {
    const bytes = base64ToBytes(element.textContent || "");
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const payloadLength = headerBytes === 8
        ? view.getUint32(0, true) + (view.getUint32(4, true) * 4294967296)
        : view.getUint32(0, true);
    const start = bytes.byteOffset + headerBytes;
    const end = Math.min(start + payloadLength, bytes.byteOffset + bytes.byteLength);
    return new TypedArray(bytes.buffer.slice(start, end));
}

function base64ToBytes(rawValue) {
    const value = rawValue.replace(/\s+/g, "");
    const chunkSize = 32768;
    const chunks = [];
    let totalLength = 0;

    for (let offset = 0; offset < value.length; offset += chunkSize) {
        const binary = atob(value.slice(offset, offset + chunkSize));
        const chunk = new Uint8Array(binary.length);
        for (let index = 0; index < binary.length; index += 1) {
            chunk[index] = binary.charCodeAt(index);
        }
        chunks.push(chunk);
        totalLength += chunk.length;
    }

    const bytes = new Uint8Array(totalLength);
    let cursor = 0;
    chunks.forEach((chunk) => {
        bytes.set(chunk, cursor);
        cursor += chunk.length;
    });
    return bytes;
}

function buildGeometry(polyData, THREE) {
    const triangleCount = countTriangles(polyData.offsets);
    const indices = new Uint32Array(triangleCount * 3);
    let indexCursor = 0;
    let start = 0;

    for (let offsetIndex = 0; offsetIndex < polyData.offsets.length; offsetIndex += 1) {
        const end = polyData.offsets[offsetIndex];
        const vertexCount = end - start;
        if (vertexCount >= 3) {
            const firstVertex = polyData.connectivity[start];
            for (let vertexIndex = 1; vertexIndex < vertexCount - 1; vertexIndex += 1) {
                indices[indexCursor] = firstVertex;
                indices[indexCursor + 1] = polyData.connectivity[start + vertexIndex];
                indices[indexCursor + 2] = polyData.connectivity[start + vertexIndex + 1];
                indexCursor += 3;
            }
        }
        start = end;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(polyData.positions, 3));
    geometry.setIndex(new THREE.BufferAttribute(indices, 1));
    geometry.computeVertexNormals();
    geometry.computeBoundingBox();
    geometry.computeBoundingSphere();
    return geometry;
}

function countTriangles(offsets) {
    let triangles = 0;
    let start = 0;
    for (let index = 0; index < offsets.length; index += 1) {
        const vertexCount = offsets[index] - start;
        if (vertexCount >= 3) {
            triangles += vertexCount - 2;
        }
        start = offsets[index];
    }
    return triangles;
}

function fitCameraToMesh(state, mesh) {
    const THREE = state.THREE;
    const box = mesh.geometry.boundingBox.clone();
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z, 1);

    mesh.position.set(-center.x, -center.y, -center.z);

    if (state.axes) {
        state.scene.remove(state.axes);
        state.axes.geometry?.dispose();
        if (Array.isArray(state.axes.material)) {
            state.axes.material.forEach((material) => material.dispose());
        } else {
            state.axes.material?.dispose();
        }
    }
    state.axes = new THREE.AxesHelper(maxDim * 0.35);
    state.scene.add(state.axes);

    const distance = (maxDim / (2 * Math.tan((Math.PI * state.camera.fov) / 360))) * 1.45;
    state.camera.near = Math.max(distance / 200, 0.001);
    state.camera.far = distance * 200;
    state.camera.position.set(distance * 0.8, -distance * 1.1, distance * 0.62);
    state.camera.updateProjectionMatrix();
    state.controls.target.set(0, 0, 0);
    state.controls.update();
}

function clearCurrentMesh(state) {
    if (!state.mesh) {
        return;
    }

    state.scene.remove(state.mesh);
    state.mesh.geometry.dispose();
    state.mesh.material.dispose();
    state.mesh = null;
}

function setStatus(status, message, state) {
    if (!status) {
        return;
    }
    status.textContent = message;
    status.dataset.state = state || "";
}

function copyValue(button) {
    const value = button.dataset.copyValue || "";
    if (!value || !navigator.clipboard) {
        return;
    }

    navigator.clipboard.writeText(value).then(() => {
        const original = button.innerHTML;
        button.innerHTML = '<i class="bi bi-check2"></i>';
        window.setTimeout(() => {
            button.innerHTML = original;
        }, 1200);
    });
}

function formatNumber(value) {
    return new Intl.NumberFormat("en-US").format(value || 0);
}
