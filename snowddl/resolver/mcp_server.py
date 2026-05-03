from typing import Any, Dict, List

import yaml

from snowddl.blueprint import MCPServerBlueprint, MCPServerTool
from snowddl.resolver.abc_schema_object_resolver import AbstractSchemaObjectResolver, ResolveResult, ObjectType


class MCPServerResolver(AbstractSchemaObjectResolver):
    """
    Resolver for Snowflake-managed MCP servers (Cortex Agents).

    The Snowflake DDL is:

        CREATE [OR REPLACE] MCP SERVER <db>.<schema>.<name>
        FROM SPECIFICATION $$<yaml>$$
        [COMMENT = '...']

    The YAML body's structure is opaque to SnowDDL beyond `tools:` — we
    rebuild it from the parsed blueprint each apply, then CREATE OR REPLACE if
    it changed (matching the SemanticView resolver's strategy, since there is
    no granular ALTER MCP SERVER for tool definitions).

    See: https://docs.snowflake.com/en/sql-reference/sql/create-mcp-server
    """

    skip_on_empty_blueprints = True

    def get_object_type(self) -> ObjectType:
        return ObjectType.MCP_SERVER

    def get_existing_objects_in_schema(self, schema: dict):
        existing_objects = {}

        cur = self.engine.execute_meta(
            "SHOW MCP SERVERS IN SCHEMA {database:i}.{schema:i}",
            {
                "database": schema["database"],
                "schema": schema["schema"],
            },
        )

        for r in cur:
            existing_objects[f"{r['database_name']}.{r['schema_name']}.{r['name']}"] = {
                "database": r["database_name"],
                "schema": r["schema_name"],
                "name": r["name"],
                "owner": r.get("owner"),
                "comment": r["comment"] if r.get("comment") else None,
            }

        return existing_objects

    def get_blueprints(self):
        return self.config.get_blueprints_by_type(MCPServerBlueprint)

    def create_object(self, bp: MCPServerBlueprint):
        create_query = self._build_create_mcp_server_sql(bp)

        # Like SEMANTIC VIEW: ALTER ... SET COMMENT is not yet exposed for
        # MCP SERVER, so we embed a hash of the spec into the comment so that
        # subsequent compare_object can detect drift.
        create_query.append_nl(
            "COMMENT = {comment}",
            {
                "comment": create_query.add_short_hash(bp.comment),
            },
        )

        self.engine.execute_safe_ddl(create_query)

        return ResolveResult.CREATE

    def compare_object(self, bp: MCPServerBlueprint, row: dict):
        create_query = self._build_create_mcp_server_sql(bp)

        if not create_query.compare_short_hash(row["comment"]):
            create_query.append_nl(
                "COMMENT = {comment}",
                {
                    "comment": create_query.add_short_hash(bp.comment),
                },
            )

            self.engine.execute_safe_ddl(create_query)

            return ResolveResult.REPLACE

        return ResolveResult.NOCHANGE

    def drop_object(self, row: dict):
        self.engine.execute_safe_ddl(
            "DROP MCP SERVER {database:i}.{schema:i}.{name:i}",
            {
                "database": row["database"],
                "schema": row["schema"],
                "name": row["name"],
            },
        )

        return ResolveResult.DROP

    def _build_create_mcp_server_sql(self, bp: MCPServerBlueprint):
        query = self.engine.query_builder()

        query.append(
            "CREATE OR REPLACE MCP SERVER {full_name:i}",
            {
                "full_name": bp.full_name,
            },
        )

        spec_yaml = self._render_spec_yaml(bp)

        # FROM SPECIFICATION accepts dollar-quoted YAML. We escape any embedded
        # `$$` defensively even though Snowflake's YAML grammar shouldn't
        # contain it.
        spec_yaml = spec_yaml.replace("$$", "$ $")

        query.append_nl(
            "FROM SPECIFICATION $${spec:r}$$",
            {
                "spec": spec_yaml,
            },
        )

        return query

    @staticmethod
    def _render_spec_yaml(bp: MCPServerBlueprint) -> str:
        tools_payload: List[Dict[str, Any]] = []

        for t in bp.tools:
            entry: Dict[str, Any] = {
                "name": t.name,
                "type": t.type,
            }
            if t.title is not None:
                entry["title"] = t.title
            if t.description is not None:
                entry["description"] = t.description
            if t.identifier is not None:
                entry["identifier"] = t.identifier
            # Per-type extras (config / input_schema / read_only / ...) are
            # appended verbatim so users can adopt new Snowflake fields without
            # waiting for a SnowDDL release.
            for k, v in (t.extra or {}).items():
                entry[k] = v
            tools_payload.append(entry)

        spec: Dict[str, Any] = {"tools": tools_payload}

        # Top-level keys outside `tools:` (allowed by the YAML grammar) round-
        # trip through here as well.
        for k, v in (bp.spec_extra or {}).items():
            spec[k] = v

        return yaml.safe_dump(spec, sort_keys=False, default_flow_style=False)
