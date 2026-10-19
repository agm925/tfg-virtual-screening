// «Ver workflow» desde Resultados (spec 012): qué se enseña en el Constructor.

// JSON con las claves ordenadas: los nodos rellenan `data` en el orden en que
// se montan, y el mismo grafo no puede parecer distinto por eso. La usa
// también el Constructor para saber si hay cambios sin guardar.
export const huella = (valor) => JSON.stringify(valor, (_, v) =>
  v && typeof v === 'object' && !Array.isArray(v)
    ? Object.fromEntries(Object.entries(v).sort(([a], [b]) => a.localeCompare(b)))
    : v);

// `ejecucion`: la respuesta de GET /workflows/ejecuciones/{id}; `actual`: el
// workflow tal como está guardado ahora (null si está borrado).
//   'actual'    la copia es la versión actual: se abre normal, editable.
//   'sin-copia' ejecución anterior a la copia: la versión actual, con aviso.
//   'consulta'  el workflow ha cambiado desde entonces: la copia, sin editar.
//   'borrado'   el workflow ya no está en el Constructor: la copia, sin editar.
export function vistaDeEjecucion(ejecucion, actual) {
  if (ejecucion.workflow_borrado) return 'borrado';
  if (!ejecucion.copia_exacta) return 'sin-copia';
  return huella(ejecucion.grafo_json) === huella(actual?.grafo_json) ? 'actual' : 'consulta';
}
