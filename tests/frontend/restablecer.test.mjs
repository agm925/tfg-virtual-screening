// Pruebas de frontend/src/utils/restablecer.js (spec 011, R6): el token del
// enlace del correo, {PUBLIC_URL}/#restablecer=<token>.
//
//   node --test "tests/frontend/**/*.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { tokenDeRestablecer, tomarTokenDeRestablecer } from '../../frontend/src/utils/restablecer.js';

test('saca el token del fragmento', () => {
  assert.equal(tokenDeRestablecer('#restablecer=abc_DEF-123'), 'abc_DEF-123');
});

test('sin el fragmento, o con otro, no hay token', () => {
  assert.equal(tokenDeRestablecer(''), null);
  assert.equal(tokenDeRestablecer('#'), null);
  assert.equal(tokenDeRestablecer('#otra=abc'), null);
  assert.equal(tokenDeRestablecer('#restablecer='), null);
});

test('un token con caracteres que token_urlsafe no produce no se acepta', () => {
  assert.equal(tokenDeRestablecer('#restablecer=abc<script>'), null);
  assert.equal(tokenDeRestablecer('#restablecer=abc&x=1'), null);
});

test('al tomarlo, la dirección se queda sin él', () => {
  const llamadas = [];
  const ventana = {
    location: { hash: '#restablecer=abc', pathname: '/molserver/', search: '' },
    history: { replaceState: (...args) => llamadas.push(args) },
  };
  assert.equal(tomarTokenDeRestablecer(ventana), 'abc');
  assert.deepEqual(llamadas, [[null, '', '/molserver/']]);
});

test('sin token no se toca la dirección', () => {
  const llamadas = [];
  const ventana = {
    location: { hash: '#otra', pathname: '/', search: '?x=1' },
    history: { replaceState: (...args) => llamadas.push(args) },
  };
  assert.equal(tomarTokenDeRestablecer(ventana), null);
  assert.deepEqual(llamadas, []);
});
