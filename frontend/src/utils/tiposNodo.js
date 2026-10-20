// Unica definicion de cada tipo de nodo del editor (spec 001). La leen la
// paleta, la cabecera de cada nodo y la pagina Algoritmos. Antes el color de
// un tipo estaba escrito dos veces --en la paleta de VisualBuilder y en
// Nodos.css-- y ya no coincidian (selectMol era rojo en uno y degradado en el
// otro).
//
// `familia` elige el color: la clase CSS `familia-<familia>` lo toma de
// --nodo-<familia> en tokens.css. `icono` es el nombre que dibuja Icono.jsx.
// El orden del array es el de la paleta. `etiqueta` y `descripcion` son claves
// de los diccionarios (spec 014): las traduce quien las enseña.
export const TIPOS_NODO = [
  { tipo: 'upload',       etiqueta: 'nodo.upload',       familia: 'entrada',     icono: 'subir',
    descripcion: 'nodo.upload_desc' },
  { tipo: 'selectMol',    etiqueta: 'nodo.selectMol',    familia: 'entrada',     icono: 'matraz',
    descripcion: 'nodo.selectMol_desc' },
  { tipo: 'selectDB',     etiqueta: 'nodo.selectDB',     familia: 'entrada',     icono: 'biblioteca',
    descripcion: 'nodo.selectDB_desc' },
  { tipo: 'preprocesado', etiqueta: 'nodo.preprocesado', familia: 'preparacion', icono: 'ajustes',
    descripcion: 'nodo.preprocesado_desc' },
  { tipo: 'alineacion',   etiqueta: 'nodo.alineacion',   familia: 'alineacion',  icono: 'alinear',
    descripcion: 'nodo.alineacion_desc' },
  { tipo: 'comparacion',  etiqueta: 'nodo.comparacion',  familia: 'comparacion', icono: 'balanza',
    descripcion: 'nodo.comparacion_desc' },
  { tipo: 'docking',      etiqueta: 'nodo.docking',      familia: 'docking',     icono: 'diana',
    descripcion: 'nodo.docking_desc' },
  { tipo: 'ejecutar',     etiqueta: 'nodo.ejecutar',     familia: 'control',     icono: 'reproducir',
    descripcion: 'nodo.ejecutar_desc' },
  { tipo: 'descargar',    etiqueta: 'nodo.descargar',    familia: 'control',     icono: 'bajar',
    descripcion: 'nodo.descargar_desc' },
];

const POR_TIPO = Object.fromEntries(TIPOS_NODO.map(t => [t.tipo, t]));

// Nombre del `tipo` de un algoritmo (Algoritmo.tipo en el backend). Coincide
// con el tipo del nodo que lo usa, de ahi su icono y su color.
export const ETIQUETA_ALGORITMO = {
  preprocesado: 'algoritmo.tipo_preprocesado',
  alineacion:   'algoritmo.tipo_alineacion',
  comparacion:  'algoritmo.tipo_comparacion',
  docking:      'algoritmo.tipo_docking',
};

export const tipoNodo = (tipo) => POR_TIPO[tipo];
