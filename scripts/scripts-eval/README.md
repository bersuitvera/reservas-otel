# Scripts auxiliares para la evaluación experimental del capítulo 7

Estos scripts recogen datos comparables durante pruebas con Locust en las tres
ramas del laboratorio. La misma carpeta `scripts/scripts-eval` debe existir en
los escenarios A, B y C.

## Detección automática

Los scripts detectan la rama activa y cargan defaults versionados:

| Rama | Escenario | Backend | Stack |
|---|---|---|---|
| `otel-collector` | `escenario_a` | OpenSearch | OTel Collector + Data Prepper + Prometheus |
| `feat-edot-elasticsearch-dual-stack` | `escenario_b` | Elasticsearch | EDoT Collector |
| `integracion-total-elastic` | `escenario_c` | Elasticsearch | Elastic APM Server + Elastic Agent |

Defaults versionados:

```text
scripts/scripts-eval/env/escenario_a.env
scripts/scripts-eval/env/escenario_b.env
scripts/scripts-eval/env/escenario_c.env
```

El fichero `.env` de la raíz del repositorio se carga antes de los defaults para
reutilizar credenciales de Docker Compose como `ELASTIC_PASSWORD`. El fichero
`scripts/scripts-eval/.env` es opcional, local e ignorado por git. Sirve para
sobrescribir valores como `USERS`, `RUN_TIME` o `ENGINE_PASS`. Las variables ya
exportadas en la shell tienen prioridad sobre ambos ficheros `.env` y sobre los
defaults.

Si el `.env` local declara un `SCENARIO` distinto al escenario activo, se
ignoran sus claves acopladas al backend (`ENGINE_*`, `PROMETHEUS_URL` y
`CONTAINER_REGEX`) para evitar arrastrar configuración de otra rama. Los
overrides neutros como `USERS`, `RUN_TIME` o `SAMPLE_INTERVAL` se siguen
aplicando.

## Uso básico

Desde la raíz del repositorio, con el stack del escenario ya levantado:

```bash
scripts/scripts-eval/run_experiment.sh
```

También se puede forzar un escenario explícitamente:

```bash
scripts/scripts-eval/run_experiment.sh escenario_b
```

O sobrescribir valores puntuales:

```bash
USERS=100 RUN_TIME=20m scripts/scripts-eval/run_experiment.sh
```

## Scripts incluidos

| Script | Función |
|---|---|
| `run_experiment.sh` | Orquesta Locust, `docker stats`, espera de vaciado e ingesta final. |
| `monitor_docker_stats.sh` | Muestrea CPU/RAM de contenedores y genera JSONL bruto. |
| `summarize_docker_stats.py` | Convierte el JSONL de Docker en CSV de muestras y resumen. |
| `collect_indices.sh` | Consulta OpenSearch/Elasticsearch y guarda evidencias comunes/específicas. |
| `summarize_indices.py` | Genera CSV resumen de tamaño en disco y documentos indexados. |
| `summarize_backend_health.py` | Genera checks PASS/WARN/FAIL a partir de salud, stats e índices del backend. |
| `collect_prometheus_snapshot.sh` | Solo Escenario A: consultas instantáneas a Prometheus. |
| `summarize_prometheus_snapshot.py` | Resume targets, colas, fallos de exportación y métricas de ingesta Prometheus. |
| `eval_env.sh` | Detección de rama, carga de defaults y resolución estable de rutas. |
| `relacion-trace-span.sh` | Consulta spans de una traza. En B usa campos OTLP (`trace_id`, `span_id`, `parent_span_id`); en C usa campos Elastic APM/ECS (`trace.id`, `span.id`, `parent.id`). |
| `logs.sh` | Consulta logs correlacionados con una traza. En B usa `logs-*` con `trace_id`; en C usa `logs-containerlogs-*` con `trace.id`. |
| `servicios.sh` | Resume servicios observados y servicios implicados en una traza. En A agrega sobre `otel-v1-apm-span-*`, `logs-otel-v1*` y conserva service map OpenSearch si existe; en B usa campos OTLP Elastic; en C usa campos Elastic APM/ECS. |

## Variables principales

| Variable | Descripción |
|---|---|
| `SCENARIO` | Escenario activo. Se detecta desde la rama salvo override explícito. |
| `HOST` | URL del API Gateway usada por Locust y el preflight. |
| `USERS` | Usuarios concurrentes de Locust. |
| `SPAWN_RATE` | Usuarios creados por segundo. |
| `RUN_TIME` | Duración de la prueba. |
| `SAMPLE_INTERVAL` | Frecuencia de muestreo de `docker stats`, en segundos. |
| `POST_RUN_SLEEP` | Espera final para permitir indexación de telemetría pendiente. |
| `OUT_ROOT` | Directorio raíz de salida, relativo a `scripts/scripts-eval` si no es absoluto. |
| `LOCUSTFILE` | Ruta del `locustfile.py`. |
| `CONTAINER_REGEX` | Filtro de contenedores para `docker stats`. |
| `ENGINE_URL` | URL de OpenSearch o Elasticsearch. |
| `ENGINE_USER` | Usuario del backend si requiere autenticación. |
| `ENGINE_PASS` | Contraseña del backend. En B/C usa `${ELASTIC_PASSWORD:-changeme}` por defecto. |
| `ENGINE_INSECURE` | Añade `-k` a curl si vale `true`. |
| `PROMETHEUS_URL` | Solo Escenario A. Vacío en B/C para omitir Prometheus. |

## Evidencias recogidas

Siempre se guardan:

```text
engine_root.json
cluster_health.json
cluster_stats.json
nodes_stats.json
indices_stats.json
indices.json
count.json
templates.json
shards.json
nodes.json
allocation.json
thread_pool.json
indices_summary.csv
indices_total.csv
backend_health_summary.csv
backend_health_summary.json
trace_correlation.env
relacion_trace_span.json
logs_correlacionados.json
servicios.json
metadata.env
```

Además:

- Escenario A: índices `otel-v1-apm-*`, `logs-otel-v1-*` y service map. No consulta `/_cat/data_streams` porque esta variante usa índices OpenSearch para la telemetría.
- Escenario B: backing indices/data streams `.ds-traces-*`, `.ds-logs-*`, `.ds-metrics-*`.
- Escenario C: `traces-apm*`, `metrics-apm*`, `logs-containerlogs-*`, `metrics-system.*`, `metrics-docker.*`.
- Escenario A con `PROMETHEUS_URL`: snapshot de métricas Prometheus en `prometheus/`, incluyendo OTel Collector, Data Prepper, OpenSearch exporter y `prometheus_summary.csv/json`.

## Salidas generadas

Cada ejecución crea un directorio similar a:

```text
scripts/scripts-eval/results/escenario_a_20260524_120000/
├── metadata.env
├── gateway_health.json
├── locust_stats.csv
├── locust_failures.csv
├── locust_exceptions.csv
├── locust_report.html
├── docker_stats_raw.jsonl
├── docker_stats_samples.csv
├── docker_stats_summary.csv
├── indices.json
├── data_streams.json
├── count.json
├── cluster_health.json
├── cluster_stats.json
├── nodes_stats.json
├── indices_stats.json
├── indices_summary.csv
├── indices_total.csv
├── backend_health_summary.csv
├── trace_correlation.env
├── relacion_trace_span.json
├── logs_correlacionados.json
└── prometheus/
```

## Nota metodológica

El `HTTP 409` generado por el flujo de conflicto controlado debe interpretarse
como error funcional esperado, no como fallo técnico. En Locust se identifica
mediante:

```text
POST /reservations [409 esperado]
```

Para el análisis conviene separar errores esperados (`409` inducidos) de errores
no esperados (`5xx`, timeouts, conexiones fallidas o conflictos fuera del flujo
controlado).
