# Using Firewalla MSP from Claude (MCP)

Two community MCP servers wrap the same MSP API. Neither is made by Firewalla or Anthropic, so read the code before giving it your token.

| Server | Access | Runtime | Use it for |
|---|---|---|---|
| [productengineered/firewalla-mcp](https://github.com/productengineered/firewalla-mcp) | Read-only | Node 18+ | Audits, "what's using bandwidth", alarm review. **Start here.** |
| [djuntgen/firewalla-mcp](https://github.com/djuntgen/firewalla-mcp) | Read/write (create, pause, resume, delete rules and target lists) | Python, `uv` | Once you trust it; let Claude change rules |

Both run on your own computer (stdio), so they work in Claude Desktop and Claude Code, not the phone app. Home Assistant stays the place for automations and alerts; MCP is for asking questions.

## 1. Get credentials

- **MSP domain**: `yourname.firewalla.net`
- **Token**: MSP → Account Settings → API → create a personal access token. Consider a separate token from the one Home Assistant uses, so you can revoke either independently.

## 2a. Read-only server in Claude Desktop

```bash
git clone https://github.com/productengineered/firewalla-mcp.git ~/mcp/firewalla-mcp
cd ~/mcp/firewalla-mcp && npm install && npm run build
```

Claude Desktop → Settings → Developer → Edit Config, add:

```json
{
  "mcpServers": {
    "firewalla": {
      "command": "node",
      "args": ["/Users/<you>/mcp/firewalla-mcp/dist/index.js"],
      "env": {
        "FIREWALLA_MSP_DOMAIN": "yourname.firewalla.net",
        "FIREWALLA_MSP_TOKEN": "<token>"
      }
    }
  }
}
```

Restart Claude Desktop.

## 2b. Same server in Claude Code

```bash
claude mcp add-json --scope user firewalla '{
  "type": "stdio",
  "command": "node",
  "args": ["/Users/<you>/mcp/firewalla-mcp/dist/index.js"],
  "env": {
    "FIREWALLA_MSP_DOMAIN": "yourname.firewalla.net",
    "FIREWALLA_MSP_TOKEN": "<token>"
  }
}'
claude mcp list   # firewalla: ✓ Connected
```

## 3. Read/write server (later)

```bash
claude mcp add firewalla-rw \
  --env FIREWALLA_MSP_DOMAIN="yourname.firewalla.net" \
  --env FIREWALLA_TOKEN="<token>" \
  -- uvx --from git+https://github.com/djuntgen/firewalla-mcp firewalla-mcp
```

Note its env var is `FIREWALLA_TOKEN`, not `FIREWALLA_MSP_TOKEN`. Its `update_rule` recreates the rule, so the rule ID (and the matching Home Assistant switch) changes.

## Things to ask

- "Any security alarms this week? Group by device."
- "Top 10 devices by upload in the last 24 hours."
- "Which devices haven't been seen in 30 days?"
- "List my block rules and which devices they apply to."
- "Did the Comcast WAN fail over to Starlink recently?"
