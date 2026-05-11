# Sistema de Reservas - Elastic + EDoT

Proyecto de ejemplo con microservicios en Python/FastAPI para gestión de salas, usuarios, reservas y notificaciones.

En esta rama (`feat-edot-elasticsearch-dual-stack`) el flujo de observabilidad activo es:

```text
App -> EDoT Collector -> Elasticsearch -> Kibana
```

## Servicios activos (compose único)

| Servicio | Puerto local | Descripción |
|---|---:|---|
| API Gateway | `8080` | Punto de entrada del flujo funcional. |
| Room Service | `8081` | Inventario de salas y consulta por id/capacidad. |
| User Service | `8082` | Consulta básica de usuarios. |
| Reservation Service | `8083` | Disponibilidad y creación de reservas. |
| Notification Service | `8084` | Consumidor de eventos desde Redis Streams. |
| Elasticsearch | `9200` | Backend de almacenamiento de telemetría OTEL. |
| Kibana | `5601` | Visualización de trazas, logs y métricas. |
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
- Kibana se autentica contra Elasticsearch con `ELASTICSEARCH_USERNAME/ELASTIC_PASSWORD`.
- Variables de entorno de ejemplo en `.env`.

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

## Nota sobre OpenSearch en esta rama

Los artefactos de OpenSearch/Data Prepper/OTel Collector en `observability/` se conservan como referencia histórica, pero **no están activos** en esta rama ni en el `docker-compose.yml` operativo.
