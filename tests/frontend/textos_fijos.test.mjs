// Vigilancia de la spec 014: ningún componente escribe texto de la interfaz a
// mano. Todo pasa por los diccionarios (textos/es.js y en.js), o la interfaz
// en inglés enseñaría ese texto en español sin que nadie se diera cuenta.
//
// Es una comprobación por patrones, no un analizador de JSX: busca texto con
// letras entre etiquetas y en los atributos que lee el usuario (aria-label,
// placeholder, title, alt). Lo que no es un texto traducible (códigos de
// idioma, siglas de formatos, nombres propios) va en EXCEPCIONES.
//
//   node --test "tests/frontend/**/*.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const SRC = fileURLToPath(new URL('../../frontend/src/', import.meta.url));

// Visualizador3D.jsx no lo importa nadie desde el Visor 3D de la spec 002: es
// código muerto que queda fuera hasta que se borre.
const SIN_REVISAR = new Set(['components/Visualizador3D.jsx']);

const EXCEPCIONES = new Set([
  'ES', 'EN', '|', 'MolServer', 'KB', '—', 'www.ual.es', '--all', 'MW>200',
  // Formatos y programas: se llaman igual en los dos idiomas.
  'SDF', 'MOL2', 'MOL', 'PDB', 'PDBQT', 'XYZ', 'Vinardo', 'Vina', 'dkoes',
  // El nombre de la opción de smina, en el tooltip para quien la conozca.
  'autobox_add',
]);

function jsxDe(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const ruta = join(dir, e.name);
    if (e.isDirectory()) return jsxDe(ruta);
    return e.name.endsWith('.jsx') ? [ruta] : [];
  });
}

const LETRA = /[A-Za-zÁÉÍÓÚáéíóúÑñ]/;
const TEXTO_ENTRE_ETIQUETAS = />([^<>{}]+)</g;
const ATRIBUTO = /\b(aria-label|placeholder|title|alt)="([^"]*)"/g;

function textosFijos(codigo) {
  // Los comentarios no se ven: fuera antes de buscar.
  const sinComentarios = codigo
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '');
  const hallados = [];
  for (const [, texto] of sinComentarios.matchAll(TEXTO_ENTRE_ETIQUETAS)) {
    const limpio = texto.trim();
    // `a => b` y comparaciones dentro de expresiones también tienen > y <.
    if (!limpio || !LETRA.test(limpio) || /[=;&|()?]/.test(limpio)) continue;
    // Una extensión de fichero (.sdf, .pdbqt…) se escribe igual en los dos idiomas.
    if (/^\.\w+$/.test(limpio)) continue;
    // Entre dos elementos de un objeto: `…/></>,` y en la línea siguiente `bajar:`.
    if (/^,?\s*\w+:$/m.test(limpio)) continue;
    if (!EXCEPCIONES.has(limpio)) hallados.push(limpio);
  }
  for (const [, atributo, texto] of sinComentarios.matchAll(ATRIBUTO)) {
    if (LETRA.test(texto) && !EXCEPCIONES.has(texto)) hallados.push(`${atributo}="${texto}"`);
  }
  return hallados;
}

test('ningún componente escribe a mano un texto de la interfaz (spec 014, CA6)', () => {
  const problemas = [];
  for (const ruta of jsxDe(SRC)) {
    const nombre = relative(SRC, ruta).replaceAll('\\', '/');
    if (SIN_REVISAR.has(nombre)) continue;
    for (const texto of textosFijos(readFileSync(ruta, 'utf8'))) problemas.push(`${nombre}: ${texto}`);
  }
  assert.deepEqual(problemas, [], 'textos sin pasar por los diccionarios');
});

test('la vigilancia detecta un texto escrito a mano', () => {
  assert.deepEqual(textosFijos('<p>Hola mundo</p>'), ['Hola mundo']);
  assert.deepEqual(textosFijos('<input placeholder="Buscar" />'), ['placeholder="Buscar"']);
  assert.deepEqual(textosFijos("<p>{t('saludo')}</p>"), []);
  assert.deepEqual(textosFijos('{/* <p>comentario</p> */}'), []);
  assert.deepEqual(textosFijos('<option value="sdf">SDF</option>'), []);
});

// El <input type="file"> lo dibuja el navegador con el idioma de su sistema
// («Seleccionar archivo», «Ningún archivo seleccionado»), y la página no
// puede cambiarlo. Por eso va siempre oculto, detrás de un botón propio
// (components/SelectorFichero.jsx o la zona de Moléculas).
test('ningún selector de ficheros del navegador queda a la vista (spec 014)', () => {
  const visibles = [];
  for (const ruta of jsxDe(SRC)) {
    const nombre = relative(SRC, ruta).replaceAll('\\', '/');
    if (SIN_REVISAR.has(nombre)) continue;
    for (const [etiqueta] of readFileSync(ruta, 'utf8').matchAll(/<input\b[^>]*type="file"[^>]*>/g)) {
      if (!/\shidden\b/.test(etiqueta)) visibles.push(`${nombre}: ${etiqueta.replace(/\s+/g, ' ').slice(0, 80)}`);
    }
  }
  assert.deepEqual(visibles, []);
});
