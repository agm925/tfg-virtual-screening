import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '../api/client';
import '../styles/MolViewer3D.css';

export default function MolViewer3D({ archivo, onClose }) {
  const viewerRef = useRef(null);
  const [estado, setEstado] = useState('cargando'); // 'cargando' | 'ok' | 'error'
  const [estilo, setEstilo] = useState('stick');

  useEffect(() => {
    if (!archivo) return;

    const init = async () => {
      try {
        // Esperar a que 3Dmol cargue si todavía no está listo
        let intentos = 0;
        while (!window.$3Dmol && intentos < 20) {
          await new Promise(r => setTimeout(r, 200));
          intentos++;
        }
        if (!window.$3Dmol) throw new Error('3Dmol.js no cargó');

        // /uploads/{archivo} exige token desde el security-review; para una
        // URL absoluta externa (poco habitual aquí) se usa fetch normal.
        const esUrlAbsoluta = archivo.startsWith('http');
        const resp = esUrlAbsoluta
          ? await fetch(archivo)
          : await apiFetch(`/uploads/${archivo}`);
        if (!resp.ok) throw new Error('No se pudo descargar el archivo');
        const content = await resp.text();

        const ext = archivo.split('.').pop().toLowerCase();
        const formato = ext === 'mol2' ? 'mol2' : 'sdf';

        const viewer = window.$3Dmol.createViewer(viewerRef.current, {
          backgroundColor: '#0f0f1a',
        });

        viewer.addModel(content, formato);
        aplicarEstilo(viewer, estilo);
        viewer.zoomTo();
        viewer.render();

        // Guardar el viewer para poder cambiar estilo después
        viewerRef.current._viewer = viewer;
        setEstado('ok');
      } catch (e) {
        console.error('MolViewer3D:', e);
        setEstado('error');
      }
    };

    init();
  }, [archivo]);

  const aplicarEstilo = (viewer, modo) => {
    viewer.setStyle({}, {});
    if (modo === 'stick') {
      viewer.setStyle({}, { stick: { radius: 0.15 }, sphere: { scale: 0.3 } });
    } else if (modo === 'sphere') {
      viewer.setStyle({}, { sphere: {} });
    } else if (modo === 'surface') {
      viewer.setStyle({}, { stick: { radius: 0.1 } });
      viewer.addSurface(window.$3Dmol.SurfaceType.VDW, { opacity: 0.6, colorscheme: 'ssJmol' });
    } else if (modo === 'cartoon') {
      viewer.setStyle({}, { cartoon: { color: 'spectrum' } });
    }
    viewer.render();
  };

  const cambiarEstilo = (nuevoEstilo) => {
    setEstilo(nuevoEstilo);
    const viewer = viewerRef.current?._viewer;
    if (viewer) aplicarEstilo(viewer, nuevoEstilo);
  };

  return (
    <div className="viewer3d-overlay" onClick={onClose}>
      <div className="viewer3d-modal" onClick={e => e.stopPropagation()}>
        <div className="viewer3d-header">
          <span className="viewer3d-titulo">🔬 {archivo}</span>
          <div className="viewer3d-estilos">
            {['stick', 'sphere', 'surface'].map(s => (
              <button
                key={s}
                className={`btn-estilo ${estilo === s ? 'activo' : ''}`}
                onClick={() => cambiarEstilo(s)}
              >
                {s}
              </button>
            ))}
          </div>
          <button className="viewer3d-close" onClick={onClose}>✕</button>
        </div>

        <div className="viewer3d-canvas-wrap">
          {estado === 'cargando' && (
            <div className="viewer3d-overlay-msg">⏳ Cargando molécula…</div>
          )}
          {estado === 'error' && (
            <div className="viewer3d-overlay-msg error">
              ❌ No se pudo visualizar este archivo.<br />
              <small>Solo se soportan .sdf y .mol2 con coordenadas 3D.</small>
            </div>
          )}
          <div ref={viewerRef} className="viewer3d-canvas" />
        </div>

        <div className="viewer3d-hint">
          🖱️ Arrastra para rotar · Scroll para zoom · Click derecho para mover
        </div>
      </div>
    </div>
  );
}
