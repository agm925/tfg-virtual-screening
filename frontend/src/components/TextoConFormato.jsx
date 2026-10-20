import { trozosConFormato } from '../utils/idioma'

// Un texto de los diccionarios con sus **negritas** (spec 014): los textos
// son planos, sin HTML, y aquí las partes marcadas pasan a <strong>. Lo usan
// el tutorial y los mensajes que resaltan un dato («…a **{email}**»).
export default function TextoConFormato({ texto }) {
  return trozosConFormato(texto).map((trozo, i) =>
    trozo.negrita ? <strong key={i}>{trozo.texto}</strong> : <span key={i}>{trozo.texto}</span>);
}
