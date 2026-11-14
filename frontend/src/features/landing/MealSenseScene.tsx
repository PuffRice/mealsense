import { useEffect, useRef, useState } from "react";
import * as THREE from "three";

type MealSenseSceneProps = {
  dark: boolean;
};

function createGlowTexture(): THREE.CanvasTexture {
  const size = 64;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    const grad = ctx.createRadialGradient(
      size / 2,
      size / 2,
      0,
      size / 2,
      size / 2,
      size / 2,
    );
    grad.addColorStop(0, "rgba(255, 255, 255, 1)");
    grad.addColorStop(0.35, "rgba(255, 255, 255, 0.55)");
    grad.addColorStop(1, "rgba(255, 255, 255, 0)");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, size, size);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
}

function createLeafGeometry(): THREE.ExtrudeGeometry {
  const shape = new THREE.Shape();
  shape.moveTo(0, 0);
  shape.bezierCurveTo(0.16, 0.12, 0.24, 0.36, 0.02, 0.58);
  shape.bezierCurveTo(-0.22, 0.36, -0.15, 0.12, 0, 0);

  const geometry = new THREE.ExtrudeGeometry(shape, {
    depth: 0.028,
    bevelEnabled: true,
    bevelSegments: 3,
    steps: 1,
    bevelSize: 0.015,
    bevelThickness: 0.012,
  });
  geometry.center();
  return geometry;
}

export function MealSenseScene({ dark }: MealSenseSceneProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const darkRef = useRef(dark);
  const [webglUnavailable, setWebglUnavailable] = useState(false);

  const themeHooksRef = useRef<{
    applyTheme: (isDark: boolean) => void;
  } | null>(null);

  useEffect(() => {
    darkRef.current = dark;
    themeHooksRef.current?.applyTheme(dark);
  }, [dark]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: true,
        powerPreference: "high-performance",
      });
    } catch {
      queueMicrotask(() => setWebglUnavailable(true));
      return;
    }

    const disposables: Array<{ dispose: () => void }> = [];
    const track = <T extends { dispose: () => void }>(item: T): T => {
      disposables.push(item);
      return item;
    };

    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = darkRef.current ? 1.15 : 1.06;
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    renderer.domElement.style.display = "block";
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(
      34,
      Math.max(container.clientWidth, 1) / Math.max(container.clientHeight, 1),
      0.1,
      50,
    );
    camera.position.set(0, 2.2, 5.45);
    camera.lookAt(0, 0.12, 0);

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xfaf8f2, 0.9);
    const hemiLight = new THREE.HemisphereLight(0xffffff, 0x9aa89b, 0.95);
    const keyLight = new THREE.DirectionalLight(0xfff5e4, 2.1);
    keyLight.position.set(4.2, 6.5, 4.5);

    const fillLight = new THREE.DirectionalLight(0x81c784, 0.95);
    fillLight.position.set(-4.5, 2.5, -3.2);

    const rimLight = new THREE.PointLight(0x649e66, 2.2, 14);
    rimLight.position.set(0.2, -1.1, 2.8);

    scene.add(ambientLight, hemiLight, keyLight, fillLight, rimLight);

    // Root interactive group
    const rootGroup = new THREE.Group();
    rootGroup.position.set(0, 0.08, 0);
    scene.add(rootGroup);

    const bowlGroup = new THREE.Group();
    bowlGroup.rotation.x = 0.24;
    rootGroup.add(bowlGroup);

    // 1. Ceramic Bowl (LatheGeometry)
    const bowlProfile = [
      new THREE.Vector2(0.0, -0.54),
      new THREE.Vector2(0.6, -0.54),
      new THREE.Vector2(0.84, -0.44),
      new THREE.Vector2(1.28, -0.08),
      new THREE.Vector2(1.52, 0.36),
      new THREE.Vector2(1.45, 0.42),
      new THREE.Vector2(1.22, 0.0),
      new THREE.Vector2(0.64, -0.34),
      new THREE.Vector2(0.0, -0.37),
    ];
    const bowlGeo = track(new THREE.LatheGeometry(bowlProfile, 72));
    const bowlMat = track(
      new THREE.MeshPhysicalMaterial({
        color: 0xfaf8f2,
        roughness: 0.24,
        metalness: 0.04,
        clearcoat: 0.78,
        clearcoatRoughness: 0.16,
      }),
    );
    const bowlMesh = new THREE.Mesh(bowlGeo, bowlMat);
    bowlGroup.add(bowlMesh);

    // Emerald ceramic rim accent
    const rimGeo = track(new THREE.TorusGeometry(1.485, 0.022, 16, 90));
    const rimMat = track(
      new THREE.MeshStandardMaterial({
        color: 0x649e66,
        roughness: 0.32,
        metalness: 0.22,
      }),
    );
    const rimMesh = new THREE.Mesh(rimGeo, rimMat);
    rimMesh.rotation.x = Math.PI / 2;
    rimMesh.position.y = 0.39;
    bowlGroup.add(rimMesh);

    // Subtle saucer shadow disc underneath bowl
    const shadowGeo = track(new THREE.RingGeometry(0.45, 1.35, 48));
    const shadowMat = track(
      new THREE.MeshBasicMaterial({
        color: 0x113e2e,
        transparent: true,
        opacity: 0.1,
        side: THREE.DoubleSide,
      }),
    );
    const shadowDisc = new THREE.Mesh(shadowGeo, shadowMat);
    shadowDisc.rotation.x = -Math.PI / 2;
    shadowDisc.position.y = -0.62;
    bowlGroup.add(shadowDisc);

    // 2. Wholesome Culinary Composition inside the bowl
    const foodGroup = new THREE.Group();
    bowlGroup.add(foodGroup);

    // Warm golden-saffron grain / khichuri mound
    const grainMoundGeo = track(new THREE.SphereGeometry(0.86, 36, 24));
    const grainMat = track(
      new THREE.MeshStandardMaterial({
        color: 0xe3b14d,
        roughness: 0.76,
        metalness: 0.02,
      }),
    );
    const grainMound = new THREE.Mesh(grainMoundGeo, grainMat);
    grainMound.scale.set(1.06, 0.44, 1.0);
    grainMound.position.set(-0.2, -0.02, 0.1);
    foodGroup.add(grainMound);

    // Instanced golden grain pearls for tactile texture
    const grainPearlGeo = track(new THREE.SphereGeometry(0.068, 12, 10));
    const grainPearlMat = track(
      new THREE.MeshStandardMaterial({
        color: 0xefc367,
        roughness: 0.65,
        metalness: 0.03,
      }),
    );
    const grainCount = 26;
    const grainInstances = new THREE.InstancedMesh(
      grainPearlGeo,
      grainPearlMat,
      grainCount,
    );
    const dummy = new THREE.Object3D();
    for (let i = 0; i < grainCount; i++) {
      const angle = (i / grainCount) * Math.PI * 2 * 2.4;
      const radius = 0.14 + (i / grainCount) * 0.64;
      const gx = -0.2 + Math.cos(angle) * radius;
      const gz = 0.1 + Math.sin(angle) * radius * 0.88;
      const gy = 0.34 - radius * 0.24 + Math.sin(i * 1.7) * 0.03;
      dummy.position.set(gx, gy, gz);
      const s = 0.78 + ((i * 7) % 5) * 0.11;
      dummy.scale.set(s * 1.2, s * 0.8, s);
      dummy.rotation.set(i * 0.5, angle, 0);
      dummy.updateMatrix();
      grainInstances.setMatrixAt(i, dummy.matrix);
    }
    foodGroup.add(grainInstances);

    // Fresh emerald botanical / herb leaves
    const leafGeo = track(createLeafGeometry());
    const leafColors = [0x2e7d32, 0x4b8f54, 0x649e66, 0x3a7c45, 0x81c784];
    const leafSpecs = [
      { pos: [0.46, 0.24, -0.22], rot: [-0.95, 0.35, -0.55], scale: 0.95 },
      { pos: [0.64, 0.18, 0.02], rot: [-1.1, 0.7, -0.9], scale: 0.86 },
      { pos: [0.22, 0.28, -0.45], rot: [-0.85, -0.1, -0.25], scale: 0.92 },
      { pos: [0.58, 0.3, -0.35], rot: [-0.7, 0.5, -0.45], scale: 0.72 },
      { pos: [-0.08, 0.24, -0.52], rot: [-1.05, -0.45, 0.22], scale: 0.82 },
    ];
    leafSpecs.forEach((spec, idx) => {
      const mat = track(
        new THREE.MeshPhysicalMaterial({
          color: leafColors[idx % leafColors.length],
          roughness: 0.42,
          metalness: 0.04,
          clearcoat: 0.25,
        }),
      );
      const leaf = new THREE.Mesh(leafGeo, mat);
      leaf.position.set(spec.pos[0], spec.pos[1], spec.pos[2]);
      leaf.rotation.set(spec.rot[0], spec.rot[1], spec.rot[2]);
      leaf.scale.setScalar(spec.scale);
      foodGroup.add(leaf);
    });

    // Halved soft-boiled egg (ivory white + marigold yolk)
    const eggGroup = new THREE.Group();
    eggGroup.position.set(0.36, 0.24, 0.36);
    eggGroup.rotation.set(0.22, -0.45, -0.18);
    const eggWhiteGeo = track(new THREE.SphereGeometry(0.3, 28, 20));
    const eggWhiteMat = track(
      new THREE.MeshPhysicalMaterial({
        color: 0xfbf8ef,
        roughness: 0.28,
        clearcoat: 0.4,
      }),
    );
    const eggWhite = new THREE.Mesh(eggWhiteGeo, eggWhiteMat);
    eggWhite.scale.set(1.18, 0.46, 0.92);
    eggGroup.add(eggWhite);

    const yolkGeo = track(new THREE.SphereGeometry(0.155, 24, 18));
    const yolkMat = track(
      new THREE.MeshPhysicalMaterial({
        color: 0xe69824,
        roughness: 0.34,
        clearcoat: 0.2,
      }),
    );
    const yolk = new THREE.Mesh(yolkGeo, yolkMat);
    yolk.scale.set(1.0, 0.68, 1.0);
    yolk.position.set(0.03, 0.1, 0);
    eggGroup.add(yolk);
    foodGroup.add(eggGroup);

    // Roasted terracotta protein cubes & fresh tomato pearls
    const proteinGeo = track(new THREE.BoxGeometry(0.25, 0.2, 0.25));
    const proteinMat = track(
      new THREE.MeshStandardMaterial({
        color: 0xc97a3e,
        roughness: 0.5,
        metalness: 0.05,
      }),
    );
    const proteinCoords = [
      { pos: [-0.62, 0.22, -0.18], rot: [0.3, 0.6, 0.15] },
      { pos: [-0.46, 0.26, -0.42], rot: [-0.2, 1.1, 0.25] },
      { pos: [-0.74, 0.14, 0.12], rot: [0.25, 0.2, -0.3] },
    ];
    proteinCoords.forEach(({ pos, rot }) => {
      const cube = new THREE.Mesh(proteinGeo, proteinMat);
      cube.position.set(pos[0], pos[1], pos[2]);
      cube.rotation.set(rot[0], rot[1], rot[2]);
      foodGroup.add(cube);
    });

    const tomatoGeo = track(new THREE.SphereGeometry(0.125, 20, 16));
    const tomatoMat = track(
      new THREE.MeshPhysicalMaterial({
        color: 0xd95b43,
        roughness: 0.22,
        clearcoat: 0.7,
      }),
    );
    [
      [-0.18, 0.26, 0.54],
      [-0.44, 0.22, 0.44],
      [0.08, 0.28, -0.12],
    ].forEach(([x, y, z]) => {
      const tomato = new THREE.Mesh(tomatoGeo, tomatoMat);
      tomato.position.set(x, y, z);
      foodGroup.add(tomato);
    });

    // Avocado crescent slices
    const avoGeo = track(
      new THREE.CylinderGeometry(0.32, 0.32, 0.075, 24, 1, false, 0, Math.PI * 0.72),
    );
    const avoMat = track(
      new THREE.MeshStandardMaterial({
        color: 0x8cc87b,
        roughness: 0.48,
      }),
    );
    [
      { pos: [0.06, 0.22, 0.58], rot: [0.45, 2.2, 0.2] },
      { pos: [-0.14, 0.18, 0.66], rot: [0.4, 2.55, 0.24] },
    ].forEach(({ pos, rot }) => {
      const slice = new THREE.Mesh(avoGeo, avoMat);
      slice.position.set(pos[0], pos[1], pos[2]);
      slice.rotation.set(rot[0], rot[1], rot[2]);
      foodGroup.add(slice);
    });

    // 3. AI Recognition & Macro Balance Orbital Rings
    const orbitGroup = new THREE.Group();
    rootGroup.add(orbitGroup);

    const orbitConfigs = [
      {
        radius: 1.94,
        tube: 0.014,
        color: 0x649e66,
        opacity: 0.72,
        tilt: [0.46, 0.15, 0.3],
        speed: 0.32,
        nodeColor: 0x81c784,
      },
      {
        radius: 2.18,
        tube: 0.011,
        color: 0xd49b42,
        opacity: 0.56,
        tilt: [-0.42, 0.35, -0.44],
        speed: -0.24,
        nodeColor: 0xefc367,
      },
      {
        radius: 2.38,
        tube: 0.01,
        color: 0x4b8f54,
        opacity: 0.44,
        tilt: [0.76, -0.32, 0.18],
        speed: 0.18,
        nodeColor: 0x649e66,
      },
    ];

    const orbitPivotGroups: Array<{ group: THREE.Group; speed: number }> = [];
    const orbitMaterials: THREE.MeshBasicMaterial[] = [];

    const nodeGeo = track(new THREE.SphereGeometry(0.062, 16, 16));

    orbitConfigs.forEach((cfg) => {
      const tiltGroup = new THREE.Group();
      tiltGroup.rotation.set(cfg.tilt[0], cfg.tilt[1], cfg.tilt[2]);
      orbitGroup.add(tiltGroup);

      const spinGroup = new THREE.Group();
      tiltGroup.add(spinGroup);

      const ringGeo = track(new THREE.TorusGeometry(cfg.radius, cfg.tube, 16, 128));
      const ringMat = track(
        new THREE.MeshBasicMaterial({
          color: cfg.color,
          transparent: true,
          opacity: cfg.opacity,
        }),
      );
      orbitMaterials.push(ringMat);

      const ring = new THREE.Mesh(ringGeo, ringMat);
      ring.rotation.x = Math.PI / 2;
      spinGroup.add(ring);

      const nodeMat = track(
        new THREE.MeshStandardMaterial({
          color: cfg.nodeColor,
          emissive: cfg.nodeColor,
          emissiveIntensity: 0.65,
          roughness: 0.2,
        }),
      );
      const node = new THREE.Mesh(nodeGeo, nodeMat);
      node.position.set(cfg.radius, 0, 0);
      spinGroup.add(node);

      orbitPivotGroups.push({ group: spinGroup, speed: cfg.speed });
    });

    // AI Scan Halo sweeping softly around the bowl
    const scanRingGeo = track(new THREE.TorusGeometry(1.66, 0.013, 14, 100));
    const scanRingMat = track(
      new THREE.MeshBasicMaterial({
        color: 0x649e66,
        transparent: true,
        opacity: 0.42,
      }),
    );
    const scanRing = new THREE.Mesh(scanRingGeo, scanRingMat);
    scanRing.rotation.x = Math.PI / 2;
    bowlGroup.add(scanRing);

    // 4. Floating Nutrient / Botanical Motes
    const particleCount = 44;
    const particlePositions = new Float32Array(particleCount * 3);
    const particleSpeeds = new Float32Array(particleCount);
    for (let i = 0; i < particleCount; i++) {
      const angle = Math.random() * Math.PI * 2;
      const dist = 1.1 + Math.random() * 1.45;
      particlePositions[i * 3] = Math.cos(angle) * dist;
      particlePositions[i * 3 + 1] = (Math.random() - 0.5) * 2.6;
      particlePositions[i * 3 + 2] = Math.sin(angle) * dist;
      particleSpeeds[i] = 0.14 + Math.random() * 0.24;
    }

    const particlesGeo = track(new THREE.BufferGeometry());
    particlesGeo.setAttribute(
      "position",
      new THREE.BufferAttribute(particlePositions, 3),
    );
    const glowTex = track(createGlowTexture());
    const particlesMat = track(
      new THREE.PointsMaterial({
        size: 0.12,
        map: glowTex,
        color: 0x649e66,
        transparent: true,
        opacity: 0.65,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    );
    const particles = new THREE.Points(particlesGeo, particlesMat);
    scene.add(particles);

    // Theme updater
    const applyTheme = (isDark: boolean) => {
      renderer.toneMappingExposure = isDark ? 1.18 : 1.05;
      bowlMat.color.setHex(isDark ? 0x192720 : 0xfaf8f2);
      bowlMat.roughness = isDark ? 0.3 : 0.22;
      rimMat.color.setHex(isDark ? 0x74b076 : 0x649e66);
      shadowMat.color.setHex(isDark ? 0x050a08 : 0x113e2e);
      shadowMat.opacity = isDark ? 0.35 : 0.1;

      ambientLight.color.setHex(isDark ? 0x355042 : 0xfaf8f2);
      ambientLight.intensity = isDark ? 1.0 : 0.9;
      hemiLight.color.setHex(isDark ? 0xc2e6ca : 0xffffff);
      hemiLight.groundColor.setHex(isDark ? 0x080d0b : 0xc8c2ae);
      rimLight.intensity = isDark ? 2.8 : 1.9;

      particlesMat.color.setHex(isDark ? 0x81c784 : 0x649e66);
      particlesMat.opacity = isDark ? 0.72 : 0.52;
      scanRingMat.color.setHex(isDark ? 0x81c784 : 0x649e66);

      orbitMaterials.forEach((mat, index) => {
        if (index === 0) mat.opacity = isDark ? 0.8 : 0.68;
        if (index === 1) mat.opacity = isDark ? 0.65 : 0.52;
        if (index === 2) mat.opacity = isDark ? 0.55 : 0.42;
      });
    };

    themeHooksRef.current = { applyTheme };
    applyTheme(darkRef.current);

    // Resize handling
    const handleResize = () => {
      if (!container) return;
      const w = Math.max(container.clientWidth, 1);
      const h = Math.max(container.clientHeight, 1);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h, false);
    };
    handleResize();

    const resizeObserver = new ResizeObserver(handleResize);
    resizeObserver.observe(container);

    // Pointer parallax & drag rotation
    let pointerX = 0;
    let pointerY = 0;
    let dragging = false;
    let lastClientX = 0;
    let lastClientY = 0;
    let dragRotY = 0;
    let dragRotX = 0;
    let velY = 0;
    let velX = 0;

    const onPointerMove = (event: PointerEvent) => {
      const rect = container.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        pointerX = ((event.clientX - rect.left) / rect.width) * 2 - 1;
        pointerY = ((event.clientY - rect.top) / rect.height) * 2 - 1;
      }
      if (dragging) {
        const dx = event.clientX - lastClientX;
        const dy = event.clientY - lastClientY;
        lastClientX = event.clientX;
        lastClientY = event.clientY;
        velY = dx * 0.008;
        velX = dy * 0.005;
        dragRotY += velY;
        dragRotX = THREE.MathUtils.clamp(dragRotX + velX, -0.45, 0.45);
      }
    };

    const onPointerDown = (event: PointerEvent) => {
      dragging = true;
      lastClientX = event.clientX;
      lastClientY = event.clientY;
      container.setPointerCapture?.(event.pointerId);
    };

    const onPointerUp = (event: PointerEvent) => {
      dragging = false;
      container.releasePointerCapture?.(event.pointerId);
    };

    const onPointerLeave = () => {
      dragging = false;
      pointerX = 0;
      pointerY = 0;
    };

    container.addEventListener("pointermove", onPointerMove);
    container.addEventListener("pointerdown", onPointerDown);
    container.addEventListener("pointerup", onPointerUp);
    container.addEventListener("pointercancel", onPointerUp);
    container.addEventListener("pointerleave", onPointerLeave);

    const reducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    let rafId = 0;
    let lastTime = performance.now();
    let elapsed = 0;

    const animate = (now: number) => {
      const dt = Math.min((now - lastTime) / 1000, 0.05);
      lastTime = now;

      if (!reducedMotion) {
        elapsed += dt;
        if (!dragging) {
          dragRotY += velY + dt * 0.24;
          dragRotX = THREE.MathUtils.lerp(dragRotX + velX, 0, dt * 1.8);
          velY *= 0.92;
          velX *= 0.92;
        }

        // Gentle floating levitation
        rootGroup.position.y = 0.08 + Math.sin(elapsed * 1.35) * 0.075;

        // Smooth pointer parallax + drag rotation
        const targetY = dragRotY + pointerX * 0.26;
        const targetX = dragRotX + pointerY * 0.14;
        rootGroup.rotation.y = THREE.MathUtils.lerp(
          rootGroup.rotation.y,
          targetY,
          0.08,
        );
        rootGroup.rotation.x = THREE.MathUtils.lerp(
          rootGroup.rotation.x,
          targetX,
          0.08,
        );

        // Orbit rings
        orbitPivotGroups.forEach(({ group, speed }) => {
          group.rotation.y += dt * speed;
        });

        // AI scan ring sweep
        const scanWave = (Math.sin(elapsed * 1.6) + 1) * 0.5;
        scanRing.position.y = -0.22 + scanWave * 0.72;
        const scanScale = 0.94 + Math.sin(scanWave * Math.PI) * 0.08;
        scanRing.scale.setScalar(scanScale);
        scanRingMat.opacity = 0.18 + Math.sin(scanWave * Math.PI) * 0.34;

        // Drift particles upward
        const posAttr = particlesGeo.getAttribute(
          "position",
        ) as THREE.BufferAttribute;
        const arr = posAttr.array as Float32Array;
        for (let i = 0; i < particleCount; i++) {
          arr[i * 3 + 1] += dt * particleSpeeds[i];
          if (arr[i * 3 + 1] > 1.55) {
            arr[i * 3 + 1] = -1.45;
          }
        }
        posAttr.needsUpdate = true;
        particles.rotation.y = elapsed * 0.06;
      } else {
        rootGroup.rotation.y = THREE.MathUtils.lerp(
          rootGroup.rotation.y,
          dragRotY,
          0.12,
        );
        rootGroup.rotation.x = THREE.MathUtils.lerp(
          rootGroup.rotation.x,
          dragRotX,
          0.12,
        );
      }

      renderer.render(scene, camera);
      rafId = window.requestAnimationFrame(animate);
    };

    rafId = window.requestAnimationFrame(animate);

    return () => {
      window.cancelAnimationFrame(rafId);
      resizeObserver.disconnect();
      container.removeEventListener("pointermove", onPointerMove);
      container.removeEventListener("pointerdown", onPointerDown);
      container.removeEventListener("pointerup", onPointerUp);
      container.removeEventListener("pointercancel", onPointerUp);
      container.removeEventListener("pointerleave", onPointerLeave);
      themeHooksRef.current = null;
      disposables.forEach((d) => d.dispose());
      renderer.dispose();
      if (renderer.domElement.parentNode === container) {
        container.removeChild(renderer.domElement);
      }
    };
  }, []);

  if (webglUnavailable) {
    return (
      <div className="landing-three-fallback">
        <img src="/MealSense_Logo.svg" alt="MealSense" />
        <p>Mindful nutrition &amp; AI food recognition</p>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="landing-three-canvas"
      aria-label="Interactive 3D MealSense nutrition bowl visualization"
      role="img"
    />
  );
}
