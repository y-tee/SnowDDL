from typing import Any, Dict, List, Optional

from ..model import BaseModelWithConfig


class MCPServerTool(BaseModelWithConfig):
    """
    Single tool entry inside the MCP server FROM SPECIFICATION YAML body.

    Snowflake supports several `type` values for tools:
      * CORTEX_SEARCH_SERVICE_QUERY
      * CORTEX_ANALYST_MESSAGE
      * CORTEX_AGENT_RUN
      * SYSTEM_EXECUTE_SQL
      * GENERIC               (custom UDF / procedure)

    Per Snowflake docs, all tool entries share a common header (name, type,
    title, description) plus per-type optional fields. We accept everything as
    optional/free-form and serialise the YAML spec in the resolver. The
    `extra` map captures keys that are type-specific (e.g. `read_only`,
    `query_timeout`, `warehouse`, `config`, `input_schema`) without us having
    to mirror Snowflake's evolving schema field-by-field.

    See: https://docs.snowflake.com/en/sql-reference/sql/create-mcp-server
    """

    name: str
    type: str
    title: Optional[str] = None
    description: Optional[str] = None
    identifier: Optional[str] = None
    extra: Dict[str, Any] = {}
