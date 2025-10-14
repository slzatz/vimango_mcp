"""MCP server implementation for vimango."""

import asyncio
import json
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

    else:
        return [TextContent(
            type="text",
            text=f"Unknown tool: {name}"
        )]


async def main():
    """Run the MCP server."""
    global db

    # Load configuration
    config = load_config()
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


if __name__ == "__main__":
    asyncio.run(main())
