export default function Navbar({ usuario, paginaActual, setPaginaActual, cerrarSesion }) {
  const enlaces = [
    { id: 'home',       label: 'Home' },
    { id: 'algoritmos', label: 'Algoritmos' },
    { id: 'peticiones', label: 'Realizar Petición' },
    { id: 'knime',      label: 'KNIME Builder' },
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