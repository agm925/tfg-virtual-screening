// Pruebas de frontend/src/utils/almacenamiento.js (spec 004, R5): las claves
// que MolServer guarda en el navegador y el cierre de sesión.
//
// En https://rt.hpca.ual.es/molserver la plataforma comparte origen con las
// demás aplicaciones del servidor, y localStorage y sessionStorage son del
// origen, no de la ruta. Por eso todas las claves llevan un prefijo propio, y
// al cerrar sesión se borran solo esas.
//
//   node --test "tests/frontend/**/*.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  PREFIJO, CLAVE_TOKEN, CLAVE_USUARIO, claveEditor, claveVisor,
  esClaveDeMolServer, olvidarSesion,
} from '../../frontend/src/utils/almacenamiento.js';

// Un Storage del navegador en miniatura: lo justo que usa olvidarSesion.
function almacen(datos) {
  const mapa = new Map(Object.entries(datos));
  return {
    get length() { return mapa.size; },
    key: (i) => [...mapa.keys()][i] ?? null,
    getItem: (k) => mapa.get(k) ?? null,
    removeItem: (k) => { mapa.delete(k); },
    claves: () => [...mapa.keys()].sort(),
  };
}

test('todas las claves llevan el prefijo de MolServer', () => {
  assert.equal(PREFIJO, 'molserver_');
  for (const clave of [CLAVE_TOKEN, CLAVE_USUARIO, claveEditor(7), claveVisor(7)]) {
    assert.ok(clave.startsWith(PREFIJO), clave);
  }
});

test('las claves de editor y visor llevan el usuario', () => {
  assert.equal(claveEditor(7), 'molserver_editor_7');
  assert.equal(claveVisor(7), 'molserver_visor_7');
  assert.notEqual(claveEditor(7), claveEditor(8));
  assert.notEqual(claveEditor(7), claveVisor(7));
});

test('reconoce las claves propias y no las de otras aplicaciones', () => {
  assert.equal(esClaveDeMolServer('molserver_token'), true);
  assert.equal(esClaveDeMolServer('access_token'), false);
  assert.equal(esClaveDeMolServer('otra_app_molserver_token'), false);
  assert.equal(esClaveDeMolServer(null), false);
});

test('cerrar sesión borra solo las claves de MolServer, de los dos almacenes', () => {
  const local = almacen({ molserver_token: 't', molserver_usuario: '{}', access_token: 'de-otra-app' });
  const sesion = almacen({ molserver_editor_7: '{}', molserver_visor_7: '{}', otra_app: 'x' });

  olvidarSesion([local, sesion]);

  assert.deepEqual(local.claves(), ['access_token']);
  assert.deepEqual(sesion.claves(), ['otra_app']);
});

test('cerrar sesión no falla si un almacén no está disponible', () => {
  // Modo privado o datos del sitio bloqueados: el acceso lanza una excepción.
  const roto = { get length() { throw new Error('SecurityError'); } };
  const local = almacen({ molserver_token: 't' });

  assert.doesNotThrow(() => olvidarSesion([roto, local]));
  assert.deepEqual(local.claves(), []);
});
