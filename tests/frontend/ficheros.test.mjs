// Pruebas de seleccionInicial (frontend/src/utils/ficheros.js, spec 012): qué
// fichero muestra el nodo «Elegir molécula» al cargarse.
//
//   node --test "tests/frontend/**/*.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { seleccionInicial } from '../../frontend/src/utils/ficheros.js';

const LISTA = [{ nombre: 'a.mol2' }, { nombre: 'b.sdf' }];

test('un nodo nuevo empieza con el primero de la lista', () => {
  assert.deepEqual(seleccionInicial(undefined, LISTA), { nombre: 'a.mol2', falta: false });
  assert.deepEqual(seleccionInicial('', LISTA), { nombre: 'a.mol2', falta: false });
});

test('un fichero guardado que sigue existiendo se mantiene', () => {
  assert.deepEqual(seleccionInicial('b.sdf', LISTA), { nombre: 'b.sdf', falta: false });
});

test('un fichero guardado que ya no existe se mantiene, marcado, y no se cambia por otro', () => {
  assert.deepEqual(seleccionInicial('borrado.mol2', LISTA), { nombre: 'borrado.mol2', falta: true });
});

test('sin ficheros no hay nada que elegir', () => {
  assert.deepEqual(seleccionInicial(undefined, []), { nombre: '', falta: false });
  assert.deepEqual(seleccionInicial('borrado.mol2', []), { nombre: 'borrado.mol2', falta: true });
});
