// Pruebas de frontend/src/utils/visor.js (spec 002): la lógica pura del
// visor 3D, sin React ni navegador. Se ejecutan con el ejecutor que trae Node,
// sin instalar nada (principio 4 de la constitución):
//
//   node --test "tests/frontend/**/*.test.mjs"
//
// Lo visual (dibujo, ratón, teclado) va en la lista de comprobaciones de la
// spec, no aquí.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  estadoInicial, colocar, activar, vaciar,
  abrirDesdeFuera, modoDisponible,
  ESTILOS, estiloInicial, estiloEfectivo,
  esFicheroDeMoleculas, recortar,
  claveVisor, serializar, restaurar, crearContadorDeBusquedas,
  tieneLista, ponerEnHueco, llegaConLista,
} from '../../frontend/src/utils/visor.js';

// Congela un objeto entero: si una función lo modificara en vez de devolver
// uno nuevo, la prueba fallaría con un TypeError.
function congelar(objeto) {
  Object.values(objeto).forEach((v) => { if (v && typeof v === 'object') congelar(v); });
  return Object.freeze(objeto);
}

const ETANOL = { fichero: 'lote.sdf', posicion: 1, nombre: 'etanol' };
const RECEPTOR = { fichero: '1hsg.pdb', posicion: null, nombre: '1hsg', es_proteina: true };
const CAFEINA = { fichero: 'cafeina.mol2', posicion: null, nombre: 'cafeina' };

// ---------------------------------------------------------------------------
// Huecos A y B (T22, RF-4)
// ---------------------------------------------------------------------------

test('el estado inicial tiene los dos huecos vacíos y A activo', () => {
  assert.deepEqual(estadoInicial(), {
    huecos: { A: null, B: null },
    activo: 'A',
    modo: 'superpuestas',
    estilos: { A: null, B: null },
  });
});

test('colocar en A vacío lo rellena y el activo pasa a B', () => {
  const estado = colocar(estadoInicial(), ETANOL);

  assert.deepEqual(estado.huecos, { A: ETANOL, B: null });
  assert.equal(estado.activo, 'B');
});

test('con A ocupado, la siguiente molécula va a B y B sigue activo', () => {
  const estado = colocar(colocar(estadoInicial(), ETANOL), RECEPTOR);

  assert.deepEqual(estado.huecos, { A: ETANOL, B: RECEPTOR });
  assert.equal(estado.activo, 'B');
});

test('con los dos ocupados, colocar sustituye la del hueco activo', () => {
  const lleno = colocar(colocar(estadoInicial(), ETANOL), RECEPTOR);

  const enB = colocar(lleno, CAFEINA);
  const enA = colocar(activar(lleno, 'A'), CAFEINA);

  assert.deepEqual(enB.huecos, { A: ETANOL, B: CAFEINA });
  assert.deepEqual(enA.huecos, { A: CAFEINA, B: RECEPTOR });
  // B ya estaba ocupado: el activo no salta solo.
  assert.equal(enA.activo, 'A');
});

test('se puede poner la misma molécula en A y en B', () => {
  const estado = colocar(colocar(estadoInicial(), ETANOL), ETANOL);

  assert.deepEqual(estado.huecos, { A: ETANOL, B: ETANOL });
});

test('colocar devuelve el estilo del hueco al de por defecto', () => {
  const conEstilo = { ...estadoInicial(), activo: 'A', estilos: { A: 'esferas', B: null } };

  assert.deepEqual(colocar(conEstilo, ETANOL).estilos, { A: null, B: null });
});

test('activar cambia el hueco activo', () => {
  assert.equal(activar(estadoInicial(), 'B').activo, 'B');
  assert.throws(() => activar(estadoInicial(), 'C'), RangeError);
});

test('vaciar quita la molécula y su estilo, y deja ese hueco activo', () => {
  const lleno = { ...colocar(colocar(estadoInicial(), ETANOL), RECEPTOR), estilos: { A: 'esferas', B: 'cintas' } };

  const estado = vaciar(lleno, 'A');

  assert.deepEqual(estado.huecos, { A: null, B: RECEPTOR });
  assert.deepEqual(estado.estilos, { A: null, B: 'cintas' });
  assert.equal(estado.activo, 'A');
});

test('ninguna función modifica el estado que recibe', () => {
  const estado = congelar(colocar(estadoInicial(), ETANOL));

  assert.doesNotThrow(() => {
    colocar(estado, RECEPTOR);
    activar(estado, 'A');
    vaciar(estado, 'A');
  });
});

// ---------------------------------------------------------------------------
// Llegar desde «Ver en 3D» y modo de dos moléculas (T23, RF-8, RF-15)
// ---------------------------------------------------------------------------

test('abrir desde fuera ocupa A y conserva B', () => {
  const lleno = colocar(colocar(estadoInicial(), ETANOL), RECEPTOR);

  const estado = abrirDesdeFuera(lleno, CAFEINA);

  assert.deepEqual(estado.huecos, { A: CAFEINA, B: RECEPTOR });
  assert.equal(estado.activo, 'A');
});

test('abrir desde fuera ocupa A aunque el activo fuera B', () => {
  const conBActivo = activar(colocar(estadoInicial(), ETANOL), 'B');

  assert.deepEqual(abrirDesdeFuera(conBActivo, CAFEINA).huecos, { A: CAFEINA, B: null });
});

test('abrir desde fuera con B vacío deja B activo, como cualquier otro relleno de A (RF-4)', () => {
  assert.equal(abrirDesdeFuera(estadoInicial(), CAFEINA).activo, 'B');
});

test('el modo superpuestas/lado a lado solo tiene sentido con dos moléculas', () => {
  const una = colocar(estadoInicial(), ETANOL);
  const dos = colocar(una, RECEPTOR);

  assert.equal(modoDisponible(estadoInicial()), false);
  assert.equal(modoDisponible(una), false);
  assert.equal(modoDisponible(dos), true);
  assert.equal(modoDisponible(vaciar(dos, 'A')), false);
});

// ---------------------------------------------------------------------------
// Estilos de representación (T24, RF-9)
// ---------------------------------------------------------------------------

test('los cuatro estilos de la spec, en orden', () => {
  assert.deepEqual(ESTILOS.map((e) => e.valor), ['varillas', 'esferas', 'cintas', 'superficie']);
});

test('una proteína se abre en cintas y lo demás en varillas', () => {
  assert.equal(estiloInicial(RECEPTOR), 'cintas');
  assert.equal(estiloInicial(ETANOL), 'varillas');
});

test('sin estilo elegido se usa el de por defecto, sin aviso', () => {
  assert.deepEqual(estiloEfectivo(null, RECEPTOR), { estilo: 'cintas', aviso: null });
  assert.deepEqual(estiloEfectivo(null, ETANOL), { estilo: 'varillas', aviso: null });
});

test('cintas en algo que no es proteína se dibuja en varillas y avisa', () => {
  const { estilo, aviso } = estiloEfectivo('cintas', ETANOL);

  assert.equal(estilo, 'varillas');
  assert.match(aviso, /proteína/);
});

test('los demás estilos se respetan en cualquier molécula', () => {
  for (const pedido of ['varillas', 'esferas', 'superficie']) {
    assert.deepEqual(estiloEfectivo(pedido, ETANOL), { estilo: pedido, aviso: null });
    assert.deepEqual(estiloEfectivo(pedido, RECEPTOR), { estilo: pedido, aviso: null });
  }
  assert.deepEqual(estiloEfectivo('cintas', RECEPTOR), { estilo: 'cintas', aviso: null });
});

test('un estilo desconocido es un error de programación', () => {
  assert.throws(() => estiloEfectivo('alambre', ETANOL), RangeError);
});

// ---------------------------------------------------------------------------
// «Ver en 3D» solo para moléculas, y valores largos (T25, RF-10, RF-15)
// ---------------------------------------------------------------------------

test('«Ver en 3D» se ofrece para ficheros de moléculas', () => {
  for (const nombre of ['lote.sdf', 'LIG.MOL', 'r.mol2', '1hsg.pdb', 'r.pdbqt', 'agua.xyz', 'cafeina.smi']) {
    assert.equal(esFicheroDeMoleculas(nombre), true, nombre);
  }
});

test('«Ver en 3D» no se ofrece para CSV, JSON ni nada sin extensión de moléculas', () => {
  for (const nombre of ['ranking_e9.csv', 'resultados_e9.json', 'notas.txt', 'sin_extension', 'raro.sdf.bak']) {
    assert.equal(esFicheroDeMoleculas(nombre), false, nombre);
  }
});

test('un valor de más de 200 caracteres se recorta y se puede ver entero', () => {
  const largo = 'x'.repeat(250);

  assert.deepEqual(recortar(largo), { corto: 'x'.repeat(200), completo: largo, recortado: true });
});

test('un valor corto no se recorta', () => {
  assert.deepEqual(recortar('-7.4'), { corto: '-7.4', completo: '-7.4', recortado: false });
  assert.equal(recortar('x'.repeat(200)).recortado, false);
});

test('recortar no parte un carácter de dos unidades por la mitad', () => {
  const valor = 'a'.repeat(199) + '😀' + 'b';

  const { corto } = recortar(valor);

  assert.equal(corto, 'a'.repeat(199) + '😀');
});

// ---------------------------------------------------------------------------
// Conservar el estado en la pestaña y búsquedas vigentes (T26, RF-6, RF-14)
// ---------------------------------------------------------------------------

test('la clave lleva el usuario: otra cuenta en la misma pestaña no hereda el visor', () => {
  assert.equal(claveVisor(7), 'molserver_visor_7');  // spec 004, R5: prefijo propio
  assert.notEqual(claveVisor(7), claveVisor(8));
});

test('serializar y restaurar devuelven los mismos huecos, modo y estilos', () => {
  const estado = {
    ...colocar(colocar(estadoInicial(), ETANOL), RECEPTOR),
    modo: 'lado_a_lado',
    estilos: { A: 'esferas', B: null },
  };

  const vuelta = restaurar(serializar(estado));

  assert.deepEqual(vuelta.huecos, {
    A: { fichero: 'lote.sdf', posicion: 1 },
    B: { fichero: '1hsg.pdb', posicion: null },
  });
  assert.equal(vuelta.activo, estado.activo);
  assert.equal(vuelta.modo, 'lado_a_lado');
  assert.deepEqual(vuelta.estilos, { A: 'esferas', B: null });
});

test('serializar guarda solo la referencia de cada molécula, no su contenido', () => {
  // Un PDB grande ocupa varios MB y sessionStorage admite unos 5 en total:
  // al volver, la página pide de nuevo cada molécula al servidor.
  const conContenido = { ...ETANOL, contenido: 'x'.repeat(100000), campos: [{ nombre: 'a', valor: '1' }] };

  const texto = serializar(colocar(estadoInicial(), conContenido));

  assert.ok(texto.length < 500);
  assert.ok(!texto.includes('xxxx'));
});

test('un estado dañado, vacío o de otra versión vuelve al inicial', () => {
  const invalidos = [
    null, '', 'esto no es json', '[]', '{}',
    JSON.stringify({ version: 999, huecos: { A: null, B: null } }),
    serializar(estadoInicial()).replace('"activo":"A"', '"activo":"Z"'),
    serializar(estadoInicial()).replace('"superpuestas"', '"de lado"'),
    serializar({ ...estadoInicial(), estilos: { A: 'alambre', B: null } }),
    serializar(colocar(estadoInicial(), ETANOL)).replace('"lote.sdf"', '42'),
  ];

  for (const texto of invalidos) {
    assert.deepEqual(restaurar(texto), estadoInicial(), String(texto));
  }
});

test('solo la última búsqueda es vigente', () => {
  const contador = crearContadorDeBusquedas();

  const primera = contador.siguiente();
  const segunda = contador.siguiente();

  // La respuesta de la primera llega tarde: no debe pintarse (RF-6).
  assert.equal(contador.esVigente(primera), false);
  assert.equal(contador.esVigente(segunda), true);
});

test('cada contador lleva su propia cuenta', () => {
  const ficheros = crearContadorDeBusquedas();
  const moleculas = crearContadorDeBusquedas();

  const idFicheros = ficheros.siguiente();
  moleculas.siguiente();

  assert.equal(ficheros.esVigente(idFicheros), true);
});

// ---------------------------------------------------------------------------
// Qué ficheros se recorren por moléculas (T29, RF-3, RF-5, RF-6)
// ---------------------------------------------------------------------------

test('un SDF con varias moléculas o aún sin contar abre su lista', () => {
  assert.equal(tieneLista({ formato: 'sdf', num_moleculas: 500 }), true);
  assert.equal(tieneLista({ formato: 'sdf', num_moleculas: null }), true);
});

test('un SDF de una molécula y cualquier otro formato se colocan enteros', () => {
  assert.equal(tieneLista({ formato: 'sdf', num_moleculas: 1 }), false);
  assert.equal(tieneLista({ formato: 'pdb', num_moleculas: null }), false);
  assert.equal(tieneLista({ formato: 'mol2', num_moleculas: null }), false);
});

// ---------------------------------------------------------------------------
// Restaurar una molécula en su hueco (T38, RF-14)
// ---------------------------------------------------------------------------

test('ponerEnHueco coloca la molécula sin tocar el activo ni los estilos guardados', () => {
  const guardado = { ...estadoInicial(), activo: 'A', modo: 'lado_a_lado', estilos: { A: null, B: 'esferas' } };

  const estado = ponerEnHueco(guardado, 'B', RECEPTOR);

  assert.deepEqual(estado.huecos, { A: null, B: RECEPTOR });
  assert.equal(estado.activo, 'A');
  assert.equal(estado.modo, 'lado_a_lado');
  assert.deepEqual(estado.estilos, { A: null, B: 'esferas' });
  assert.throws(() => ponerEnHueco(guardado, 'C', RECEPTOR), RangeError);
});

// ---------------------------------------------------------------------------
// Llegada desde «Ver en 3D» en otra página (T39, RF-15)
// ---------------------------------------------------------------------------

test('desde fuera, un SDF llega con su lista desplegada y el resto se coloca entero', () => {
  assert.equal(llegaConLista('poses_e12.sdf'), true);
  assert.equal(llegaConLista('CHEMBL.SDF'), true);
  for (const nombre of ['1hsg.pdb', 'cafeina.mol2', 'etanol.mol', 'agua.xyz', 'x.pdbqt', 'y.smi']) {
    assert.equal(llegaConLista(nombre), false, nombre);
  }
});

test('lo que se elige de la lista tras llegar desde fuera va a A y conserva B', () => {
  // Al llegar con lista, el visor solo pone A activo (activar): lo que hubiera
  // en A sigue a la vista hasta que se elige otra molécula.
  const guardado = { ...estadoInicial(), huecos: { A: CAFEINA, B: RECEPTOR }, activo: 'B' };

  const llegado = activar(guardado, 'A');
  assert.deepEqual(llegado.huecos, { A: CAFEINA, B: RECEPTOR });

  assert.deepEqual(colocar(llegado, ETANOL).huecos, { A: ETANOL, B: RECEPTOR });
});

test('abrir desde fuera con B ya restaurado deja A activo (RF-4)', () => {
  // El visor aplica la llegada cuando ha terminado de recuperar B; si la
  // aplicara antes, el activo pasaría a B aunque B acabe ocupado.
  const restaurado = ponerEnHueco(estadoInicial(), 'B', RECEPTOR);
  assert.equal(abrirDesdeFuera(restaurado, CAFEINA).activo, 'A');
});
