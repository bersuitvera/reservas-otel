# AGENTS.md

## Propósito del repositorio

Este repositorio es un laboratorio de observabilidad basado en microservicios Python/FastAPI. Su finalidad es comparar tres escenarios arquitectónicos distintos de instrumentación, trazabilidad, logging y métricas:

- **Escenario A:** OpenSearch OTel-native.
- **Escenario B:** Elastic híbrido con EDoT.
- **Escenario C:** Elastic integrado.

No es una aplicación de negocio tradicional. Es una **POC didáctica, técnica y comparativa**. La claridad arquitectónica y la conservación de los escenarios son más importantes que la simplificación automática del código.

---

## Regla principal para agentes

Antes de modificar, mover o eliminar cualquier archivo, servicio, volumen, pipeline o configuración, el agente debe entender:

1. La rama actual.
2. El escenario conceptual asociado a esa rama.
3. El flujo funcional de negocio.
4. El flujo de observabilidad.
5. Qué piezas son específicas del escenario activo.

No deben borrarse componentes porque parezcan duplicados, antiguos, residuales o redundantes sin comprobar antes si forman parte de uno de los escenarios.

---

## Mapa de escenarios y ramas

Cada rama representa un escenario conceptual distinto. No son ramas equivalentes ni deben unificarse automáticamente.

| Escenario | Rama | Concepto | Stack principal |
|---|---|---|---|
| A | `otel-collector` | OpenSearch OTel-native | FastAPI → OTel Collector → Data Prepper → OpenSearch/OpenSearch Dashboards + Prometheus |
| B | `feat-edot-elasticsearch-dual-stack` | Elastic híbrido con EDoT | FastAPI → EDoT Collector → Elasticsearch → Kibana |
| C | `integracion-total-elastic` | Elastic integrado | FastAPI + Elastic APM Agent → APM Server → Elasticsearch/Kibana + Elastic Agent |

---

## Filosofía de ramas

Este repositorio es **comparativo, no evolutivo**.

Las ramas no representan simplemente versiones sucesivas de una misma solución. Representan tres formas diferentes de resolver la observabilidad de la misma arquitectura de microservicios.

Por tanto:

- No se debe “normalizar” una rama para que se parezca a otra.
- No se deben copiar servicios de una rama a otra sin una razón explícita.
- No se deben eliminar piezas de observabilidad solo porque en otra rama no existan.
- No se debe asumir que `observability/` tiene el mismo significado en todas las ramas.
- La fuente de verdad de cada escenario es siempre la combinación de:

```text
nombre de rama + README.md + docker-compose.yml
```

## Definición de terminado

Una tarea solo se considera terminada cuando el agente ha indicado:

1. Rama activa detectada.
2. Escenario identificado.
3. Archivos modificados.
4. Motivo de cada cambio.
5. Comandos ejecutados.
6. Resultado de tests o validaciones.
7. Evidencias pendientes, si no se han podido comprobar visualmente.

---

## Escenario A: OpenSearch OTel-native

### Rama

```text
otel-collector
```

### Objetivo

Demostrar una arquitectura basada en OpenTelemetry estándar, OTel Collector, Data Prepper, OpenSearch, OpenSearch Dashboards y Prometheus.

Este escenario prioriza una aproximación OTel-native con backend OpenSearch.

### Flujo conceptual

```text
Microservicios FastAPI
  → OTel Collector
  → Data Prepper
  → OpenSearch
  → OpenSearch Dashboards

Métricas:
Microservicios / Collector / Data Prepper
  → Prometheus
```

### Componentes esperados

- Microservicios FastAPI.
- OTel Collector.
- Data Prepper.
- OpenSearch.
- OpenSearch Dashboards.
- Prometheus.
- Redis.
- PostgreSQL.

### Reglas específicas

En esta rama:

- Mantener `otel-collector`.
- Mantener `data-prepper`.
- Mantener `opensearch`.
- Mantener `opensearch-dashboards`.
- Mantener `prometheus`.
- Mantener la exportación OTLP desde los servicios.
- Mantener la configuración de trazas, logs y métricas compatible con OpenSearch/Data Prepper.

No hacer:

- No sustituir OpenSearch por Elasticsearch.
- No sustituir Data Prepper por APM Server.
- No añadir Elastic Agent como pieza central.
- No eliminar Collector porque parezca intermediario.
- No convertir esta rama en un escenario Elastic.

---

## Escenario B: Elastic híbrido con EDoT

### Rama

```text
feat-edot-elasticsearch-dual-stack
```

### Objetivo

Probar Elastic usando EDoT Collector como puente OTLP hacia Elasticsearch/Kibana, manteniendo instrumentación basada en OpenTelemetry en la aplicación.

Este escenario es híbrido porque conserva la lógica OpenTelemetry en los servicios, pero cambia el backend hacia Elastic.

### Flujo conceptual

```text
Microservicios FastAPI
  → EDoT Collector
  → Elasticsearch
  → Kibana
```

### Componentes esperados

- Microservicios FastAPI.
- EDoT Collector.
- Elasticsearch.
- Kibana.
- Redis.
- PostgreSQL.

### Reglas específicas

En esta rama:

- Mantener `edot-collector`.
- Mantener exportación OTLP desde los servicios.
- Mantener Elasticsearch como backend.
- Mantener Kibana como interfaz de visualización.
- Mantener la idea de puente entre OpenTelemetry y Elastic.

No hacer:

- No sustituir EDoT Collector por OTel Collector genérico sin justificarlo.
- No introducir APM Server como pieza central si no forma parte del diseño de la rama.
- No reactivar Data Prepper u OpenSearch por similitud con el escenario A.
- No convertir esta rama en Elastic integrado.

---

## Escenario C: Elastic integrado

### Rama

```text
integracion-total-elastic
```

### Objetivo

Representar una integración más nativa con el ecosistema Elastic, usando Elastic APM Python Agent, APM Server, Elasticsearch, Kibana y Elastic Agent.

Este escenario prioriza la integración propia de Elastic frente a una arquitectura OpenTelemetry pura.

### Flujo conceptual

```text
Microservicios FastAPI
  → Elastic APM Python Agent
  → APM Server
  → Elasticsearch
  → Kibana

Elastic Agent
  → logs de contenedores
  → métricas de infraestructura
  → Elasticsearch
```

### Componentes esperados

- Microservicios FastAPI.
- Elastic APM Python Agent.
- APM Server.
- Elasticsearch.
- Kibana.
- Elastic Agent.
- Logs ECS JSON.
- Redis.
- PostgreSQL.

### Reglas específicas

En esta rama:

- Mantener `apm-server`.
- Mantener `elastic-agent`.
- Mantener `services/common/apm.py` si existe.
- Mantener logs estructurados compatibles con ECS.
- Mantener la integración nativa Elastic.

No hacer:

- No añadir OTel Collector como pieza central.
- No añadir EDoT Collector como pieza central.
- No reintroducir OpenSearch.
- No reintroducir Data Prepper.
- No eliminar APM Server ni Elastic Agent por considerarlos sustituibles.

---

## Regla crítica al cambiar de rama

Cada cambio de rama implica un cambio de arquitectura.

Antes de editar, ejecutar:

```bash
git branch --show-current
```

Después:

1. Identificar el escenario activo.
2. Leer el `README.md` de esa rama.
3. Revisar `docker-compose.yml`.
4. Revisar los servicios activos.
5. Revisar la carpeta `observability/`, sin asumir que todo lo que contiene está activo.
6. Confirmar qué backend de observabilidad se está usando.
7. Evitar copiar configuraciones de otra rama salvo que se solicite explícitamente.

---

## Regla anti-confusión

La carpeta `observability/` puede contener configuraciones relacionadas con distintos enfoques.

No debe asumirse que todo lo presente en `observability/` está en uso en la rama actual.

La fuente de verdad es:

```text
README.md
+ docker-compose.yml
+ nombre de rama
```

---

## Estructura funcional habitual del repositorio

### Raíz

- `README.md`: documentación principal de la rama actual.
- `docker-compose.yml`: definición operativa del escenario activo.
- `AGENTS.md`: instrucciones para agentes automáticos.
- `scripts/`: scripts auxiliares, pruebas de smoke test o validación.
- `services/`: microservicios y código compartido.
- `observability/`: configuraciones de observabilidad.

### Microservicios

La arquitectura funcional se basa habitualmente en los siguientes servicios:

- `api-gateway`: punto de entrada funcional.
- `user-service`: validación o consulta de usuarios.
- `room-service`: catálogo o disponibilidad de salas.
- `reservation-service`: lógica principal de reservas.
- `notification-service`: consumo de eventos asíncronos.

### Código compartido

- `services/common/otel.py`: bootstrap común de OpenTelemetry cuando aplica.
- `services/common/logger.py`: logging estructurado y correlación con trazas.
- `services/common/apm.py`: integración Elastic APM cuando aplica.

No todos los archivos compartidos son igual de relevantes en todos los escenarios. Antes de eliminarlos, comprobar si pertenecen al escenario activo o a otra rama.

---

## Flujo funcional de negocio esperado

Aunque la observabilidad cambia por rama, el flujo de negocio debe mantenerse estable:

1. `api-gateway` recibe una petición de reserva.
2. Se valida el usuario mediante `user-service`.
3. Se consulta la sala mediante `room-service`.
4. `reservation-service` comprueba disponibilidad.
5. Se persiste la reserva en PostgreSQL.
6. Se publica un evento en Redis.
7. `notification-service` consume el evento.
8. La traza distribuida debe permitir seguir el flujo completo.

No romper este flujo al modificar observabilidad.

---

## Observabilidad esperada

Todos los escenarios deben conservar, de una forma u otra:

- Trazas distribuidas.
- Logs estructurados.
- Correlación entre logs y trazas.
- Métricas de aplicación o infraestructura.
- Visibilidad del flujo de reserva.

La implementación concreta cambia según la rama.

---

## Spans y atributos de negocio

Cuando se use OpenTelemetry o instrumentación manual equivalente, deben conservarse los spans de negocio relevantes, por ejemplo:

- `reservation.flow.create`
- `reservation.validate.user`
- `reservation.validate.room`
- `reservation.check.availability`
- `reservation.persist.confirmed`
- `reservation.event.publish`
- `notification.consume.reservation_created`

Los atributos de negocio deben usar preferentemente el prefijo:

```text
app_*
```

Ejemplos:

- `app.user_id`
- `app.room_id`
- `app.reservation_id`
- `app.reservation.status`
- `app.event.type`

---

## Propagación de contexto

Cuando existan eventos asíncronos mediante Redis, debe mantenerse la propagación de contexto de trazas.

Si se usa OpenTelemetry, conservar campos como:

```text
trace.traceparent
```

No eliminar metadatos de trazabilidad en eventos Redis sin comprobar el impacto en la traza distribuida.

---

## Convenciones obligatorias

- Mantener nombres de servicios coherentes con `docker-compose.yml`.
- No cambiar endpoints públicos sin actualizar documentación y tests.
- No romper el flujo principal por `api-gateway`.
- Mantener correlación entre logs y trazas.
- Mantener los nombres de servicio consistentes entre aplicación y backend de observabilidad.
- Mantener variables de entorno necesarias para instrumentación.
- No eliminar healthchecks sin revisar dependencias.
- No cambiar puertos sin actualizar documentación, scripts y pruebas.

---

## Archivos y carpetas sensibles

No borrar ni modificar sin justificación clara:

- `docker-compose.yml`
- `README.md`
- `services/common/otel.py`
- `services/common/logger.py`
- `services/common/apm.py`
- `services/tests/`
- `scripts/test-services.sh`
- `observability/otel-collector/`
- `observability/data-prepper/`
- `observability/prometheus/`
- `observability/opensearch-dashboards/`
- Configuración de Elasticsearch/Kibana cuando corresponda.
- Configuración de APM Server cuando corresponda.
- Configuración de Elastic Agent cuando corresponda.

Antes de eliminar cualquier archivo de observabilidad, buscar referencias en:

```bash
grep -R "nombre-del-servicio-o-archivo" .
```

---

## Validación antes de cerrar cambios

### Tests unitarios

Desde la carpeta de servicios, si aplica:

```bash
cd services
pytest -q
```

Si el repositorio usa requirements específicos:

```bash
python3 -m pip install -r common/requirements.txt -r requirements-dev.txt
pytest -q tests
```

### Levantar entorno completo

Desde la raíz del repositorio:

```bash
docker compose up -d --build
```

### Smoke test

Si existe el script:

```bash
bash scripts/test-services.sh
```

### Comprobaciones mínimas

Verificar que:

- Una reserva válida responde correctamente.
- Una reserva duplicada o conflictiva responde con error controlado.
- Los servicios principales levantan.
- El backend de observabilidad del escenario activo levanta.
- Las trazas aparecen en el backend correspondiente.
- Los logs mantienen correlación con trazas.
- Las métricas siguen disponibles si forman parte del escenario.

---

## Puertos habituales

Los puertos pueden variar por rama, pero habitualmente:

- API Gateway: `8080`
- Room Service: `8081`
- User Service: `8082`
- Reservation Service: `8083`
- Notification Service: `8084`
- OpenSearch: `9200`
- OpenSearch Dashboards: `5601`
- Elasticsearch: `9200`
- Kibana: `5601`
- Prometheus: `9090`
- OTel Collector OTLP gRPC: `4317`
- OTel Collector OTLP HTTP: `4318`
- OTel Collector metrics: `8888`
- Data Prepper API: `4900`
- Data Prepper OTLP gRPC: `21890`
- APM Server: `8200`

No cambiar puertos sin actualizar documentación, scripts y referencias internas.

---

## Criterio de edición para agentes

Los cambios deben ser:

- Pequeños.
- Explicables.
- Reversibles.
- Coherentes con el escenario activo.

Antes de eliminar código:

1. Buscar referencias.
2. Verificar si participa en trazas, logs o métricas.
3. Verificar si participa en tests.
4. Verificar si está referenciado en `docker-compose.yml`.
5. Verificar si aparece en el `README.md`.
6. Confirmar que no es una pieza específica del escenario.

---

## Qué no debe hacer un agente

Un agente no debe:

- Unificar los tres escenarios.
- Convertir OpenSearch en Elastic sin petición explícita.
- Convertir Elastic integrado en OpenTelemetry puro sin petición explícita.
- Eliminar Collector, Data Prepper, APM Server o Elastic Agent por considerarlos intercambiables.
- Borrar configuraciones de observabilidad sin comprobar si pertenecen a otra rama.
- Cambiar nombres de servicio sin actualizar el backend de observabilidad.
- Simplificar el laboratorio hasta perder valor comparativo.
- Hacer refactors amplios sin necesidad.
- Introducir dependencias nuevas sin justificarlo.

---

## Qué sí debe hacer un agente

Un agente debe:

- Identificar la rama antes de actuar.
- Respetar el escenario conceptual.
- Mantener la aplicación funcional.
- Mantener la observabilidad funcional.
- Actualizar documentación si cambia arquitectura, puertos o servicios.
- Añadir comentarios cuando una decisión pueda parecer extraña pero sea necesaria para el escenario.
- Preferir cambios locales antes que refactors globales.
- Validar con tests y smoke test siempre que sea posible.

---

## Resumen mental rápido

```text
Rama otel-collector
  = OpenSearch OTel-native
  = OTel Collector + Data Prepper + OpenSearch + Prometheus

Rama feat-edot-elasticsearch-dual-stack
  = Elastic híbrido
  = EDoT Collector + Elasticsearch + Kibana

Rama integracion-total-elastic
  = Elastic integrado
  = Elastic APM Agent + APM Server + Elastic Agent
```

---

## Regla final

Este repositorio cuenta tres historias técnicas distintas.

No borres piezas porque no encajen con otra rama.
No mezcles escenarios.
No simplifiques perdiendo valor didáctico.

Primero identifica el escenario. Después modifica.




## Formato de respuesta esperado

Al finalizar una intervención, responder siempre con:

- Escenario detectado.
- Cambios realizados.
- Archivos modificados.
- Validaciones ejecutadas.
- Riesgos o comprobaciones pendientes.

No afirmar que algo funciona si no se ha probado.