import { useState } from 'react'

// Escudo de la Universidad de Almería junto a su nombre, como en la cabecera
// de ual.es. El escudo es un disco blanco con el sello en azul, así que sirve
// igual sobre la cabecera azul que sobre fondo blanco.
//
// public/ual/escudo-ual.png es una copia recortada y reducida a 192 px de
// logo-blanco.png (2188 px, 184 KB): se muestra a menos de 64 px. Si no
// carga, queda el nombre en texto en vez de un icono de imagen rota.
//
// Se pide relativo a la base de la aplicación (spec 004): bajo /molserver/,
// una ruta /ual/... iría a la raíz del dominio, fuera de MolServer.
const ESCUDO = `${import.meta.env.BASE_URL}ual/escudo-ual.png`;

export default function LogoUAL({ className = '', claseTexto = '' }) {
  const [sinImagen, setSinImagen] = useState(false);

  return (
    <span className={`logo-ual ${className}`}>
      {!sinImagen && (
        <img
          src={ESCUDO}
          alt=""
          className="logo-ual-escudo"
          onError={() => setSinImagen(true)}
        />
      )}
      <span className={`logo-ual-texto ${claseTexto}`}>
        Universidad<br />de Almería
      </span>
    </span>
  );
}
