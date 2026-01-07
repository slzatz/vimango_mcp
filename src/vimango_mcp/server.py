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
            name="search_notes",
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
            description="Retrieve the full note content by note_id or note_tid. Use note_id for unsynced notes, note_tid for synced notes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "note_id": {
                        "type": "integer",
                        "description": "Local database ID (always present)"
                    },
                    "note_tid": {
                        "type": "integer",
                        "description": "Sync ID (only present after sync to server)"
                    }
                }
            }
        ),
        Tool(
            name="update_note",
            description="Update metadata on an existing note (context, folder, title, star). At least one field must be provided.",
            inputSchema={
                "type": "object",
                "properties": {
                    "note_id": {
                        "type": "integer",
                        "description": "Local database ID of the note to update"
                    },
                    "context": {
                        "type": "string",
                        "description": "New context name (optional)"
                    },
                    "folder": {
                        "type": "string",
                        "description": "New folder name (optional)"
                    },
                    "title": {
                        "type": "string",
                        "description": "New title (optional)"
                    },
                    "star": {
                        "type": "boolean",
                        "description": "Star/favorite the note (optional)"
                    }
                },
                "required": ["note_id"]
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

        # Resolve context and folder names to UUIDs
        context_uuid = db.get_context_uuid_by_name(context_name)
        if context_uuid is None:
            return [TextContent(
                type="text",
                text=f"Error: Context '{context_name}' not found. Use list_contexts to see available contexts."
            )]

        folder_uuid = db.get_folder_uuid_by_name(folder_name)
        if folder_uuid is None:
            return [TextContent(
                type="text",
                text=f"Error: Folder '{folder_name}' not found. Use list_folders to see available folders."
            )]

        # Insert the note
        try:
            task_id = db.insert_note(
                title=title,
                note=note,
                context_uuid=context_uuid,
                folder_uuid=folder_uuid,
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
        for id, tid, title, uuid, star in contexts:
            star_marker = " ⭐" if star else ""
            result += f"- {title}{star_marker} (uuid: {uuid})\n"
        return [TextContent(type="text", text=result)]

    elif name == "list_folders":
        folders = db.list_folders()
        result = "Available folders:\n"
        for id, tid, title, uuid, star in folders:
            star_marker = " ⭐" if star else ""
            result += f"- {title}{star_marker} (uuid: {uuid})\n"
        return [TextContent(type="text", text=result)]

    elif name == "search_notes":
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
        note_id = arguments.get("note_id")
        note_tid = arguments.get("note_tid")

        if note_id is None and note_tid is None:
            return [TextContent(
                type="text",
                text="Error: Either 'note_id' or 'note_tid' must be provided."
            )]

        # Prefer note_id if both provided (it's always present)
        if note_id is not None:
            try:
                note_id = int(note_id)
            except (TypeError, ValueError):
                return [TextContent(
                    type="text",
                    text="Error: 'note_id' must be an integer."
                )]
            note_record = db.get_note_by_id(note_id)
            lookup_desc = f"id {note_id}"
        else:
            try:
                note_tid = int(note_tid)
            except (TypeError, ValueError):
                return [TextContent(
                    type="text",
                    text="Error: 'note_tid' must be an integer."
                )]
            note_record = db.get_note_by_tid(note_tid)
            lookup_desc = f"tid {note_tid}"

        if not note_record:
            return [TextContent(
                type="text",
                text=f"No active note found with {lookup_desc}."
            )]

        context_title = note_record.get("context_title") or "none"
        folder_title = note_record.get("folder_title") or "none"
        tid_display = note_record['tid'] if note_record['tid'] is not None else "(unsynced)"
        header = (
            f"Title: {note_record['title']}\n"
            f"Context: {context_title}\n"
            f"Folder: {folder_title}\n"
            f"tid: {tid_display}\n"
            f"id: {note_record['id']}\n"
        )
        body = note_record.get("note", "")
        text = f"{header}\n{body}" if body else header
        return [TextContent(type="text", text=text)]

    elif name == "update_note":
        # Validate note_id
        try:
            note_id = int(arguments["note_id"])
        except (KeyError, TypeError, ValueError):
            return [TextContent(
                type="text",
                text="Error: 'note_id' must be provided as an integer."
            )]

        # Get optional update fields
        context_name = arguments.get("context")
        folder_name = arguments.get("folder")
        title = arguments.get("title")
        star = arguments.get("star")

        # Check at least one field is provided
        if context_name is None and folder_name is None and title is None and star is None:
            return [TextContent(
                type="text",
                text="Error: At least one field (context, folder, title, star) must be provided."
            )]

        # Resolve context name to UUID if provided
        context_uuid = None
        if context_name is not None:
            context_uuid = db.get_context_uuid_by_name(context_name)
            if context_uuid is None:
                return [TextContent(
                    type="text",
                    text=f"Error: Context '{context_name}' not found. Use list_contexts to see available contexts."
                )]

        # Resolve folder name to UUID if provided
        folder_uuid = None
        if folder_name is not None:
            folder_uuid = db.get_folder_uuid_by_name(folder_name)
            if folder_uuid is None:
                return [TextContent(
                    type="text",
                    text=f"Error: Folder '{folder_name}' not found. Use list_folders to see available folders."
                )]

        # Perform the update
        try:
            updated = db.update_note_metadata(
                note_id=note_id,
                context_uuid=context_uuid,
                folder_uuid=folder_uuid,
                title=title,
                star=star
            )
            if updated:
                # Build description of what was updated
                changes = []
                if context_name is not None:
                    changes.append(f"context='{context_name}'")
                if folder_name is not None:
                    changes.append(f"folder='{folder_name}'")
                if title is not None:
                    changes.append(f"title='{title}'")
                if star is not None:
                    changes.append(f"star={star}")
                return [TextContent(
                    type="text",
                    text=f"Successfully updated note {note_id}: {', '.join(changes)}"
                )]
            else:
                return [TextContent(
                    type="text",
                    text=f"No note found with id {note_id}, or no changes were made."
                )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Error updating note: {str(e)}"
            )]

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
