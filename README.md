# AnnoLab Claude plugin marketplace

Source of truth for the Claude plugins AnnoLab distributes to customers. This repository is both the development workspace and the marketplace customers point at.

```
.claude-plugin/marketplace.json     the catalog
plugins/annolab-title/              the plugin (skills live here)
```

## Develop

Edit files in `plugins/annolab-title/` like any other source. To load the plugin without installing it:

```bash
claude --plugin-dir ./plugins/annolab-title
```

Inside the session, `/reload-plugins` picks up edits without a restart. When the local plugin shares a name with an installed one, the local copy wins for that session — so you can iterate without uninstalling.

Before committing:

```bash
claude plugin validate ./plugins/annolab-title
```

Add `--strict` to treat warnings as errors.

To measure whether the plugin actually fires and helps, rather than just loads:

```bash
claude plugin eval ./plugins/annolab-title
```

Each prompt runs several times with and without the plugin loaded. Worth gating CI on, both for your own changes and for when a new model ships.

**Test in Cowork too.** Examiners run this in Cowork, not Code, and there is no `--plugin-dir` equivalent there. Add this repo as a marketplace in Cowork (Customize → Plugins → Add marketplace) and hit **Update**, or upload a packaged `.plugin` file.

## Release

1. Bump `version` in `plugins/annolab-title/.claude-plugin/plugin.json`
2. Update the version history in that plugin's README
3. Commit and push to the default branch

Claude compares the installed version against the catalog on a background refresh and pulls the new one when `version` changes. Customers who haven't disabled auto-update get it without acting.

The version deliberately lives **only** in `plugin.json`, not in the marketplace entry. Claude resolves the marketplace entry's `version` first if present, so carrying it in both places means two things to bump and a silent no-op update when they disagree.

## How customers install

The marketplace is hosted at <https://github.com/annotationhub/annolab-claude-plugin>.

**Cowork** — Customize → Plugins → **Add marketplace**, then enter `https://github.com/annotationhub/annolab-claude-plugin`. Install `annolab-title` from the catalog that appears.

**Claude Code**

```
/plugin marketplace add annotationhub/annolab-claude-plugin
/plugin install annolab-title@annolab
```

**Enterprise customers** — their administrator adds this repo under organization settings and sets the plugin to *installed by default* or *required*, so it reaches every member without each person adding a marketplace. Requires a Team or Enterprise plan with Cowork and Skills enabled on their side.

## Treat this repo as production infrastructure

Skills are instructions that execute inside a customer's session with whatever tools are loaded — including the AnnoLab SDK holding their API key. Write access here is functionally the ability to act inside every customer's environment, and auto-update means a change reaches them in the background without review on their end.

- Restrict write access; no direct pushes to the default branch
- Require review on every skill change, the same as application code
- Run `claude plugin validate` and `claude plugin eval` in CI before merge
- Never add a top-level `bin/` directory — plugins distributed through claude.ai organization settings can't include one

## Version compatibility

The plugin auto-updates. The `annolab` Python SDK does not. Skills are written against a specific SDK version (currently **0.7.2**), so a customer on an older SDK can receive a plugin update that assumes methods they don't have.

When bumping the plugin, check whether the skills still hold for the oldest SDK version you support, and state the minimum in the plugin README.

The MCP server (`web-server/src/mcp`) is deployed independently of the plugin and carries most of the instructions. Tool renames or removals there break every installed plugin version at once, so treat tool names and prompt names as a public API: add and deprecate rather than rename.
