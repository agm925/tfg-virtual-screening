// Pruebas de frontend/src/utils/interfaz.js (spec 013): la interfaz de un
// algoritmo --entradas, salida y opciones-- en el formulario y en el nodo.
//
//   node --test "tests/frontend/**/*.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  MAX_ENTRADAS, interfazPorDefecto, conectoresDe, conexionesSobrantes, vistaPreviaLlamada,
} from '../../frontend/src/utils/interfaz.js';

const CLEAN = {
  entradas: [{ nombre: 'Molécula', clase: 'molecula' }],
  opcion_salida: '-o',
  opciones: [{ opcion: '--all', nombre: 'Quitar todos los hidrógenos' }],
};

test('al elegir un tipo, el formulario empieza con sus entradas de hoy', () => {
  assert.deepEqual(interfazPorDefecto('docking').entradas, [
    { nombre: 'Ligando', clase: 'molecula' },
    { nombre: 'Receptor', clase: 'proteina' },
  ]);
  assert.equal(interfazPorDefecto('comparacion').entradas.length, 2);
  assert.equal(interfazPorDefecto('preprocesado').opcion_salida, null);
  assert.deepEqual(interfazPorDefecto('preprocesado').opciones, []);
  assert.equal(MAX_ENTRADAS, 6);
});

test('cada entrada es un conector con su nombre, en orden', () => {
  const interfaz = { entradas: [{ nombre: 'A', clase: 'molecula' }, { nombre: 'Receptor', clase: 'proteina' }] };
  assert.deepEqual(conectoresDe(interfaz), [
    { id: 'entrada_0', nombre: 'A' },
    { id: 'entrada_1', nombre: 'Receptor' },
  ]);
  // Sin interfaz el nodo pinta los conectores de siempre de su tipo.
  assert.equal(conectoresDe(null), null);
});

test('al cambiar de algoritmo sobran las conexiones a conectores que ya no existen', () => {
  const aristas = [
    { id: 'a', target: 'nodo_1', targetHandle: 'entrada_0' },
    { id: 'b', target: 'nodo_1', targetHandle: 'entrada_3' },
    { id: 'c', target: 'nodo_1', targetHandle: 'input_molecula' },
    { id: 'd', target: 'otro', targetHandle: 'entrada_5' },
    { id: 'e', source: 'nodo_1', target: 'otro', targetHandle: 'input_molecula' },
  ];
  const sobrantes = conexionesSobrantes(aristas, 'nodo_1', ['entrada_0', 'entrada_1']);
  assert.deepEqual(sobrantes.map(a => a.id), ['b', 'c']);
});

test('la vista previa enseña la llamada como la verá el script', () => {
  assert.equal(vistaPreviaLlamada('clean_hidrogens.py', CLEAN),
    'clean_hidrogens.py Molécula -o salida --all');
  assert.equal(vistaPreviaLlamada('docking.py', interfazPorDefecto('docking')),
    'docking.py Ligando Receptor salida');
  // Sin fichero elegido todavía.
  assert.equal(vistaPreviaLlamada('', CLEAN), 'algoritmo.py Molécula -o salida --all');
});
