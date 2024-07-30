# Configuration

The `OCM-Gear` is configured via contents of directory `cfg`.
Each (`YAML`) file contains inline documentation.
Following, a rough overview:

| Filename | Description |
| --- | --- |
| `aws.yaml` | [OPTIONAL] used for compliance-scans if s3-client is required |
| `bdba.yaml` | [OPTIONAL] used for compliance-scans and rescoring |
| `config_types.yaml` | Metadata, do not modify |
| `configs.yaml` | Structural metadata, see inline documentation |
| `container_registry.yaml` | [REQUIRED] ServiceAccounts to interact with Container Registries (OCI Registries) |
| `delivery_dashboard.yaml` | [REQUIRED] Delivery-Dashboard specific configuration like ingress-class and hostname |
| `delivery_db.yaml` | [REQUIRED] Delivery-Database specific configuration like Postgres User |
| `delivery_endpoints.yaml` | [REQUIRED] Hostnames of Delivery-Service and -Dashboard |
| `delivery_gear_extensions.yaml` | [OPTIONAL] used for available extensions, e.g. bdba-scans and issue-replicator |
| `delivery_service.yaml` | [REQUIRED] Delivery-Service specific configuration like ingress-class and hostname <br/> Also configure active features (see Section [Features](./features.md)) |
| `delivery.yaml` | [REQUIRED] Configuration of OAuth related aspects for Delivery-Service |
| `elasticsearch.yaml` | [OPTIONAL] If configured, logs certain events to Elasticsearch |
| `github.yaml` | [OPTIONAL] Required by certain features interacting with GitHub |
| `ingress.yaml` | [REQUIRED] Configure TLS ingress settings |
