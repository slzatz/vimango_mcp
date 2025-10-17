"""MCP server implementation for vimango."""

import asyncio
import json
from pathlib import Path
from typing import Any
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .db import VimangoDatabase, load_config


# Initialize MCP server
app = Server("vimango-mcp")

# Global database instance
db: VimangoDatabase = None


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        Tool(
            name="create_note",
            description="Create a new note in vimango with title and markdown body",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Note title"
                    },
                    "note": {
                        "type": "string",
                        "description": "Note body (markdown format)"
                    },
                    "context": {
                        "type": "string",
                        "description": "Context name (optional, defaults to 'none')",
                        "default": "none"
                    },
                    "folder": {
                        "type": "string",
                        "description": "Folder name (optional, defaults to 'none')",
                        "default": "none"
                    },
                    "star": {
                        "type": "boolean",
                        "description": "Star/favorite the note (optional)",
                        "default": False
                    }
                },
                "required": ["title", "note"]
            }
        ),
        Tool(
            name="list_contexts",
            description="List all available contexts for categorizing notes",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="list_folders",
            description="List all available folders for organizing notes",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="find_note",
            description="Search notes using full-text search and return matching titles",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Full-text search query (minimum 3 characters)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return",
                        "default": 5,
                        "minimum": 1
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="get_note",
            description="Retrieve the full note content for a given tid",
            inputSchema={
                "type": "object",
                "properties": {
                    "tid": {
                        "type": "integer",
                        "description": "Task tid returned by find_note"
                    }
                },
                "required": ["tid"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""

    if name == "create_note":
        title = arguments["title"]
        note = arguments["note"]
        context_name = arguments.get("context", "none")
        folder_name = arguments.get("folder", "none")
        star = arguments.get("star", False)

        # Resolve context and folder names to TIDs
        context_tid = db.get_context_tid_by_name(context_name)
        if context_tid is None:
            return [TextContent(
                type="text",
                text=f"Error: Context '{context_name}' not found. Use list_contexts to see available contexts."
            )]

        folder_tid = db.get_folder_tid_by_name(folder_name)
        if folder_tid is None:
            return [TextContent(
                type="text",
                text=f"Error: Folder '{folder_name}' not found. Use list_folders to see available folders."
            )]

        # Insert the note
        try:
            task_id = db.insert_note(
                title=title,
                note=note,
                context_tid=context_tid,
                folder_tid=folder_tid,
                star=star
            )
            return [TextContent(
                type="text",
                text=f"Successfully created note '{title}' with ID {task_id} in folder '{folder_name}' and context '{context_name}'"
            )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Error creating note: {str(e)}"
            )]

    elif name == "list_contexts":
        contexts = db.list_contexts()
        result = "Available contexts:\n"
        for id, tid, title, star in contexts:
            star_marker = " ⭐" if star else ""
            result += f"- {title}{star_marker} (tid: {tid})\n"
        return [TextContent(type="text", text=result)]

    elif name == "list_folders":
        folders = db.list_folders()
        result = "Available folders:\n"
        for id, tid, title, star in folders:
            star_marker = " ⭐" if star else ""
            result += f"- {title}{star_marker} (tid: {tid})\n"
        return [TextContent(type="text", text=result)]

    elif name == "find_note":
        query = arguments["query"]
        limit = arguments.get("limit", 5)
        try:
            limit_value = int(limit)
        except (TypeError, ValueError):
            return [TextContent(
                type="text",
                text="Error: 'limit' must be an integer."
            )]

        try:
            matches = db.find_notes(query, limit_value)
        except ValueError as exc:
            return [TextContent(type="text", text=f"Error: {exc}")]
        except Exception as exc:
            return [TextContent(
                type="text",
                text=f"Error running find_note: {exc}"
            )]

        if not matches:
            return [TextContent(
                type="text",
                text=f"No notes matched '{query}'."
            )]

        lines = [f"Matches for '{query}':"]
        for match in matches:
            context_title = match.get("context_title") or "none"
            folder_title = match.get("folder_title") or "none"
            lines.append(
                f"{match['rank']}. {match['title']} "
                f"(context: {context_title}, folder: {folder_title}, "
                f"id: {match['id']}, tid: {match['tid']})"
            )
        return [TextContent(type="text", text="\n".join(lines))]

    elif name == "get_note":
        try:
            tid = int(arguments["tid"])
        except (KeyError, TypeError, ValueError):
            return [TextContent(
                type="text",
                text="Error: 'tid' must be provided as an integer."
            )]

        note_record = db.get_note_by_tid(tid)
        if not note_record:
            return [TextContent(
                type="text",
                text=f"No active note found with tid {tid}."
            )]

        context_title = note_record.get("context_title") or "none"
        folder_title = note_record.get("folder_title") or "none"
        header = (
            f"Title: {note_record['title']}\n"
            f"Context: {context_title}\n"
            f"Folder: {folder_title}\n"
            f"tid: {note_record['tid']}\n"
            f"id: {note_record['id']}\n"
        )
        body = note_record.get("note", "")
        text = f"{header}\n{body}" if body else header
        return [TextContent(type="text", text=text)]

    else:
        return [TextContent(
            type="text",
            text=f"Unknown tool: {name}"
        )]


async def async_main():
    """Run the MCP server (async)."""
    global db

    # Load configuration from project root
    config_path = Path(__file__).parent.parent.parent / "config.json"
    config = load_config(str(config_path))
    main_db_path = config["vimango"]["main_db"]
    fts_db_path = config["vimango"]["fts_db"]

    # Initialize database
    db = VimangoDatabase(main_db_path, fts_db_path)
    db.connect()

    try:
        # Run the server
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())
    finally:
        db.close()


def main():
    """Entry point for the MCP server."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
