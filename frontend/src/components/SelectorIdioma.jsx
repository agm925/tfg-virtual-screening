import { useIdioma } from '../hooks/useIdioma'
import { BanderaEspana, BanderaReinoUnido } from './Banderas'

// «ES | EN» con la bandera del idioma activo (spec 014, R2). Dos botones con
// aria-pressed y no un desplegable: son dos opciones, siempre a la vista, y un
// lector de pantalla anuncia cuál está pulsada.
//
// `className` sitúa cada copia: la cabecera pinta una en la franja superior y
// otra junto a «Menú» para el móvil, y el CSS enseña la que toca a cada ancho.
export default function SelectorIdioma({ className = '' }) {
  const { idioma, cambiarIdioma, t } = useIdioma();
  const Bandera = idioma === 'en' ? BanderaReinoUnido : BanderaEspana;

  return (
    <div className={`selector-idioma ${className}`} role="group" aria-label={t('idioma.grupo')}>
      <Bandera className="selector-idioma-bandera" />
      {['es', 'en'].map((codigo, i) => (
        <span key={codigo} className="selector-idioma-opcion">
          {i > 0 && <span className="selector-idioma-separador" aria-hidden="true">|</span>}
          <button
            type="button"
            lang={codigo}
            title={t(`idioma.${codigo}`)}
            aria-pressed={idioma === codigo}
            onClick={() => idioma !== codigo && cambiarIdioma(codigo)}
          >
            {codigo.toUpperCase()}
          </button>
        </span>
      ))}
    </div>
  );
}
