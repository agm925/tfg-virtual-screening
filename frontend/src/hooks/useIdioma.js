import { createContext, useContext } from 'react';
import { IDIOMA_POR_DEFECTO, traducir } from '../utils/idioma';

// El idioma de la interfaz (spec 014). Lo da ProveedorIdioma
// (components/Idioma.jsx) y lo lee cualquier componente con useIdioma():
//   const { t, idioma, cambiarIdioma } = useIdioma();
//   t('cabecera.menu')  ·  t('inicio.saludo', { nombre })
//
// El valor por defecto sirve fuera del proveedor (pruebas, un componente
// suelto): español y sin poder cambiarlo.
export const ContextoIdioma = createContext({
  idioma: IDIOMA_POR_DEFECTO,
  cambiarIdioma: () => {},
  t: (clave, variables) => traducir(IDIOMA_POR_DEFECTO, clave, variables),
});

export function useIdioma() {
  return useContext(ContextoIdioma);
}
