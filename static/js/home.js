import * as THREE from "/static/vendor/three.module.js";

const stage = document.querySelector(".hero-stage");
const parallaxItems = document.querySelectorAll(".hero-3d-stage, .kw");
const canvas = document.querySelector("#hero-3d-canvas");

let targetX = 0;
let targetY = 0;

function bindParallax() {
  if (!stage) return;
  stage.addEventListener("pointermove", (event) => {
    const x = event.clientX / window.innerWidth - 0.5;
    const y = event.clientY / window.innerHeight - 0.5;
    targetX = x;
    targetY = y;
    parallaxItems.forEach((item, index) => {
      const strength = Number(item.dataset.depth || 10 + index * 4);
      item.style.setProperty("--mx", `${x * strength}px`);
      item.style.setProperty("--my", `${y * strength}px`);
    });
  });

  stage.addEventListener("pointerleave", () => {
    targetX = 0;
    targetY = 0;
    parallaxItems.forEach((item) => {
      item.style.setProperty("--mx", "0px");
      item.style.setProperty("--my", "0px");
    });
  });
}

function createCrystalMaterial(color, roughness = 0.22) {
  return new THREE.MeshPhysicalMaterial({
    color,
    metalness: 0.18,
    roughness,
    transmission: 0.18,
    thickness: 0.35,
    clearcoat: 0.8,
    clearcoatRoughness: 0.18,
    emissive: color,
    emissiveIntensity: 0.08,
  });
}

function createMatcapLikeMaterial(color, emissiveIntensity = 0.05) {
  return new THREE.MeshStandardMaterial({
    color,
    metalness: 0.42,
    roughness: 0.34,
    emissive: color,
    emissiveIntensity,
  });
}

function buildScene() {
  if (!canvas || !stage) return null;

  const renderer = new THREE.WebGLRenderer({
    canvas,
    alpha: true,
    antialias: true,
    powerPreference: "high-performance",
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.8));
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
  camera.position.set(0, 0.2, 8.2);

  const group = new THREE.Group();
  scene.add(group);
  const character = new THREE.Group();
  character.rotation.z = -0.1;
  character.scale.setScalar(1.16);
  group.add(character);

  const suitMaterial = createMatcapLikeMaterial(0xf0ede2, 0.015);
  const shadowMaterial = createMatcapLikeMaterial(0x24262b, 0.02);
  const visorMaterial = createCrystalMaterial(0xd6b15f, 0.12);
  const glowMaterial = new THREE.MeshBasicMaterial({ color: 0x8be9ff, transparent: true, opacity: 0.9 });
  const goldGlowMaterial = new THREE.MeshBasicMaterial({ color: 0xd6b15f, transparent: true, opacity: 0.72 });

  const torso = new THREE.Mesh(new THREE.CapsuleGeometry(0.56, 1.18, 12, 24), suitMaterial);
  torso.position.set(0, -0.08, 0);
  torso.rotation.z = -0.06;
  torso.scale.set(1.04, 1.16, 0.72);
  character.add(torso);

  const shoulders = new THREE.Mesh(new THREE.CapsuleGeometry(0.16, 1.08, 8, 18), suitMaterial);
  shoulders.position.set(0.02, 0.6, 0.04);
  shoulders.rotation.z = Math.PI / 2 - 0.06;
  shoulders.scale.set(1, 1, 0.62);
  character.add(shoulders);

  const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.2, 0.22, 18), shadowMaterial);
  neck.position.set(0.03, 0.86, 0.01);
  neck.rotation.z = -0.04;
  character.add(neck);

  const chestPlate = new THREE.Mesh(new THREE.BoxGeometry(0.82, 0.14, 0.08), shadowMaterial);
  chestPlate.position.set(0.08, 0.34, 0.44);
  chestPlate.rotation.z = -0.14;
  character.add(chestPlate);

  const coreLight = new THREE.Mesh(new THREE.TorusGeometry(0.19, 0.012, 10, 72), goldGlowMaterial);
  coreLight.position.set(0.08, 0.18, 0.49);
  coreLight.rotation.set(0, 0.16, -0.1);
  character.add(coreLight);

  const head = new THREE.Mesh(new THREE.SphereGeometry(0.38, 32, 20), suitMaterial);
  head.position.set(0.05, 1.22, 0.04);
  head.scale.set(1.02, 0.88, 0.96);
  character.add(head);

  const visor = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.18, 0.08), visorMaterial);
  visor.position.set(0.09, 1.22, 0.37);
  visor.rotation.z = -0.08;
  character.add(visor);

  const headRim = new THREE.Mesh(new THREE.TorusGeometry(0.42, 0.015, 10, 96), goldGlowMaterial);
  headRim.position.set(0.04, 1.22, 0.05);
  headRim.rotation.set(1.45, 0.05, -0.08);
  character.add(headRim);

  const makeLimb = (length, radius, material) => new THREE.Mesh(new THREE.CapsuleGeometry(radius, length, 10, 18), material);
  const leftArm = makeLimb(1.0, 0.15, suitMaterial);
  leftArm.position.set(-0.78, 0.16, 0.08);
  leftArm.rotation.z = 0.7;
  leftArm.rotation.x = -0.14;
  character.add(leftArm);

  const rightArm = makeLimb(1.12, 0.14, suitMaterial);
  rightArm.position.set(0.84, 0.2, 0.12);
  rightArm.rotation.z = -0.92;
  rightArm.rotation.x = 0.1;
  character.add(rightArm);

  const leftLeg = makeLimb(1.12, 0.18, shadowMaterial);
  leftLeg.position.set(-0.34, -1.0, 0);
  leftLeg.rotation.z = -0.28;
  character.add(leftLeg);

  const rightLeg = makeLimb(1.18, 0.18, shadowMaterial);
  rightLeg.position.set(0.38, -1.02, 0);
  rightLeg.rotation.z = 0.38;
  character.add(rightLeg);

  const handGlow = new THREE.Mesh(new THREE.TorusGeometry(0.38, 0.012, 10, 108), glowMaterial);
  handGlow.position.set(1.22, -0.22, 0.38);
  handGlow.rotation.set(1.2, 0.25, -0.32);
  character.add(handGlow);

  const stylus = new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.018, 1.45, 10), glowMaterial);
  stylus.position.set(1.42, -0.4, 0.44);
  stylus.rotation.z = -0.74;
  stylus.rotation.x = 0.35;
  character.add(stylus);

  const board = new THREE.Mesh(
    new THREE.BoxGeometry(1.42, 0.86, 0.035),
    new THREE.MeshBasicMaterial({ color: 0x8be9ff, transparent: true, opacity: 0.15 }),
  );
  board.position.set(1.7, -0.58, 0.16);
  board.rotation.set(-0.15, -0.35, -0.12);
  character.add(board);

  const boardEdge = new THREE.LineSegments(
    new THREE.EdgesGeometry(new THREE.BoxGeometry(1.42, 0.86, 0.035)),
    new THREE.LineBasicMaterial({ color: 0x8be9ff, transparent: true, opacity: 0.52 }),
  );
  boardEdge.position.copy(board.position);
  boardEdge.rotation.copy(board.rotation);
  character.add(boardEdge);

  const ringMaterial = new THREE.MeshBasicMaterial({
    color: 0xf7f0df,
    transparent: true,
    opacity: 0.38,
    side: THREE.DoubleSide,
  });
  const rings = [];
  for (let i = 0; i < 4; i += 1) {
    const ring = new THREE.Mesh(new THREE.TorusGeometry(1.86 + i * 0.42, 0.007, 12, 180), ringMaterial.clone());
    ring.rotation.set(Math.PI / 2.7, i * 0.58, i * 0.18);
    ring.material.opacity = 0.23 - i * 0.035;
    rings.push(ring);
    group.add(ring);
  }

  const shardMaterial = createCrystalMaterial(0xf7f0df, 0.28);
  const shards = [];
  for (let i = 0; i < 8; i += 1) {
    const shard = new THREE.Mesh(new THREE.TetrahedronGeometry(0.1 + Math.random() * 0.13, 0), shardMaterial.clone());
    const angle = (i / 16) * Math.PI * 2;
    const radius = 2.4 + Math.random() * 1.7;
    shard.position.set(Math.cos(angle) * radius, (Math.random() - 0.5) * 2.8, Math.sin(angle) * radius * 0.34);
    shard.rotation.set(Math.random() * Math.PI, Math.random() * Math.PI, Math.random() * Math.PI);
    shard.material.opacity = 0.65;
    shards.push(shard);
    group.add(shard);
  }

  const particleCount = 320;
  const positions = new Float32Array(particleCount * 3);
  for (let i = 0; i < particleCount; i += 1) {
    const radius = 2.2 + Math.random() * 4.8;
    const angle = Math.random() * Math.PI * 2;
    positions[i * 3] = Math.cos(angle) * radius;
    positions[i * 3 + 1] = (Math.random() - 0.5) * 5.2;
    positions[i * 3 + 2] = Math.sin(angle) * radius * 0.52;
  }
  const particleGeometry = new THREE.BufferGeometry();
  particleGeometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  const particles = new THREE.Points(
    particleGeometry,
    new THREE.PointsMaterial({
      color: 0x8be9ff,
      size: 0.026,
      transparent: true,
      opacity: 0.72,
      depthWrite: false,
    }),
  );
  group.add(particles);

  scene.add(new THREE.AmbientLight(0xf7f0df, 0.8));
  const key = new THREE.DirectionalLight(0xffffff, 2.6);
  key.position.set(2.6, 3.4, 4);
  scene.add(key);
  const rim = new THREE.PointLight(0x8be9ff, 28, 14);
  rim.position.set(-3.5, 1.8, 2.8);
  scene.add(rim);
  const gold = new THREE.PointLight(0xd6b15f, 18, 10);
  gold.position.set(3.4, -2.3, 3.4);
  scene.add(gold);

  function resize() {
    const rect = stage.getBoundingClientRect();
    const width = Math.max(1, rect.width);
    const height = Math.max(1, rect.height);
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }

  let rafId = 0;
  let pageVisible = true;
  const clock = new THREE.Clock();
  function tick() {
    if (!pageVisible) {
      rafId = requestAnimationFrame(tick);
      return;
    }
    const elapsed = clock.getElapsedTime();
    group.rotation.y = -0.34 + targetX * 0.42 + Math.sin(elapsed * 0.32) * 0.08;
    group.rotation.x = -0.04 + Math.sin(elapsed * 0.42) * 0.05 + targetY * 0.18;
    group.position.x = 1.15 + targetX * 0.32;
    group.position.y = Math.sin(elapsed * 0.7) * 0.08 - targetY * 0.16;
    character.rotation.z = -0.1 + Math.sin(elapsed * 0.8) * 0.035;
    rightArm.rotation.z = -0.92 + Math.sin(elapsed * 1.15) * 0.09;
    coreLight.rotation.z = elapsed * 1.1;
    headRim.rotation.z = -0.08 + Math.sin(elapsed * 0.8) * 0.08;
    handGlow.rotation.z = -0.32 + elapsed * 0.9;
    handGlow.scale.setScalar(1 + Math.sin(elapsed * 2.2) * 0.08);
    board.material.opacity = 0.14 + Math.sin(elapsed * 2.4) * 0.045;
    boardEdge.material.opacity = 0.42 + Math.sin(elapsed * 2.1) * 0.12;
    rings.forEach((ring, index) => {
      ring.rotation.z = elapsed * (0.12 + index * 0.035);
      ring.rotation.y += 0.0018 + index * 0.0005;
    });
    shards.forEach((shard, index) => {
      shard.rotation.x += 0.004 + index * 0.0002;
      shard.rotation.y += 0.006;
    });
    particles.rotation.y = -elapsed * 0.035;
    particles.rotation.x = Math.sin(elapsed * 0.2) * 0.04;
    renderer.render(scene, camera);
    rafId = requestAnimationFrame(tick);
  }

  resize();
  window.addEventListener("resize", resize);
  document.addEventListener("visibilitychange", () => {
    pageVisible = document.visibilityState === "visible";
    if (pageVisible) clock.getElapsedTime();
  });
  tick();

  return () => {
    cancelAnimationFrame(rafId);
    window.removeEventListener("resize", resize);
    renderer.dispose();
    particleGeometry.dispose();
  };
}

bindParallax();
try {
  buildScene();
} catch (error) {
  console.warn("3D hero unavailable", error);
}
