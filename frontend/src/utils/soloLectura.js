import { createContext } from 'react';

// Modo consulta del Constructor (spec 012): el workflow de una ejecución tal
// como se lanzó, que no se puede cambiar. Lo da VisualBuilder y lo leen los
// nodos a través de MarcoNodo.
export const SoloLectura = createContext(false);
