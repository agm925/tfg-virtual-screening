# Contexto: nueva medición de escalado de *workers* (TFG cribado virtual)

> Documento autocontenido para retomar esto en otra conversación y llevarlo a la
> memoria. Incluye qué se midió, por qué hubo que volver a medir, qué cambió
> respecto a la medición anterior y qué hay que tocar exactamente en el LaTeX.

---

## 1. De qué proyecto se trata

Plataforma web de cribado virtual (TFG). Pila: FastAPI + SQLAlchemy +
PostgreSQL, Celery + Redis como cola de tareas, React + Vite + React Flow en el
frontend, todo en Docker Compose (6 servicios: `db`, `redis`, `backend`,
`worker`, `flower`, `frontend`). Los algoritmos de cribado son *scripts* de
Python sueltos en `algoritmos/` que el backend invoca como subprocesos.

El paralelismo se obtiene lanzando **réplicas del servicio `worker`**
(`docker compose up --scale worker=N`), todas consumiendo de la misma cola de
Redis. Es una paralelización de alto nivel (HLP): cada *worker* procesa una
molécula entera, no se paraleliza dentro de cada algoritmo.

## 2. Qué mide el benchmark, exactamente

`scripts/benchmark.py`, invocado en tanda por `scripts/tanda_escalado.sh`.

Mide la **ruta de petición individual**, no el cribado por lotes:

1. Descarga ~1000 moléculas reales de **ChEMBL** en SDF (se cachea en
   `uploads/benchmark_chembl.sdf`).
2. Las parte en `.mol2` individuales con Open Babel dentro del contenedor.
3. Para cada tamaño de lote (100, 500, 1000) sube cada fichero con
   `POST /peticiones` — lo que encola **una tarea Celery por molécula** — y
   sondea `GET /peticiones/{id}/estado` hasta que todas acaban en `COMPLETADO`
   o `ERROR`. Cronometra desde la primera subida hasta la última confirmación.

El algoritmo medido es **`filtroLipinski.py`** (regla de los cinco).

**Importante:** esto NO mide el *chord* de Celery del cribado por lotes
(`ejecutar_workflow_batch_async` → `procesar_bloque_batch` → `consolidar_batch`).
Son dos caminos distintos del sistema. El benchmark mide el de peticiones
sueltas, que es el que estaba medido en la memoria y por tanto el comparable.

El número de *workers* no lo cambia el script: se fija antes con
`docker compose up --scale worker=N` y el flag `--workers` solo etiqueta la
fila del CSV. Eso es deliberado — un script no debe cronometrar un cambio de
configuración que él mismo controla.

## 3. Por qué hubo que volver a medir

El CSV anterior es del **2026-08-25**. Entre esa fecha y hoy cambiaron cosas que
afectan justo a lo que se mide:

| Commit | Fecha | Qué cambió | Efecto sobre la medición |
|---|---|---|---|
| `7d0bce6` | 2026-09-09 | `worker_prefetch_multiplier=1` en `app/celery_app.py` | **El grande.** Antes regía el valor por defecto de Celery (4): un *worker* reservaba por adelantado 4 tareas largas mientras otros estaban ociosos, anulando el reparto. La medición vieja de escalado se hizo con el reparto saboteado. |
| `7d0bce6` | 2026-09-09 | `task_acks_late=True` y `task_reject_on_worker_lost=True` | La tarea se confirma al terminarla, no al entregarla: un *worker* que muere devuelve su trabajo a la cola en vez de perderlo. |
| `c9f2a05` | 2026-09-09 | `mem_limit: 2g` por *worker* en `docker-compose.yml` | Un algoritmo desbocado mata su propio *worker* en vez de agotar la máquina. |
| `3fcc2f8` | 2026-09-10 | Tolerancia a la kekulización en `filtroLipinski.py` | **Cambia la carga de trabajo.** Antes, 302 de 1000 moléculas (30 %) acababan en `ERROR` porque RDKit no sabía leer el `.mol2` generado por Open Babel. Ahora se procesan de verdad. |

### Consecuencia metodológica que hay que declarar en la memoria

Las dos tandas **no son comparables en tiempos absolutos**. Con el arreglo de
kekulización, cada lote hace más trabajo real que en agosto: una molécula que
fallaba al cargarse costaba milisegundos, y ahora se calculan sus descriptores.
Un tiempo total mayor no significaría una regresión.

Lo que **sí** es comparable es el *speedup* **dentro de cada tanda** (tiempo con
1 *worker* / tiempo con N), porque las tres escalas de la tanda nueva procesan
exactamente el mismo conjunto de moléculas con el mismo código.

Por eso la tanda nueva añade **2 *workers*** (antes solo había 1 y 4) y las
columnas `speedup` y `eficiencia`.

## 4. El script de benchmark estaba roto y hubo que arreglarlo

Antes de poder medir nada: `scripts/benchmark.py` era anterior al endurecimiento
de seguridad y ya no funcionaba contra la API actual. Dos fallos:

1. **Sin autenticación.** Llamaba a `POST /peticiones`, `GET /algoritmos` y
   `GET /peticiones/{id}/estado` pasando `usuario_id` como campo de formulario.
   Hoy los tres exigen JWT (`obtener_usuario_actual`), el propietario se toma
   del token y no del formulario, y subir un algoritmo exige rol
   `desarrollador` (`requiere_rol("admin", "desarrollador")`).
   *Arreglo:* el script se registra, se marca el correo como verificado y se
   eleva el rol contra la BD vía `docker compose exec`, hace `POST /login` y
   opera con `Authorization: Bearer` como el frontend.
2. **Correo inválido.** Usaba `benchmark_bot@tfg.local`; la validación de
   entrada con `EmailStr` rechaza los TLD reservados con un 422
   (*"The part after the @-sign is a special-use or reserved name"*).
   *Arreglo:* `benchmark_bot@example.com`.

A esos dos se sumaron, ya midiendo, otros dos problemas de método:

3. **La imagen del *worker* estaba desfasada** cinco días respecto a `HEAD`.
   `app/` no está montado como volumen —solo lo están `uploads/` y
   `algoritmos/`—, así que el código va horneado en la imagen y
   `docker compose up` no lo actualiza. Y `backend` y `worker` son dos entradas
   de *build* distintas: reconstruir solo una deja la otra atrás.
   *Arreglo:* `docker compose build` **sin argumentos** dentro del script de
   tanda, comentado para que no vuelva a morder.
4. **El benchmark re-subía ficheros que ya estaban en `uploads/`**, así que cada
   subida colisionaba consigo misma y `nombre_libre()` recorría candidatos
   `_2`, `_3`, `_4`… con **una consulta a la base de datos por candidato**.
   Medido: 144,4 ms por subida con colisión frente a 111,5 ms sin ella. Peor
   aún, era acumulativo y asimétrico: cada escala dejaba un nivel más de
   sufijos que la siguiente tenía que saltarse, penalizando a los recuentos
   altos de *workers* — justo lo que se intentaba medir.
   *Arreglo:* cada tanda sube con un `RUN_ID` propio y purga sus ficheros al
   terminar cada lote, fuera de la región cronometrada.

Los dos primeros son la misma historia: **el endurecimiento de seguridad dejó
atrás herramientas internas que nadie volvió a ejecutar**. Merece una frase en la
memoria, porque es un efecto colateral real y honesto de una mejora.

Además se añadió `scripts/tanda_escalado.sh`, que orquesta las tres escalas
seguidas; antes esa secuencia se hacía a mano y por tanto no quedaba registrada
en ninguna parte.

## 5. Resultados (27 mediciones, 2026-09-15)

3 repeticiones × 3 escalas (1, 2, 4 *workers*) × 3 tamaños de lote.
Máquina: 12 CPUs y 8 GB para Docker. Cada réplica con `worker_concurrency=1`,
así que N réplicas son N procesos y el techo teórico es N×.

### 5.1 Tabla completa

| Lote | Workers | Media (s) | Desv. (s) | CV | Mín (s) | Máx (s) | *Speedup* | Eficiencia |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 1 | 74.6 | 9.2 | 12.3 % | 67.7 | 85.0 | 1.00 | 1.00 |
| 100 | 2 | 42.8 | 3.8 | 8.9 % | 38.9 | 46.6 | 1.74 | 0.87 |
| 100 | 4 | 29.4 | 0.1 | **0.3 %** | 29.3 | 29.5 | 2.31 | 0.58 |
| 500 | 1 | 673.2 | 371.3 | **55.2 %** | 423.5 | 1099.9 | 1.00 | 1.00 |
| 500 | 2 | 258.5 | 29.3 | 11.4 % | 224.6 | 276.4 | 1.89 | 0.94 |
| 500 | 4 | 126.2 | 2.3 | 1.8 % | 124.3 | 128.8 | 3.41 | 0.85 |
| 1000 | 1 | 1538.2 | 950.1 | **61.8 %** | 855.3 | 2623.2 | 1.00 | 1.00 |
| 1000 | 2 | 445.7 | 52.7 | 11.8 % | 404.2 | 505.0 | 2.12 | 1.06 |
| 1000 | 4 | 264.3 | 11.7 | 4.4 % | 253.4 | 276.6 | 3.38 | 0.84 |

Moléculas fallidas: **1/100, 18/500, 35/1000 (3,5 %)**, idénticas en las nueve
combinaciones — el *pipeline* es determinista respecto al número de réplicas.

### 5.2 El hallazgo principal no es el speedup: es la dispersión

Mirando la columna CV de arriba, el patrón salta a la vista:

| Workers | CV del lote de 1000 |
|---:|---:|
| 1 | **61,8 %** |
| 2 | 11,8 % |
| 4 | **4,4 %** |

**Con un solo *worker* la medición es basura; con cuatro es casi perfecta.**
El extremo: el lote de 1000 con 1 *worker* tardó 855 s en una repetición y
2.623 s en otra — un factor 3 entre medidas de lo mismo.

La explicación es de exposición temporal. La configuración de 1 *worker* es la
más lenta, así que su ventana de medida es la más larga (hasta 44 minutos para
el lote de 1000) y por tanto la más expuesta a cualquier otra carga de la
máquina. Y un solo proceso no tiene holgura: cada ciclo de CPU que se le quita
va directo al reloj. Con 4 procesos sobre 12 núcleos hay margen para absorber
la interferencia.

> **Hay que decirlo en la memoria:** parte de esa interferencia la causé yo
> trabajando en la misma máquina mientras medía (compilar el LaTeX, reconstruir
> imágenes, consultas a la base de datos). No es una excusa, es la causa, y
> condiciona cómo hay que leer los números.

### 5.3 Por qué los *speedups* se calculan sobre el mínimo

El *speedup* es un cociente cuyo **denominador es la medida más ruidosa** (la
de 1 *worker*). Con las medias sale 5,82× a 4 *workers* — superlineal otra vez,
y por la misma razón que el 4,09× de la memoria: el numerador está inflado.

Por eso la tabla usa el **mínimo de las tres repeticiones** de cada
configuración. Es práctica habitual al medir sobre una máquina no dedicada: el
mínimo es la ejecución con menos interferencia, es decir, la más cercana al
tiempo real del sistema. Así sale una curva coherente:

| Lote | 2 workers | 4 workers |
|---:|---:|---:|
| 500 | 1,89× (ef. 0,94) | **3,41× (ef. 0,85)** |
| 1000 | 2,12× (ef. 1,06) | **3,38× (ef. 0,84)** |

### 5.4 Qué se puede afirmar, y qué no

**Se puede afirmar:** con 4 *workers*, el cribado de 500 y 1000 moléculas se
acelera **≈3,4×**, con una eficiencia de **≈0,85**. La cifra es consistente
entre los dos tamaños de lote y proviene de las configuraciones cuya medición
es reproducible (CV del 1,8 % y el 4,4 %).

**No se puede afirmar** el 4,09× que figura hoy en la memoria. Implicaba una
eficiencia de 1,02 —superlineal, imposible con cuatro procesos— y era el
síntoma de un denominador contaminado, exactamente el mismo efecto que aquí se
ha cuantificado.

**Queda una anomalía honesta:** 1000 moléculas con 2 *workers* da eficiencia
1,06, ligeramente superlineal. Es ruido residual del denominador, y conviene
decirlo en vez de redondearlo a 1,00.

### 5.5 El lote de 100 no mide paralelismo

Eficiencia 0,58 con 4 *workers*, y un CV del 0,3 % — reproducibilidad
altísima midiendo algo que no es el paralelismo. De 2 a 4 *workers* solo baja
de 38,9 s a 29,3 s porque ya ha tocado el suelo que imponen las 100 subidas
secuenciales más el sondeo. Es el mismo efecto que en la medición anterior
producía un imposible 10,98×.

### 5.6 La fase serie, medida aparte

Subir una molécula cuesta **0,1337 s** (medido sobre 100 subidas con nombres
sin colisión), es decir **133,7 s para mil**: el **17,6 %** del tiempo del lote
de 1000 con un *worker*. Por la ley de Amdahl con f = 0,176, el techo de
escalado es 5,7× y la predicción a 4 *workers* es 2,62×, frente al 3,38×
medido — el medido queda por encima porque los *workers* empiezan a consumir
mientras las subidas siguen en marcha, solapando parte de la fase serie.

**Esa fase serie es del medidor, no de la plataforma.** Un usuario real que
hace un cribado por lotes sube **un único SDF** y el *chord* reparte las
moléculas; no hay mil subidas HTTP secuenciales. El techo que mide este
benchmark es pesimista respecto al caso de uso real.

### 5.7 Para obtener cifras de calidad de publicación

Lo que falta no es más código, es un entorno limpio: **máquina dedicada, sin
nadie usándola**, y preferiblemente 5 repeticiones en vez de 3. Con eso, el CV
del 1 *worker* debería bajar del 60 % a un rango parecido al del resto, y los
*speedups* podrían darse como media ± desviación en lugar de sobre el mínimo.

## 6. Qué hay que cambiar en la memoria

Todo está en `contenido2.tex` (proyecto LaTeX en
`C:\Users\aleja\Desktop\TFG_Alejandro_Gomez (2)`). Cinco sitios citan las cifras
viejas — si se cambia solo la tabla, el documento se queda incoherente:

| Dónde | Línea aprox. | Qué dice ahora |
|---|---|---|
| `\section{Evaluación de rendimiento del escalado de workers}` (`sec:evaluacion-rendimiento`) → subsección *Resultados* | 2799 | «los **seis** lotes medidos» → ahora son nueve |
| Tabla `tab:benchmark-workers` | 2813–2818 | Las 6 filas de 1 y 4 *workers* |
| Párrafo de interpretación | 2826–2830 | «$4.04\times$ con 500 y $4.09\times$ con 1000», «$10.98\times$» en el lote de 100 |
| Párrafo de moléculas fallidas | 2836 | «302 ($\sim$30 %) terminan en estado ERROR» |
| Conclusiones | 3075 | «de 722 s a 177 s — un factor $4.09\times$» |
| Trabajo futuro, punto 1 | 3127 | «$4.09\times$ con 4 *workers* sobre 1000 moléculas» |
| Limitaciones, punto 1 | 2967–2968 | «escalado cercano al lineal al pasar de 1 a 4 *workers*» |

La subsección de **Metodología** (línea ~2770) también necesita un retoque: ya
no describe bien el procedimiento, porque ahora hay un script que orquesta las
escalas y porque el bot se autentica.

### Sugerencia de enfoque para el texto nuevo

No presentar esto como «hemos vuelto a medir y salen otros números», sino como
lo que es: **una medición anterior estaba contaminada por una mala
configuración de Celery que se corrigió después**. La historia buena es que el
`prefetch_multiplier` por defecto es una trampa clásica en Celery con tareas
largas, que se detectó en la auditoría, y que la nueva medición cuantifica lo
que costaba. Eso convierte un número actualizado en un hallazgo.

## 7. Ficheros implicados

- `scripts/benchmark.py` — medición de una configuración (modificado: auth + email + columna `fecha`).
- `scripts/tanda_escalado.sh` — orquesta 1, 2 y 4 *workers* (nuevo).
- `scripts/benchmark_results.csv` — filas crudas de la tanda nueva.
- `scripts/benchmark_escalado.csv` — mismas filas con `speedup` y `eficiencia`.
- `scripts/benchmark_results_2026-08-25.csv` — la tanda vieja, preservada.
- `app/celery_app.py` — `worker_prefetch_multiplier`, `acks_late`.
- `docker-compose.yml` — `mem_limit` del *worker*.
- `algoritmos/filtroLipinski.py` — tolerancia a la kekulización.

## 8. Cabos sueltos

- La tanda deja varios miles de ficheros de resultado en `uploads/`. Se limpian
  con `scripts/limpiar_uploads.py`, que va en simulación por defecto y solo
  borra con `--borrar`. **Hay que ejecutarlo DENTRO del contenedor**: desde el
  host, `DATABASE_URL` cae a SQLite y consultaría una base de datos vacía.
- Nada de esto está empujado al remoto todavía.
