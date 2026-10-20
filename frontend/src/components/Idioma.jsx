import { useCallback, useEffect, useMemo, useState } from 'react'
import { ContextoIdioma } from '../hooks/useIdioma'
import { guardarIdioma, idiomaInicial, traducir } from '../utils/idioma'

function almacenLocal() {
  try { return window.localStorage; } catch { return null; }
}

// Da el idioma a toda la aplicación (spec 014). Envuelve a <App /> en
// main.jsx, por fuera de la sesión: la pantalla de acceso también se traduce.
export default function ProveedorIdioma({ children }) {
  // Se lee al crear el estado y no en un efecto: así la primera pintura ya
  // sale en el idioma guardado, sin un parpadeo en español.
  const [idioma, setIdioma] = useState(() => idiomaInicial(almacenLocal()));

  // El lang del documento: los lectores de pantalla eligen la voz con él y el
  // navegador, el diccionario del corrector y la partición de palabras.
  useEffect(() => {
    document.documentElement.lang = idioma;
  }, [idioma]);

  const cambiarIdioma = useCallback((nuevo) => {
    guardarIdioma(almacenLocal(), nuevo);
    setIdioma(nuevo);
  }, []);

  const valor = useMemo(() => ({
    idioma,
    cambiarIdioma,
    t: (clave, variables) => traducir(idioma, clave, variables),
  }), [idioma, cambiarIdioma]);

  return <ContextoIdioma.Provider value={valor}>{children}</ContextoIdioma.Provider>;
}
