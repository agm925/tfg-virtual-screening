import { useState } from 'react'
import LogoUAL from './LogoUAL'

// Las secciones, agrupadas por lo que hace el usuario: trabajar (lanzar y
// recoger cribados), preparar lo que usan (moléculas y algoritmos) y aprender.
const ENLACES = [
  { id: 'home',       label: 'Inicio' },
  { id: 'visual',     label: 'Constructor' },
  { id: 'peticiones', label: 'Resultados' },
  { id: 'moleculas',  label: 'Moléculas' },
  { id: 'visor',      label: 'Visor 3D' },
  { id: 'algoritmos', label: 'Algoritmos' },
  { id: 'tutorial',   label: 'Tutorial' },
];

// Solo visibles para admin. El resto de la plataforma está abierta a cualquier
// usuario autenticado: lo único que separa al admin del biólogo es la
// administración de la propia plataforma. El backend rechaza con 403 a un
// biólogo igualmente; ocultar los enlaces es solo para no ofrecerlos rotos.
const ENLACES_ADMIN = [
  { id: 'administracion', label: 'Administración' },
  { id: 'sistema',        label: 'Sistema' },
];

export default function Navbar({ usuario, paginaActual, setPaginaActual, nuevoWorkflow, cerrarSesion }) {
  const [menuAbierto, setMenuAbierto] = useState(false);
  const enlaces = usuario.rol === 'admin' ? [...ENLACES, ...ENLACES_ADMIN] : ENLACES;

  const ir = (id) => {
    setPaginaActual(id);
    setMenuAbierto(false);
  };

  return (
    <header>
      <div className="franja-ual">
        <div className="franja-ual-contenido">
          <span className="franja-ual-tfg">Universidad de Almería</span>
          <div className="franja-usuario">
            <span>{usuario.nombre}</span>
            <button onClick={cerrarSesion}>Cerrar sesión</button>
          </div>
        </div>
      </div>

      <nav className="navbar" aria-label="Secciones de la plataforma">
        <div className="navbar-contenido">
          <button className="navbar-marca" onClick={() => ir('home')} aria-label="Ir al inicio">
            <LogoUAL className="navbar-logo" claseTexto="navbar-logo-texto" />
            <span className="navbar-separador" aria-hidden="true" />
            <span className="navbar-app">Cribado virtual</span>
          </button>

          <button
            className="nav-menu-boton"
            aria-expanded={menuAbierto}
            aria-controls="navbar-links"
            onClick={() => setMenuAbierto(!menuAbierto)}
          >
            Menú
          </button>

          <div id="navbar-links" className={`navbar-links ${menuAbierto ? 'abierto' : ''}`}>
            {enlaces.map(e => (
              <button
                key={e.id}
                className={`nav-btn ${paginaActual === e.id ? 'activo' : ''}`}
                aria-current={paginaActual === e.id ? 'page' : undefined}
                onClick={() => ir(e.id)}
              >
                {e.label}
              </button>
            ))}
            {/* En el constructor sobra: el editor tiene su propio botón. */}
            {paginaActual !== 'visual' && (
              <button className="nav-destacado" onClick={() => { nuevoWorkflow(); setMenuAbierto(false); }}>
                Nuevo workflow
              </button>
            )}
          </div>
        </div>
      </nav>
    </header>
  );
}
