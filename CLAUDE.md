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

1. MCP server creates entries in the `task` table without setting `tid` (leaves it NULL until the server assigns an ID)
2. Entry includes: title, note body, folder_uuid, context_uuid, star flag, and timestamps
3. FTS database remains unchanged by the MCP server
4. When vimango syncs with remote server:
   - Remote server assigns real `tid` values
   - Sync process updates local FTS database

This approach keeps the MCP server simple and leverages vimango's existing sync infrastructure.

### UUID-Based Foreign Keys

The vimango schema uses UUID-based foreign keys for container references:
- Tasks reference contexts and folders via `context_uuid` and `folder_uuid` columns
- Container tables (context, folder) have a `uuid` column as the unique identifier
- Default UUIDs:
  - Context "none": `00000000-0000-0000-0000-000000000001`
  - Folder "none": `00000000-0000-0000-0000-000000000002`
- The old `tid` columns are retained for backward compatibility with PostgreSQL sync

### Code Structure

- **server.py**: MCP server implementation using the `mcp` library
  - Tools: `create_note`, `list_contexts`, `list_folders`, `search_notes`, `get_note`, `update_note`
  - Global `db` instance initialized in `async_main()` from `config.json`
  - Entry point `main()` is a synchronous wrapper that calls `asyncio.run(async_main())`
  - Uses stdio transport for communication with Claude Desktop

- **db.py**: Database operations and SQLite interaction
  - `VimangoDatabase` opens the main database read-write and the FTS database read-only
  - `insert_note()` creates new task entries using `context_uuid` and `folder_uuid`, with `tid` left NULL
  - `find_notes()` runs FTS queries and joins back to task/context/folder tables via UUID
  - `get_note_by_tid()` returns the full note body and metadata for a given `tid`
  - `get_note_by_id()` returns the full note body and metadata for a given local `id`
  - `get_context_uuid_by_name()` and `get_folder_uuid_by_name()` resolve names to UUIDs
  - `update_note_metadata()` updates context, folder, title, or star on an existing note
  - `load_config()` reads database paths from `config.json`
  - Default UUID constants: `DEFAULT_CONTEXT_UUID`, `DEFAULT_FOLDER_UUID`

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

While `fts_db` is specified, it's used in read-only mode to power the `search_notes` tool.

**Important**: The server uses `Path(__file__).parent.parent.parent / "config.json"` to locate the config file, making it work regardless of the current working directory when launched by Claude Desktop.

## Database Schema Notes

### task Table
- `tid`: Task ID (NULL for new notes awaiting sync, positive integers for synced)
- `title`: Note title
- `note`: Markdown body
- `folder_uuid`: UUID foreign key to folder table (default: `00000000-0000-0000-0000-000000000002`)
- `context_uuid`: UUID foreign key to context table (default: `00000000-0000-0000-0000-000000000001`)
- `folder_tid`, `context_tid`: Legacy integer FKs (retained for sync compatibility)
- `star`: Boolean for favorited notes
- `added`, `modified`: Timestamps (set to `datetime('now')` on insert)
- `deleted`: Soft-delete flag

### context and folder Tables
- Both follow the same pattern: `id`, `tid`, `title`, `uuid`, `star`, `deleted`
- `uuid` is the primary identifier used by foreign keys
- Default "none" entries have well-known UUIDs:
  - Context "none": `00000000-0000-0000-0000-000000000001` (tid=1)
  - Folder "none": `00000000-0000-0000-0000-000000000002` (tid=1)

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

### Tool Summary

- `create_note`: Insert a new note into `task` using `context_uuid` and `folder_uuid`, leaving `tid` NULL for sync.
- `list_contexts`: Enumerate undeleted contexts with their UUIDs, titles, and star flags.
- `list_folders`: Enumerate undeleted folders with their UUIDs, titles, and star flags.
- `search_notes`: Run an FTS search (minimum 3 characters) and return ranked results with `id`, `tid`, `title`, context, and folder (joined via UUID).
- `get_note`: Retrieve the full markdown body by `note_id` (local ID) or `note_tid` (sync ID), plus metadata (context/folder resolved via UUID joins), without modifying either database.
- `update_note`: Update metadata on an existing note by `note_id`. Can change context, folder, title, or star flag.
