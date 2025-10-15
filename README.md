# Vimango MCP Server

A Model Context Protocol (MCP) server that enables Claude Desktop to write markdown notes directly to the local vimango SQLite databases.

## Overview

This MCP server allows Claude to create research notes and other content directly in your vimango note-taking application during conversations. It handles the database insertion logic, allowing seamless integration between Claude Desktop's research capabilities and your local note database.

## Architecture

### Database Structure

Vimango uses two separate SQLite databases:
- **vimango.db** - Main database containing tasks/notes, contexts, folders, and keywords
- **fts5_vimango.db** - Full-text search database (FTS5) for fast searching

### Note Creation Workflow

1. MCP server creates new entry in `task` table without setting `tid` (left NULL until sync assigns it)
2. Entry includes: title, note body, folder_tid, context_tid, timestamps
3. **FTS database is NOT touched** - it will be updated during sync
4. When you sync vimango with the remote server:
   - Server assigns real `tid` to entry
   - Sync process updates local FTS database

This design keeps the MCP server simple and leverages vimango's existing sync machinery.

## Installation

### Prerequisites

- Python 3.11 or higher
- [UV](https://github.com/astral-sh/uv) package manager
- Vimango application with configured databases

### Setup

```bash
# Clone or navigate to the repository
cd /home/slzatz/vimango_mcp

# Create virtual environment and install dependencies
uv sync

# Configure database paths
cp config.json.example config.json
# Edit config.json to point to your vimango databases
```

## Configuration

Create a `config.json` file in the project root:

```json
{
  "vimango": {
    "main_db": "/path/to/vimango.db",
    "fts_db": "/path/to/fts5_vimango.db"
  }
}
```

## Usage

### Running the MCP Server

```bash
uv run vimango-mcp
```

### Claude Desktop Configuration

Add to your Claude Desktop MCP settings:

```json
{
  "mcpServers": {
    "vimango": {
      "command": "/path/to/vimango_mcp/.venv/bin/vimango-mcp"
    }
  }
}
```

### Available MCP Tools

- **create_note** - Create a new note with title and markdown body
- **list_contexts** - List available contexts for note categorization
- **list_folders** - List available folders for note organization

## Development

### Project Structure

```
vimango_mcp/
├── src/
│   └── vimango_mcp/
│       ├── __init__.py     # Package initialization
│       ├── server.py       # MCP server implementation
│       └── db.py          # Database operations
├── tests/                  # Test suite
├── pyproject.toml         # UV project configuration
└── README.md
```

### Running Tests

```bash
uv run pytest
```

## Notes

- The MCP server creates notes with `tid` left NULL so the server can assign IDs during sync
- FTS synchronization happens automatically during vimango's normal sync process
- Concurrent access is handled by SQLite's locking mechanisms
- Research notes are typically created in the "research" folder

## License

MIT
