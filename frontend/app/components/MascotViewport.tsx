"use client";

import React, { useEffect, useRef, useImperativeHandle, forwardRef } from "react";
import * as THREE from "three";
import { MaterialType, EyeExpression, ActiveAnimation, LightingConfig } from "../types";

interface MascotViewportProps {
  materialType?: MaterialType;
  expression?: EyeExpression;
  animation?: ActiveAnimation;
  lighting?: LightingConfig;
  backdropColor?: string;
  gridVisible?: boolean;
}

export interface MascotViewportRef {
  recenterView: () => void;
}

export const MascotViewport = forwardRef<MascotViewportRef, MascotViewportProps>(
  (
    {
      materialType = "matte_clay",
      expression = "neutral",
      animation = "float",
      lighting = { intensity: 1.0, direction: "top_left" },
      backdropColor = "transparent",
      gridVisible = false,
    },
    ref
  ) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);

    const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
    const sceneRef = useRef<THREE.Scene | null>(null);
    const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
    const robotGroupRef = useRef<THREE.Group | null>(null);
    const headGroupRef = useRef<THREE.Group | null>(null);

    // Mouse tracking state
    const mousePos = useRef<{ x: number; y: number }>({ x: 0, y: 0 });

    const recenterView = () => {
      if (cameraRef.current) {
        cameraRef.current.position.set(0, 0.1, 3.2);
        cameraRef.current.lookAt(0, 0, 0);
      }
    };

    useImperativeHandle(ref, () => ({
      recenterView,
    }));

    // Window mouse move listener for gaze tracking
    useEffect(() => {
      const handleMouseMove = (e: MouseEvent) => {
        // Map mouse coordinates to [-1, 1] range
        const x = (e.clientX / window.innerWidth) * 2 - 1;
        const y = -(e.clientY / window.innerHeight) * 2 + 1;
        mousePos.current.x = x;
        mousePos.current.y = y;
      };

      window.addEventListener("mousemove", handleMouseMove);
      return () => {
        window.removeEventListener("mousemove", handleMouseMove);
      };
    }, []);

    useEffect(() => {
      if (!containerRef.current || !canvasRef.current) return;

      const container = containerRef.current;
      const width = container.clientWidth || 400;
      const height = container.clientHeight || 400;

      // 1. Scene
      const scene = new THREE.Scene();
      sceneRef.current = scene;

      // 2. Camera
      const camera = new THREE.PerspectiveCamera(40, width / height, 0.1, 100);
      camera.position.set(0, 0.1, 3.2);
      cameraRef.current = camera;

      // 3. Renderer
      const renderer = new THREE.WebGLRenderer({
        canvas: canvasRef.current,
        antialias: true,
        alpha: true,
        powerPreference: "high-performance",
        precision: "highp"
      });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 3));
      renderer.setSize(width, height);
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = THREE.PCFSoftShadowMap; // Beautiful soft shadows
      
      if (backdropColor === "transparent") {
        renderer.setClearColor(0x000000, 0);
      } else {
        renderer.setClearColor(new THREE.Color(backdropColor), 1);
      }
      rendererRef.current = renderer;

      // 4. Lights - Set up upper-left directional lighting casting soft shadows to bottom-right
      const ambientLight = new THREE.AmbientLight(0xffffff, 0.8);
      scene.add(ambientLight);

      const directionalLight = new THREE.DirectionalLight(0xffffff, 1.2);
      // upper-left light source position
      directionalLight.position.set(-3.5, 4.5, 3.5);
      directionalLight.castShadow = true;
      directionalLight.shadow.mapSize.width = 2048;
      directionalLight.shadow.mapSize.height = 2048;
      directionalLight.shadow.camera.near = 0.5;
      directionalLight.shadow.camera.far = 15;
      directionalLight.shadow.camera.left = -2.5;
      directionalLight.shadow.camera.right = 2.5;
      directionalLight.shadow.camera.top = 2.5;
      directionalLight.shadow.camera.bottom = -2.5;
      directionalLight.shadow.radius = 8.5; // Gaussian-like blur for soft shadows
      directionalLight.shadow.bias = -0.0005;
      scene.add(directionalLight);

      // Fill light from bottom-right
      const fillLight = new THREE.DirectionalLight(0xffffff, 0.35);
      fillLight.position.set(3, -3, 2);
      scene.add(fillLight);

      // 5. Background Plane to catch the soft shadows
      const bgPlaneGeom = new THREE.PlaneGeometry(15, 15);
      const bgPlaneMat = new THREE.MeshStandardMaterial({
        color: backdropColor === "transparent" ? 0xe6e6e6 : new THREE.Color(backdropColor),
        roughness: 1.0,
        metalness: 0.0,
      });

      const shadowReceiver = new THREE.Mesh(
        bgPlaneGeom,
        backdropColor === "transparent"
          ? new THREE.ShadowMaterial({ opacity: 0.16 })
          : bgPlaneMat
      );
      shadowReceiver.position.z = -0.65;
      shadowReceiver.receiveShadow = true;
      scene.add(shadowReceiver);

      // 6. Robot Main Group
      const robotGroup = new THREE.Group();
      scene.add(robotGroup);
      robotGroupRef.current = robotGroup;

      // Define Materials (Polished Premium White palette)
      const robotMaterial = new THREE.MeshStandardMaterial({
        color: 0xffffff, // Pure white body shell
        roughness: 0.01,
        metalness: 0.01,
      });

      const faceplateMaterial = new THREE.MeshStandardMaterial({
        color: 0xf1f5f9, // Slate-100 faceplate
        roughness: 0.95,
        metalness: 0.02,
      });

      const eyeMaterial = new THREE.MeshStandardMaterial({
        color: 0x4f46e5, // Indigo-600 (Vibrant indigo eyes)
        roughness: 0.9,
        metalness: 0.0,
      });

      // --- Robot Head Creation ---
      const headGroup = new THREE.Group();
      headGroup.position.set(0, 0.35, 0);
      robotGroup.add(headGroup);
      headGroupRef.current = headGroup;

      // Head Shell (Large rounded oval, extruded with a smooth bevel)
      const headShape = new THREE.Shape();
      headShape.absellipse(0, 0, 0.58, 0.38, 0, Math.PI * 2, false);
      const headGeom = new THREE.ExtrudeGeometry(headShape, {
        depth: 0.08,
        bevelEnabled: true,
        bevelSegments: 6,
        bevelSize: 0.05,
        bevelThickness: 0.05,
      });
      headGeom.center();
      const headMesh = new THREE.Mesh(headGeom, robotMaterial);
      headMesh.castShadow = true;
      headMesh.receiveShadow = true;
      headGroup.add(headMesh);

      // Face Visor Screen (Inset oval)
      const faceShape = new THREE.Shape();
      faceShape.absellipse(0, 0, 0.42, 0.22, 0, Math.PI * 2, false);
      const faceGeom = new THREE.ExtrudeGeometry(faceShape, {
        depth: 0.03,
        bevelEnabled: true,
        bevelSegments: 4,
        bevelSize: 0.02,
        bevelThickness: 0.02,
      });
      faceGeom.center();
      const faceMesh = new THREE.Mesh(faceGeom, faceplateMaterial);
      faceMesh.position.set(0, 0, 0.06);
      faceMesh.castShadow = true;
      faceMesh.receiveShadow = true;
      headGroup.add(faceMesh);

      // Eyes (Two vertical ovals)
      const eyeShape = new THREE.Shape();
      eyeShape.absellipse(0, 0, 0.046, 0.076, 0, Math.PI * 2, false);
      
      const leftEyeGeom = new THREE.ExtrudeGeometry(eyeShape, {
        depth: 0.015,
        bevelEnabled: true,
        bevelSegments: 3,
        bevelSize: 0.01,
        bevelThickness: 0.01,
      });
      leftEyeGeom.center();

      const leftEyeMesh = new THREE.Mesh(leftEyeGeom, eyeMaterial);
      leftEyeMesh.position.set(-0.16, 0, 0.085);
      leftEyeMesh.castShadow = true;
      headGroup.add(leftEyeMesh);

      const rightEyeMesh = leftEyeMesh.clone();
      rightEyeMesh.position.set(0.16, 0, 0.085);
      headGroup.add(rightEyeMesh);

      // Antennas (Two placed at top-left and top-right corners)
      const stemGeom = new THREE.CylinderGeometry(0.009, 0.009, 0.2, 16);
      const tipGeom = new THREE.SphereGeometry(0.032, 16, 16);

      // Left Antenna
      const leftStem = new THREE.Mesh(stemGeom, robotMaterial);
      leftStem.position.set(-0.35, 0.38, -0.02);
      leftStem.castShadow = true;
      headGroup.add(leftStem);

      const leftTip = new THREE.Mesh(tipGeom, robotMaterial);
      leftTip.position.set(-0.35, 0.48, -0.02);
      leftTip.castShadow = true;
      headGroup.add(leftTip);

      // Right Antenna
      const rightStem = leftStem.clone();
      rightStem.position.set(0.35, 0.38, -0.02);
      headGroup.add(rightStem);

      const rightTip = leftTip.clone();
      rightTip.position.set(0.35, 0.48, -0.02);
      headGroup.add(rightTip);

      // --- Robot Torso / Body Creation ---
      const bodyGroup = new THREE.Group();
      bodyGroup.position.set(0, -0.38, -0.12);
      robotGroup.add(bodyGroup);

      // Torso shape: Curvy Teardrop (rounded top, beautifully curved/rounded bottom)
      const bodyShape = new THREE.Shape();
      bodyShape.moveTo(0, -0.48);
      bodyShape.bezierCurveTo(0.22, -0.48, 0.32, -0.15, 0.32, 0.18);
      bodyShape.bezierCurveTo(0.32, 0.52, -0.32, 0.52, -0.32, 0.18);
      bodyShape.bezierCurveTo(-0.32, -0.15, -0.22, -0.48, 0, -0.48);

      const bodyGeom = new THREE.ExtrudeGeometry(bodyShape, {
        depth: 0.06,
        bevelEnabled: true,
        bevelSegments: 6,
        bevelSize: 0.04,
        bevelThickness: 0.04,
      });
      bodyGeom.center();
      const bodyMesh = new THREE.Mesh(bodyGeom, robotMaterial);
      bodyMesh.castShadow = true;
      bodyMesh.receiveShadow = true;
      bodyGroup.add(bodyMesh);

      // Detached shoulder side panels (vertical capsules curving inward)
      const armShape = new THREE.Shape();
      armShape.absellipse(0, 0, 0.055, 0.22, 0, Math.PI * 2, false);

      const armGeom = new THREE.ExtrudeGeometry(armShape, {
        depth: 0.035,
        bevelEnabled: true,
        bevelSegments: 4,
        bevelSize: 0.02,
        bevelThickness: 0.02,
      });
      armGeom.center();

      const leftArm = new THREE.Mesh(armGeom, robotMaterial);
      leftArm.position.set(-0.25, 0.02, 0.04);
      leftArm.rotation.z = 0.12; // curve inward
      leftArm.castShadow = true;
      leftArm.receiveShadow = true;
      bodyGroup.add(leftArm);

      const rightArm = leftArm.clone();
      rightArm.position.set(0.25, 0.02, 0.04);
      rightArm.rotation.z = -0.12;
      bodyGroup.add(rightArm);

      // Resize observer
      const resizeObserver = new ResizeObserver((entries) => {
        if (!entries[0]) return;
        const { width: newW, height: newH } = entries[0].contentRect;
        if (cameraRef.current && rendererRef.current) {
          cameraRef.current.aspect = newW / newH;
          cameraRef.current.updateProjectionMatrix();
          rendererRef.current.setSize(newW, newH);
        }
      });
      resizeObserver.observe(container);

      // Animation loop
      let animationFrameId: number;
      const startTime = performance.now();

      const animate = () => {
        animationFrameId = requestAnimationFrame(animate);

        const time = (performance.now() - startTime) / 1000;

        // Subtle idle floating translation (very calm)
        if (robotGroupRef.current) {
          robotGroupRef.current.position.y = Math.sin(time * 1.5) * 0.025;
        }

        // Active gaze tracking: Tilt head to track mouse cursor
        if (headGroupRef.current) {
          const targetGazeY = mousePos.current.x * 0.35;
          const targetGazeX = -mousePos.current.y * 0.22;
          headGroupRef.current.rotation.y = THREE.MathUtils.lerp(headGroupRef.current.rotation.y, targetGazeY, 0.08);
          headGroupRef.current.rotation.x = THREE.MathUtils.lerp(headGroupRef.current.rotation.x, targetGazeX, 0.08);
        }

        renderer.render(scene, camera);
      };

      animate();

      return () => {
        cancelAnimationFrame(animationFrameId);
        resizeObserver.disconnect();
        
        scene.traverse((object) => {
          if (object instanceof THREE.Mesh) {
            object.geometry.dispose();
            if (Array.isArray(object.material)) {
              object.material.forEach((mat) => mat.dispose());
            } else {
              object.material.dispose();
            }
          }
        });
        renderer.dispose();
      };
    }, []);

    return (
      <div 
        ref={containerRef} 
        className="w-full h-full relative overflow-hidden select-none"
      >
        <canvas ref={canvasRef} className="w-full h-full block" />
      </div>
    );
  }
);

MascotViewport.displayName = "MascotViewport";
export default MascotViewport;
