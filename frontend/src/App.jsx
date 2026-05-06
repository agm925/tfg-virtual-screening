import { useState, useEffect } from 'react'
import Navbar from './components/Navbar'
import Login from './components/Login'
import Home from './components/Home'
import Algoritmos from './components/Algoritmos'
import RealizarPeticion from './components/RealizarPeticion'
import './App.css'

function App() {
  const [usuario, setUsuario] = useState(null);
  const [paginaActual, setPaginaActual] = useState('home');

  useEffect(() => {
    const sesionGuardada = localStorage.getItem('usuario_tfg');
    if (sesionGuardada) setUsuario(JSON.parse(sesionGuardada));
  }, []);

  const cerrarSesion = () => {
    localStorage.removeItem('usuario_tfg');
    setUsuario(null);
    setPaginaActual('home');
  };

  const alLoguear = (datos) => {
    setUsuario(datos);
    localStorage.setItem('usuario_tfg', JSON.stringify(datos));
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
        {paginaActual === 'algoritmos' && <Algoritmos usuario={usuario} />}
        {paginaActual === 'peticiones' && <RealizarPeticion usuario={usuario} />}
      </main>
    </div>
  );
}

export default App