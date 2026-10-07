// Unica definicion de cada tipo de nodo del editor (spec 001). La leen la
// paleta, la cabecera de cada nodo y la pagina Algoritmos. Antes el color de
// un tipo estaba escrito dos veces --en la paleta de VisualBuilder y en
// Nodos.css-- y ya no coincidian (selectMol era rojo en uno y degradado en el
// otro).
//
// `familia` elige el color: la clase CSS `familia-<familia>` lo toma de
// --nodo-<familia> en tokens.css. `icono` es el nombre que dibuja Icono.jsx.
// El orden del array es el de la paleta.
export const TIPOS_NODO = [
  { tipo: 'upload',       etiqueta: 'Subir molécula',    familia: 'entrada',     icono: 'subir',
    descripcion: 'Sube una molécula desde tu equipo.' },
  { tipo: 'selectMol',    etiqueta: 'Elegir molécula',   familia: 'entrada',     icono: 'matraz',
    descripcion: 'Usa una molécula que ya subiste.' },
  { tipo: 'selectDB',     etiqueta: 'Elegir biblioteca', familia: 'entrada',     icono: 'biblioteca',
    descripcion: 'Aplica el workflow a todas las moléculas de una biblioteca SDF.' },
  { tipo: 'preprocesado', etiqueta: 'Preparar',          familia: 'preparacion', icono: 'ajustes',
    descripcion: 'Convierte, añade hidrógenos, genera 3D o filtra (Lipinski).' },
  { tipo: 'alineacion',   etiqueta: 'Alinear',           familia: 'alineacion',  icono: 'alinear',
    descripcion: 'Superpone una molécula sobre otra de referencia.' },
  { tipo: 'comparacion',  etiqueta: 'Comparar',          familia: 'comparacion', icono: 'balanza',
    descripcion: 'Puntúa el parecido entre dos moléculas (Tanimoto, RMSD).' },
  { tipo: 'docking',      etiqueta: 'Docking',           familia: 'docking',     icono: 'diana',
    descripcion: 'Encaja el ligando en el receptor y estima la afinidad.' },
  { tipo: 'ejecutar',     etiqueta: 'Inicio',            familia: 'control',     icono: 'reproducir',
    descripcion: 'Marca dónde empieza el workflow.' },
  { tipo: 'descargar',    etiqueta: 'Descargar',         familia: 'control',     icono: 'bajar',
    descripcion: 'Deja el resultado listo para descargar.' },
];

const POR_TIPO = Object.fromEntries(TIPOS_NODO.map(t => [t.tipo, t]));

// Nombre del `tipo` de un algoritmo (Algoritmo.tipo en el backend). Coincide
// con el tipo del nodo que lo usa, de ahi su icono y su color.
export const ETIQUETA_ALGORITMO = {
  preprocesado: 'Preparación',
  alineacion:   'Alineación',
  comparacion:  'Comparación',
  docking:      'Docking',
};

export const tipoNodo = (tipo) => POR_TIPO[tipo];
