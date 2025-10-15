# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vimango MCP Server is a Model Context Protocol (MCP) server that enables Claude Desktop to write markdown notes directly to local vimango SQLite databases. The server acts as a bridge between Claude Desktop and the vimango note-taking application.

## Development Commands

### Setup and Installation
```bash
# Install dependencies and create virtual environment
uv sync

# Run the MCP server
uv run vimango-mcp
```

### Testing
```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_filename.py

# Run with verbose output
uv run pytest -v
```

## Architecture

### Two-Database Design

Vimango uses a dual-database architecture:
- **vimango.db** (main database): Contains `task`, `context`, `folder`, and `keyword` tables
- **fts5_vimango.db** (FTS database): Full-text search index (FTS5) for fast searching

**Critical Design Pattern**: The MCP server writes ONLY to the main database. The FTS database is deliberately NOT touched by this server.

### Note Creation Flow

1. MCP server creates entries in the `task` table with `tid = -1` (sentinel value meaning "needs server-assigned ID")
2. Entry includes: title, note body, folder_tid, context_tid, star flag, and timestamps
3. FTS database remains unchanged by the MCP server
4. When vimango syncs with remote server:
   - Remote server assigns real `tid` values
   - Sync process updates local FTS database

This approach keeps the MCP server simple and leverages vimango's existing sync infrastructure.

### Code Structure

- **server.py**: MCP server implementation using the `mcp` library
  - Defines three tools: `create_note`, `list_contexts`, `list_folders`
  - Global `db` instance initialized in `async_main()` from `config.json`
  - Entry point `main()` is a synchronous wrapper that calls `asyncio.run(async_main())`
  - Uses stdio transport for communication with Claude Desktop

- **db.py**: Database operations and SQLite interaction
  - `VimangoDatabase` class manages connection to main database
  - `insert_note()` creates new task entries with `tid = -1`
  - Name-to-TID resolution for contexts and folders
  - `load_config()` reads database paths from `config.json`

### Configuration

The server requires a `config.json` file at project root:
```json
{
  "vimango": {
    "main_db": "/path/to/vimango.db",
    "fts_db": "/path/to/fts5_vimango.db"
  }
}
```

While `fts_db` is specified, it's currently unused by the server (reserved for future features).

**Important**: The server uses `Path(__file__).parent.parent.parent / "config.json"` to locate the config file, making it work regardless of the current working directory when launched by Claude Desktop.

## Database Schema Notes

### task Table
- `tid`: Task ID (-1 for new notes awaiting sync, positive integers for synced)
- `title`: Note title
- `note`: Markdown body
- `folder_tid`: Foreign key to folder table
- `context_tid`: Foreign key to context table
- `star`: Boolean for favorited notes
- `added`, `modified`: Timestamps (set to `datetime('now')` on insert)
- `deleted`: Soft-delete flag

### context and folder Tables
- Both follow the same pattern: `id`, `tid`, `title`, `star`, `deleted`
- Default "none" entries have `tid = 1`

## Claude Desktop Integration

Add to your Claude Desktop MCP configuration (`~/.config/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "vimango": {
      "command": "/path/to/vimango_mcp/.venv/bin/vimango-mcp"
    }
  }
}
```

The entry point script handles all necessary setup, including:
- Activating the virtual environment
- Loading the config.json from the project root
- Running the async MCP server via stdio

## Testing Approach

The project uses pytest with asyncio support. When writing tests:
- Use `pytest-asyncio` for async test functions
- Mock database connections to avoid requiring actual vimango databases
- Test MCP tool schemas and responses
- Verify database operations in isolation
