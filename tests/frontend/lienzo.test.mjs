// Pruebas de frontend/src/utils/lienzo.js (spec 010, R3): dónde aparece un
// nodo añadido tocando la paleta. En el móvil no se puede arrastrar (el
// arrastre del navegador no funciona con el dedo), así que tocar lo añade en
// el centro de lo que se ve del lienzo.
//
//   node --test "tests/frontend/**/*.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { aCoordenadasDelLienzo, posicionNuevoNodo } from '../../frontend/src/utils/lienzo.js';

const SIN_ZOOM = { x: 0, y: 0, zoom: 1 };

test('un punto de la pantalla pasa a coordenadas del lienzo con desplazamiento y zoom', () => {
  assert.deepEqual(aCoordenadasDelLienzo({ x: 100, y: 50 }, SIN_ZOOM), { x: 100, y: 50 });
  // Lienzo desplazado 40 px a la derecha y con zoom 2.
  assert.deepEqual(aCoordenadasDelLienzo({ x: 100, y: 50 }, { x: 40, y: 10, zoom: 2 }), { x: 30, y: 20 });
});

test('el nodo nuevo queda centrado en lo que se ve', () => {
  const p = posicionNuevoNodo({ ancho: 360, alto: 400, viewport: SIN_ZOOM, nodos: [] });
  // Centro (180, 200) menos la mitad de un nodo típico, para que quede centrado.
  assert.deepEqual(p, { x: 180 - 90, y: 200 - 40 });
});

test('con el lienzo movido y ampliado, sigue en el centro de lo visible', () => {
  const p = posicionNuevoNodo({ ancho: 360, alto: 400, viewport: { x: -200, y: 0, zoom: 2 }, nodos: [] });
  assert.deepEqual(p, { x: (180 + 200) / 2 - 90, y: 200 / 2 - 40 });
});

test('si ya hay un nodo en ese sitio, el nuevo se desplaza para no taparlo', () => {
  const primero = posicionNuevoNodo({ ancho: 360, alto: 400, viewport: SIN_ZOOM, nodos: [] });
  const segundo = posicionNuevoNodo({ ancho: 360, alto: 400, viewport: SIN_ZOOM, nodos: [{ position: primero }] });
  assert.notDeepEqual(segundo, primero);
  const tercero = posicionNuevoNodo({ ancho: 360, alto: 400, viewport: SIN_ZOOM,
                                      nodos: [{ position: primero }, { position: segundo }] });
  assert.notDeepEqual(tercero, primero);
  assert.notDeepEqual(tercero, segundo);
});
