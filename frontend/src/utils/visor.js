// Lógica pura del visor 3D (spec 002): qué molécula hay en cada hueco, cuál
// está activo, en qué modo y con qué estilo se dibuja. Sin React ni DOM, para
// poder probarla con `node --test tests/frontend/` sin navegador. Todo lo que
// decide el servidor (qué ficheros se ven, qué contiene cada uno) vive en
// app/visor.py; aquí solo el estado de la pantalla (principio 3).
//
// Ninguna función modifica el estado que recibe: devuelven uno nuevo, que es
// lo que React necesita para saber que algo ha cambiado.

export const HUECOS = ['A', 'B'];

function comprobarHueco(hueco) {
  if (!HUECOS.includes(hueco)) throw new RangeError(`Hueco desconocido: ${hueco}`);
}

// Los dos huecos vacíos y A activo (RF-4). `estilos` a null significa "el de
// por defecto para esa molécula" (estiloInicial).
export function estadoInicial() {
  return {
    huecos: { A: null, B: null },
    activo: 'A',
    modo: 'superpuestas',
    estilos: { A: null, B: null },
  };
}

// Pone la molécula en el hueco activo, sustituyendo lo que hubiera, con el
// estilo de por defecto. Si se acaba de rellenar A y B está vacío, el activo
// pasa a B: así se eligen dos moléculas seguidas sin cambiar de hueco a mano.
export function colocar(estado, molecula) {
  const hueco = estado.activo;
  const huecos = { ...estado.huecos, [hueco]: molecula };
  const activo = hueco === 'A' && huecos.B === null ? 'B' : hueco;
  return { ...estado, huecos, activo, estilos: { ...estado.estilos, [hueco]: null } };
}

export function activar(estado, hueco) {
  comprobarHueco(hueco);
  return { ...estado, activo: hueco };
}

// Vacía el hueco y lo deja activo: lo siguiente que se elija va a él, que es
// lo que suele querer quien acaba de vaciarlo.
export function vaciar(estado, hueco) {
  comprobarHueco(hueco);
  return {
    ...estado,
    huecos: { ...estado.huecos, [hueco]: null },
    estilos: { ...estado.estilos, [hueco]: null },
    activo: hueco,
  };
}

// Llegada desde «Ver en 3D» en otra página (RF-15): la molécula va siempre a
// A y lo que hubiera en B se conserva, para comparar lo nuevo con lo que ya
// estaba cargado. El hueco activo resultante sigue la regla de siempre (RF-4).
export function abrirDesdeFuera(estado, molecula) {
  return colocar(activar(estado, 'A'), molecula);
}

// Elegir entre superpuestas y lado a lado solo tiene sentido con las dos
// moléculas puestas (RF-8); con una sola hay un único visor.
export function modoDisponible(estado) {
  return estado.huecos.A !== null && estado.huecos.B !== null;
}

// Los cuatro estilos de representación de la spec (RF-9), con el nombre que
// ve el usuario. Una sola lista para el selector y para las comprobaciones.
export const ESTILOS = [
  { valor: 'varillas', etiqueta: 'Varillas' },
  { valor: 'esferas', etiqueta: 'Esferas' },
  { valor: 'cintas', etiqueta: 'Cintas' },
  { valor: 'superficie', etiqueta: 'Superficie' },
];

export const AVISO_CINTAS = 'Las cintas solo representan cadenas de proteína, y el fichero no declara '
  + 'esta molécula como proteína: se dibuja en varillas.';

// El de por defecto: cintas si el fichero declara una proteína (lo decide el
// servidor, `es_proteina`), varillas en cualquier otro caso.
export function estiloInicial(molecula) {
  return molecula.es_proteina ? 'cintas' : 'varillas';
}

// Lo que se dibuja de verdad para el estilo elegido (null = el de por
// defecto): cintas sobre algo que no es proteína no dibujaría nada, así que
// pasa a varillas y se dice por qué.
export function estiloEfectivo(estiloPedido, molecula) {
  if (estiloPedido === null) return { estilo: estiloInicial(molecula), aviso: null };
  if (!ESTILOS.some((e) => e.valor === estiloPedido)) {
    throw new RangeError(`Estilo desconocido: ${estiloPedido}`);
  }
  if (estiloPedido === 'cintas' && !molecula.es_proteina) {
    return { estilo: 'varillas', aviso: AVISO_CINTAS };
  }
  return { estilo: estiloPedido, aviso: null };
}

// Las extensiones que el visor sabe abrir (las mismas que formato_de en
// app/visor.py). Decide si una página ofrece «Ver en 3D» junto a un fichero:
// un CSV de ranking o un JSON de resultados no contienen moléculas (RF-15).
// El SMILES sí se ofrece: el visor explica que no tiene coordenadas.
const EXTENSIONES_DE_MOLECULAS = ['.sdf', '.mol', '.mol2', '.pdb', '.pdbqt', '.xyz', '.smi'];

export function esFicheroDeMoleculas(nombre) {
  const punto = nombre.lastIndexOf('.');
  return punto > 0 && EXTENSIONES_DE_MOLECULAS.includes(nombre.slice(punto).toLowerCase());
}

// Valores de campos de más de `max` caracteres: se enseña el principio y se
// ofrece ver el completo (RF-10). Se cuentan caracteres, no unidades UTF-16,
// para no partir uno de dos (un símbolo o un emoji) por la mitad.
export function recortar(valor, max = 200) {
  const caracteres = Array.from(valor);
  const recortado = caracteres.length > max;
  return { corto: recortado ? caracteres.slice(0, max).join('') : valor, completo: valor, recortado };
}

// --- Conservar el estado en la pestaña (RF-14) ---
//
// En sessionStorage: dura lo que la pestaña, y se borra al cerrar sesión
// (olvidarSesion). La clave lleva el usuario para que otra cuenta en la misma
// pestaña no herede el visor de la anterior; como todas las de la plataforma,
// sale de utils/almacenamiento.js (spec 004).

export const MODOS = ['superpuestas', 'lado_a_lado'];
const VERSION_GUARDADO = 1;

export { claveVisor } from './almacenamiento.js';

// De cada hueco solo se guarda qué molécula es (fichero y posición), no su
// contenido: un PDB grande ocupa varios MB y sessionStorage admite unos 5 en
// total. Al volver, la página pide de nuevo cada molécula al servidor, que
// además vuelve a comprobar que sigue existiendo y se puede ver (RF-13).
export function serializar(estado) {
  const referencia = (m) => (m ? { fichero: m.fichero, posicion: m.posicion ?? null } : null);
  return JSON.stringify({
    version: VERSION_GUARDADO,
    huecos: { A: referencia(estado.huecos.A), B: referencia(estado.huecos.B) },
    activo: estado.activo,
    modo: estado.modo,
    estilos: estado.estilos,
  });
}

const esReferencia = (m) => m === null
  || (typeof m === 'object' && typeof m.fichero === 'string'
      && (m.posicion === null || Number.isInteger(m.posicion)));
const esEstilo = (e) => e === null || ESTILOS.some((x) => x.valor === e);

// Lo guardado, o el estado inicial si no hay nada, está dañado o es de otra
// versión: un visor vacío es mejor que uno a medio restaurar.
export function restaurar(texto) {
  let guardado;
  try {
    guardado = JSON.parse(texto);
  } catch {
    return estadoInicial();
  }
  const valido = guardado !== null && typeof guardado === 'object'
    && guardado.version === VERSION_GUARDADO
    && HUECOS.every((h) => esReferencia(guardado.huecos?.[h]) && esEstilo(guardado.estilos?.[h]))
    && HUECOS.includes(guardado.activo)
    && MODOS.includes(guardado.modo);
  if (!valido) return estadoInicial();
  return {
    huecos: { A: guardado.huecos.A, B: guardado.huecos.B },
    activo: guardado.activo,
    modo: guardado.modo,
    estilos: { A: guardado.estilos.A, B: guardado.estilos.B },
  };
}

// --- Búsquedas vigentes (RF-6) ---
//
// Al teclear deprisa, la respuesta de una búsqueda anterior puede llegar
// después que la de la última. Cada búsqueda toma un número y solo se pinta
// la respuesta del último.
export function crearContadorDeBusquedas() {
  let ultimo = 0;
  return {
    siguiente: () => {
      ultimo += 1;
      return ultimo;
    },
    esVigente: (id) => id === ultimo,
  };
}

// Si un fichero del buscador se recorre por moléculas (RF-6) o se coloca
// entero (RF-5): solo un SDF con varias, o uno del que aún no se sabe cuántas
// tiene (biblioteca recién subida, RF-3); con un solo registro, la propia
// lista lo coloca directamente.
export function tieneLista(fichero) {
  return fichero.formato === 'sdf' && (fichero.num_moleculas === null || fichero.num_moleculas > 1);
}

// Pone una molécula en un hueco concreto sin cambiar nada más. Es para
// restaurar lo guardado (RF-14): el hueco activo y los estilos tienen que
// quedar como estaban, y `colocar` los cambia.
export function ponerEnHueco(estado, hueco, molecula) {
  comprobarHueco(hueco);
  return { ...estado, huecos: { ...estado.huecos, [hueco]: molecula } };
}

// --- Llegada desde «Ver en 3D» en otra página (RF-15) ---
//
// Desde fuera solo se conoce el nombre del fichero. Un SDF puede traer miles
// de moléculas, así que llega con su lista desplegada (RF-6); si resulta
// tener una sola, la propia lista la coloca (RF-5). Lo demás se coloca entero.
export function llegaConLista(nombre) {
  return nombre.toLowerCase().endsWith('.sdf');
}
