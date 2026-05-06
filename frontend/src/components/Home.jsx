export default function Home({ usuario, setPaginaActual }) {
  return (
    <div className="home-wrapper">
      <h1 className="home-bienvenida">
        Bienvenido, <span className="nombre-usuario">{usuario.nombre}</span> 👋
      </h1>
      <p className="home-subtitulo">¿Qué quieres hacer hoy?</p>

      <div className="home-tarjetas">
        <div className="tarjeta" onClick={() => setPaginaActual('algoritmos')}>
          <div className="tarjeta-icono">⚙️</div>
          <h2>Sube tu propio algoritmo</h2>
          <p>Registra un script de comparación molecular en la plataforma para usarlo en tus simulaciones.</p>
          <button className="tarjeta-btn azul">Ir a Algoritmos →</button>
        </div>

        <div className="tarjeta" onClick={() => setPaginaActual('peticiones')}>
          <div className="tarjeta-icono">🔬</div>
          <h2>Prueba los algoritmos disponibles</h2>
          <p>Sube tu molécula en formato .mol2 y ejecuta cualquier algoritmo registrado en la plataforma.</p>
          <button className="tarjeta-btn verde">Realizar Petición →</button>
        </div>
      </div>
    </div>
  );
}