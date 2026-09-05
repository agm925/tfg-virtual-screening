export default function Navbar({ usuario, paginaActual, setPaginaActual, cerrarSesion }) {
  const enlaces = [
    { id: 'home',       label: 'Home' },
    { id: 'algoritmos', label: 'Algoritmos' },
    { id: 'moleculas',  label: 'Moléculas' },
    { id: 'peticiones', label: 'Peticiones' },
    { id: 'visual',     label: 'Constructor Visual' },
    { id: 'tutorial',   label: 'Tutorial' },
    // Solo visible para admin: el backend igualmente rechaza con 403 a
    // cualquier otro rol, esto es solo para no ofrecer un enlace roto.
    ...(usuario.rol === 'admin' ? [{ id: 'sistema', label: '🛠️ Sistema' }] : []),
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