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
          <p>Registra un script Python de análisis molecular en la plataforma para usarlo en tus pipelines y peticiones.</p>
          <button className="tarjeta-btn azul">Ir a Algoritmos →</button>
        </div>

        <div className="tarjeta" onClick={() => setPaginaActual('peticiones')}>
          <div className="tarjeta-icono">🔬</div>
          <h2>Prueba los algoritmos disponibles</h2>
          <p>Sube una molécula y ejecuta cualquier algoritmo registrado. Los resultados se procesan en cola y recibirás un aviso al terminar.</p>
          <button className="tarjeta-btn verde">Realizar Petición →</button>
        </div>

        <div className="tarjeta" onClick={() => setPaginaActual('visual')}>
          <div className="tarjeta-icono">🔧</div>
          <h2>Constructor de flujo de trabajo</h2>
          <p>Diseña y ejecuta pipelines de cribado virtual completos de forma visual, conectando nodos de preprocesado, alineación, comparación y docking.</p>
          <button className="tarjeta-btn" style={{ background: '#8e44ad' }}>Abrir Constructor Visual →</button>
        </div>

        <div className="tarjeta" onClick={() => setPaginaActual('tutorial')}>
          <div className="tarjeta-icono">📖</div>
          <h2>Aprende a usar la plataforma</h2>
          <p>Guía paso a paso sobre todas las secciones: cómo subir moléculas, registrar algoritmos, construir workflows y entender los resultados.</p>
          <button className="tarjeta-btn" style={{ background: '#e67e22' }}>Ver Tutorial →</button>
        </div>
      </div>
    </div>
  );
}