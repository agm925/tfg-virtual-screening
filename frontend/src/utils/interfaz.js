// La interfaz de un algoritmo (spec 013): sus entradas de fichero, cómo recibe
// la salida y sus opciones de sí/no. La declara su autor al subirlo y la
// comprueba el banco de pruebas (app/banco_pruebas.py, validar_interfaz); aquí
// está lo que comparten el formulario de subida y los nodos del Constructor.
import { IDIOMA_POR_DEFECTO, traductor } from './idioma.js';

export const MAX_ENTRADAS = 6;
export const MAX_OPCIONES = 6;

// Las entradas de hoy de cada tipo, las mismas que ENTRADAS_POR_DEFECTO del
// backend. Una interfaz así se guarda como null y se ejecuta como siempre.
// Los nombres son claves (spec 014): el backend solo compara las clases, así
// que el nombre que proponga el formulario puede estar en cualquier idioma.
const ENTRADAS_POR_DEFECTO = {
  preprocesado: [{ nombre: 'interfaz.molecula', clase: 'molecula' }],
  alineacion:   [{ nombre: 'interfaz.molecula', clase: 'molecula' }],
  comparacion:  [{ nombre: 'interfaz.molecula_1', clase: 'molecula' }, { nombre: 'interfaz.molecula_2', clase: 'molecula' }],
  docking:      [{ nombre: 'interfaz.ligando', clase: 'molecula' }, { nombre: 'interfaz.receptor', clase: 'proteina' }],
};

export function interfazPorDefecto(tipo, t = traductor(IDIOMA_POR_DEFECTO)) {
  return {
    entradas: (ENTRADAS_POR_DEFECTO[tipo] || ENTRADAS_POR_DEFECTO.preprocesado).map(e => ({ ...e, nombre: t(e.nombre) })),
    opcion_salida: null,
    opciones: [],
  };
}

// Un conector por entrada, en orden; los ids son los que lee el motor
// (entrada_0..N-1). Sin interfaz, null: el nodo pinta los de siempre.
export function conectoresDe(interfaz) {
  if (!interfaz?.entradas?.length) return null;
  return interfaz.entradas.map((e, i) => ({ id: `entrada_${i}`, nombre: e.nombre }));
}

// Las conexiones que llegan a este nodo por un conector que ya no tiene: al
// cambiar de algoritmo, quedarían colgando de un punto que no se ve.
export function conexionesSobrantes(aristas, nodoId, idsConectores) {
  return aristas.filter(a => a.target === nodoId && !idsConectores.includes(a.targetHandle));
}

// La llamada como la verá el script, con los nombres de las entradas.
export function vistaPreviaLlamada(nombreScript, interfaz, t = traductor(IDIOMA_POR_DEFECTO)) {
  const partes = [nombreScript || t('interfaz.script'), ...interfaz.entradas.map(e => e.nombre || '?')];
  if (interfaz.opcion_salida) partes.push(interfaz.opcion_salida);
  partes.push(t('interfaz.salida'));
  partes.push(...interfaz.opciones.map(o => o.opcion).filter(Boolean));
  return partes.join(' ');
}
