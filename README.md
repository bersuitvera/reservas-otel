# Sistema de Reservas - Elastic Observability

Proyecto de ejemplo con microservicios Python/FastAPI para gestión de salas, usuarios, reservas y notificaciones.
La observabilidad de la POC está orientada a Elastic APM + Elasticsearch + Kibana + Elastic Agent.

## Objetivo de esta rama

Esta rama (`integracion-total-elastic`) prioriza una POC estable y coherente con el stack Elastic:

- Trazas y métricas de aplicación con Elastic APM Python Agent.
- Logs de aplicación en formato ECS JSON.
- Ingesta de logs de contenedores y métricas de infraestructura con Elastic Agent (standalone).

## Componentes y puertos

| Componente | Puerto | Uso |
|---|---:|---|
| API Gateway | `8080` | Punto de entrada del flujo funcional. |
| Room Service | `8081` | Catálogo de salas. |
| User Service | `8082` | Validación de usuarios. |
| Reservation Service | `8083` | Disponibilidad y creación de reservas. |
| Notification Service | `8084` | Consumo asíncrono de eventos. |
| Elasticsearch | `9200` | Almacenamiento de telemetría. |
| Kibana | `5601` | UI de observabilidad. |
| APM intake | `8200` | Entrada para agentes APM Python. |
| PostgreSQL | `5432` | Persistencia funcional. |
| Redis | `6379` | Bus de eventos. |

## Arranque rápido

1. Levantar stack completo:

```bash
docker compose -f docker-compose.yml -f docker-compose.elastic.yml up -d --build
```

2. Parar stack completo:

```bash
docker compose -f docker-compose.yml -f docker-compose.elastic.yml down --remove-orphans
```

3. Ver logs del agente:

```bash
docker compose -f docker-compose.yml -f docker-compose.elastic.yml logs -f elastic-agent
```

## Variables importantes

Archivo `.env`:

- `KIBANA_SERVICE_TOKEN`: token del service account de Kibana.

Variables que inyecta `docker-compose.elastic.yml` en servicios:

- `ELASTIC_APM_SERVER_URL`
- `ELASTIC_APM_SERVICE_NAME`
- `ELASTIC_APM_SERVICE_VERSION`
- `ELASTIC_APM_ENVIRONMENT`
- `ELASTIC_APM_ENABLE_LOG_CORRELATION`

Credenciales usadas en la POC local:

- `ELASTIC_PASSWORD` (por defecto `changeme`)
- `ELASTICSEARCH_USERNAME` (por defecto `elastic`)

## Ficheros de configuración Elastic

### `docker-compose.elastic.yml`

Define los servicios de observabilidad de la POC:

- `elasticsearch` con seguridad habilitada.
- `kibana` autenticado mediante `ELASTICSEARCH_SERVICEACCOUNTTOKEN`.
- `apm-server` para intake de agentes APM Python.
- `elastic-agent` standalone para logs de contenedor y métricas de infraestructura.

Además sobreescribe variables de cada microservicio para activar APM.

### `observability/apm-server/apm-server.yml`

Configura APM Server con:

- `host: 0.0.0.0:8200`
- salida `output.elasticsearch` hacia `elasticsearch:9200`

Notas de la POC:

- Se mantiene `anonymous.enabled: true` para simplicidad en laboratorio.
- En productivo conviene token/API key y TLS extremo a extremo.

### `observability/elastic-agent/elastic-agent.yml`

Configura Elastic Agent standalone:

- `outputs.default` contra Elasticsearch.
- Input `filestream` para logs Docker en `/var/lib/docker/containers/*/*-json.log`.
- Parser de contenedor y `decode_json_fields` para aprovechar el JSON ECS emitido por la app.
- Input `system/metrics` para `cpu`, `memory`, `network`, `filesystem`.
- Input `docker/metrics` para métricas por contenedor (cpu, memory, network, diskio, container).

### `services/common/apm.py`

Bootstrap común por servicio:

- `elasticapm.instrument()` (auto-instrumentación compatible).
- Middleware `ElasticAPM` para FastAPI/Starlette.
- Configuración por variables `ELASTIC_APM_*`.

### `services/common/logger.py`

Logging unificado de aplicación:

- `ecs_logging.StdlibFormatter()`.
- Salida JSON por `stdout`.
- Campos de servicio y entorno para facilitar consulta/correlación en Kibana.

## Flujo funcional de negocio

1. `api-gateway` valida usuario en `user-service`.
2. `api-gateway` delega reserva en `reservation-service`.
3. `reservation-service` valida sala en `room-service`.
4. Si hay hueco, persiste reserva en PostgreSQL.
5. Publica evento en Redis stream `events`.
6. `notification-service` consume y procesa el evento.

## Comprobaciones en Kibana

Después de ejecutar `scripts/test-services.sh`, validar:

- APM > Services: aparecen 5 servicios.
- APM > Traces: traza `POST /reservations` con casos `200` y `409`.
- Logs/Discover: entradas con `service.name`, `trace.id` y `span.id`.
- Data streams esperados:
  - `traces-apm*`
  - `metrics-apm*`
  - `logs-containerlogs-*`
  - `metrics-system.*`
  - `metrics-docker.*`

## Decisión de arquitectura en esta POC

Sobre si usar APM gestionado por Fleet: sí es una opción más completa para operación centralizada.
Para esta POC se mantiene APM Server standalone + Elastic Agent standalone porque:

- reduce complejidad operativa inicial,
- acelera pruebas funcionales,
- mantiene la rama estable para comparativas.

Cuando la POC cierre, el siguiente paso natural es migrar a Fleet-managed para políticas centralizadas.

## Tests

### Smoke test E2E

```bash
bash scripts/test-services.sh
```

Opcionales:

```bash
TEST_DAY=2026-05-04 bash scripts/test-services.sh
BASE_URL_GATEWAY=http://localhost:8080 bash scripts/test-services.sh
```

### Unit tests Python

```bash
python3 -m pip install -r services/common/requirements.txt -r services/requirements-dev.txt
pytest -q services/tests
```

## Troubleshooting rápido

- Si `down` no para todo, usar ambos archivos compose y `--remove-orphans`.
- Si Kibana no arranca, revisar `KIBANA_SERVICE_TOKEN` en `.env`.
- Si no ves logs, revisar:
  - `docker compose ... logs elastic-agent`
  - montaje `/var/lib/docker/containers` en `elastic-agent`
  - que la app esté emitiendo logs en JSON ECS.
