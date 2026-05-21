#!/usr/bin/env python3
"""Inicializa el workspace de OpenSearch Dashboards para la POC de reservas.

Este script se ejecuta desde el servicio `opensearch-dashboards-init` definido en
`docker-compose.yml`. Su objetivo es dejar OpenSearch Dashboards listo para
explorar logs, trazas, service map y metricas de Prometheus sin pasos manuales en
la interfaz web.

Pasos necesarios para una inicializacion correcta:

1. OpenSearch debe estar levantado, sano y accesible por HTTPS desde la red de
   Docker. El usuario y password deben coincidir con `OPENSEARCH_USER` y
   `OPENSEARCH_PASSWORD`.
2. OpenSearch Dashboards debe arrancar con `workspace.enabled`,
   `data_source.enabled`, `explore.enabled`, `explore.discoverTraces.enabled`,
   `explore.discoverMetrics.enabled` y `datasetManagement.enabled` activados en
   `observability/opensearch-dashboards/opensearch_dashboards.yml`.
3. El workspace indicado por `OPENSEARCH_WORKSPACE_NAME` se crea si no existe,
   y despues se usan sus APIs scoped (`/w/{workspace_id}/...`) para crear los
   objetos de Discover/APM.
4. Prometheus debe ser resoluble desde el contenedor init mediante
   `PROMETHEUS_HOST` y `PROMETHEUS_PORT` para que la conexion Direct Query pueda
   apuntar al endpoint correcto.
5. Ejecutar el servicio init despues del healthcheck de Dashboards:

       docker compose up -d opensearch-dashboards-init

   En el flujo normal basta con `docker compose up -d --build`, porque Compose
   respeta el `depends_on` configurado para OpenSearch y Dashboards.

El script es idempotente en los objetos principales: primero busca data sources,
data connections, index patterns y correlations existentes, y solo crea lo que
falte. Esto permite relanzar el contenedor init despues de reinicios o cambios de
volumenes sin duplicar la configuracion.
"""

import base64
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request


BASE_URL = os.getenv("OPENSEARCH_DASHBOARDS_URL", "http://opensearch-dashboards:5601")
USERNAME = os.getenv("OPENSEARCH_USER", "admin")
PASSWORD = os.getenv("OPENSEARCH_PASSWORD", "ChangeMe_123!")
WORKSPACE_NAME = os.getenv("OPENSEARCH_WORKSPACE_NAME", "reservas_app")
OPENSEARCH_ENDPOINT = os.getenv("OPENSEARCH_ENDPOINT", "https://opensearch:9200")
PROMETHEUS_HOST = os.getenv("PROMETHEUS_HOST", "prometheus")
PROMETHEUS_PORT = os.getenv("PROMETHEUS_PORT", "9090")
WORKSPACE_FEATURES = ["use-case-observability"]
WORKSPACE_DESCRIPTION = "Reservas observability workspace"

JSON_HEADERS = {
    "Content-Type": "application/json",
    "osd-xsrf": "true",
}


def _auth_header():
    """Construye el header Basic Auth usado por todas las llamadas a Dashboards."""
    token = base64.b64encode(f"{USERNAME}:{PASSWORD}".encode("utf-8")).decode("utf-8")
    return f"Basic {token}"


def _request(method, path, payload=None, timeout=10):
    """Ejecuta una peticion HTTP contra la API de OpenSearch Dashboards.

    Devuelve siempre una tupla `(status, body)` para simplificar el flujo de
    bootstrap: los codigos 2xx y los errores HTTP se tratan de forma uniforme.
    El `body` se parsea como JSON cuando es posible y se deja en `{"raw": ...}`
    para endpoints que devuelven texto plano.
    """
    body = None
    headers = dict(JSON_HEADERS)
    headers["Authorization"] = _auth_header()

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url=f"{BASE_URL}{path}",
        data=body,
        headers=headers,
        method=method,
    )

    # Dashboards is HTTP in this setup, but this also works if switched to HTTPS.
    context = ssl._create_unverified_context()

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
            raw = resp.read().decode("utf-8")
            if not raw:
                return resp.status, {}
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                # Some Dashboards endpoints can return plain text or empty-like payloads.
                return resp.status, {"raw": raw}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8") if e.fp else ""
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return e.code, parsed


def wait_for_dashboards():
    """Espera hasta que `/api/status` indique que Dashboards esta listo.

    Aunque Compose ya espera el healthcheck del servicio, este reintento local
    hace que el script sea tolerante a arranques lentos o ejecuciones manuales.
    """
    print("Waiting for OpenSearch Dashboards...")
    for _ in range(90):
        status, _ = _request("GET", "/api/status", timeout=5)
        if status == 200:
            print("OpenSearch Dashboards is ready")
            return True
        time.sleep(2)
    print("Dashboards did not become ready in time")
    return False


def get_or_create_workspace_id():
    """Obtiene o crea el workspace configurado en `OPENSEARCH_WORKSPACE_NAME`.

    Las APIs de objetos guardados que se usan para Discover/APM son scoped al
    workspace (`/w/{workspace_id}/...`). Si la API de workspaces no esta
    disponible, se devuelve `None` y el bootstrap se detiene.
    """
    status, body = _request("POST", "/api/workspaces/_list", {})
    if status != 200:
        print(f"Workspace API not available (status={status}), skipping workspace bootstrap")
        return None

    workspaces = body.get("result", {}).get("workspaces", [])
    for ws in workspaces:
        if ws.get("name") == WORKSPACE_NAME:
            workspace_id = ws.get("id")
            print(f"Workspace already exists: {WORKSPACE_NAME} ({workspace_id})")
            ensure_observability_workspace(workspace_id, ws.get("features", []))
            return workspace_id

    payload = {
        "attributes": {
            "name": WORKSPACE_NAME,
            "description": WORKSPACE_DESCRIPTION,
            "features": WORKSPACE_FEATURES,
        }
    }
    status, body = _request("POST", "/api/workspaces", payload)
    if status == 200:
        workspace_id = body.get("result", {}).get("id")
        print(f"Created workspace: {WORKSPACE_NAME} ({workspace_id})")
        return workspace_id

    print(f"Failed creating workspace '{WORKSPACE_NAME}': status={status}, body={body}")
    return None


def ensure_observability_workspace(workspace_id, current_features):
    """Corrige workspaces creados con otro use case, por ejemplo Analytics."""
    if current_features == WORKSPACE_FEATURES:
        return

    payload = {
        "attributes": {
            "name": WORKSPACE_NAME,
            "description": WORKSPACE_DESCRIPTION,
            "features": WORKSPACE_FEATURES,
        }
    }
    status, body = _request("PUT", f"/api/workspaces/{workspace_id}", payload)
    if status == 200:
        print(f"Workspace use case set to Observability: {WORKSPACE_NAME} ({workspace_id})")
    else:
        print(f"Failed updating workspace use case: status={status}, body={body}")


def find_saved_object(workspace_id, obj_type, title):
    """Busca un saved object por tipo y titulo dentro de un workspace."""
    quoted_title = urllib.parse.quote(title)
    path = (
        f"/w/{workspace_id}/api/saved_objects/_find"
        f"?type={obj_type}&search_fields=title&search={quoted_title}&per_page=10000"
    )
    status, body = _request("GET", path)
    if status != 200:
        return None

    for obj in body.get("saved_objects", []):
        if obj.get("attributes", {}).get("title") == title:
            return obj.get("id")
    return None


def find_saved_object_global(obj_type, title, title_field="title"):
    """Busca un saved object global por tipo y campo de titulo.

    Algunos objetos, como `data-source` y `data-connection`, se crean en el
    ambito global de Dashboards y despues se asocian al workspace.
    """
    quoted_title = urllib.parse.quote(title)
    path = (
        f"/api/saved_objects/_find"
        f"?type={obj_type}&search_fields={title_field}&search={quoted_title}&per_page=10000"
    )
    status, body = _request("GET", path)
    if status != 200:
        return None

    for obj in body.get("saved_objects", []):
        if obj.get("attributes", {}).get(title_field) == title:
            return obj.get("id")
    return None


def create_index_pattern(workspace_id, title, time_field, signal_type=None, schema_mappings=None):
    """Crea o reutiliza un index pattern del workspace.

    Los index patterns indican a Discover/Explore que indices de OpenSearch debe
    consultar y que campo temporal debe usar. Para logs se anade ademas
    `signalType` y `schemaMappings`, necesarios para que Dashboards reconozca
    traceId, spanId y service.name en el formato OTEL.
    """
    existing = find_saved_object(workspace_id, "index-pattern", title)
    if existing:
        print(f"Index pattern already exists: {title}")
        return existing

    attrs = {"title": title}
    if time_field:
        attrs["timeFieldName"] = time_field
    if signal_type:
        attrs["signalType"] = signal_type
    if schema_mappings:
        attrs["schemaMappings"] = schema_mappings

    status, body = _request(
        "POST",
        f"/w/{workspace_id}/api/saved_objects/index-pattern",
        {"attributes": attrs},
    )
    if status == 200:
        _id = body.get("id")
        print(f"Created index pattern: {title} ({_id})")
        return _id

    print(f"Failed creating index pattern {title}: status={status}, body={body}")
    return None


def create_or_get_local_cluster_datasource(workspace_id):
    """Crea o reutiliza el data source `local_cluster` para OpenSearch.

    Este objeto representa el cluster OpenSearch local como fuente de datos de
    Dashboards. Se almacena de forma global y luego se asocia al workspace para
    que este pueda usarlo.
    """
    title = "local_cluster"
    # Datasource saved object is global (same pattern used by observability-stack init).
    status, body = _request(
        "GET",
        "/api/saved_objects/_find?type=data-source&search_fields=title&search=local_cluster&per_page=10000",
    )
    if status == 200:
        for obj in body.get("saved_objects", []):
            if obj.get("attributes", {}).get("title") == title:
                ds_id = obj.get("id")
                print(f"Datasource already exists: {title} ({ds_id})")
                associate_saved_object(workspace_id, "data-source", ds_id)
                return ds_id

    payload = {
        "attributes": {
            "title": title,
            "description": "Local OpenSearch cluster",
            "endpoint": OPENSEARCH_ENDPOINT,
            "auth": {
                "type": "username_password",
                "credentials": {
                    "username": USERNAME,
                    "password": PASSWORD,
                },
            },
            "dataSourceVersion": "3.6.0",
            "dataSourceEngineType": "OpenSearch",
        }
    }
    status, body = _request("POST", "/api/saved_objects/data-source", payload)
    if status == 200:
        ds_id = body.get("id")
        print(f"Created datasource: {title} ({ds_id})")
        associate_saved_object(workspace_id, "data-source", ds_id)
        return ds_id

    print(f"Failed creating datasource {title}: status={status}, body={body}")
    return None


def associate_saved_object(workspace_id, obj_type, obj_id):
    """Asocia un saved object global al workspace indicado."""
    payload = {"workspaceId": workspace_id, "savedObjects": [{"type": obj_type, "id": obj_id}]}
    status, body = _request("POST", "/api/workspaces/_associate", payload)
    if status == 200:
        print(f"Associated {obj_type}:{obj_id} with workspace {workspace_id}")
    else:
        print(f"Association failed for {obj_type}:{obj_id}: status={status}, body={body}")


def create_or_get_prometheus_dataconnection(workspace_id):
    """Crea o reutiliza la conexion Direct Query hacia Prometheus.

    La correlacion `apm-config` referencia esta conexion para que la experiencia
    APM pueda consultar metricas desde Prometheus. El endpoint se forma con
    `PROMETHEUS_HOST` y `PROMETHEUS_PORT`.
    """
    connection_name = "ObservabilityStack_Prometheus"
    existing = find_saved_object_global("data-connection", connection_name, "connectionId")
    if existing:
        print(f"Prometheus data-connection already exists: {connection_name} ({existing})")
        associate_saved_object(workspace_id, "data-connection", existing)
        return existing

    payload = {
        "name": connection_name,
        "allowedRoles": [],
        "connector": "prometheus",
        "properties": {
            "prometheus.uri": f"http://{PROMETHEUS_HOST}:{PROMETHEUS_PORT}",
            "prometheus.auth.type": "basicauth",
            "prometheus.auth.username": "",
            "prometheus.auth.password": "",
        },
    }

    status, body = _request("POST", "/api/directquery/dataconnections", payload)
    if status == 200:
        created = find_saved_object_global("data-connection", connection_name, "connectionId")
        if created:
            print(f"Created Prometheus data-connection: {connection_name} ({created})")
            associate_saved_object(workspace_id, "data-connection", created)
            return created
        print("Prometheus data-connection created but saved object id not found")
        return None

    # idempotent behavior when already exists
    body_text = json.dumps(body)
    if status == 400 and "already exists" in body_text:
        existing = find_saved_object_global("data-connection", connection_name, "connectionId")
        if existing:
            print(f"Prometheus data-connection already existed: {connection_name} ({existing})")
            associate_saved_object(workspace_id, "data-connection", existing)
            return existing

    print(f"Failed creating Prometheus data-connection: status={status}, body={body}")
    return None


def get_existing_correlation_id(workspace_id, title):
    """Devuelve el ID de una correlation existente en el workspace por titulo."""
    quoted_title = urllib.parse.quote(title)
    path = (
        f"/w/{workspace_id}/api/saved_objects/_find"
        f"?type=correlations&search_fields=title&search={quoted_title}&per_page=10000"
    )
    status, body = _request("GET", path)
    if status != 200:
        return None

    for obj in body.get("saved_objects", []):
        if obj.get("attributes", {}).get("title") == title:
            return obj.get("id")
    return None


def create_trace_to_logs_correlation(workspace_id, traces_pattern_id, logs_pattern_id):
    """Crea la correlation que permite saltar de trazas a logs relacionados.

    La correlation enlaza el index pattern de trazas (`otel-v1-apm-span*`) con el
    de logs (`logs-otel-v1*`). Dashboards usa esta relacion para buscar logs que
    compartan `traceId`/`spanId` con una traza.
    """
    title = "trace-to-logs_otel-v1-apm-span*"
    existing = get_existing_correlation_id(workspace_id, title)
    if existing:
        print(f"Trace-to-logs correlation already exists: {existing}")
        return existing

    payload = {
        "attributes": {
            "correlationType": "trace-to-logs-otel-v1-apm-span*",
            "title": title,
            "version": "1.0.0",
            "entities": [
                {"tracesDataset": {"id": "references[0].id"}},
                {"logsDataset": {"id": "references[1].id"}},
            ],
        },
        "references": [
            {"name": "entities[0].index", "type": "index-pattern", "id": traces_pattern_id},
            {"name": "entities[1].index", "type": "index-pattern", "id": logs_pattern_id},
        ],
        "workspaces": [workspace_id],
    }

    status, body = _request("POST", f"/w/{workspace_id}/api/saved_objects/correlations", payload)
    if status == 200:
        corr_id = body.get("id")
        print(f"Created trace-to-logs correlation: {corr_id}")
        return corr_id

    print(f"Failed creating trace-to-logs correlation: status={status}, body={body}")
    return None


def create_apm_config_correlation(workspace_id, traces_pattern_id, service_map_pattern_id, prom_conn_id):
    """Crea la correlation de configuracion APM del workspace.

    Esta correlation conecta tres piezas que APM necesita trabajar juntas:
    trazas, service map y la conexion a Prometheus. Si no existe conexion de
    Prometheus, se omite para evitar una configuracion parcial invalida.
    """
    if not prom_conn_id:
        print("Skipping apm-config correlation (no Prometheus data-connection id)")
        return None

    title = "apm-config"
    existing = get_existing_correlation_id(workspace_id, title)
    if existing:
        print(f"APM config correlation already exists: {existing}")
        return existing

    payload = {
        "attributes": {
            "correlationType": f"APM-Config-{workspace_id}",
            "title": title,
            "version": "1.0.0",
            "entities": [
                {"tracesDataset": {"id": "references[0].id"}},
                {"serviceMapDataset": {"id": "references[1].id"}},
                {"prometheusDataSource": {"id": "references[2].id"}},
            ],
        },
        "references": [
            {"name": "entities[0].index", "type": "index-pattern", "id": traces_pattern_id},
            {"name": "entities[1].index", "type": "index-pattern", "id": service_map_pattern_id},
            {"name": "entities[2].dataConnection", "type": "data-connection", "id": prom_conn_id},
        ],
        "workspaces": [workspace_id],
    }

    status, body = _request("POST", f"/w/{workspace_id}/api/saved_objects/correlations", payload)
    if status == 200:
        corr_id = body.get("id")
        print(f"Created apm-config correlation: {corr_id}")
        return corr_id

    print(f"Failed creating apm-config correlation: status={status}, body={body}")
    return None


def set_default_index(workspace_id, index_pattern_id):
    """Marca el index pattern de logs como indice por defecto del workspace."""
    payload = {"value": index_pattern_id}
    status, body = _request(
        "POST",
        f"/w/{workspace_id}/api/opensearch-dashboards/settings/defaultIndex",
        payload,
    )
    if status == 200:
        print(f"Default index pattern set: {index_pattern_id}")
    else:
        print(f"Failed setting default index pattern: status={status}, body={body}")


def main():
    """Orquesta el bootstrap completo del workspace de Dashboards."""
    if not wait_for_dashboards():
        return

    workspace_id = get_or_create_workspace_id()
    if not workspace_id:
        return

    create_or_get_local_cluster_datasource(workspace_id)
    prom_conn_id = create_or_get_prometheus_dataconnection(workspace_id)

    logs_schema_mappings = (
        '{"otelLogs":{"timestamp":"time","traceId":"traceId","spanId":"spanId",'
        '"serviceName":"resource.attributes.service.name"}}'
    )

    logs_id = create_index_pattern(
        workspace_id=workspace_id,
        title="logs-otel-v1*",
        time_field="time",
        signal_type="logs",
        schema_mappings=logs_schema_mappings,
    )
    traces_id = create_index_pattern(
        workspace_id=workspace_id,
        title="otel-v1-apm-span*",
        time_field="endTime",
        signal_type="traces",
    )
    service_map_id = create_index_pattern(
        workspace_id=workspace_id,
        title="otel-v2-apm-service-map*",
        time_field="timestamp",
    )

    if logs_id:
        set_default_index(workspace_id, logs_id)
    if traces_id and logs_id:
        create_trace_to_logs_correlation(workspace_id, traces_id, logs_id)
    if traces_id and service_map_id:
        create_apm_config_correlation(workspace_id, traces_id, service_map_id, prom_conn_id)

    print("Dashboards workspace bootstrap completed")


if __name__ == "__main__":
    main()
