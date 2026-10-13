// Cuentas del lienzo del Constructor (spec 010). Sin React, para poder
// probarlas con node.

// Tamaño aproximado de un nodo recién puesto: sirve para centrarlo, no hace
// falta que sea exacto.
const NODO = { ancho: 180, alto: 80 };
// Lo que se desplaza un nodo nuevo si ya hay otro justo en su sitio.
const SALTO = 30;

// Un punto relativo a la esquina del lienzo, en coordenadas del diagrama: el
// lienzo puede estar desplazado (x, y) y ampliado (zoom).
export function aCoordenadasDelLienzo(punto, { x, y, zoom }) {
  return { x: (punto.x - x) / zoom, y: (punto.y - y) / zoom };
}

// Dónde poner un nodo añadido tocando la paleta: en el centro de lo que se
// ve, y en diagonal si ese sitio ya está ocupado (tocar dos veces no debe
// dejar un nodo escondido debajo de otro).
export function posicionNuevoNodo({ ancho, alto, viewport, nodos }) {
  const centro = aCoordenadasDelLienzo({ x: ancho / 2, y: alto / 2 }, viewport);
  const pos = { x: centro.x - NODO.ancho / 2, y: centro.y - NODO.alto / 2 };
  const ocupado = (p) => nodos.some(n => Math.abs(n.position.x - p.x) < SALTO / 2
                                      && Math.abs(n.position.y - p.y) < SALTO / 2);
  while (ocupado(pos)) {
    pos.x += SALTO;
    pos.y += SALTO;
  }
  return pos;
}
