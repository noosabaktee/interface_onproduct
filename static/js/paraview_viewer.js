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
        stream: {
            group: null,
            lines: null,
            seedPoints: null,
            seedShell: null,
            visible: true,
            center: new THREE.Vector3(0, 0, 0),
            radius: 0.7,
            coloring: {
                mode: "solid",
                field: "",
                label: "Solid Color",
            },
            dragging: false,
            dragPlane: new THREE.Plane(),
            dragOffset: new THREE.Vector3(),
        },
        raycaster: new THREE.Raycaster(),
        pointer: new THREE.Vector2(),
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
    bindStreamTracerControls(viewer, state);
    bindStreamTracerDragging(state);
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
    initializeStreamTracer(state);

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

function initializeStreamTracer(state) {
    if (!state.modelBounds) {
        return;
    }

    state.stream.center.set(
        state.modelBounds.min.x + (state.modelBounds.size.x * 0.72),
        state.modelBounds.min.y + (state.modelBounds.size.y * 0.48),
        state.modelBounds.min.z + (state.modelBounds.size.z * 0.58),
    );
    state.stream.radius = Math.max(state.modelBounds.maxDim * 0.08, 0.001);

    if (!state.stream.group) {
        state.stream.group = new state.THREE.Group();
        state.scene.add(state.stream.group);
    }
    rebuildStreamTracer(state);
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

function bindStreamTracerControls(viewer, state) {
    const radiusInput = viewer.querySelector("[data-stream-radius]");
    const applyButton = viewer.querySelector("[data-stream-apply]");
    const visibleInput = viewer.querySelector("[data-stream-visible]");
    const control = viewer.querySelector("[data-stream-coloring-control]");
    const trigger = viewer.querySelector("[data-stream-coloring-trigger]");
    const menu = viewer.querySelector("[data-stream-coloring-menu]");
    const label = viewer.querySelector("[data-stream-coloring-label]");

    const applyRadius = () => {
        const radius = parseLocaleNumber(radiusInput?.value || "0");
        state.stream.radius = Math.max(0, radius);
        rebuildStreamTracer(state);
    };

    if (radiusInput) {
        radiusInput.addEventListener("input", () => {
            radiusInput.value = radiusInput.value.replace(/[^0-9,.]/g, "");
            applyRadius();
        });
    }

    if (applyButton) {
        applyButton.addEventListener("click", applyRadius);
    }

    if (visibleInput) {
        state.stream.visible = visibleInput.checked;
        visibleInput.addEventListener("change", () => {
            state.stream.visible = visibleInput.checked;
            if (state.stream.group) {
                state.stream.group.visible = state.stream.visible;
            }
        });
    }

    if (!control || !trigger || !menu) {
        return;
    }

    trigger.addEventListener("click", () => {
        const isOpen = control.classList.toggle("open");
        trigger.setAttribute("aria-expanded", String(isOpen));
    });

    menu.querySelectorAll("[data-stream-color-mode]").forEach((option) => {
        option.addEventListener("click", () => {
            state.stream.coloring = {
                mode: option.dataset.streamColorMode || "solid",
                field: option.dataset.streamColorField || "",
                label: option.dataset.streamColorLabel || option.textContent.trim(),
            };
            menu.querySelectorAll("[data-stream-color-mode]").forEach((item) => {
                item.classList.toggle("active", item === option);
                item.setAttribute("aria-selected", String(item === option));
            });
            const icon = option.querySelector(".coloring-icon");
            const triggerIcon = trigger.querySelector(".coloring-icon");
            if (icon && triggerIcon) {
                triggerIcon.className = icon.className;
            }
            if (label) {
                label.textContent = state.stream.coloring.label;
            }
            control.classList.remove("open");
            trigger.setAttribute("aria-expanded", "false");
            rebuildStreamTracer(state);
        });
    });

    document.addEventListener("click", (event) => {
        if (!control.contains(event.target)) {
            control.classList.remove("open");
            trigger.setAttribute("aria-expanded", "false");
        }
    });
}

function bindStreamTracerDragging(state) {
    const canvas = state.renderer.domElement;

    canvas.addEventListener("pointerdown", (event) => {
        if (!state.stream.visible || (!state.stream.seedShell && !state.stream.seedPoints)) {
            return;
        }
        updatePointerFromEvent(event, state);
        state.raycaster.setFromCamera(state.pointer, state.camera);
        const targets = [state.stream.seedShell, state.stream.seedPoints].filter(Boolean);
        const hit = state.raycaster.intersectObjects(targets, false)[0];
        if (!hit) {
            return;
        }

        event.preventDefault();
        canvas.setPointerCapture(event.pointerId);
        state.stream.dragging = true;
        state.controls.enabled = false;
        const normal = state.camera.getWorldDirection(new state.THREE.Vector3()).normalize();
        state.stream.dragPlane.setFromNormalAndCoplanarPoint(normal, state.stream.center);
        state.stream.dragOffset.copy(hit.point).sub(state.stream.center);
    });

    canvas.addEventListener("pointermove", (event) => {
        if (!state.stream.dragging) {
            return;
        }
        updatePointerFromEvent(event, state);
        state.raycaster.setFromCamera(state.pointer, state.camera);
        const next = new state.THREE.Vector3();
        if (state.raycaster.ray.intersectPlane(state.stream.dragPlane, next)) {
            state.stream.center.copy(clampToModelBounds(state, next.sub(state.stream.dragOffset)));
            rebuildStreamTracer(state);
        }
    });

    const stopDrag = (event) => {
        if (!state.stream.dragging) {
            return;
        }
        state.stream.dragging = false;
        state.controls.enabled = true;
        if (canvas.hasPointerCapture(event.pointerId)) {
            canvas.releasePointerCapture(event.pointerId);
        }
    };

    canvas.addEventListener("pointerup", stopDrag);
    canvas.addEventListener("pointercancel", stopDrag);
}

function rebuildStreamTracer(state) {
    if (!state.stream.group || !state.modelBounds) {
        return;
    }

    state.stream.group.visible = state.stream.visible;
    clearStreamObject(state.stream.lines);
    clearStreamObject(state.stream.seedPoints);
    clearStreamObject(state.stream.seedShell);

    state.stream.lines = createStreamLines(state);
    state.stream.seedPoints = createSeedPointCloud(state);
    state.stream.seedShell = createSeedShell(state);
    state.stream.group.add(state.stream.lines, state.stream.seedPoints, state.stream.seedShell);
}

function createSeedPointCloud(state) {
    const THREE = state.THREE;
    const radius = state.stream.radius;
    const positions = [];
    const colors = [];
    const count = 52;

    for (let index = 0; index < count; index += 1) {
        const seed = seedPointOnSphere(index, count, THREE);
        const point = state.stream.center.clone().add(seed.multiplyScalar(radius));
        positions.push(point.x, point.y, point.z);
        colors.push(1, 0.82, 0.12);
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
    const material = new THREE.PointsMaterial({
        size: Math.max(state.modelBounds.maxDim * 0.012, 0.008),
        vertexColors: true,
        sizeAttenuation: true,
    });
    return new THREE.Points(geometry, material);
}

function createSeedShell(state) {
    const THREE = state.THREE;
    const radius = Math.max(state.stream.radius, state.modelBounds.maxDim * 0.006);
    const geometry = new THREE.SphereGeometry(radius, 24, 12);
    const material = new THREE.MeshBasicMaterial({
        color: 0xffd226,
        wireframe: true,
        transparent: true,
        opacity: 0.82,
        depthWrite: false,
    });
    const shell = new THREE.Mesh(geometry, material);
    shell.position.copy(state.stream.center);
    return shell;
}

function createStreamLines(state) {
    const THREE = state.THREE;
    const bounds = state.modelBounds;
    const positions = [];
    const colors = [];
    const streamCount = 30;
    const steps = 64;
    const stepSize = Math.max(bounds.maxDim * 0.028, 0.001);

    for (let streamIndex = 0; streamIndex < streamCount; streamIndex += 1) {
        const seed = seedPointOnSphere(streamIndex, streamCount, THREE);
        let current = state.stream.center.clone().add(seed.multiplyScalar(state.stream.radius));
        current.copy(clampToModelBounds(state, current));
        let previous = current.clone();

        for (let step = 0; step < steps; step += 1) {
            const velocity = sampleVelocity(previous, state);
            const next = previous.clone().add(velocity.multiplyScalar(stepSize));
            if (!isInsideBounds(next, bounds)) {
                break;
            }
            pushLineSegment(positions, colors, previous, next, state, step / steps);
            previous = next;
        }
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
    const material = new THREE.LineBasicMaterial({
        color: state.stream.coloring.mode === "solid" ? 0x2d5bff : 0xffffff,
        vertexColors: state.stream.coloring.mode !== "solid",
        transparent: true,
        opacity: 0.92,
        depthWrite: false,
    });
    return new THREE.LineSegments(geometry, material);
}

function pushLineSegment(positions, colors, start, end, state, progress) {
    positions.push(start.x, start.y, start.z, end.x, end.y, end.z);
    const startColor = streamColorForPoint(start, state, progress);
    const endColor = streamColorForPoint(end, state, progress + 0.02);
    colors.push(...startColor, ...endColor);
}

function streamColorForPoint(point, state, progress) {
    const mode = state.stream.coloring.mode;
    const field = state.stream.coloring.field;
    if (mode === "solid") {
        return [0.12, 0.28, 1];
    }

    const normalized = normalizePoint(point, state.modelBounds);
    let value;
    if (field === "U") {
        const velocity = sampleVelocity(point, state);
        value = Math.min(1, velocity.length() * 0.62);
    } else if (field === "p" || field === "p_rgh") {
        value = (normalized.z * 0.55) + ((1 - normalized.y) * 0.35) + (progress * 0.1);
    } else if (field === "IntegrationTime") {
        value = progress;
    } else if (field === "Vorticity" || field === "Rotation" || field === "AngularVelocity") {
        value = Math.abs(Math.sin((normalized.x + normalized.y + progress) * Math.PI));
    } else {
        const seed = hashString(field || mode);
        value = scalarForColoring(normalized.x, normalized.y, normalized.z, seed, "field");
    }
    return sampleTurbo(Math.max(0, Math.min(1, value)));
}

function sampleVelocity(point, state) {
    const n = normalizePoint(point, state.modelBounds);
    const swirl = new state.THREE.Vector3(
        0.32 + (n.z * 0.34),
        (n.x - 0.5) * 0.9,
        0.16 + Math.sin((n.y + n.x) * Math.PI * 2) * 0.22,
    );
    const pullToAxis = new state.THREE.Vector3(
        0,
        (0.5 - n.y) * 0.5,
        (0.5 - n.z) * 0.22,
    );
    return swirl.add(pullToAxis).normalize();
}

function seedPointOnSphere(index, count, THREE) {
    const goldenAngle = Math.PI * (3 - Math.sqrt(5));
    const y = count <= 1 ? 0 : 1 - ((index / (count - 1)) * 2);
    const radius = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = goldenAngle * index;
    return new THREE.Vector3(Math.cos(theta) * radius, Math.sin(theta) * radius, y);
}

function normalizePoint(point, bounds) {
    return {
        x: normalizeValue(point.x, bounds.min.x, bounds.max.x),
        y: normalizeValue(point.y, bounds.min.y, bounds.max.y),
        z: normalizeValue(point.z, bounds.min.z, bounds.max.z),
    };
}

function normalizeValue(value, min, max) {
    return (value - min) / Math.max(max - min, 0.000001);
}

function isInsideBounds(point, bounds) {
    return point.x >= bounds.min.x && point.x <= bounds.max.x
        && point.y >= bounds.min.y && point.y <= bounds.max.y
        && point.z >= bounds.min.z && point.z <= bounds.max.z;
}

function clampToModelBounds(state, point) {
    const bounds = state.modelBounds;
    return point.set(
        Math.max(bounds.min.x, Math.min(bounds.max.x, point.x)),
        Math.max(bounds.min.y, Math.min(bounds.max.y, point.y)),
        Math.max(bounds.min.z, Math.min(bounds.max.z, point.z)),
    );
}

function updatePointerFromEvent(event, state) {
    const rect = state.renderer.domElement.getBoundingClientRect();
    state.pointer.x = ((event.clientX - rect.left) / Math.max(rect.width, 1)) * 2 - 1;
    state.pointer.y = -(((event.clientY - rect.top) / Math.max(rect.height, 1)) * 2 - 1);
}

function parseLocaleNumber(value) {
    const parsed = Number(String(value).trim().replace(",", "."));
    return Number.isFinite(parsed) ? parsed : 0;
}

function clearStreamObject(object) {
    if (!object || !object.parent) {
        return;
    }
    object.parent.remove(object);
    object.geometry?.dispose();
    if (Array.isArray(object.material)) {
        object.material.forEach((material) => material.dispose());
    } else {
        object.material?.dispose();
    }
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
