import * as THREE from 'three';

const canvas = document.querySelector('#airport-scene');
const loading = document.querySelector('#scene-loading');
const sceneModeLabel = document.querySelector('#scene-mode-label');
const gateLabel = document.querySelector('#scene-gate-label');
const scene = new THREE.Scene();
scene.background = new THREE.Color('#101a19');
scene.fog = new THREE.Fog('#101a19', 32, 82);

const camera = new THREE.PerspectiveCamera(36, 1, 0.1, 150);
camera.position.set(0, 25, 39);
camera.lookAt(0, 0, 0);

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.12;

scene.add(new THREE.HemisphereLight('#d8eadc', '#24312d', 2.15));
const keyLight = new THREE.DirectionalLight('#fff0d7', 3.2);
keyLight.position.set(-12, 24, 10);
scene.add(keyLight);
const mintLight = new THREE.PointLight('#80d8a5', 48, 48, 2);
mintLight.position.set(-15, 5, -8);
scene.add(mintLight);
const amberLight = new THREE.PointLight('#e89d5d', 34, 38, 2);
amberLight.position.set(15, 4, 9);
scene.add(amberLight);

const ground = new THREE.Mesh(
  new THREE.PlaneGeometry(54, 35),
  new THREE.MeshStandardMaterial({ color: '#15201d', roughness: 0.94, metalness: 0.08 })
);
ground.rotation.x = -Math.PI / 2;
ground.position.y = -0.15;
scene.add(ground);
const grid = new THREE.GridHelper(54, 54, '#527066', '#2d4039');
grid.position.y = -0.12;
grid.material.transparent = true;
grid.material.opacity = 0.22;
scene.add(grid);

const runway = new THREE.Mesh(
  new THREE.BoxGeometry(1.6, 0.035, 28),
  new THREE.MeshStandardMaterial({ color: '#28332f', roughness: 0.8 })
);
runway.position.set(0, 0.01, 0);
scene.add(runway);
for (let marker = -12; marker <= 12; marker += 3) {
  const stripe = new THREE.Mesh(
    new THREE.BoxGeometry(0.08, 0.045, 1.05),
    new THREE.MeshBasicMaterial({ color: '#879b8c', transparent: true, opacity: 0.5 })
  );
  stripe.position.set(0, 0.045, marker);
  scene.add(stripe);
}

const gatePads = [];
const gateMaterials = [];
const gatePositions = [];
const gateNameByObject = new WeakMap();
const gateFontColor = '#b7c8bd';
const labelCanvas = document.createElement('canvas');
labelCanvas.width = 256;
labelCanvas.height = 96;
const labelContext = labelCanvas.getContext('2d');

function makeLabel(number, isA380) {
  const localCanvas = document.createElement('canvas');
  localCanvas.width = 256;
  localCanvas.height = 96;
  const context = localCanvas.getContext('2d');
  context.clearRect(0, 0, 256, 96);
  context.font = '700 58px sans-serif';
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.fillStyle = isA380 ? '#a7e6bd' : gateFontColor;
  context.fillText(String(number).padStart(2, '0'), 128, 46);
  const texture = new THREE.CanvasTexture(localCanvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false }));
  sprite.scale.set(1.45, 0.54, 1);
  return sprite;
}

for (let number = 1; number <= 40; number++) {
  const index = number - 1;
  const column = index % 8;
  const row = Math.floor(index / 8);
  const x = (column - 3.5) * 4.65;
  const z = (row - 2) * 4.15;
  const isA380 = number <= 10;
  const padMaterial = new THREE.MeshStandardMaterial({
    color: isA380 ? '#294538' : '#27342f',
    emissive: isA380 ? '#17462d' : '#14231f',
    emissiveIntensity: isA380 ? 0.58 : 0.25,
    roughness: 0.67,
    metalness: 0.24,
  });
  const pad = new THREE.Mesh(new THREE.BoxGeometry(2.65, 0.16, 1.9), padMaterial);
  pad.position.set(x, 0.06, z);
  pad.userData = { gate: `Gate ${number}`, isA380 };
  scene.add(pad);
  gatePads.push(pad);
  gateMaterials.push(padMaterial);
  gatePositions.push(new THREE.Vector3(x, 0.16, z));
  gateNameByObject.set(pad, `Gate ${number}`);

  const edge = new THREE.LineSegments(
    new THREE.EdgesGeometry(pad.geometry),
    new THREE.LineBasicMaterial({ color: isA380 ? '#84d6a5' : '#64776e', transparent: true, opacity: isA380 ? 0.7 : 0.42 })
  );
  edge.position.copy(pad.position);
  scene.add(edge);

  const label = makeLabel(number, isA380);
  label.position.set(x, 0.31, z);
  scene.add(label);

  const stopLine = new THREE.Mesh(
    new THREE.BoxGeometry(0.055, 0.055, 1.25),
    new THREE.MeshBasicMaterial({ color: isA380 ? '#a7e6bd' : '#85928b', transparent: true, opacity: 0.58 })
  );
  stopLine.position.set(x, 0.18, z + 0.72);
  scene.add(stopLine);
}

// Small, custom aircraft geometry keeps the scene self-contained and inspectable.
function buildAircraft(color) {
  const aircraft = new THREE.Group();
  const bodyMaterial = new THREE.MeshStandardMaterial({ color, metalness: 0.64, roughness: 0.3 });
  const wingMaterial = new THREE.MeshStandardMaterial({ color: '#c5d1ca', metalness: 0.72, roughness: 0.36 });
  const fuselage = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.23, 2.45, 14), bodyMaterial);
  fuselage.rotation.x = Math.PI / 2;
  aircraft.add(fuselage);
  const nose = new THREE.Mesh(new THREE.ConeGeometry(0.16, 0.62, 14), bodyMaterial);
  nose.rotation.x = Math.PI / 2;
  nose.position.z = 1.49;
  aircraft.add(nose);
  const tailCone = new THREE.Mesh(new THREE.ConeGeometry(0.16, 0.5, 14), bodyMaterial);
  tailCone.rotation.x = -Math.PI / 2;
  tailCone.position.z = -1.42;
  aircraft.add(tailCone);
  const wings = new THREE.Mesh(new THREE.BoxGeometry(3.2, 0.085, 0.56), wingMaterial);
  wings.position.set(0, -0.02, 0.18);
  aircraft.add(wings);
  const tailWing = new THREE.Mesh(new THREE.BoxGeometry(1.05, 0.07, 0.3), wingMaterial);
  tailWing.position.set(0, 0.02, -1.05);
  aircraft.add(tailWing);
  const fin = new THREE.Mesh(new THREE.BoxGeometry(0.09, 0.47, 0.46), bodyMaterial);
  fin.position.set(0, 0.22, -1.08);
  aircraft.add(fin);
  for (const side of [-1, 1]) {
    const engine = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.46, 10), bodyMaterial);
    engine.rotation.x = Math.PI / 2;
    engine.position.set(side * 0.78, -0.16, 0.27);
    aircraft.add(engine);
  }
  return aircraft;
}

const aircraftFleet = [
  buildAircraft('#e9c28f'),
  buildAircraft('#c5ddd0'),
  buildAircraft('#db8f69'),
  buildAircraft('#d6d9cd'),
];
aircraftFleet.forEach((aircraft, index) => {
  aircraft.scale.setScalar(index === 0 ? 0.88 : 0.68);
  aircraft.position.set(-15 + index * 9.5, 1.1 + (index % 2) * 0.45, -1 + index * 1.2);
  aircraft.rotation.y = Math.PI / 2;
  scene.add(aircraft);
});

const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
let pointerDown = null;
let hoveredGate = null;
let sceneMode = 'baseline';
let orbitYaw = 0;
let orbitPitch = 0.03;
let zoom = 0;
let dragState = null;
let targetLook = new THREE.Vector3(0, 0, 0);

function resizeScene() {
  const rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  camera.aspect = rect.width / rect.height;
  camera.updateProjectionMatrix();
  renderer.setSize(rect.width, rect.height, false);
}
new ResizeObserver(resizeScene).observe(canvas);
resizeScene();

function updateCamera() {
  const radius = 43 - zoom;
  const pitch = 0.52 + orbitPitch;
  camera.position.set(
    Math.sin(orbitYaw) * radius * Math.cos(pitch),
    8 + Math.sin(pitch) * radius,
    Math.cos(orbitYaw) * radius * Math.cos(pitch)
  );
  camera.lookAt(targetLook);
}
updateCamera();

function setSceneMode(mode) {
  sceneMode = mode;
  sceneModeLabel.textContent = mode === 'flexible' ? 'SHARED A380 GATES' : 'BASELINE POLICY';
  gateMaterials.forEach((material, index) => {
    const isA380 = index < 10;
    material.emissiveIntensity = isA380 ? (mode === 'flexible' ? 0.92 : 0.58) : 0.25;
  });
}
window.setAirportSceneMode = setSceneMode;

function handlePointerMove(event) {
  const rect = canvas.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  if (dragState) {
    const dx = event.clientX - dragState.x;
    const dy = event.clientY - dragState.y;
    orbitYaw -= dx * 0.005;
    orbitPitch = THREE.MathUtils.clamp(orbitPitch + dy * 0.003, -0.24, 0.44);
    dragState.x = event.clientX;
    dragState.y = event.clientY;
    updateCamera();
    return;
  }
  raycaster.setFromCamera(pointer, camera);
  const hit = raycaster.intersectObjects(gatePads, false)[0];
  if (hoveredGate && hoveredGate !== hit?.object) {
    const previousIndex = gatePads.indexOf(hoveredGate);
    hoveredGate.material.emissiveIntensity = previousIndex < 10
      ? (sceneMode === 'flexible' ? 0.92 : 0.58)
      : 0.25;
  }
  hoveredGate = hit?.object ?? null;
  canvas.style.cursor = hoveredGate ? 'pointer' : 'grab';
}

canvas.addEventListener('pointerdown', (event) => {
  pointerDown = { x: event.clientX, y: event.clientY };
  dragState = { x: event.clientX, y: event.clientY };
  canvas.setPointerCapture(event.pointerId);
});
canvas.addEventListener('pointerup', (event) => {
  const moved = pointerDown && Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y) > 5;
  if (!moved) {
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects(gatePads, false)[0];
    if (hit) {
      const { gate, isA380 } = hit.object.userData;
      gateLabel.textContent = `${gate.toUpperCase()} / ${isA380 ? 'A380-COMPATIBLE' : 'STANDARD'}`;
      targetLook.lerp(gatePositions[Number(gate.split(' ')[1]) - 1], 0.15);
    }
  }
  dragState = null;
  pointerDown = null;
});
canvas.addEventListener('pointercancel', () => { dragState = null; pointerDown = null; });
canvas.addEventListener('pointermove', handlePointerMove);
canvas.addEventListener('wheel', (event) => {
  event.preventDefault();
  zoom = THREE.MathUtils.clamp(zoom + Math.sign(event.deltaY) * 1.4, 0, 14);
  updateCamera();
}, { passive: false });

const clock = new THREE.Clock();
function animate() {
  const time = clock.getElapsedTime();
  aircraftFleet.forEach((aircraft, index) => {
    const phase = time * (0.18 + index * 0.012) + index * 1.55;
    const radiusX = sceneMode === 'flexible' ? 13 + (index % 2) * 5 : 17;
    const radiusZ = sceneMode === 'flexible' ? 9 + (index % 2) * 2 : 11;
    aircraft.position.x = Math.cos(phase) * radiusX;
    aircraft.position.z = Math.sin(phase * 0.8) * radiusZ;
    aircraft.position.y = 1.1 + Math.sin(phase * 1.7) * 0.22;
    aircraft.rotation.y = -Math.atan2(-Math.cos(phase * 0.8) * radiusZ * 0.8, Math.sin(phase) * radiusX);
  });
  if (hoveredGate) hoveredGate.material.emissiveIntensity = 1.3;
  renderer.render(scene, camera);
  requestAnimationFrame(animate);
}
animate();
loading.classList.add('is-hidden');

const scenarioData = {
  baseline: {
    title: 'DEDICATED GATE GROUPS', conflicts: 7, moved: 135, pairs: '5,208', lowerBound: 6,
    note: 'With 10 A380-only gates and 30 standard gates, the solver reduced the initial same-gate conflicts to 7. A simple peak-demand bound is 6; the remaining gap and FEASIBLE status mean optimality is not established.',
    reduction: '−96%', track: '96%', modeLabel: 'BASELINE POLICY',
  },
  flexible: {
    title: 'SHARED A380-COMPATIBLE GATES', conflicts: 6, moved: 130, pairs: '7,599', lowerBound: 3,
    note: 'Allowing standard aircraft to use any gate reduced the feasible conflict count to 6. Eighteen non-A380 aircraft use A380-compatible gates. CP-SAT remained FEASIBLE, with a lower bound of 3; optimality is not established.',
    reduction: '−97%', track: '97%', modeLabel: 'SHARED A380 GATES',
  },
};

function selectScenario(name) {
  const data = scenarioData[name];
  document.querySelectorAll('.scenario-button').forEach((button) => {
    const selected = button.dataset.scenario === name;
    button.classList.toggle('is-selected', selected);
    button.setAttribute('aria-pressed', String(selected));
  });
  document.querySelector('#outcome-title').textContent = data.title;
  document.querySelector('#optimized-conflicts').textContent = data.conflicts;
  document.querySelector('#moved-count').innerHTML = `${data.moved} <small>/ 300</small>`;
  document.querySelector('#pair-count').textContent = data.pairs;
  document.querySelector('#lower-bound').innerHTML = `${data.lowerBound} <small>conflicts</small>`;
  document.querySelector('#conflict-reduction').textContent = data.reduction;
  document.querySelector('#result-track-fill').style.width = data.track;
  document.querySelector('#scenario-note').textContent = data.note;
  setSceneMode(name);
}
document.querySelectorAll('.scenario-button').forEach((button) => {
  button.addEventListener('click', () => selectScenario(button.dataset.scenario));
});

const sectionElements = [...document.querySelectorAll('[data-section]')];
const ribbonLinks = [...document.querySelectorAll('.ribbon-step')];
const sectionObserver = new IntersectionObserver((entries) => {
  const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
  if (!visible) return;
  ribbonLinks.forEach((link) => link.classList.toggle('is-active', link.hash === `#${visible.target.id}`));
}, { rootMargin: '-20% 0px -62% 0px', threshold: [0, 0.1, 0.35] });
sectionElements.forEach((section) => sectionObserver.observe(section));

const revealObserver = new IntersectionObserver((entries, observer) => {
  entries.forEach((entry) => {
    if (entry.isIntersecting) {
      entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    }
  });
}, { threshold: 0.08 });
document.querySelectorAll('.reveal').forEach((element) => revealObserver.observe(element));

const progressBar = document.querySelector('#reading-progress');
function updateProgress() {
  const scrollable = document.documentElement.scrollHeight - window.innerHeight;
  progressBar.style.width = `${scrollable > 0 ? (window.scrollY / scrollable) * 100 : 0}%`;
}
window.addEventListener('scroll', updateProgress, { passive: true });
window.addEventListener('resize', updateProgress);
updateProgress();