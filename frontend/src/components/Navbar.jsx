import { useState } from 'react'
import LogoUAL from './LogoUAL'
import SelectorIdioma from './SelectorIdioma'
import { useIdioma } from '../hooks/useIdioma'

// Las secciones, agrupadas por lo que hace el usuario: trabajar (lanzar y
// recoger cribados), preparar lo que usan (moléculas y algoritmos) y aprender.
// `texto` es la clave de su nombre en los diccionarios (spec 014).
const ENLACES = [
  { id: 'home',       texto: 'cabecera.inicio' },
  { id: 'visual',     texto: 'cabecera.constructor' },
  { id: 'peticiones', texto: 'cabecera.resultados' },
  { id: 'moleculas',  texto: 'cabecera.moleculas' },
  { id: 'visor',      texto: 'cabecera.visor' },
  { id: 'algoritmos', texto: 'cabecera.algoritmos' },
  { id: 'tutorial',   texto: 'cabecera.tutorial' },
];

// Solo visibles para admin. El resto de la plataforma está abierta a cualquier
// usuario autenticado: lo único que separa al admin del biólogo es la
// administración de la propia plataforma. El backend rechaza con 403 a un
// biólogo igualmente; ocultar los enlaces es solo para no ofrecerlos rotos.
const ENLACES_ADMIN = [
  { id: 'administracion', texto: 'cabecera.administracion' },
  { id: 'sistema',        texto: 'cabecera.sistema' },
];

export default function Navbar({ usuario, paginaActual, setPaginaActual, nuevoWorkflow, cerrarSesion }) {
  const { t } = useIdioma();
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
          <span className="franja-ual-tfg">{t('cabecera.universidad')}</span>
          <div className="franja-usuario">
            <SelectorIdioma />
            <span>{usuario.nombre}</span>
            <button onClick={cerrarSesion}>{t('cabecera.cerrar_sesion')}</button>
          </div>
        </div>
      </div>

      <nav className="navbar" aria-label={t('cabecera.secciones')}>
        <div className="navbar-contenido">
          <button className="navbar-marca" onClick={() => ir('home')} aria-label={t('cabecera.ir_inicio')}>
            <LogoUAL className="navbar-logo" claseTexto="navbar-logo-texto" />
            <span className="navbar-separador" aria-hidden="true" />
            <span className="navbar-app">{t('cabecera.app')}</span>
          </button>

          {/* En el móvil la franja se oculta: el idioma pasa aquí, junto a
              «Menú», para cambiarlo sin abrir el menú (spec 014, R3). */}
          <SelectorIdioma className="en-barra" />
          <button
            className="nav-menu-boton"
            aria-expanded={menuAbierto}
            aria-controls="navbar-links"
            onClick={() => setMenuAbierto(!menuAbierto)}
          >
            {t('cabecera.menu')}
          </button>

          <div id="navbar-links" className={`navbar-links ${menuAbierto ? 'abierto' : ''}`}>
            {enlaces.map(e => (
              <button
                key={e.id}
                className={`nav-btn ${paginaActual === e.id ? 'activo' : ''}`}
                aria-current={paginaActual === e.id ? 'page' : undefined}
                onClick={() => ir(e.id)}
              >
                {t(e.texto)}
              </button>
            ))}
            {/* En el móvil la franja de arriba se oculta para que la cabecera
                no se coma la pantalla (spec 010): quién eres y salir pasan
                aquí, dentro del menú. */}
            <div className="menu-usuario">
              <span>{usuario.nombre}</span>
              <button onClick={cerrarSesion}>{t('cabecera.cerrar_sesion')}</button>
            </div>
            {/* En el constructor sobra: el editor tiene su propio botón. */}
            {paginaActual !== 'visual' && (
              <button className="nav-destacado" onClick={() => { nuevoWorkflow(); setMenuAbierto(false); }}>
                {t('cabecera.nuevo_workflow')}
              </button>
            )}
          </div>
        </div>
      </nav>
    </header>
  );
}
