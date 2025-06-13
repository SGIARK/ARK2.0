#!/usr/bin/env python3
"""
Enhanced MCP-compliant Radicale Calendar Server

This module provides a fully MCP-compliant server for Radicale calendar operations
using the FastMCP framework. It replaces the previous WebSocket-based bridge with
a standardized MCP implementation that can be used with LangChain MCP adapters.

Features:
- Full MCP protocol compliance
- Async operation support
- Comprehensive error handling
- Tool discovery and schema validation
- Multiple transport options (stdio, HTTP)
- Environment-based configuration

Usage:
    # Run with stdio transport (default)
    python mcp_radicale_server.py
    
    # Run with HTTP transport
    python mcp_radicale_server.py --transport http --port 8765

Dependencies:
    pip install mcp caldav python-dotenv
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

# MCP imports
try:
    from mcp.server.fastmcp import FastMCP
    from mcp.types import Tool, TextContent
except ImportError:
    print("MCP package not found. Please install with: pip install mcp")
    exit(1)

# Local imports
from radicale_calendar_manager import RadicaleCalendarManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("mcp-radicale-server")

# Load environment variables
load_dotenv()

class MCPError(Exception):
    """Custom exception for MCP operations"""
    pass

class MCPRadicaleServer:
    """
    MCP-compliant server for Radicale calendar operations.
    
    This class implements a FastMCP server that provides calendar operations
    as MCP tools. It handles connection management, tool registration, and
    provides async operations for calendar management.
    """
    
    def __init__(self):
        """Initialize the MCP server with calendar manager and tool registration"""
        self.mcp = FastMCP("RadicaleCalendar")
        self.calendar_manager = None
        self._initialize_calendar_manager()
        self._register_tools()
        
    def _initialize_calendar_manager(self):
        """Initialize the Radicale calendar manager with environment configuration"""
        try:
            radicale_url = os.getenv("RADICALE_URL", "http://localhost:5232")
            radicale_username = os.getenv("RADICALE_USERNAME", "")
            radicale_password = os.getenv("RADICALE_PASSWORD", "")
            
            if not radicale_username or not radicale_password:
                logger.warning("Radicale credentials not found in environment variables")
                
            self.calendar_manager = RadicaleCalendarManager(
                url=radicale_url,
                username=radicale_username,
                password=radicale_password
            )
            
            # Test connection during initialization
            if not self.calendar_manager.connect():
                raise MCPError("Failed to connect to Radicale server during initialization")
                
            logger.info(f"Successfully connected to Radicale server at {radicale_url}")
            
        except Exception as e:
            logger.error(f"Failed to initialize calendar manager: {e}")
            raise MCPError(f"Calendar manager initialization failed: {e}")
    
    def _register_tools(self):
        """Register all calendar tools with the MCP server"""
        
        @self.mcp.tool()
        async def list_calendars() -> str:
            """
            List all available calendars in the Radicale server.
            
            Returns:
                JSON string containing list of calendar names
                
            Example:
                ["Personal", "Work", "Family"]
            """
            try:
                if not self.calendar_manager or not self.calendar_manager.calendars:
                    # Reconnect if needed
                    if not self.calendar_manager.connect():
                        raise MCPError("Failed to connect to Radicale server")
                
                calendar_names = [cal.name for cal in self.calendar_manager.calendars]
                logger.info(f"Listed {len(calendar_names)} calendars")
                
                return json.dumps({
                    "status": "success",
                    "calendars": calendar_names,
                    "count": len(calendar_names)
                })
                
            except Exception as e:
                logger.error(f"Error listing calendars: {e}")
                raise MCPError(f"Failed to list calendars: {e}")
        
        @self.mcp.tool()
        async def get_events(
            calendar_name: Optional[str] = None,
            start_date: Optional[str] = None,
            end_date: Optional[str] = None
        ) -> str:
            """
            Get events from a calendar within a specified date range.
            
            Args:
                calendar_name: Name of the calendar (optional, uses first available if not specified)
                start_date: Start date in ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
                end_date: End date in ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
                
            Returns:
                JSON string containing list of events with their details
                
            Example:
                {
                    "status": "success",
                    "calendar": "Work",
                    "events": [
                        {
                            "id": "event-123",
                            "summary": "Team Meeting",
                            "start": "2023-06-01T10:00:00",
                            "end": "2023-06-01T11:00:00",
                            "location": "Conference Room",
                            "description": "Weekly team sync"
                        }
                    ],
                    "count": 1
                }
            """
            try:
                # Parse date parameters
                start_dt = None
                end_dt = None
                
                if start_date:
                    try:
                        start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    except ValueError:
                        raise MCPError(f"Invalid start_date format: {start_date}. Use ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)")
                
                if end_date:
                    try:
                        end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    except ValueError:
                        raise MCPError(f"Invalid end_date format: {end_date}. Use ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)")
                
                # Get events
                events = self.calendar_manager.get_events(calendar_name, start_dt, end_dt)
                
                # Determine which calendar was used
                used_calendar = calendar_name
                if not used_calendar and self.calendar_manager.calendars:
                    used_calendar = self.calendar_manager.calendars[0].name
                
                logger.info(f"Retrieved {len(events)} events from calendar '{used_calendar}'")
                
                return json.dumps({
                    "status": "success",
                    "calendar": used_calendar,
                    "events": events,
                    "count": len(events),
                    "date_range": {
                        "start": start_date,
                        "end": end_date
                    }
                })
                
            except MCPError:
                raise
            except Exception as e:
                logger.error(f"Error getting events: {e}")
                raise MCPError(f"Failed to get events: {e}")
        
        @self.mcp.tool()
        async def create_event(
            calendar_name: str,
            summary: str,
            start: str,
            end: Optional[str] = None,
            location: Optional[str] = None,
            description: Optional[str] = None
        ) -> str:
            """
            Create a new calendar event.
            
            Args:
                calendar_name: Name of the calendar to create the event in
                summary: Event title/summary (required)
                start: Start datetime in ISO format (YYYY-MM-DDTHH:MM:SS) (required)
                end: End datetime in ISO format (optional, defaults to start + 1 hour)
                location: Event location (optional)
                description: Event description (optional)
                
            Returns:
                JSON string with created event details and ID
                
            Example:
                {
                    "status": "success",
                    "message": "Event 'Team Meeting' created successfully",
                    "event_id": "event-123",
                    "calendar": "Work"
                }
            """
            try:
                # Validate required fields
                if not summary.strip():
                    raise MCPError("Event summary is required and cannot be empty")
                
                if not start.strip():
                    raise MCPError("Event start time is required and cannot be empty")
                
                # Validate start time format
                try:
                    datetime.fromisoformat(start.replace('Z', '+00:00'))
                except ValueError:
                    raise MCPError(f"Invalid start time format: {start}. Use ISO format (YYYY-MM-DDTHH:MM:SS)")
                
                # Validate end time format if provided
                if end:
                    try:
                        datetime.fromisoformat(end.replace('Z', '+00:00'))
                    except ValueError:
                        raise MCPError(f"Invalid end time format: {end}. Use ISO format (YYYY-MM-DDTHH:MM:SS)")
                
                # Prepare event data
                event_data = {
                    "summary": summary,
                    "start": start
                }
                
                if end:
                    event_data["end"] = end
                if location:
                    event_data["location"] = location
                if description:
                    event_data["description"] = description
                
                # Create the event
                event_id = self.calendar_manager.add_event(calendar_name, event_data)
                
                logger.info(f"Created event '{summary}' with ID '{event_id}' in calendar '{calendar_name}'")
                
                return json.dumps({
                    "status": "success",
                    "message": f"Event '{summary}' created successfully",
                    "event_id": event_id,
                    "calendar": calendar_name,
                    "event_data": event_data
                })
                
            except MCPError:
                raise
            except Exception as e:
                logger.error(f"Error creating event: {e}")
                raise MCPError(f"Failed to create event: {e}")
        
        @self.mcp.tool()
        async def update_event(
            calendar_name: str,
            event_id: str,
            summary: Optional[str] = None,
            start: Optional[str] = None,
            end: Optional[str] = None,
            location: Optional[str] = None,
            description: Optional[str] = None
        ) -> str:
            """
            Update an existing calendar event.
            
            Args:
                calendar_name: Name of the calendar containing the event
                event_id: ID of the event to update (required)
                summary: New event title/summary (optional)
                start: New start datetime in ISO format (optional)
                end: New end datetime in ISO format (optional)
                location: New event location (optional)
                description: New event description (optional)
                
            Returns:
                JSON string with update status
                
            Example:
                {
                    "status": "success",
                    "message": "Event 'event-123' updated successfully",
                    "event_id": "event-123",
                    "updated_fields": ["summary", "location"]
                }
            """
            try:
                # Validate required fields
                if not event_id.strip():
                    raise MCPError("Event ID is required and cannot be empty")
                
                # Validate date formats if provided
                if start:
                    try:
                        datetime.fromisoformat(start.replace('Z', '+00:00'))
                    except ValueError:
                        raise MCPError(f"Invalid start time format: {start}. Use ISO format (YYYY-MM-DDTHH:MM:SS)")
                
                if end:
                    try:
                        datetime.fromisoformat(end.replace('Z', '+00:00'))
                    except ValueError:
                        raise MCPError(f"Invalid end time format: {end}. Use ISO format (YYYY-MM-DDTHH:MM:SS)")
                
                # Prepare update data (only include non-None values)
                update_data = {}
                updated_fields = []
                
                if summary is not None:
                    update_data["summary"] = summary
                    updated_fields.append("summary")
                if start is not None:
                    update_data["start"] = start
                    updated_fields.append("start")
                if end is not None:
                    update_data["end"] = end
                    updated_fields.append("end")
                if location is not None:
                    update_data["location"] = location
                    updated_fields.append("location")
                if description is not None:
                    update_data["description"] = description
                    updated_fields.append("description")
                
                if not update_data:
                    raise MCPError("At least one field must be provided for update")
                
                # Update the event
                success = self.calendar_manager.set_event(calendar_name, event_id, update_data)
                
                if success:
                    logger.info(f"Updated event '{event_id}' in calendar '{calendar_name}'. Fields: {updated_fields}")
                    return json.dumps({
                        "status": "success",
                        "message": f"Event '{event_id}' updated successfully",
                        "event_id": event_id,
                        "calendar": calendar_name,
                        "updated_fields": updated_fields,
                        "update_data": update_data
                    })
                else:
                    raise MCPError(f"Failed to update event '{event_id}' - event may not exist")
                    
            except MCPError:
                raise
            except Exception as e:
                logger.error(f"Error updating event: {e}")
                raise MCPError(f"Failed to update event: {e}")
        
        @self.mcp.tool()
        async def delete_event(calendar_name: str, event_id: str) -> str:
            """
            Delete a calendar event.
            
            Args:
                calendar_name: Name of the calendar containing the event
                event_id: ID of the event to delete (required)
                
            Returns:
                JSON string with deletion status
                
            Example:
                {
                    "status": "success",
                    "message": "Event 'event-123' deleted successfully",
                    "event_id": "event-123",
                    "calendar": "Work"
                }
            """
            try:
                # Validate required fields
                if not event_id.strip():
                    raise MCPError("Event ID is required and cannot be empty")
                
                if not calendar_name.strip():
                    raise MCPError("Calendar name is required and cannot be empty")
                
                # Delete the event
                success = self.calendar_manager.delete_event(calendar_name, event_id)
                
                if success:
                    logger.info(f"Deleted event '{event_id}' from calendar '{calendar_name}'")
                    return json.dumps({
                        "status": "success",
                        "message": f"Event '{event_id}' deleted successfully",
                        "event_id": event_id,
                        "calendar": calendar_name
                    })
                else:
                    raise MCPError(f"Failed to delete event '{event_id}' - event may not exist")
                    
            except MCPError:
                raise
            except Exception as e:
                logger.error(f"Error deleting event: {e}")
                raise MCPError(f"Failed to delete event: {e}")
    
    async def run_server(self, transport="stdio", port=8765):
        """
        Run the MCP server with specified transport method.
        
        Args:
            transport: Transport method ("stdio" or "sse")
            port: Port number for SSE transport (default: 8765)
        """
        logger.info(f"Starting MCP Radicale server with {transport} transport")
        
        try:
            if transport == "stdio":
                logger.info("Running MCP server with stdio transport")
                await self.mcp.run_stdio_async()
            elif transport == "http" or transport == "sse":
                logger.info(f"Running MCP server with SSE transport on port {port}")
                # Get the SSE app and run it with uvicorn
                import uvicorn
                app = self.mcp.sse_app()
                config = uvicorn.Config(app, host="localhost", port=port, log_level="info")
                server = uvicorn.Server(config)
                await server.serve()
            else:
                raise ValueError(f"Unsupported transport: {transport}. Use 'stdio' or 'sse'")
                
        except Exception as e:
            logger.error(f"Error running MCP server: {e}")
            raise

def main():
    """Main entry point for the MCP server"""
    import argparse
    
    parser = argparse.ArgumentParser(description="MCP Radicale Calendar Server")
    parser.add_argument(
        "--transport", 
        choices=["stdio", "http", "sse"], 
        default="stdio",
        help="Transport method for MCP communication (default: stdio)"
    )
    parser.add_argument(
        "--port", 
        type=int, 
        default=8765,
        help="Port number for HTTP transport (default: 8765)"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)"
    )
    
    args = parser.parse_args()
    
    # Set logging level
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    # Create and run server
    server = MCPRadicaleServer()
    
    try:
        asyncio.run(server.run_server(transport=args.transport, port=args.port))
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        exit(1)

if __name__ == "__main__":
    main()