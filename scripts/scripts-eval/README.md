# Scripts auxiliares para la evaluación experimental del capítulo 7

Estos scripts ayudan a recoger datos comparables durante las pruebas con Locust.

La idea de uso es:

1. Levantar un escenario concreto del repositorio.
2. Verificar que el API Gateway responde en `http://localhost:8080/health`.
3. Revisar `scripts/scripts-eval/.env`.
4. Ejecutar `scripts/scripts-eval/run_experiment.sh`.
5. Analizar los CSV/JSON generados en `scripts/scripts-eval/results/<escenario>_<timestamp>/`.

Todos los scripts Bash de esta carpeta cargan `scripts/scripts-eval/.env` al
arrancar. Si una variable ya está exportada en la shell, esa variable tiene
prioridad sobre el valor del `.env`.

## Scripts incluidos

| Script | Función |
|---|---|
| `run_experiment.sh` | Orquesta una prueba completa: lanza Locust, muestrea `docker stats`, espera el vaciado del pipeline y recoge índices/data streams. |
| `monitor_docker_stats.sh` | Muestrea CPU/RAM de contenedores durante la prueba y genera JSONL bruto. |
| `summarize_docker_stats.py` | Convierte el JSONL de Docker en CSV de muestras y CSV resumen. |
| `collect_indices.sh` | Consulta OpenSearch/Elasticsearch mediante APIs REST y guarda índices, data streams, conteos y estado del clúster. |
| `summarize_indices.py` | Genera CSV resumen de tamaño en disco y documentos indexados. |
| `collect_prometheus_snapshot.sh` | Opcional para Escenario A: lanza consultas instantáneas a Prometheus. |
| `.env` | Variables comunes de evaluación. Se carga automáticamente por el runner y auxiliares. |
| `eval_env.sh` | Carga común del `.env` y resolución estable de rutas. |

## Uso básico

Desde la raíz del repositorio, con el stack ya levantado:

```bash
scripts/scripts-eval/run_experiment.sh
```

El escenario por defecto está definido en `.env` como `SCENARIO=escenario_a`.
También puedes sobrescribir valores puntuales sin editar el fichero:

```bash
USERS=100 RUN_TIME=20m scripts/scripts-eval/run_experiment.sh escenario_a
```

## Ejemplo por escenario

### Escenario A: OpenSearch OTel-native

```bash
scripts/scripts-eval/run_experiment.sh escenario_a
```

El `.env` incluido ya usa los valores esperados para esta rama:
`ENGINE_URL=https://localhost:9200`, credenciales `admin/ChangeMe_123!`,
`ENGINE_INSECURE=true`, `PROMETHEUS_URL=http://localhost:9090` y filtro de
contenedores para microservicios, PostgreSQL, Redis, OTel Collector, Data Prepper,
OpenSearch, OpenSearch Dashboards, Prometheus y exporter.

### Escenario B: Elastic híbrido con EDOT

```bash
export ENGINE_URL="http://localhost:9200"
export CONTAINER_REGEX="edot|elasticsearch|kibana"

scripts/scripts-eval/run_experiment.sh escenario_b
```

Si Elasticsearch usa autenticación:

```bash
export ENGINE_URL="https://localhost:9200"
export ENGINE_USER="elastic"
export ENGINE_PASS="TU_PASSWORD"
export ENGINE_INSECURE="true"
```

### Escenario C: Elastic integrado

```bash
export ENGINE_URL="http://localhost:9200"
export CONTAINER_REGEX="elasticsearch|kibana|apm|elastic-agent"

scripts/scripts-eval/run_experiment.sh escenario_c
```

## Variables principales

| Variable | Valor por defecto | Descripción |
|---|---:|---|
| `SCENARIO` | `escenario_a` | Nombre metodológico del escenario si no se pasa argumento al runner. |
| `HOST` | `http://localhost:8080` | URL del API Gateway usada por Locust y el preflight. |
| `USERS` | `50` | Usuarios concurrentes de Locust. |
| `SPAWN_RATE` | `5` | Usuarios creados por segundo. |
| `RUN_TIME` | `10m` | Duración de la prueba. |
| `SAMPLE_INTERVAL` | `5` | Frecuencia de muestreo de `docker stats`, en segundos. |
| `POST_RUN_SLEEP` | `30` | Espera final para permitir que collectors/APM Server indexen datos pendientes. |
| `OUT_ROOT` | `results` | Directorio raíz de salida. Si es relativo, se resuelve contra `scripts/scripts-eval`. |
| `LOCUSTFILE` | `locustfile.py` | Ruta del `locustfile.py`. Si es relativa, se resuelve contra `scripts/scripts-eval`. |
| `CONTAINER_REGEX` | escenario A | Filtro opcional sobre nombres de contenedores. Vacío muestrea todos. |
| `ENGINE_URL` | `https://localhost:9200` | URL de OpenSearch o Elasticsearch. |
| `ENGINE_USER` | `admin` | Usuario si el motor requiere autenticación. |
| `ENGINE_PASS` | `ChangeMe_123!` | Contraseña si el motor requiere autenticación. |
| `ENGINE_INSECURE` | `true` | Añade `-k` a curl para certificados autofirmados. |
| `PROMETHEUS_URL` | `http://localhost:9090` | URL de Prometheus para Escenario A. |
| `EVAL_ENV_FILE` | `scripts/scripts-eval/.env` | Ruta alternativa de configuración dotenv. |

## Salidas generadas

Cada ejecución crea un directorio similar a:

```text
scripts/scripts-eval/results/escenario_a_20260524_120000/
├── metadata.env
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
├── indices_summary.csv
├── indices_total.csv
└── prometheus/
```

## Nota metodológica

El `HTTP 409` generado por el flujo de conflicto controlado debe interpretarse como error funcional esperado, no como fallo técnico. En Locust se identifica mediante el nombre:

```text
POST /reservations [409 esperado]
```

Para el análisis del TFG conviene separar:
- errores esperados: `409` inducidos deliberadamente;
- errores no esperados: `5xx`, timeouts, conexiones fallidas o `409` fuera del flujo de conflicto.
