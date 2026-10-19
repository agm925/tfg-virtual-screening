// Pruebas de frontend/src/utils/ejecucion.js (spec 012): qué se enseña en el
// Constructor al pulsar «Ver workflow» en una ejecución.
//
//   node --test "tests/frontend/**/*.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { huella, vistaDeEjecucion } from '../../frontend/src/utils/ejecucion.js';

const GRAFO = { nodes: [{ id: 'selectMol_0', type: 'selectMol', data: { nombre_archivo: 'a.mol2', extra: 1 } }], edges: [] };
// El mismo grafo con las claves en otro orden: los nodos rellenan `data` en el
// orden en que se montan, y eso no puede contar como un cambio.
const MISMO_GRAFO = { edges: [], nodes: [{ data: { extra: 1, nombre_archivo: 'a.mol2' }, type: 'selectMol', id: 'selectMol_0' }] };
const OTRO_GRAFO = { nodes: [{ id: 'selectMol_0', type: 'selectMol', data: { nombre_archivo: 'b.mol2' } }], edges: [] };

test('huella no depende del orden de las claves', () => {
  assert.equal(huella(GRAFO), huella(MISMO_GRAFO));
  assert.notEqual(huella(GRAFO), huella(OTRO_GRAFO));
});

test('la copia igual a la versión actual abre el workflow normal', () => {
  const ejecucion = { grafo_json: MISMO_GRAFO, copia_exacta: true, workflow_borrado: false };
  assert.equal(vistaDeEjecucion(ejecucion, { grafo_json: GRAFO }), 'actual');
});

test('si el workflow ha cambiado desde la ejecución, modo consulta', () => {
  const ejecucion = { grafo_json: GRAFO, copia_exacta: true, workflow_borrado: false };
  assert.equal(vistaDeEjecucion(ejecucion, { grafo_json: OTRO_GRAFO }), 'consulta');
});

test('una ejecución sin copia abre la versión actual con aviso', () => {
  const ejecucion = { grafo_json: GRAFO, copia_exacta: false, workflow_borrado: false };
  assert.equal(vistaDeEjecucion(ejecucion, { grafo_json: GRAFO }), 'sin-copia');
});

test('con el workflow borrado no hay versión actual que abrir', () => {
  const ejecucion = { grafo_json: GRAFO, copia_exacta: true, workflow_borrado: true };
  assert.equal(vistaDeEjecucion(ejecucion, null), 'borrado');
  assert.equal(vistaDeEjecucion({ ...ejecucion, copia_exacta: false }, null), 'borrado');
});
