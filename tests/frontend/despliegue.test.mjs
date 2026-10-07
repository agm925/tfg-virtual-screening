// Pruebas de la spec 004 (despliegue en https://rt.hpca.ual.es/molserver).
// Leen la configuración y el código como texto: lo que importa es qué rutas,
// claves y puertos quedan escritos. Lo que depende del proxy real del servidor
// va en docs/specs/004-despliegue/comprobaciones.md.
//
//   node --test "tests/frontend/**/*.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const RAIZ = fileURLToPath(new URL('../../', import.meta.url));
const leer = (ruta) => readFileSync(join(RAIZ, ruta), 'utf8');

// Los ficheros de código del frontend, sin comentarios: un comentario que
// cuente cómo era antes no es una ruta en uso.
function codigoDelFrontend() {
  const ficheros = [];
  const recorrer = (dir) => {
    for (const nombre of readdirSync(dir)) {
      const ruta = join(dir, nombre);
      if (statSync(ruta).isDirectory()) recorrer(ruta);
      else if (/\.(jsx?|css)$/.test(nombre)) ficheros.push(ruta);
    }
  };
  recorrer(join(RAIZ, 'frontend/src'));
  ficheros.push(join(RAIZ, 'frontend/index.html'));
  return ficheros.map((ruta) => ({
    ruta: ruta.slice(RAIZ.length),
    texto: readFileSync(ruta, 'utf8')
      .replace(/<!--[\s\S]*?-->/g, '')
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/^\s*\/\/.*$/gm, ''),
  }));
}

// ---------------------------------------------------------------------------
// R1, R2: la aplicación cuelga de /molserver/ y no pide nada a la raíz
// ---------------------------------------------------------------------------

test('el build de producción cuelga de /molserver/ y se puede cambiar con VITE_BASE (R1)', () => {
  const vite = leer('frontend/vite.config.js');
  assert.match(vite, /process\.env\.VITE_BASE/);
  assert.match(vite, /['"]\/molserver\/['"]/);
});

test('el cliente de la API pide relativo a la base de la aplicación (R2)', () => {
  const cliente = leer('frontend/src/api/client.js');
  assert.match(cliente, /import\.meta\.env\.BASE_URL/);
  assert.doesNotMatch(cliente, /\?\?\s*['"]\/api['"]/, "API con '/api' escrito a mano");
});

test('ningún fichero del frontend pide rutas absolutas a la raíz del dominio (CA2)', () => {
  for (const { ruta, texto } of codigoDelFrontend()) {
    assert.doesNotMatch(texto, /\b(src|href)=["']\/(api|ual|assets)\//, `${ruta}: src/href absoluto`);
    assert.doesNotMatch(texto, /url\(\s*["']?\/(api|ual|assets)\//, `${ruta}: url() absoluto`);
    assert.doesNotMatch(texto, /['"`]\/(api|ual|assets)\//, `${ruta}: cadena con ruta absoluta`);
  }
});

// ---------------------------------------------------------------------------
// R3: nginx atiende con y sin el prefijo /molserver
// ---------------------------------------------------------------------------

test('nginx quita el prefijo /molserver si el proxy lo conserva (R3, CA3)', () => {
  assert.match(leer('frontend/nginx.conf'), /rewrite\s+\^\/molserver\/\(\.\*\)\$\s+\/\$1\s+last;/);
});

test('nginx redirige /molserver a /molserver/ sin inventarse host ni puerto (R3, CA3)', () => {
  const nginx = leer('frontend/nginx.conf');
  assert.match(nginx, /location\s*=\s*\/molserver\s*\{\s*return\s+301\s+\/molserver\/;\s*\}/);
  assert.match(nginx, /absolute_redirect\s+off;/);
});

test('nginx conserva la API, el tamaño de subida y los tiempos de espera (R3)', () => {
  const nginx = leer('frontend/nginx.conf');
  assert.match(nginx, /location\s+\/api\/\s*\{/);
  assert.match(nginx, /proxy_pass\s+http:\/\/backend:8000\/;/);
  assert.match(nginx, /client_max_body_size\s+512M;/);
  assert.match(nginx, /proxy_read_timeout\s+300s;/);
});

// ---------------------------------------------------------------------------
// R5: almacenamiento propio en el navegador
// ---------------------------------------------------------------------------

test('el frontend no guarda nada con una clave escrita a mano (R5, CA5)', () => {
  // Las claves salen todas de utils/almacenamiento.js, con el prefijo.
  for (const { ruta, texto } of codigoDelFrontend()) {
    assert.doesNotMatch(texto, /(local|session)Storage\.(getItem|setItem|removeItem)\(\s*['"`]/,
      `${ruta}: clave literal en el almacenamiento`);
  }
});

test('no quedan las claves antiguas sin prefijo (R5, CA5)', () => {
  for (const { ruta, texto } of codigoDelFrontend()) {
    assert.doesNotMatch(texto, /['"`](access_token|usuario_tfg|editor_tfg_|visor_tfg_)/, `${ruta}: clave antigua`);
  }
});

test('cerrar sesión no vacía el almacenamiento de las demás aplicaciones (R5, CA5)', () => {
  for (const { ruta, texto } of codigoDelFrontend()) {
    assert.doesNotMatch(texto, /(local|session)Storage\.clear\(/, `${ruta}: clear() borra todo el dominio`);
  }
});

// ---------------------------------------------------------------------------
// R6: puertos
// ---------------------------------------------------------------------------

test('el puerto del frontend es configurable (R6, CA6)', () => {
  assert.match(leer('docker-compose.yml'), /- "\$\{FRONTEND_PORT:-5173\}:80"/);
});

test('el backend solo escucha en la propia máquina: se llega por el proxy (R6, CA6)', () => {
  const compose = leer('docker-compose.yml');
  assert.match(compose, /- "127\.0\.0\.1:8000:8000"/);
  assert.doesNotMatch(compose, /- "8000:8000"/);
});
