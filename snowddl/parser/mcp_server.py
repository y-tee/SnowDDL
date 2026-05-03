from snowddl.blueprint import (
    MCPServerBlueprint,
    MCPServerTool,
    SchemaObjectIdent,
)
from snowddl.parser.abc_parser import AbstractParser, ParsedFile


# Snowflake's CREATE MCP SERVER `FROM SPECIFICATION` body is a YAML doc with at
# minimum a `tools:` array. We accept a free-form `spec_extra` mapping for any
# additional top-level keys Snowflake may add (the feature is in active
# development and the spec schema may evolve).
#
# See: https://docs.snowflake.com/en/sql-reference/sql/create-mcp-server
# fmt: off
mcp_server_json_schema = {
    "type": "object",
    "properties": {
        "tools": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "identifier": {"type": "string"},
                },
                "required": ["name", "type"],
                # Per-type extras (config/input_schema/read_only/query_timeout/
                # warehouse/...) are accepted as free-form additional fields.
                "additionalProperties": True,
            },
            "minItems": 1,
        },
        "spec_extra": {
            "type": "object",
            "additionalProperties": True,
        },
        "comment": {"type": "string"},
    },
    "required": ["tools"],
    "additionalProperties": False,
}
# fmt: on


# Header keys that map directly to MCPServerTool fields. Anything else on a
# tool dict is preserved verbatim under MCPServerTool.extra so it round-trips
# back into the YAML body emitted by the resolver.
_TOOL_HEADER_KEYS = {"name", "type", "title", "description", "identifier"}


class MCPServerParser(AbstractParser):
    def load_blueprints(self):
        self.parse_schema_object_files("mcp_server", mcp_server_json_schema, self.process_mcp_server)

    def process_mcp_server(self, f: ParsedFile):
        bp = MCPServerBlueprint(
            full_name=SchemaObjectIdent(self.env_prefix, f.database, f.schema, f.name),
            tools=[self._build_tool(t) for t in f.params.get("tools", [])],
            spec_extra=f.params.get("spec_extra", {}) or {},
            comment=f.params.get("comment"),
        )

        self.config.add_blueprint(bp)

    def _build_tool(self, tool_def: dict) -> MCPServerTool:
        extra = {k: v for k, v in tool_def.items() if k not in _TOOL_HEADER_KEYS}

        return MCPServerTool(
            name=tool_def["name"],
            type=tool_def["type"],
            title=tool_def.get("title"),
            description=tool_def.get("description"),
            identifier=tool_def.get("identifier"),
            extra=extra,
        )
