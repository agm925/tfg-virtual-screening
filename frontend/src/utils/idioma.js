// El idioma de la interfaz (spec 014): español o inglés.
//
// Diccionario propio en vez de una librería (react-i18next): con dos idiomas,
// textos que ya van en el bundle e interpolación simple, la librería añadía
// dos dependencias para lo que cabe aquí (principio 1 de la constitución).
//
// Sin React ni DOM: se prueba con node --test (tests/frontend/). El contexto
// que lo usa desde los componentes está en components/Idioma.jsx.
import { CLAVE_IDIOMA } from './almacenamiento.js';
import es from '../textos/es.js';
import en from '../textos/en.js';

export const IDIOMAS = ['es', 'en'];
export const IDIOMA_POR_DEFECTO = 'es';

const DICCIONARIOS = { es, en };
const LOCALES = { es: 'es-ES', en: 'en-GB' };

// El texto de `clave` en `idioma`, con sus {variables} rellenas. Si al inglés
// le falta la clave se usa el español (mejor que nada); si tampoco existe, la
// propia clave, para que se note al probar y no quede un hueco en blanco.
export function traducir(idioma, clave, variables = {}, diccionarios = DICCIONARIOS) {
  const texto = diccionarios[idioma]?.[clave]
    ?? diccionarios[IDIOMA_POR_DEFECTO]?.[clave]
    ?? clave;
  // Una variable que no llega se deja a la vista: un «undefined» en pantalla
  // no dice qué falta.
  return texto.replace(/\{(\w+)\}/g, (marca, nombre) =>
    variables[nombre] === undefined || variables[nombre] === null ? marca : String(variables[nombre]));
}

const valido = (idioma) => (IDIOMAS.includes(idioma) ? idioma : IDIOMA_POR_DEFECTO);

// traducir() con el idioma ya puesto: `t` para quien no está en un componente.
// Los módulos de utils/ lo reciben como último parámetro y, sin él, hablan en
// español, el texto de referencia.
export const traductor = (idioma) => (clave, variables) => traducir(idioma, clave, variables);

// La preferencia guardada en este navegador, o español. El almacén puede no
// existir o fallar (modo privado, datos del sitio bloqueados).
export function idiomaInicial(almacen) {
  try {
    return valido(almacen?.getItem(CLAVE_IDIOMA));
  } catch {
    return IDIOMA_POR_DEFECTO;
  }
}

export function guardarIdioma(almacen, idioma) {
  try {
    almacen?.setItem(CLAVE_IDIOMA, idioma);
  } catch {
    /* sin almacén: el idioma dura lo que la pestaña */
  }
}

// Para toLocaleDateString y compañía. Reino Unido y no EE. UU.: día/mes/año,
// como en español, para que una fecha no cambie de orden al cambiar de idioma.
export function localeDe(idioma) {
  return LOCALES[valido(idioma)];
}

// "Pulsa **Guardar**" → [{texto: 'Pulsa ', negrita: false}, {texto: 'Guardar',
// negrita: true}]. Las negritas del tutorial se marcan así para no meter HTML
// en los diccionarios: React los pinta como texto, sin dangerouslySetInnerHTML.
export function trozosConFormato(texto) {
  const partes = texto.split('**');
  // Un número par de partes es que algún ** no se cierra: se deja tal cual.
  if (partes.length % 2 === 0) return [{ texto, negrita: false }];
  return partes
    .map((parte, i) => ({ texto: parte, negrita: i % 2 === 1 }))
    .filter(trozo => trozo.texto);
}
