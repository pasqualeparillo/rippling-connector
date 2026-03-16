from databricks.labs.community_connector.pipeline import ingest
from databricks.labs.community_connector import register

# Enable the injection of connection options from Unity Catalog connections into connectors
spark.conf.set("spark.databricks.unityCatalog.connectionDfOptionInjection.enabled", "true")

# Connector source name.
source_name = "rippling"

# =============================================================================
# INGESTION PIPELINE CONFIGURATION
# =============================================================================
pipeline_spec = {
    "connection_name": "rippling-community",
    "objects": [
        {"table": {"source_table": "companies"}},
        {"table": {"source_table": "custom_fields"}},
        {"table": {"source_table": "departments"}},
        {"table": {"source_table": "employment_types"}},
        {"table": {"source_table": "leave_balances"}},
        {"table": {"source_table": "leave_requests"}},
        {"table": {"source_table": "leave_types"}},
        {"table": {"source_table": "legal_entities"}},
        {"table": {"source_table": "levels"}},
        {"table": {"source_table": "teams"}},
        {"table": {"source_table": "tracks"}},
        {"table": {"source_table": "users"}},
        {"table": {"source_table": "work_locations"}},
        {"table": {"source_table": "workers"}},
    ],
}

# Dynamically import and register the LakeFlow source
register(spark, source_name)

# Ingest the tables specified in the pipeline spec
ingest(spark, pipeline_spec)
