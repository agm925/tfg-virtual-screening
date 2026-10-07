import { useState, useEffect, useRef } from 'react'
import Navbar from './components/Navbar'
import Login from './components/Login'
import Home from './components/Home'
import Algoritmos from './components/Algoritmos'
import RealizarPeticion from './components/RealizarPeticion'
import VisualBuilder from './components/VisualBuilder'
import Tutorial from './components/Tutorial'
import Moleculas from './components/Moleculas'
import Visor3D from './components/Visor3D'
import Sistema from './components/Sistema'
import Administracion from './components/Administracion'
import { getToken, setToken, tokenValido, alExpirarSesion } from './api/client'
import { CLAVE_USUARIO, olvidarSesion } from './utils/almacenamiento'
import './App.css'

function App() {
  const [usuario, setUsuario] = useState(null);
  const [paginaActual, setPaginaActual] = useState('home');
  // "Nuevo workflow" (cabecera e Inicio) abre el constructor Y crea uno. Se
  // pasa como aviso que el constructor consume una sola vez: si se quedara
  // puesto, cada visita posterior al constructor volveria a pedir un nombre.
  const [nuevoWorkflowPedido, setNuevoWorkflowPedido] = useState(false);
  // Fichero que «Ver en 3D» manda al visor (spec 002, RF-15). Como el aviso
  // anterior, el visor lo consume una sola vez al montarse: si se quedara
  // puesto, volver al visor desde el menú lo colocaría otra vez en A.
  const [ficheroParaVisor, setFicheroParaVisor] = useState(null);

  // El editor deja aqui una funcion que, si hay cambios sin guardar, pregunta
  // si se pueden perder (VisualBuilder, confirmarDescarte). Se consulta antes
  // de sacar al usuario del editor.
  const salidaEditorRef = useRef(null);
  const puedeSalirDelEditor = () => salidaEditorRef.current?.() ?? true;

  // Devuelve si se ha cambiado de página: el usuario puede quedarse en el
  // editor para no perder los cambios.
  const irA = (pagina) => {
    if (pagina !== paginaActual && paginaActual === 'visual' && !puedeSalirDelEditor()) return false;
    setPaginaActual(pagina);
    return true;
  };

  // Pasa por irA para que, desde el editor con cambios sin guardar, se pida
  // la misma confirmación que en cualquier otra salida (RF-15, spec 001).
  const abrirEnVisor = (fichero) => {
    if (irA('visor')) setFicheroParaVisor(fichero);
  };

  // Desde la cabecera; el cierre por token caducado no pregunta: la sesion
  // ya no sirve para guardar nada.
  const salir = () => {
    if (paginaActual === 'visual' && !puedeSalirDelEditor()) return;
    cerrarSesion();
  };

  const nuevoWorkflow = () => {
    setNuevoWorkflowPedido(true);
    setPaginaActual('visual');
  };

  const cerrarSesion = () => {
    // El token, el usuario y los borradores del editor y del visor (llevan
    // nombres de ficheros y grafos del usuario): no se dejan en un equipo
    // compartido. Solo las claves de MolServer: el resto del almacenamiento
    // es de las demás aplicaciones del mismo dominio (spec 004).
    olvidarSesion();
    setUsuario(null);
    setPaginaActual('home');
  };

  useEffect(() => {
    // Restaura la sesión solo si el JWT sigue siendo válido (no caducado);
    // antes se restauraba cualquier objeto de usuario guardado, sin importar
    // cuánto tiempo llevara ahí.
    const token = getToken();
    const sesionGuardada = localStorage.getItem(CLAVE_USUARIO);
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
    localStorage.setItem(CLAVE_USUARIO, JSON.stringify(datos.usuario));
  };

  if (!usuario) return <Login alLoguear={alLoguear} />;

  return (
    <div className={`app-wrapper ${paginaActual === 'visual' ? 'pantalla-completa' : ''}`}>
      <Navbar
        usuario={usuario}
        paginaActual={paginaActual}
        setPaginaActual={irA}
        nuevoWorkflow={nuevoWorkflow}
        cerrarSesion={salir}
      />
      <main className="contenido-principal">
        {paginaActual === 'home'      && <Home usuario={usuario} setPaginaActual={irA} nuevoWorkflow={nuevoWorkflow} abrirEnVisor={abrirEnVisor} />}
        {paginaActual === 'algoritmos' && <Algoritmos />}
        {paginaActual === 'moleculas'  && <Moleculas abrirEnVisor={abrirEnVisor} />}
        {paginaActual === 'visor'      && (
          <Visor3D
            key={usuario.id}
            usuario={usuario}
            irA={irA}
            llegada={ficheroParaVisor}
            alLlegar={() => setFicheroParaVisor(null)}
          />
        )}
        {paginaActual === 'peticiones' && <RealizarPeticion key={usuario.id} usuario={usuario} abrirEnVisor={abrirEnVisor} />}
        {paginaActual === 'visual'    && (
          <VisualBuilder
            key={usuario.id}
            usuario={usuario}
            crearAlAbrir={nuevoWorkflowPedido}
            alCrearAlAbrir={() => setNuevoWorkflowPedido(false)}
            salidaRef={salidaEditorRef}
            abrirEnVisor={abrirEnVisor}
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
          <span>MolServer · Plataforma de cribado virtual — Universidad de Almería</span>
          <a href="https://www.ual.es" target="_blank" rel="noopener noreferrer">www.ual.es</a>
        </footer>
      )}
    </div>
  );
}

export default App