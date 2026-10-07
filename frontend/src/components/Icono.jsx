import React from 'react';

// Iconos de la interfaz (spec 001). Sustituyen a los emojis, que cada sistema
// dibuja a su manera --en los Windows de la universidad salian en color y en
// otros como cuadros vacios-- y que no siguen el color del texto. Son trazos
// propios en una cuadricula de 24x24, sin rellenos, que heredan el color con
// currentColor; se dibujan aqui y no con una libreria porque la constitucion
// (principio 1) no admite dependencias nuevas para esto.
const TRAZOS = {
  subir:      <><path d="M12 15V3M7 8l5-5 5 5" /><path d="M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4" /></>,
  bajar:      <><path d="M12 3v12M7 10l5 5 5-5" /><path d="M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4" /></>,
  matraz:     <><path d="M9 3h6M10 3v6L4.5 19a1.5 1.5 0 0 0 1.3 2h12.4a1.5 1.5 0 0 0 1.3-2L14 9V3" /><path d="M7 15h10" /></>,
  biblioteca: <><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5" /><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" /></>,
  ajustes:    <><path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0" /><circle cx="16" cy="6" r="2" /><circle cx="10" cy="12" r="2" /><circle cx="18" cy="18" r="2" /></>,
  alinear:    <><rect x="3" y="3" width="12" height="12" rx="1" /><rect x="9" y="9" width="12" height="12" rx="1" /></>,
  balanza:    <><path d="M12 3v18M7 21h10M5 7h14" /><path d="M5 7l-3 7a3 3 0 0 0 6 0zM19 7l-3 7a3 3 0 0 0 6 0z" /></>,
  diana:      <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1" /></>,
  reproducir: <path d="M7 4l13 8-13 8z" />,
  mas:        <path d="M12 5v14M5 12h14" />,
  guardar:    <><path d="M5 3h11l5 5v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z" /><path d="M7 3v6h8M7 21v-7h10v7" /></>,
  papelera:   <><path d="M3 6h18M8 6V4h8v2M6 6l1 15h10l1-15" /><path d="M10 11v6M14 11v6" /></>,
  reloj:      <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  procesando: <><path d="M21 12a9 9 0 1 1-3-6.7" /><path d="M21 4v5h-5" /></>,
  grafico:    <path d="M4 20h16M7 16v-5M12 16V7M17 16V8" />,
  ok:         <><circle cx="12" cy="12" r="9" /><path d="M8 12l3 3 5-6" /></>,
  error:      <><circle cx="12" cy="12" r="9" /><path d="M9 9l6 6M15 9l-6 6" /></>,
  aviso:      <><path d="M12 3l10 18H2z" /><path d="M12 10v4M12 17.5v.5" /></>,
  filtro:     <path d="M3 4h18l-7 8v6l-4 2v-8z" />,
  fichero:    <><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" /><path d="M14 3v6h6" /></>,
  cubo:       <><path d="M12 2l9 5v10l-9 5-9-5V7z" /><path d="M3 7l9 5 9-5M12 12v10" /></>,
  cerrar:     <path d="M6 6l12 12M18 6L6 18" />,
  // Para las secciones del tutorial (spec 003); no son tipos de nodo.
  codigo:     <path d="M8 6l-6 6 6 6M16 6l6 6-6 6M14 4l-4 16" />,
  nodos:      <><rect x="3" y="4" width="6" height="5" rx="1" /><rect x="15" y="4" width="6" height="5" rx="1" /><rect x="9" y="15" width="6" height="5" rx="1" /><path d="M9 6.5h6M6 9v3h12V9M12 12v3" /></>,
  bloques:    <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><path d="M17.5 14v7M14 17.5h7" /></>,
  bombilla:   <><path d="M9 18h6M10 21h4" /><path d="M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z" /></>,
};

// Decorativo por defecto (aria-hidden): casi siempre va junto a un texto que
// ya dice lo mismo. Si el icono va solo, quien lo usa pone el aria-label en el
// boton que lo contiene.
const Icono = ({ nombre, tamano = 16, className = '' }) => (
  <svg className={`icono ${className}`} width={tamano} height={tamano} viewBox="0 0 24 24"
       fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"
       strokeLinejoin="round" aria-hidden="true" focusable="false">
    {TRAZOS[nombre]}
  </svg>
);

export default Icono;
