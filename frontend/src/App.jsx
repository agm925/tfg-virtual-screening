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
    <div className="app-wrapper">
      <Navbar
        usuario={usuario}
        paginaActual={paginaActual}
        setPaginaActual={setPaginaActual}
        cerrarSesion={cerrarSesion}
      />
      <main className="contenido-principal">
        {paginaActual === 'home'      && <Home usuario={usuario} setPaginaActual={setPaginaActual} />}
        {paginaActual === 'algoritmos' && <Algoritmos />}
        {paginaActual === 'moleculas'  && <Moleculas />}
        {paginaActual === 'peticiones' && <RealizarPeticion key={usuario.id} usuario={usuario} />}
        {paginaActual === 'visual'    && <VisualBuilder key={usuario.id} usuario={usuario} />}
        {paginaActual === 'tutorial'  && <Tutorial />}
        {paginaActual === 'sistema'   && usuario.rol === 'admin' && <Sistema />}
        {paginaActual === 'administracion' && usuario.rol === 'admin' && <Administracion usuario={usuario} />}
      </main>
    </div>
  );
}

export default App