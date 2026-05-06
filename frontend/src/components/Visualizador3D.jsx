import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';
import '../styles/Visualizador3D.css';

const Visualizador3D = ({ nombreArchivo }) => {
  const containerRef = useRef(null);
  const sceneRef = useRef(null);
  const cameraRef = useRef(null);
  const rendererRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current || !nombreArchivo) return;

    // Inicializar Three.js
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf5f5f5);
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(
      75,
      containerRef.current.clientWidth / containerRef.current.clientHeight,
      0.1,
      1000
    );
    camera.position.z = 10;
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(containerRef.current.clientWidth, containerRef.current.clientHeight);
    renderer.shadowMap.enabled = true;
    containerRef.current.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // Iluminación
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);

    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(10, 10, 10);
    directionalLight.castShadow = true;
    scene.add(directionalLight);

    // Cargar molécula simulada (ej: átomos de ejemplo)
    // En un caso real, parseamos el archivo .mol2
    const atomosSimulados = [
      { posicion: [0, 0, 0], radio: 0.3, color: 0x1f77b4, nombre: 'C' },
      { posicion: [1.5, 0, 0], radio: 0.25, color: 0xff7f0e, nombre: 'O' },
      { posicion: [-1.5, 0, 0], radio: 0.25, color: 0xff7f0e, nombre: 'O' },
      { posicion: [0, 1.5, 0], radio: 0.2, color: 0x2ca02c, nombre: 'N' },
      { posicion: [0, -1.5, 0], radio: 0.2, color: 0x2ca02c, nombre: 'N' },
    ];

    // Crear esferas para átomos
    atomosSimulados.forEach((atomo) => {
      const geometry = new THREE.SphereGeometry(atomo.radio, 32, 32);
      const material = new THREE.MeshStandardMaterial({
        color: atomo.color,
        metalness: 0.3,
        roughness: 0.4,
      });
      const sphere = new THREE.Mesh(geometry, material);
      sphere.position.set(...atomo.posicion);
      sphere.castShadow = true;
      sphere.receiveShadow = true;
      scene.add(sphere);
    });

    // Crear enlaces (cilindros)
    const enlaces = [
      [0, 1],
      [0, 2],
      [0, 3],
      [0, 4],
    ];

    enlaces.forEach(([i, j]) => {
      const pos1 = new THREE.Vector3(...atomosSimulados[i].posicion);
      const pos2 = new THREE.Vector3(...atomosSimulados[j].posicion);
      const distancia = pos1.distanceTo(pos2);

      const cilindro = new THREE.CylinderGeometry(0.08, 0.08, distancia, 8);
      const material = new THREE.MeshStandardMaterial({
        color: 0x888888,
        metalness: 0.2,
        roughness: 0.5,
      });
      const mesh = new THREE.Mesh(cilindro, material);

      const punto_medio = new THREE.Vector3().addVectors(pos1, pos2).multiplyScalar(0.5);
      mesh.position.copy(punto_medio);

      const direccion = new THREE.Vector3().subVectors(pos2, pos1).normalize();
      mesh.lookAt(pos2);

      mesh.castShadow = true;
      mesh.receiveShadow = true;
      scene.add(mesh);
    });

    // Controles de interacción
    let isDragging = false;
    let previousMousePosition = { x: 0, y: 0 };
    let rotation = { x: 0, y: 0 };

    containerRef.current.addEventListener('mousedown', (e) => {
      isDragging = true;
      previousMousePosition = { x: e.clientX, y: e.clientY };
    });

    containerRef.current.addEventListener('mousemove', (e) => {
      if (isDragging) {
        const deltaX = e.clientX - previousMousePosition.x;
        const deltaY = e.clientY - previousMousePosition.y;

        rotation.y += deltaX * 0.005;
        rotation.x += deltaY * 0.005;

        scene.rotation.y = rotation.y;
        scene.rotation.x = rotation.x;

        previousMousePosition = { x: e.clientX, y: e.clientY };
      }
    });

    containerRef.current.addEventListener('mouseup', () => {
      isDragging = false;
    });

    // Scroll para zoom
    containerRef.current.addEventListener('wheel', (e) => {
      e.preventDefault();
      const delta = e.deltaY > 0 ? 0.1 : -0.1;
      camera.position.z += delta * 2;
      camera.position.z = Math.max(2, Math.min(50, camera.position.z));
    });

    // Render loop
    const animate = () => {
      requestAnimationFrame(animate);
      renderer.render(scene, camera);
    };
    animate();

    // Handle resize
    const handleResize = () => {
      if (containerRef.current) {
        const width = containerRef.current.clientWidth;
        const height = containerRef.current.clientHeight;
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        renderer.setSize(width, height);
      }
    };
    window.addEventListener('resize', handleResize);

    // Cleanup
    return () => {
      window.removeEventListener('resize', handleResize);
      if (containerRef.current && renderer.domElement.parentNode === containerRef.current) {
        containerRef.current.removeChild(renderer.domElement);
      }
    };
  }, [nombreArchivo]);

  return (
    <div className="visualizador-3d-container">
      <div className="visualizador-3d-header">
        <h3>🧬 Visualizador Molecular 3D</h3>
        <p className="help-text">Arrastra para rotar • Scroll para zoom</p>
      </div>
      <div ref={containerRef} className="visualizador-3d-canvas" />
    </div>
  );
};

export default Visualizador3D;
