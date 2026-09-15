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

Ambos son la misma historia: **el endurecimiento de seguridad dejó atrás
herramientas internas que nadie volvió a ejecutar**. Merece una frase en la
memoria, porque es un efecto colateral real y honesto de una mejora.

Además se añadió `scripts/tanda_escalado.sh`, que orquesta las tres escalas
seguidas; antes esa secuencia se hacía a mano y por tanto no quedaba registrada
en ninguna parte.

## 5. Resultados (medidos el 2026-09-15)

Máquina: 12 CPUs y 8 GB de RAM disponibles para Docker. Cada réplica de
`worker` corre con `worker_concurrency=1`, así que N réplicas son N procesos.
La CPU **no** es el factor limitante en ninguna de las escalas medidas.

### 5.1 Tabla completa

| Moléculas | Workers | Tiempo (s) | s/molécula | mol/s | *Speedup* | Eficiencia |
|---:|---:|---:|---:|---:|---:|---:|
| 100  | 1 | 156.94 | 1.5694 | 0.64 | 1.00 | 1.00 |
| 100  | 2 | 38.90  | 0.3890 | 2.57 | 4.03 | 2.02 |
| 100  | 4 | 30.48  | 0.3048 | 3.28 | 5.15 | 1.29 |
| 500  | 1 | 464.45 | 0.9289 | 1.08 | 1.00 | 1.00 |
| 500  | 2 | 208.22 | 0.4164 | 2.40 | 2.23 | 1.12 |
| 500  | 4 | 135.01 | 0.2700 | 3.70 | 3.44 | 0.86 |
| 1000 | 1 | 758.57 | 0.7586 | 1.32 | 1.00 | 1.00 |
| 1000 | 2 | 435.95 | 0.4359 | 2.29 | 1.74 | 0.87 |
| 1000 | 4 | 253.94 | 0.2539 | 3.94 | 2.99 | 0.75 |

Moléculas fallidas, **idénticas en las tres escalas** (mismo conjunto, mismo
código): 1/100, 18/500 y **35/1000 (3,5 %)**.

### 5.2 Los tres hallazgos

**(a) La tasa de error cae del 30,2 % al 3,5 %.**
En agosto, 302 de 1000 moléculas de ChEMBL acababan en `ERROR` porque RDKit no
sabía kekulizar el `.mol2` que generaba Open Babel. Con la tolerancia añadida en
`3fcc2f8`, fallan 35. Se recupera cerca del **27 % de la biblioteca**. Que el
número sea idéntico con 1, 2 y 4 *workers* confirma además que el *pipeline* es
determinista respecto al número de réplicas.

**(b) Los tiempos absolutos suben, y eso NO es una regresión.**
El lote de 1000 con 1 *worker* pasa de 722,5 s a 758,6 s. La causa es (a): antes
el 30 % de las tareas fallaba en milisegundos al cargar la molécula; ahora se
calculan de verdad sus descriptores. **El lote hace más trabajo.** Poner las dos
tandas en la misma tabla sin explicar esto haría parecer que el sistema ha
empeorado.

**(c) El $4.09\times$ de la memoria no era creíble, y el nuevo $2.99\times$ sí.**
La cifra de agosto daba una eficiencia de **1.02**: un rendimiento superlineal,
por encima del máximo teórico de 4× que permiten cuatro procesos. Eso no puede
pasar en una paralelización de este tipo, y era la señal de que algo contaminaba
la medida. La tanda nueva da una curva con la forma esperada —eficiencia
decreciente: 1.00 → 0.87 → 0.75— y eso es lo que la hace defendible.

### 5.3 Por qué la eficiencia baja: medido, no supuesto

No es contención de CPU (4 procesos sobre 12 núcleos). Es que **el benchmark
incluye una fase estrictamente secuencial**: sube las moléculas una a una con
`POST /peticiones` antes de esperar a ninguna.

Medición directa de esa fase: **0,1337 s por subida**, es decir **133,7 s para
1000 moléculas**, el **17,6 %** del tiempo con un solo *worker*.

Aplicando la ley de Amdahl con esa fracción serie $f = 0.176$:

| Workers | *Speedup* predicho | *Speedup* medido |
|---:|---:|---:|
| 2 | 1.70× | 1.74× |
| 4 | 2.62× | 2.99× |

El modelo explica la curva (el medido queda algo por encima del predicho porque
los *workers* empiezan a consumir mientras las subidas siguen en marcha, así que
parte de la fase serie se solapa con el cómputo).

**La consecuencia importante para la memoria:** ese 17,6 % es una limitación
**del medidor**, no de la plataforma. Un usuario real que hace un cribado por
lotes sube **un único SDF** y el *chord* de Celery reparte las moléculas entre
los *workers*; no hay mil subidas secuenciales. El techo de escalado que mide
este benchmark es, por tanto, pesimista respecto al caso de uso real.

### 5.4 El lote de 100 no mide paralelismo

Da eficiencias de 2.02 y 1.29, imposibles. La prueba está en que pasar de 2 a 4
*workers* solo lo mejora de 38,9 s a 30,5 s (1,28×): ya ha tocado el suelo que
imponen las 100 subidas más el sondeo. **No debería sostener ninguna
conclusión**; la memoria ya lo intuía al atribuir su $10.98\times$ a "efectos de
arranque", pero la causa concreta es esta.

### 5.5 Honestidad sobre la precisión

Hay **una sola medición por punto**. La dispersión entre lotes lo demuestra: el
*speedup* con 2 *workers* sale 2.23× con 500 moléculas y 1.74× con 1000. Para
afirmar algo más fino haría falta repetir cada punto y dar media y desviación.
Conviene decirlo en la memoria en vez de presentar estos números como exactos.

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
