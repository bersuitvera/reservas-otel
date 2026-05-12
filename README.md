# Sistema de Reservas - Elastic + EDoT

Proyecto de ejemplo con microservicios en Python/FastAPI para gestión de salas, usuarios, reservas y notificaciones.

En esta rama (`feat-edot-elasticsearch-dual-stack`) el flujo de observabilidad activo es:

```text
App -> EDoT Collector -> Elasticsearch -> Kibana
```

## Servicios activos (compose único)

El `docker-compose.yml` operativo solo declara servicios de aplicación, PostgreSQL, Redis, Elasticsearch, Kibana, `kibana-setup` y `edot-collector`.

| Servicio | Puerto local | Descripción |
|---|---:|---|
| API Gateway | `8080` | Punto de entrada del flujo funcional. |
| Room Service | `8081` | Inventario de salas y consulta por id/capacidad. |
| User Service | `8082` | Consulta básica de usuarios. |
| Reservation Service | `8083` | Disponibilidad y creación de reservas. |
| Notification Service | `8084` | Consumidor de eventos desde Redis Streams. |
| Elasticsearch | `9200` | Backend de almacenamiento de telemetría OTEL. |
| Kibana | `5601` | Visualización de trazas, logs y métricas. |
| Kibana Setup | n/a | Genera el service account token y `kibana.yml`. |
| EDoT Collector OTLP gRPC | `4317` | Receiver OTLP gRPC. |
| EDoT Collector OTLP HTTP | `4318` | Receiver OTLP HTTP. |
| PostgreSQL | `5432` | Persistencia de salas y reservas. |
| Redis | `6379` | Bus de eventos para notificaciones. |

## Arquitectura de observabilidad

```text
[Microservicios FastAPI]
    |
    | OTLP (traces/logs/metrics)
    v
[EDoT Collector]
    |
    | Exporter Elasticsearch (mapping OTEL)
    v
[Elasticsearch]
    |
    v
[Kibana]
```

## Mejoras de integración aplicadas (5)

1. **`elasticapm` processor + connector en EDoT**  
   Se añadió `elasticapm` para enriquecer trazas y generar métricas agregadas APM compatibles con vistas de servicio.

2. **Pipelines de métricas separadas**  
   - `metrics/app`: métricas OTLP de la aplicación.  
   - `metrics/aggregated-apm`: métricas derivadas desde `elasticapm`.

3. **Robustez de exportación a Elasticsearch**  
   El exporter `elasticsearch` ahora usa `sending_queue` para tolerancia a picos y desacople de envío.

4. **Saneado de atributos sensibles**  
   Se incorpora `attributes/sanitize` para eliminar campos sensibles o de alta cardinalidad antes de indexar.

5. **Temporality de métricas alineada con Elastic**  
   Se fuerza temporality delta para histogramas/contadores en la app (`services/common/otel.py`) y se mantiene `cumulativetodelta` en collector para compatibilidad.

### Nota operativa

- El warning de exemplars no bloquea ingestión de trazas/logs/métricas principales en este piloto.
- Configuración activa EDoT: [config.yaml](/home/avr12s/repos/github/reservas-otel/observability/edot-collector/config.yaml)

## Levantar el entorno

```bash
docker compose up -d --build
```

Este es el **único** comando operativo de despliegue en esta rama.

## Telemetría OTLP en la app

Todos los servicios de aplicación publican hacia `edot-collector`:

- `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://edot-collector:4318/v1/traces`
- `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=http://edot-collector:4318/v1/logs`
- `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://edot-collector:4318/v1/metrics`

## Seguridad

- Elasticsearch se ejecuta con `xpack.security.enabled=true`.
- `kibana-setup` crea un service account token para `elastic/kibana` con la API de Elasticsearch y genera el `kibana.yml` que usa Kibana.
- Kibana se autentica contra Elasticsearch con `elasticsearch.serviceAccountToken`, evitando el uso del superusuario `elastic` como usuario interno de Kibana.
- Docker Compose lee las variables desde un `.env` local no versionado.

Variables mínimas esperadas:

```dotenv
ELASTICSEARCH_USERNAME=elastic
ELASTIC_PASSWORD=<password-local>
KIBANA_ENCRYPTED_SAVED_OBJECTS_KEY=<clave-32-caracteres-o-mas>
KIBANA_SECURITY_ENCRYPTION_KEY=<clave-32-caracteres-o-mas>
KIBANA_REPORTING_ENCRYPTION_KEY=<clave-32-caracteres-o-mas>
```

## ¿Hace falta APM Server?

No en esta rama. El flujo activo es `App -> EDoT -> Elasticsearch -> Kibana`; EDoT exporta directamente a Elasticsearch y Kibana consume los data streams APM/OTEL resultantes.

## Smoke test funcional

Script incluido:

```bash
bash scripts/test-services.sh
```

Valida healthchecks y flujo funcional de reserva (`200`) + conflicto duplicado (`409`).

## Verificación rápida de ingestión

Ejemplos:

```bash
curl -s -u elastic:${ELASTIC_PASSWORD} 'http://localhost:9200/_cat/indices?v&s=index'
curl -s -u elastic:${ELASTIC_PASSWORD} 'http://localhost:9200/.ds-traces-*/_search?size=1&sort=@timestamp:desc'
curl -s -u elastic:${ELASTIC_PASSWORD} 'http://localhost:9200/.ds-logs-*/_search?size=1&sort=@timestamp:desc'
curl -s -u elastic:${ELASTIC_PASSWORD} 'http://localhost:9200/.ds-metrics-*/_search?size=1&sort=@timestamp:desc'
```

## Nota sobre `observability/`

El directorio `observability/` conserva configuraciones usadas por otras ramas del laboratorio. En esta rama no se activan por estar presentes en esa carpeta: el escenario operativo lo define el `docker-compose.yml`, que levanta Elasticsearch, Kibana y `edot-collector` con `observability/edot-collector/config.yaml`.
