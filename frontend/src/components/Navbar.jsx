export default function Navbar({ usuario, paginaActual, setPaginaActual, cerrarSesion }) {
  const enlaces = [
    { id: 'home',       label: 'Home' },
    { id: 'algoritmos', label: 'Algoritmos' },
    { id: 'moleculas',  label: 'Moléculas' },
    { id: 'peticiones', label: 'Peticiones' },
    { id: 'visual',     label: 'Constructor Visual' },
    { id: 'tutorial',   label: 'Tutorial' },
    // Solo visibles para admin. El resto de la plataforma está abierta a
    // cualquier usuario autenticado: lo único que separa al admin del
    // biólogo es la administración de la propia plataforma. El backend
    // rechaza con 403 a un biólogo igualmente; ocultar los enlaces es solo
    // para no ofrecerlos rotos.
    ...(usuario.rol === 'admin' ? [
      { id: 'sistema',        label: '🛠️ Sistema' },
      { id: 'administracion', label: '🛡️ Administración' },
    ] : []),
  ];

  return (
    <nav className="navbar">
      <span className="navbar-logo">🧬 VirtualScreening</span>
      <div className="navbar-links">
        {enlaces.map(e => (
          <button
            key={e.id}
            className={`nav-btn ${paginaActual === e.id ? 'activo' : ''}`}
            onClick={() => setPaginaActual(e.id)}
          >
            {e.label}
          </button>
        ))}
        <button className="nav-btn cerrar-sesion" onClick={cerrarSesion}>
          Cerrar Sesión
        </button>
      </div>
    </nav>
  );
}