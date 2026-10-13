// Pruebas de frontend/src/utils/sistema.js (spec 009, R7): el texto de la
// tarjeta «Copias de seguridad» de la página Sistema. El estado lo decide el
// backend (app/copias_estado.py); aquí solo se dice en lenguaje llano.
//
//   node --test "tests/frontend/**/*.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { avisoCopias, tamanoLegible } from '../../frontend/src/utils/sistema.js';

const ULTIMA = { copia: '2026-10-12_0300', fecha: '2026-10-12T03:00+02:00', ficheros: 540, bytes: 211686423 };

test('con las copias al día no hay aviso', () => {
  assert.equal(avisoCopias({ estado: 'ok', ultima: ULTIMA }), null);
});

test('cada problema tiene su aviso en lenguaje llano', () => {
  assert.match(avisoCopias({ estado: 'sin_copias', ultima: null }), /todavía no se ha hecho ninguna/i);
  assert.match(avisoCopias({ estado: 'atrasada', ultima: ULTIMA }), /más de un día/);
  const fallida = avisoCopias({ estado: 'fallida', ultima: ULTIMA, error: 'pg_dump ha fallado: x' });
  assert.match(fallida, /ha fallado/);
  // Sin jerga ni el error técnico (principio 7): eso va al log del servidor.
  assert.doesNotMatch(fallida, /pg_dump/);
});

test('un estado desconocido también avisa', () => {
  assert.notEqual(avisoCopias({ estado: 'raro' }), null);
  assert.notEqual(avisoCopias(undefined), null);
});

test('los tamaños se leen en KB, MB o GB', () => {
  assert.equal(tamanoLegible(41232), '40 KB');
  assert.equal(tamanoLegible(211686423), '202 MB');
  assert.equal(tamanoLegible(3 * 1024 ** 3), '3,0 GB');
});
