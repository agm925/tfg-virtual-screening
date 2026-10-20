import Icono from './Icono'
import { esFicheroDeMoleculas } from '../utils/visor'
import { useIdioma } from '../hooks/useIdioma'

// «Ver en 3D» de cualquier página (spec 002, RF-15): lleva al Visor 3D con
// este fichero en el hueco A. No se pinta junto a un fichero sin moléculas
// (un CSV de ranking, un JSON de resultados): ahí el visor no tendría nada
// que dibujar.
export default function VerEn3D({ fichero, abrirEnVisor, className = 'btn-descarga' }) {
  const { t } = useIdioma()
  if (!esFicheroDeMoleculas(fichero)) return null
  return (
    <button className={className} onClick={() => abrirEnVisor(fichero)} title={t('ver3d.titulo', { fichero })}>
      <Icono nombre="cubo" />{t('ver3d.boton')}
    </button>
  )
}
