import { useId } from 'react'

// Banderas del selector de idioma (spec 014). SVG propios y no emojis: los
// emojis de bandera no existen en Windows (se ven las letras «ES» y «GB»), y
// la plataforma no usa emojis en ningún sitio (spec 001). Son decorativas: el
// botón ya dice el idioma, así que el lector de pantalla no las lee.

// España sin escudo (decisión del usuario): a este tamaño no se distingue, y
// en SVG pesaría más que todo el selector. Franjas 1:2:1.
export function BanderaEspana({ className = '' }) {
  return (
    <svg className={className} viewBox="0 0 30 20" aria-hidden="true" focusable="false">
      <rect width="30" height="20" fill="#AA151B" />
      <rect y="5" width="30" height="10" fill="#F1BF00" />
    </svg>
  );
}

// Reino Unido: la Union Jack en 3:2 y no en su 1:2, para que las dos banderas
// ocupen lo mismo. Las aspas rojas van sin el desplazamiento de la original: a
// 20 px no se aprecia.
export function BanderaReinoUnido({ className = '' }) {
  // El recorte necesita un id, y la cabecera pinta dos selectores: con un id
  // fijo habría dos iguales en la página.
  const recorte = useId();
  return (
    <svg className={className} viewBox="0 0 60 40" aria-hidden="true" focusable="false">
      <clipPath id={recorte}><rect width="60" height="40" /></clipPath>
      <g clipPath={`url(#${recorte})`}>
        <rect width="60" height="40" fill="#012169" />
        <path d="M0 0L60 40M60 0L0 40" stroke="#fff" strokeWidth="8" />
        <path d="M0 0L60 40M60 0L0 40" stroke="#C8102E" strokeWidth="3" />
        <path d="M30 0V40M0 20H60" stroke="#fff" strokeWidth="12" />
        <path d="M30 0V40M0 20H60" stroke="#C8102E" strokeWidth="7" />
      </g>
    </svg>
  );
}
