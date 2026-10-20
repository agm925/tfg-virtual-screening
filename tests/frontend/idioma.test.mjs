// Pruebas de frontend/src/utils/idioma.js y de los diccionarios (spec 014):
// la plataforma en español o en inglés.
//
// Los diccionarios se escriben a mano, pantalla a pantalla. Lo que más fácil
// se rompe al hacerlo es que a un idioma le falte una clave o una variable:
// la interfaz enseñaría la clave o un «{nombre}» sin rellenar. Por eso se
// comprueba aquí que los dos idiomas tienen exactamente lo mismo.
//
//   node --test "tests/frontend/**/*.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  IDIOMAS, IDIOMA_POR_DEFECTO, traducir, idiomaInicial, guardarIdioma,
  localeDe, trozosConFormato,
} from '../../frontend/src/utils/idioma.js';
import { CLAVE_IDIOMA, CLAVE_TOKEN, olvidarSesion } from '../../frontend/src/utils/almacenamiento.js';
import es from '../../frontend/src/textos/es.js';
import en from '../../frontend/src/textos/en.js';
import tutorialEs from '../../frontend/src/textos/tutorial.es.js';
import tutorialEn from '../../frontend/src/textos/tutorial.en.js';

// Un Storage del navegador en miniatura.
function almacen(datos = {}) {
  const mapa = new Map(Object.entries(datos));
  return {
    get length() { return mapa.size; },
    key: (i) => [...mapa.keys()][i] ?? null,
    getItem: (k) => mapa.get(k) ?? null,
    setItem: (k, v) => { mapa.set(k, String(v)); },
    removeItem: (k) => { mapa.delete(k); },
    claves: () => [...mapa.keys()].sort(),
  };
}

// Un almacén que falla en todo, como en modo privado con los datos bloqueados.
const roto = {
  get length() { throw new Error('bloqueado'); },
  getItem() { throw new Error('bloqueado'); },
  setItem() { throw new Error('bloqueado'); },
};

const variables = (texto) => [...texto.matchAll(/\{(\w+)\}/g)].map(m => m[1]).sort();

for (const [nombre, a, b] of [['interfaz', es, en], ['tutorial', tutorialEs, tutorialEn]]) {
  test(`${nombre}: los dos idiomas tienen las mismas claves`, () => {
    const soloEs = Object.keys(a).filter(k => !(k in b));
    const soloEn = Object.keys(b).filter(k => !(k in a));
    assert.deepEqual(soloEs, [], 'claves sin traducir al inglés');
    assert.deepEqual(soloEn, [], 'claves en inglés que no existen en español');
  });

  test(`${nombre}: cada clave usa las mismas variables en los dos idiomas`, () => {
    for (const clave of Object.keys(a)) {
      if (!(clave in b)) continue;
      assert.deepEqual(variables(b[clave]), variables(a[clave]), clave);
    }
  });

  test(`${nombre}: ningún texto está vacío`, () => {
    for (const dic of [a, b]) {
      for (const [clave, texto] of Object.entries(dic)) {
        assert.equal(typeof texto, 'string', clave);
        assert.ok(texto.trim(), clave);
      }
    }
  });
}

test('español por defecto, e inglés como segundo idioma', () => {
  assert.equal(IDIOMA_POR_DEFECTO, 'es');
  assert.deepEqual(IDIOMAS, ['es', 'en']);
});

test('traducir rellena las variables', () => {
  const dic = { es: { saludo: 'Hola, {nombre}' }, en: { saludo: 'Hello, {nombre}' } };
  assert.equal(traducir('en', 'saludo', { nombre: 'Ana' }, dic), 'Hello, Ana');
  assert.equal(traducir('es', 'saludo', { nombre: 'Ana' }, dic), 'Hola, Ana');
  // Una variable que no se pasa se deja a la vista: mejor que un «undefined».
  assert.equal(traducir('es', 'saludo', {}, dic), 'Hola, {nombre}');
  // Los números también.
  assert.equal(traducir('es', 'saludo', { nombre: 0 }, dic), 'Hola, 0');
});

test('traducir cae al español y, si tampoco existe, a la clave', () => {
  const dic = { es: { solo: 'Solo en español' }, en: {} };
  assert.equal(traducir('en', 'solo', {}, dic), 'Solo en español');
  assert.equal(traducir('en', 'no.existe', {}, dic), 'no.existe');
  // Un idioma desconocido se trata como el de por defecto.
  assert.equal(traducir('fr', 'solo', {}, dic), 'Solo en español');
});

test('traducir usa los diccionarios reales si no se le pasan otros', () => {
  assert.equal(traducir('es', 'cabecera.menu'), es['cabecera.menu']);
  assert.equal(traducir('en', 'cabecera.menu'), en['cabecera.menu']);
});

test('idiomaInicial lee la preferencia guardada', () => {
  assert.equal(idiomaInicial(almacen({ [CLAVE_IDIOMA]: 'en' })), 'en');
  assert.equal(idiomaInicial(almacen({ [CLAVE_IDIOMA]: 'es' })), 'es');
});

test('idiomaInicial da español sin preferencia, con una desconocida o sin almacén', () => {
  assert.equal(idiomaInicial(almacen()), 'es');
  assert.equal(idiomaInicial(almacen({ [CLAVE_IDIOMA]: 'fr' })), 'es');
  assert.equal(idiomaInicial(roto), 'es');
  assert.equal(idiomaInicial(null), 'es');
});

test('guardarIdioma escribe la clave, y no rompe sin almacén', () => {
  const a = almacen();
  guardarIdioma(a, 'en');
  assert.equal(a.getItem(CLAVE_IDIOMA), 'en');
  assert.doesNotThrow(() => guardarIdioma(roto, 'en'));
  assert.doesNotThrow(() => guardarIdioma(null, 'en'));
});

test('localeDe da el formato de fechas de cada idioma', () => {
  assert.equal(localeDe('es'), 'es-ES');
  assert.equal(localeDe('en'), 'en-GB');
  assert.equal(localeDe('fr'), 'es-ES');
});

test('trozosConFormato separa las negritas marcadas con **', () => {
  assert.deepEqual(trozosConFormato('Pulsa **Guardar** y sigue'), [
    { texto: 'Pulsa ', negrita: false },
    { texto: 'Guardar', negrita: true },
    { texto: ' y sigue', negrita: false },
  ]);
  assert.deepEqual(trozosConFormato('**Todo**'), [{ texto: 'Todo', negrita: true }]);
  assert.deepEqual(trozosConFormato('Sin formato'), [{ texto: 'Sin formato', negrita: false }]);
  // Un ** sin cerrar se deja tal cual: no se inventa una negrita hasta el final.
  assert.deepEqual(trozosConFormato('a ** b'), [{ texto: 'a ** b', negrita: false }]);
});

test('el idioma sobrevive al cierre de sesión', () => {
  const local = almacen({ [CLAVE_TOKEN]: 'jwt', [CLAVE_IDIOMA]: 'en', ajena: 'x' });
  olvidarSesion([local]);
  assert.deepEqual(local.claves(), ['ajena', CLAVE_IDIOMA].sort());
});

// --- Los textos de utils/ en inglés (spec 014, T06) ---
// Los módulos de utils/ no leen el contexto de React: reciben el traductor
// (o el idioma) como último parámetro, y sin él siguen en español, como antes.
import { traductor } from '../../frontend/src/utils/idioma.js';
import { mensajeError, ErrorLegible } from '../../frontend/src/utils/mensajes.js';
import { etiquetaFichero, formatFecha, textoEstado } from '../../frontend/src/utils/ficheros.js';
import { avisoCopias, tamanoLegible } from '../../frontend/src/utils/sistema.js';
import { interfazPorDefecto, vistaPreviaLlamada } from '../../frontend/src/utils/interfaz.js';
import { detalleFichero, ESTILOS, estiloEfectivo } from '../../frontend/src/utils/visor.js';
import { TIPOS_NODO, ETIQUETA_ALGORITMO } from '../../frontend/src/utils/tiposNodo.js';

const tEn = traductor('en');
const tEs = traductor('es');

test('mensajeError en inglés', () => {
  assert.equal(mensajeError('load the molecules', new ErrorLegible('Not found.'), tEn),
    'Could not load the molecules: Not found.');
  assert.match(mensajeError('load the molecules', new Error('x'), tEn), /^Could not load the molecules\. Try again/);
  assert.equal(mensajeError('cargar', 'No existe.'), 'No se pudo cargar: No existe.');
});

test('fechas, estados y ficheros en inglés', () => {
  const iso = '2026-10-19T08:05:00';
  assert.match(formatFecha(iso, 'en'), /^19\/10\/2026,? 08:05$/);
  assert.match(formatFecha(iso), /^19\/10\/2026,? 08:05$/);
  assert.equal(textoEstado('PENDIENTE', tEn), 'Queued');
  assert.equal(textoEstado('completado'), 'Completado');
  assert.equal(etiquetaFichero('ranking_x_e3.csv', tEn), 'Ranking (CSV)');
  assert.equal(etiquetaFichero('resultados_x_e3.json', tEn), 'Full results (JSON)');
});

test('Sistema en inglés', () => {
  assert.match(avisoCopias({ estado: 'sin_copias' }, tEn), /no backup has been made/i);
  assert.match(avisoCopias({ estado: 'raro' }, tEn), /backups/i);
  assert.equal(tamanoLegible(3 * 1024 ** 3, 'en'), '3.0 GB');
  assert.equal(tamanoLegible(3 * 1024 ** 3), '3,0 GB');
});

test('interfaz por defecto y vista previa en inglés', () => {
  assert.deepEqual(interfazPorDefecto('docking', tEn).entradas.map(e => e.nombre), ['Ligand', 'Receptor']);
  assert.equal(vistaPreviaLlamada('a.py', interfazPorDefecto('preprocesado', tEn), tEn), 'a.py Molecule output');
});

test('visor en inglés', () => {
  assert.equal(detalleFichero({ formato: 'sdf', grupo: 'resultado', num_moleculas: 3 }, tEn), '3 molecules');
  assert.equal(detalleFichero({ formato: 'sdf', grupo: 'resultado', num_moleculas: 1 }, tEn), '1 molecule');
  assert.deepEqual(ESTILOS.map(e => tEn(e.etiqueta)), ['Sticks', 'Spheres', 'Cartoon', 'Surface']);
  assert.match(tEn(estiloEfectivo('cintas', { es_proteina: false }).aviso), /protein/);
});

test('tipos de nodo y de algoritmo: claves con texto en los dos idiomas', () => {
  for (const tipo of TIPOS_NODO) {
    for (const clave of [tipo.etiqueta, tipo.descripcion]) {
      assert.ok(clave in es && clave in en, clave);
    }
  }
  assert.equal(tEs(TIPOS_NODO[0].etiqueta), 'Subir molécula');
  assert.equal(tEn(ETIQUETA_ALGORITMO.preprocesado), 'Preparation');
});
