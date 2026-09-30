# dog-geroscience plugin for Claude Code

Wires the `dog-geroscience-mcp` server (installed on demand with `uvx`) into Claude Code and
adds a skill that routes dog-aging questions to the right tools and explains how to read
their output.

```text
/plugin marketplace add w0lph/k9
/plugin install dog-geroscience@k9
```

Requires `uv` on the PATH. The server downloads its prebuilt database (about 90 MB) from the
Hugging Face Hub on first use.

To use the skill without the plugin, copy `skills/dog-geroscience/` into `~/.claude/skills/`
and add the MCP server to your own configuration:

```json
{ "mcpServers": { "dog-geroscience": { "command": "uvx", "args": ["dog-geroscience-mcp"] } } }
```
