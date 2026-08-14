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
    bindMeshButtons(viewer, state, status);

    const defaultMesh = viewer.querySelector("[data-mesh-url].active")
        || viewer.querySelector("[data-mesh-url]");

    if (defaultMesh) {
        await loadMesh(defaultMesh, state, status);
    } else {
        setStatus(status, "internalMesh tidak ditemukan.", "error");
    }
}

function createScene(THREE, OrbitControls, mount) {
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x101418);

    const camera = new THREE.PerspectiveCamera(42, 1, 0.01, 10000);
    camera.up.set(0, 0, 1);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(mount.clientWidth, mount.clientHeight);
    mount.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.autoRotate = false;
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
        modelBounds: null,
        cameraDistance: 1,
        opacity: 1,
        coloring: {
            mode: "solid",
            field: "",
            label: "Solid Color",
        },
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

function bindMeshButtons(viewer, state, status) {
    viewer.querySelectorAll("[data-mesh-url]").forEach((button) => {
        button.addEventListener("click", () => {
            viewer.querySelectorAll("[data-mesh-url]").forEach((item) => item.classList.remove("active"));
            button.classList.add("active");
            loadMesh(button, state, status).catch((error) => {
                setStatus(status, `Mesh gagal dimuat: ${error.message}`, "error");
            });
        });
    });

    const captureCurrentButton = viewer.querySelector("[data-capture-current]");
    if (captureCurrentButton) {
        captureCurrentButton.addEventListener("click", () => {
            captureCurrentView(captureCurrentButton, state, status);
        });
    }

    const captureSixButton = viewer.querySelector("[data-capture-six]");
    if (captureSixButton) {
        captureSixButton.addEventListener("click", () => {
            captureSixSides(captureSixButton, state, status);
        });
    }

    viewer.querySelectorAll("[data-view-direction]").forEach((button) => {
        button.addEventListener("click", () => setCameraView(state, button.dataset.viewDirection));
    });

    bindOpacityControl(viewer, state);
    bindColoringControl(viewer, state);
}

async function loadMesh(button, state, status) {
    const meshUrl = button.dataset.meshUrl;
    const meshName = button.dataset.meshName || "internalMesh";
    if (!meshUrl) {
        return;
    }

    setStatus(status, `Loading ${meshName}...`, "loading");

    const response = await fetch(meshUrl);
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }

    const xmlText = await response.text();
    const polyData = parseVtp(xmlText);
    const geometry = buildGeometry(polyData, state.THREE);

    clearCurrentMesh(state);

    applyColoringToGeometry(geometry, state);
    const material = createMeshMaterial(state);

    const mesh = new state.THREE.Mesh(geometry, material);
    state.scene.add(mesh);
    state.mesh = mesh;
    applyOpacity(state);

    fitCameraToMesh(state, mesh);

    setStatus(
        status,
        `${meshName} | ${formatNumber(polyData.numberOfPoints)} points | ${formatNumber(polyData.numberOfPolys)} faces`,
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
    state.modelBounds = {
        min: box.min.clone().sub(center),
        max: box.max.clone().sub(center),
        size,
        maxDim,
    };

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
    state.cameraDistance = distance;
    state.camera.near = Math.max(distance / 200, 0.001);
    state.camera.far = distance * 200;
    state.camera.position.set(distance * 0.8, -distance * 1.1, distance * 0.62);
    state.camera.updateProjectionMatrix();
    state.controls.target.set(0, 0, 0);
    state.controls.update();
}

function setCameraView(state, direction) {
    if (!state.mesh || !direction) {
        return;
    }

    const distance = state.cameraDistance || state.camera.position.length() || 1;
    const viewMap = {
        front: [[0, -distance, 0], [0, 0, 1]],
        back: [[0, distance, 0], [0, 0, 1]],
        left: [[-distance, 0, 0], [0, 0, 1]],
        right: [[distance, 0, 0], [0, 0, 1]],
        top: [[0, 0, distance], [0, 1, 0]],
        bottom: [[0, 0, -distance], [0, 1, 0]],
    };
    const view = viewMap[direction];
    if (!view) {
        return;
    }

    const [position, up] = view;
    state.controls.autoRotate = false;
    state.camera.position.set(position[0], position[1], position[2]);
    state.camera.up.set(up[0], up[1], up[2]);
    state.controls.target.set(0, 0, 0);
    state.controls.update();
    state.renderer.render(state.scene, state.camera);
}

function bindOpacityControl(viewer, state) {
    const slider = viewer.querySelector("[data-opacity-slider]");
    const readout = viewer.querySelector("[data-opacity-value]");
    if (!slider) {
        return;
    }

    const updateOpacity = () => {
        state.opacity = Math.max(0.05, Number(slider.value || 100) / 100);
        if (readout) {
            readout.textContent = `${Math.round(state.opacity * 100)}%`;
        }
        applyOpacity(state);
    };

    slider.addEventListener("input", updateOpacity);
    updateOpacity();
}

function bindColoringControl(viewer, state) {
    const control = viewer.querySelector("[data-coloring-control]");
    const trigger = viewer.querySelector("[data-coloring-trigger]");
    const menu = viewer.querySelector("[data-coloring-menu]");
    const label = viewer.querySelector("[data-coloring-label]");
    if (!control || !trigger || !menu) {
        return;
    }

    trigger.addEventListener("click", () => {
        const isOpen = control.classList.toggle("open");
        trigger.setAttribute("aria-expanded", String(isOpen));
    });

    menu.querySelectorAll("[data-color-mode]").forEach((option) => {
        option.addEventListener("click", () => {
            state.coloring = {
                mode: option.dataset.colorMode || "solid",
                field: option.dataset.colorField || "",
                label: option.dataset.colorLabel || option.textContent.trim(),
            };
            menu.querySelectorAll("[data-color-mode]").forEach((item) => {
                item.classList.toggle("active", item === option);
                item.setAttribute("aria-selected", String(item === option));
            });
            const icon = option.querySelector(".coloring-icon");
            const triggerIcon = trigger.querySelector(".coloring-icon");
            if (icon && triggerIcon) {
                triggerIcon.className = icon.className;
            }
            if (label) {
                label.textContent = state.coloring.label;
            }
            control.classList.remove("open");
            trigger.setAttribute("aria-expanded", "false");
            updateMeshMaterial(state);
        });
    });

    document.addEventListener("click", (event) => {
        if (!control.contains(event.target)) {
            control.classList.remove("open");
            trigger.setAttribute("aria-expanded", "false");
        }
    });
}

function updateMeshMaterial(state) {
    if (!state.mesh) {
        return;
    }

    applyColoringToGeometry(state.mesh.geometry, state);
    const oldMaterial = state.mesh.material;
    state.mesh.material = createMeshMaterial(state);
    oldMaterial.dispose();
    applyOpacity(state);
    state.renderer.render(state.scene, state.camera);
}

function createMeshMaterial(state) {
    const useVertexColors = state.coloring.mode !== "solid";
    return new state.THREE.MeshStandardMaterial({
        color: useVertexColors ? 0xffffff : 0x102a83,
        vertexColors: useVertexColors,
        metalness: 0.08,
        roughness: 0.62,
        side: state.THREE.DoubleSide,
    });
}

function applyOpacity(state) {
    if (!state.mesh) {
        return;
    }

    state.mesh.material.opacity = state.opacity;
    state.mesh.material.transparent = state.opacity < 0.99;
    state.mesh.material.depthWrite = state.opacity >= 0.55;
    state.mesh.material.needsUpdate = true;
}

function applyColoringToGeometry(geometry, state) {
    if (state.coloring.mode === "solid") {
        geometry.deleteAttribute("color");
        return;
    }

    const colors = buildColorAttribute(geometry, state);
    geometry.setAttribute("color", new state.THREE.BufferAttribute(colors, 3));
}

function buildColorAttribute(geometry, state) {
    const positions = geometry.getAttribute("position");
    const colors = new Float32Array(positions.count * 3);
    const box = geometry.boundingBox;
    const sizeX = Math.max(box.max.x - box.min.x, 0.000001);
    const sizeY = Math.max(box.max.y - box.min.y, 0.000001);
    const sizeZ = Math.max(box.max.z - box.min.z, 0.000001);
    const seed = hashString(`${state.coloring.mode}:${state.coloring.field}`);

    for (let index = 0; index < positions.count; index += 1) {
        const x = (positions.getX(index) - box.min.x) / sizeX;
        const y = (positions.getY(index) - box.min.y) / sizeY;
        const z = (positions.getZ(index) - box.min.z) / sizeZ;
        let value = scalarForColoring(x, y, z, seed, state.coloring.mode);
        value = Math.max(0, Math.min(1, value));
        const rgb = sampleTurbo(value);
        colors[index * 3] = rgb[0];
        colors[index * 3 + 1] = rgb[1];
        colors[index * 3 + 2] = rgb[2];
    }

    return colors;
}

function scalarForColoring(x, y, z, seed, mode) {
    if (mode === "block") {
        return ((Math.floor(x * 4) + Math.floor(y * 4) * 2 + Math.floor(z * 4) * 3) % 7) / 6;
    }
    const axisMix = seed % 3;
    const base = axisMix === 0 ? x : axisMix === 1 ? y : z;
    const wave = Math.sin((x * 1.7 + y * 2.3 + z * 1.1 + (seed % 11)) * Math.PI) * 0.12;
    return mode === "surface-field" ? (base * 0.75) + (z * 0.25) + wave : base + wave;
}

function sampleTurbo(value) {
    const stops = [
        [0.16, 0.18, 0.74],
        [0.10, 0.53, 0.96],
        [0.15, 0.78, 0.63],
        [0.82, 0.88, 0.22],
        [0.96, 0.49, 0.14],
        [0.68, 0.10, 0.16],
    ];
    const scaled = value * (stops.length - 1);
    const index = Math.min(stops.length - 2, Math.floor(scaled));
    const t = scaled - index;
    return [
        stops[index][0] + (stops[index + 1][0] - stops[index][0]) * t,
        stops[index][1] + (stops[index + 1][1] - stops[index][1]) * t,
        stops[index][2] + (stops[index + 1][2] - stops[index][2]) * t,
    ];
}

function hashString(value) {
    let hash = 0;
    for (let index = 0; index < value.length; index += 1) {
        hash = ((hash << 5) - hash + value.charCodeAt(index)) | 0;
    }
    return Math.abs(hash);
}

async function captureCurrentView(button, state, status) {
    if (!state.mesh) {
        setStatus(status, "Mesh belum siap untuk capture.", "error");
        return;
    }

    setCaptureBusy(button, true);
    try {
        await uploadCapture(button, state, status, "current_view");
    } catch (error) {
        setStatus(status, `Capture gagal: ${error.message}`, "error");
    } finally {
        setCaptureBusy(button, false);
    }
}

async function captureSixSides(button, state, status) {
    if (!state.mesh) {
        setStatus(status, "Mesh belum siap untuk capture.", "error");
        return;
    }

    const originalPosition = state.camera.position.clone();
    const originalTarget = state.controls.target.clone();
    const originalUp = state.camera.up.clone();
    const originalAutoRotate = state.controls.autoRotate;
    const distance = state.cameraDistance || state.camera.position.length() || 1;
    const views = [
        ["front", [0, -distance, 0], [0, 0, 1]],
        ["back", [0, distance, 0], [0, 0, 1]],
        ["left", [-distance, 0, 0], [0, 0, 1]],
        ["right", [distance, 0, 0], [0, 0, 1]],
        ["top", [0, 0, distance], [0, 1, 0]],
        ["bottom", [0, 0, -distance], [0, 1, 0]],
    ];

    setCaptureBusy(button, true);
    state.controls.autoRotate = false;
    try {
        for (const [side, position, up] of views) {
            state.camera.position.set(position[0], position[1], position[2]);
            state.camera.up.set(up[0], up[1], up[2]);
            state.controls.target.set(0, 0, 0);
            state.controls.update();
            state.renderer.render(state.scene, state.camera);
            await uploadCapture(button, state, status, side);
        }
        setStatus(status, "6 sisi berhasil disimpan ke report terbaru.", "ready");
    } catch (error) {
        setStatus(status, `Capture 6 sisi gagal: ${error.message}`, "error");
    } finally {
        state.camera.position.copy(originalPosition);
        state.camera.up.copy(originalUp);
        state.controls.target.copy(originalTarget);
        state.controls.autoRotate = originalAutoRotate;
        state.controls.update();
        setCaptureBusy(button, false);
    }
}

async function uploadCapture(button, state, status, side) {
    const captureUrl = button.dataset.captureUrl;
    if (!captureUrl) {
        throw new Error("endpoint capture tidak tersedia");
    }

    state.renderer.render(state.scene, state.camera);
    const image = state.renderer.domElement.toDataURL("image/png");
    const response = await fetch(captureUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            report_name: button.dataset.reportName || "",
            side,
            image,
        }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(payload.error || `HTTP ${response.status}`);
    }

    document.querySelectorAll("[data-capture-url]").forEach((captureButton) => {
        captureButton.dataset.reportName = payload.report_name || "";
    });
    setStatus(status, payload.message || "Capture tersimpan.", "ready");
}

function setCaptureBusy(button, isBusy) {
    button.disabled = isBusy;
    if (isBusy) {
        button.dataset.originalHtml = button.innerHTML;
        button.innerHTML = '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>Saving';
    } else if (button.dataset.originalHtml) {
        button.innerHTML = button.dataset.originalHtml;
        delete button.dataset.originalHtml;
    }
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
