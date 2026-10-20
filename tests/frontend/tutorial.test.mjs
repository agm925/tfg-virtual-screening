// Pruebas de frontend/src/components/Tutorial.jsx y styles/Tutorial.css
// (spec 003): leen los dos ficheros como texto, porque el componente importa
// CSS y Node no lo carga. Comprueban lo que se puede decidir sin navegador:
// que el tutorial no vuelva a tener emojis ni colores sueltos, que no hable
// de cosas del administrador y que tenga todas sus secciones. Lo visual
// (teclado, pantalla estrecha, que el ejemplo coincida con el Constructor)
// va en docs/specs/003-tutorial/comprobaciones.md.
//
//   node --test "tests/frontend/**/*.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const leer = (ruta) => readFileSync(new URL(ruta, import.meta.url), 'utf8');
const JSX = leer('../../frontend/src/components/Tutorial.jsx');
const CSS = leer('../../frontend/src/styles/Tutorial.css');
// Desde la spec 014 la prosa vive en los diccionarios del tutorial; el texto
// de referencia es el español, y el inglés pasa las mismas reglas de forma.
const TEXTO_ES = leer('../../frontend/src/textos/tutorial.es.js');
const TEXTO_EN = leer('../../frontend/src/textos/tutorial.en.js');
const TEXTO = JSX + TEXTO_ES;

// Flechas, símbolos y dingbats (U+2190 en adelante), emojis y el selector de
// variante que los acompaña: cada sistema los dibuja a su manera. Quedan
// permitidos los acentos, la «ñ», las comillas «», el guion largo, la raya y
// los puntos suspensivos, que están por debajo de U+2190. Una flecha o un
// icono se dibuja con Icono.jsx, no con texto.
const EMOJI = /[\u{2190}-\u{2BFF}\u{FE0F}\u{1F000}-\u{1FAFF}]/u;

const nombres = (texto, patron) => [...texto.matchAll(patron)].map((m) => m[1]);

// ---------------------------------------------------------------------------
// CA1 y CA2: sin emojis ni colores escritos a mano
// ---------------------------------------------------------------------------

test('el componente no tiene emojis (CA1)', () => {
  const linea = JSX.split('\n').findIndex((l) => EMOJI.test(l));
  assert.equal(linea, -1, `emoji en la línea ${linea + 1}: ${JSX.split('\n')[linea]?.trim()}`);
});

test('el componente no escribe colores ni estilos en línea (CA1)', () => {
  assert.doesNotMatch(JSX, /#[0-9a-fA-F]{3,8}\b/, 'color hexadecimal');
  assert.doesNotMatch(JSX, /rgba?\(/, 'color rgb');
  assert.doesNotMatch(JSX, /linear-gradient/, 'degradado');
  assert.doesNotMatch(JSX, /style=\{\{/, 'estilo en línea');
});

test('la hoja de estilo solo usa colores de tokens.css (CA2)', () => {
  assert.doesNotMatch(CSS, /#[0-9a-fA-F]{3,8}\b/, 'color hexadecimal');
  assert.doesNotMatch(CSS, /rgba?\(/, 'color rgb o rgba');
  assert.doesNotMatch(CSS, /linear-gradient/, 'degradado');
});

// ---------------------------------------------------------------------------
// CA3: nombres y colores de nodo de una sola fuente
// ---------------------------------------------------------------------------

test('los tipos de nodo se leen de tiposNodo.js y no se escriben a mano (CA3)', () => {
  assert.match(JSX, /from '\.\.\/utils\/tiposNodo'/);
  for (const etiqueta of ['Subir molécula', 'Elegir molécula', 'Elegir biblioteca', 'Preparar',
    'Alinear', 'Comparar', 'Docking', 'Inicio', 'Descargar']) {
    assert.doesNotMatch(JSX, new RegExp(`(titulo|etiqueta|label)=["']${etiqueta}["']`),
      `«${etiqueta}» escrito a mano`);
  }
});

// ---------------------------------------------------------------------------
// CA4: sin nombres antiguos ni jerga del servidor
// ---------------------------------------------------------------------------

const PROHIBIDAS = ['Seleccionar BD', 'Seleccionar Molécula', 'Upload Molécula', 'Builder',
  'Preprocesar', 'Celery', 'worker', 'uploads/', 'servidor', 'canvas', 'conda', 'PATH'];

test('el texto no usa nombres antiguos ni habla del servidor (CA4)', () => {
  for (const palabra of PROHIBIDAS) {
    assert.ok(!TEXTO.toLowerCase().includes(palabra.toLowerCase()), `aparece «${palabra}»`);
  }
});

// ---------------------------------------------------------------------------
// CA5: las ocho secciones del índice, accesibles
// ---------------------------------------------------------------------------

test('el índice tiene las ocho secciones, con el Visor 3D (CA5, R3)', () => {
  const ids = nombres(JSX.slice(0, JSX.indexOf('];')), /\bid: '([a-z]+)'/g);
  assert.deepEqual(ids, ['plataforma', 'moleculas', 'algoritmos', 'constructor', 'nodos', 'flujo', 'visor', 'consejos']);
});

test('cada sección del índice tiene su contenido', () => {
  for (const id of ['plataforma', 'moleculas', 'algoritmos', 'constructor', 'nodos', 'flujo', 'visor', 'consejos']) {
    assert.match(JSX, new RegExp(`seccionAbierta === '${id}'`), id);
  }
});

test('el índice marca la sección abierta para los lectores de pantalla (CA5)', () => {
  assert.match(JSX, /aria-current=/);
});

test('el índice es un menú de botones nativos, que se usan con teclado (CA5)', () => {
  assert.match(JSX, /<nav[^>]*aria-label=/);
  assert.match(JSX, /<button/);
  assert.doesNotMatch(JSX, /<div[^>]*onClick/);
});

// ---------------------------------------------------------------------------
// R4: contenido al día
// ---------------------------------------------------------------------------

test('el tutorial usa los nombres de los botones y de la página de hoy (R4)', () => {
  assert.match(TEXTO_ES, /Ejecutar workflow/);
  assert.match(TEXTO_ES, /Nuevo workflow/);
  assert.doesNotMatch(TEXTO_ES, /Ejecutar Workflow|Nuevo Workflow/);
});

test('el ejemplo no exige los nodos opcionales Inicio y Descargar (R4)', () => {
  const ejemplo = TEXTO_ES.split('\n').filter((l) => l.includes("'flujo.")).join('\n');
  assert.ok(ejemplo.length > 200, 'no se encontró la sección del ejemplo');
  assert.doesNotMatch(ejemplo, /Añade el nodo (Inicio|Ejecutar|Descargar)/);
});

// ---------------------------------------------------------------------------
// Spec 007: lo subido es privado o público, a elección de quien lo sube
// ---------------------------------------------------------------------------

test('el tutorial explica la pregunta de privado o público (spec 007)', () => {
  assert.doesNotMatch(TEXTO_ES, /biblioteca compartida/, 'ya no todo lo subido es compartido');
  assert.match(TEXTO_ES, /¿Quién puede ver este fichero\?/);
  assert.match(TEXTO_ES, /Privado/);
  assert.match(TEXTO_ES, /Público/);
});

// ---------------------------------------------------------------------------
// Spec 014: el tutorial en español o en inglés
// ---------------------------------------------------------------------------

test('cada clave que pide el componente existe en el diccionario (spec 014, R6)', () => {
  // Las claves escritas enteras (tt('…') o f('…')); las que se montan con el
  // número de paso o el tipo las cubre idioma.test.mjs: es y en tienen las mismas claves.
  const claves = nombres(JSX, /\b(?:tt|f)\('([^']+)'/g);
  assert.ok(claves.length > 50, 'el componente no lee sus textos del diccionario');
  for (const clave of claves) {
    assert.ok(TEXTO_ES.includes(`'${clave}':`), `falta «${clave}» en tutorial.es.js`);
  }
});
