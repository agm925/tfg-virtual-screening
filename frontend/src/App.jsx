import { useState, useEffect } from 'react'
import Navbar from './components/Navbar'
import Login from './components/Login'
import Home from './components/Home'
import Algoritmos from './components/Algoritmos'
import RealizarPeticion from './components/RealizarPeticion'
import VisualBuilder from './components/VisualBuilder'
import Tutorial from './components/Tutorial'
import Moleculas from './components/Moleculas'
import Sistema from './components/Sistema'
import Administracion from './components/Administracion'
import { getToken, setToken, clearToken, tokenValido, alExpirarSesion } from './api/client'
import './App.css'

function App() {
  const [usuario, setUsuario] = useState(null);
  const [paginaActual, setPaginaActual] = useState('home');
  // "Nuevo workflow" (cabecera e Inicio) abre el constructor Y crea uno. Se
  // pasa como aviso que el constructor consume una sola vez: si se quedara
  // puesto, cada visita posterior al constructor volveria a pedir un nombre.
  const [nuevoWorkflowPedido, setNuevoWorkflowPedido] = useState(false);

  const nuevoWorkflow = () => {
    setNuevoWorkflowPedido(true);
    setPaginaActual('visual');
  };

  const cerrarSesion = () => {
    clearToken();
    localStorage.removeItem('usuario_tfg');
    setUsuario(null);
    setPaginaActual('home');
  };

  useEffect(() => {
    // Restaura la sesión solo si el JWT sigue siendo válido (no caducado);
    // antes se restauraba cualquier objeto de usuario guardado, sin importar
    // cuánto tiempo llevara ahí.
    const token = getToken();
    const sesionGuardada = localStorage.getItem('usuario_tfg');
    if (token && tokenValido(token) && sesionGuardada) {
      setUsuario(JSON.parse(sesionGuardada));
    } else {
      cerrarSesion();
    }
    // Si cualquier petición a la API responde 401 (token caducado o
    // revocado entre medias), se fuerza la vuelta a la pantalla de login.
    alExpirarSesion(cerrarSesion);
  }, []);

  const alLoguear = (datos) => {
    setToken(datos.access_token);
    setUsuario(datos.usuario);
    localStorage.setItem('usuario_tfg', JSON.stringify(datos.usuario));
  };

  if (!usuario) return <Login alLoguear={alLoguear} />;

  return (
    <div className={`app-wrapper ${paginaActual === 'visual' ? 'pantalla-completa' : ''}`}>
      <Navbar
        usuario={usuario}
        paginaActual={paginaActual}
        setPaginaActual={setPaginaActual}
        nuevoWorkflow={nuevoWorkflow}
        cerrarSesion={cerrarSesion}
      />
      <main className="contenido-principal">
        {paginaActual === 'home'      && <Home usuario={usuario} setPaginaActual={setPaginaActual} nuevoWorkflow={nuevoWorkflow} />}
        {paginaActual === 'algoritmos' && <Algoritmos />}
        {paginaActual === 'moleculas'  && <Moleculas />}
        {paginaActual === 'peticiones' && <RealizarPeticion key={usuario.id} usuario={usuario} />}
        {paginaActual === 'visual'    && (
          <VisualBuilder
            key={usuario.id}
            usuario={usuario}
            crearAlAbrir={nuevoWorkflowPedido}
            alCrearAlAbrir={() => setNuevoWorkflowPedido(false)}
          />
        )}
        {paginaActual === 'tutorial'  && <Tutorial />}
        {paginaActual === 'sistema'   && usuario.rol === 'admin' && <Sistema />}
        {paginaActual === 'administracion' && usuario.rol === 'admin' && <Administracion usuario={usuario} />}
      </main>
      {/* El constructor ocupa toda la altura de la ventana: el pie solo va
          en las demás pantallas. */}
      {paginaActual !== 'visual' && (
        <footer className="pie-ual">
          <span>Plataforma de cribado virtual — Trabajo Fin de Grado, Universidad de Almería</span>
          <a href="https://www.ual.es" target="_blank" rel="noopener noreferrer">www.ual.es</a>
        </footer>
      )}
    </div>
  );
}

export default App