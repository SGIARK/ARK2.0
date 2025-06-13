"""
LangChain MCP Integration for Radicale Calendar

This module provides integration between LangChain and MCP (Model Context Protocol)
for calendar operations. It replaces the direct tool adapter approach with a 
standardized MCP-based integration using LangChain's official MCP adapters.

Features:
- Uses LangChain MCP adapters for tool conversion
- Supports multiple MCP transport methods (stdio, HTTP)
- Automatic tool discovery and schema validation
- Async operation support
- Comprehensive error handling
- Configuration-based MCP server management

Usage:
    # Basic usage with default configuration
    integration = CalendarMCPIntegration()
    tools = await integration.initialize()
    
    # Use with LangChain agent
    agent = create_openai_functions_agent(llm, prompt, tools)
    
Dependencies:
    pip install langchain-mcp-adapters mcp
    # OR alternative:
    pip install langchain-mcp-tools
"""

import os
import json
import asyncio
import logging
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path

# LangChain imports
from langchain.tools import Tool
from langchain_core.tools import BaseTool

# Environment configuration
from dotenv import load_dotenv

# Configure logging
logger = logging.getLogger("langchain-mcp-integration")

class MCPIntegrationError(Exception):
    """Custom exception for MCP integration operations"""
    pass

class CalendarMCPIntegration:
    """
    LangChain MCP Integration for Radicale Calendar Operations.
    
    This class manages the connection between LangChain and MCP servers,
    providing automatic tool discovery and conversion from MCP tools to
    LangChain-compatible tools.
    """
    
    def __init__(self, mcp_server_config: Optional[Dict[str, Any]] = None):
        """
        Initialize the MCP integration with server configuration.
        
        Args:
            mcp_server_config: Dictionary containing MCP server configuration.
                              If None, uses default configuration.
        """
        load_dotenv()
        
        self.mcp_server_config = mcp_server_config or self._get_default_config()
        self.tools: List[BaseTool] = []
        self.cleanup_fn: Optional[Callable] = None
        self._mcp_client = None
        self._integration_method = None
        
    def _get_default_config(self) -> Dict[str, Any]:
        """
        Get default MCP server configuration.
        
        Returns:
            Dictionary containing default server configuration
        """
        # Get the directory where this script is located
        script_dir = Path(__file__).parent
        server_script = script_dir / "mcp_radicale_server.py"
        
        return {
            "radicale-calendar": {
                "command": "python",
                "args": [str(server_script)],
                "transport": "stdio",
                "env": {
                    "RADICALE_URL": os.getenv("RADICALE_URL", "http://localhost:5232"),
                    "RADICALE_USERNAME": os.getenv("RADICALE_USERNAME", ""),
                    "RADICALE_PASSWORD": os.getenv("RADICALE_PASSWORD", "")
                }
            }
        }
    
    async def initialize(self) -> List[BaseTool]:
        """
        Initialize MCP connection and load calendar tools.
        
        Returns:
            List of LangChain-compatible tools converted from MCP server
            
        Raises:
            MCPIntegrationError: If initialization fails
        """
        logger.info("Initializing LangChain MCP integration for calendar operations")
        
        try:
            # Try primary method: langchain-mcp-tools
            tools = await self._initialize_with_mcp_tools()
            if tools:
                self._integration_method = "langchain-mcp-tools"
                self.tools = tools
                logger.info(f"Successfully initialized with langchain-mcp-tools: {len(tools)} tools loaded")
                return tools
                
        except ImportError as e:
            logger.warning(f"langchain-mcp-tools not available: {e}")
        except Exception as e:
            logger.warning(f"Failed to initialize with langchain-mcp-tools: {e}")
        
        try:
            # Fallback method: langchain-mcp-adapters
            tools = await self._initialize_with_adapters()
            if tools:
                self._integration_method = "langchain-mcp-adapters"
                self.tools = tools
                logger.info(f"Successfully initialized with langchain-mcp-adapters: {len(tools)} tools loaded")
                return tools
                
        except ImportError as e:
            logger.error(f"langchain-mcp-adapters not available: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize with langchain-mcp-adapters: {e}")
        
        # If both methods fail, try manual tool creation
        try:
            tools = await self._initialize_manual_tools()
            self._integration_method = "manual"
            self.tools = tools
            logger.info(f"Successfully initialized with manual tools: {len(tools)} tools loaded")
            return tools
            
        except Exception as e:
            logger.error(f"Failed to initialize with manual tools: {e}")
            raise MCPIntegrationError(f"All MCP integration methods failed: {e}")
    
    async def _initialize_with_mcp_tools(self) -> List[BaseTool]:
        """
        Initialize using langchain-mcp-tools package.
        
        Returns:
            List of converted LangChain tools
        """
        try:
            from langchain_mcp_tools import convert_mcp_to_langchain_tools
            
            logger.info("Using langchain-mcp-tools for MCP integration")
            
            # Initialize MCP servers and get tools
            tools, cleanup_fn = await convert_mcp_to_langchain_tools(
                self.mcp_server_config
            )
            
            self.cleanup_fn = cleanup_fn
            
            # Validate tools
            if not tools:
                raise MCPIntegrationError("No tools returned from MCP server")
            
            logger.info(f"Loaded {len(tools)} tools from MCP server using langchain-mcp-tools")
            return tools
            
        except ImportError:
            raise ImportError("langchain-mcp-tools package not installed")
    
    async def _initialize_with_adapters(self) -> List[BaseTool]:
        """
        Initialize using langchain-mcp-adapters package.
        
        Returns:
            List of converted LangChain tools
        """
        try:
            from langchain_mcp_adapters.client import load_mcp_tools
            
            logger.info("Using langchain-mcp-adapters for MCP integration")
            
            # For stdio transport
            server_config = self.mcp_server_config.get("radicale-calendar", {})
            if server_config.get("transport") == "stdio":
                # Start the MCP server as a subprocess
                import subprocess
                
                cmd = [server_config["command"]] + server_config["args"]
                env = os.environ.copy()
                env.update(server_config.get("env", {}))
                
                # Start MCP server process
                self._mcp_process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    text=True
                )
                
                # Load tools using stdio connection
                from langchain_mcp_adapters.client import stdio_client
                
                # Create stdio connection and load tools
                async with stdio_client(self._mcp_process.stdin, self._mcp_process.stdout) as session:
                    tools = await load_mcp_tools(session)
                    
            else:
                # For HTTP transport, connect to running server
                from langchain_mcp_adapters.client import sse_client
                server_url = f"http://localhost:8765/sse"
                
                async with sse_client(server_url) as session:
                    tools = await load_mcp_tools(session)
            
            if not tools:
                raise MCPIntegrationError("No tools returned from MCP server")
            
            logger.info(f"Loaded {len(tools)} tools from MCP server using langchain-mcp-adapters")
            return tools
            
        except ImportError:
            raise ImportError("langchain-mcp-adapters package not installed")
    
    async def _initialize_manual_tools(self) -> List[BaseTool]:
        """
        Fallback: Create tools manually by communicating with MCP server.
        
        Returns:
            List of manually created LangChain tools
        """
        logger.info("Creating manual MCP tools as fallback")
        
        # Import the server class to get tool definitions
        from mcp_radicale_server import MCPRadicaleServer
        
        # Create server instance to get tool information
        server = MCPRadicaleServer()
        
        # Manually create LangChain tools that call the MCP server
        tools = []
        
        def list_calendars_sync(input_str: str = "") -> str:
            """List all available calendars"""
            try:
                if not server.calendar_manager.calendars:
                    server.calendar_manager.connect()
                calendar_names = [cal.name for cal in server.calendar_manager.calendars]
                return json.dumps({
                    "status": "success", 
                    "calendars": calendar_names,
                    "count": len(calendar_names)
                })
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e)})
        
        tools.append(Tool(
            name="list_calendars",
            func=list_calendars_sync,
            description="List all available calendars in the Radicale server"
        ))
        
        def parse_natural_date(date_str: str):
            """Parse natural language dates into datetime objects"""
            from datetime import datetime, timedelta
            import re
            
            if not date_str:
                return None
                
            date_str = date_str.strip().lower()
            now = datetime.now()
            
            # Handle specific natural language patterns
            if date_str == 'today':
                return now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif date_str == 'tomorrow':
                return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            elif date_str == 'yesterday':
                return (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            elif 'next friday' in date_str or 'friday' in date_str:
                # Find next Friday
                days_ahead = 4 - now.weekday()  # Friday is 4
                if days_ahead <= 0:  # Today is Friday or past Friday
                    days_ahead += 7
                return (now + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)
            elif 'next week' in date_str:
                return (now + timedelta(weeks=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            elif '+7 days' in date_str or 'next 7 days' in date_str:
                return (now + timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Try to parse as ISO format
            try:
                return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            except ValueError:
                pass
            
            # Try to parse as simple date format YYYY-MM-DD
            try:
                return datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                pass
                
            # If all else fails, raise error
            raise ValueError(f"Could not parse date: {date_str}")
        
        def get_events_sync(input_str: str) -> str:
            """Get events from calendar with parameter parsing"""
            try:
                from datetime import datetime
                import re
                
                # Parse input parameters from string - handle comma-separated values
                calendar_match = re.search(r'calendar[_\s]*name[:\s]*["\']?([^"\',:]+)["\']?', input_str, re.IGNORECASE)
                start_match = re.search(r'start[_\s]*date[:\s]*["\']?([^"\',:]+)["\']?', input_str, re.IGNORECASE)
                end_match = re.search(r'end[_\s]*date[:\s]*["\']?([^"\',:]+)["\']?', input_str, re.IGNORECASE)
                
                calendar_name = calendar_match.group(1).strip() if calendar_match else None
                start_date = start_match.group(1).strip() if start_match else None
                end_date = end_match.group(1).strip() if end_match else None
                
                # If no explicit parameters found, treat whole string as start_date
                if not calendar_name and not start_date and not end_date:
                    start_date = input_str.strip()
                
                start_dt = None
                end_dt = None
                
                # Use natural date parsing
                if start_date:
                    start_dt = parse_natural_date(start_date)
                if end_date:
                    end_dt = parse_natural_date(end_date)
                
                # If no calendar specified, use first available
                if not calendar_name and server.calendar_manager.calendars:
                    calendar_name = server.calendar_manager.calendars[0].name
                
                events = server.calendar_manager.get_events(calendar_name, start_dt, end_dt)
                
                # If looking for events "after" a specific time, filter them
                if "after" in input_str.lower() and start_dt:
                    filtered_events = []
                    for event in events:
                        try:
                            event_start = datetime.fromisoformat(event['start'].replace('Z', '+00:00'))
                            if event_start >= start_dt:
                                filtered_events.append(event)
                        except:
                            filtered_events.append(event)  # Include if can't parse
                    events = filtered_events
                
                used_calendar = calendar_name or "Default Calendar"
                
                return json.dumps({
                    "status": "success",
                    "calendar": used_calendar,
                    "events": events,
                    "count": len(events)
                })
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e)})
        
        tools.append(Tool(
            name="get_events",
            func=get_events_sync,
            description="Get events from a calendar within a date range. Provide parameters as text like 'calendar_name: Work, start_date: 2023-06-01'"
        ))
        
        def parse_natural_datetime(datetime_str: str) -> str:
            """Parse natural language datetime into ISO format"""
            from datetime import datetime, timedelta
            import re
            
            if not datetime_str:
                return None
                
            datetime_str = datetime_str.strip().lower()
            now = datetime.now()
            
            # Handle relative times like "tomorrow at 2pm", "next Friday at 10am"
            time_match = re.search(r'at (\d{1,2})(?::(\d{2}))?\s*(am|pm)?', datetime_str)
            hour = 0
            minute = 0
            
            if time_match:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2) or 0)
                ampm = time_match.group(3)
                
                if ampm == 'pm' and hour != 12:
                    hour += 12
                elif ampm == 'am' and hour == 12:
                    hour = 0
            
            # Get the base date
            if 'today' in datetime_str:
                base_date = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            elif 'tomorrow' in datetime_str:
                base_date = (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
            elif 'next friday' in datetime_str or 'friday' in datetime_str:
                days_ahead = 4 - now.weekday()  # Friday is 4
                if days_ahead <= 0:
                    days_ahead += 7
                base_date = (now + timedelta(days=days_ahead)).replace(hour=hour, minute=minute, second=0, microsecond=0)
            else:
                # Try to parse as ISO format first
                try:
                    return datetime.fromisoformat(datetime_str.replace('Z', '+00:00')).isoformat()
                except ValueError:
                    # Default to parsing as date only
                    base_date = parse_natural_date(datetime_str)
                    if base_date and (hour or minute):
                        base_date = base_date.replace(hour=hour, minute=minute)
                    elif not base_date:
                        base_date = now.replace(hour=hour or 0, minute=minute or 0, second=0, microsecond=0)
            
            return base_date.isoformat()

        def create_event_structured(calendar_name: str, summary: str, start: str, duration: int = 60) -> str:
            """Create a new event with structured parameters"""
            try:
                # Parse natural language datetime
                start_iso = parse_natural_datetime(start)
                
                # Calculate end time from duration (in minutes)
                from datetime import datetime, timedelta
                start_dt = datetime.fromisoformat(start_iso)
                end_dt = start_dt + timedelta(minutes=duration)
                
                # If no calendar name provided, use first available
                if not calendar_name and server.calendar_manager.calendars:
                    calendar_name = server.calendar_manager.calendars[0].name
                
                # Create the event
                event_data = {
                    "summary": summary,
                    "start": start_iso,
                    "end": end_dt.isoformat()
                }
                
                event_id = server.calendar_manager.add_event(calendar_name, event_data)
                
                return json.dumps({
                    "status": "success",
                    "message": f"Event '{summary}' created successfully",
                    "event_id": event_id,
                    "calendar": calendar_name,
                    "start": start_iso,
                    "duration": duration
                })
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e)})
        
        from langchain_core.tools import StructuredTool
        from pydantic import BaseModel, Field
        
        class CreateEventInput(BaseModel):
            calendar_name: str = Field(description="Name of the calendar to add event to")
            summary: str = Field(description="Event title/summary")
            start: str = Field(description="Start time - can be natural language like 'tomorrow at 2pm' or ISO format")
            duration: int = Field(default=60, description="Duration in minutes (default 60)")
        
        tools.append(StructuredTool(
            name="create_event",
            func=create_event_structured,
            description="Create a new calendar event with natural language date/time support",
            args_schema=CreateEventInput
        ))
        
        logger.info(f"Created {len(tools)} manual MCP tools")
        return tools
    
    async def cleanup(self):
        """
        Clean up MCP connections and resources.
        """
        logger.info("Cleaning up MCP integration resources")
        
        try:
            if self.cleanup_fn:
                await self.cleanup_fn()
                logger.info("MCP cleanup function called successfully")
                
            if hasattr(self, '_mcp_process') and self._mcp_process:
                self._mcp_process.terminate()
                self._mcp_process.wait()
                logger.info("MCP server process terminated")
                
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")
    
    def get_tool_names(self) -> List[str]:
        """
        Get names of all loaded tools.
        
        Returns:
            List of tool names
        """
        return [tool.name for tool in self.tools]
    
    def get_tool_descriptions(self) -> Dict[str, str]:
        """
        Get descriptions of all loaded tools.
        
        Returns:
            Dictionary mapping tool names to descriptions
        """
        return {tool.name: tool.description for tool in self.tools}
    
    def get_integration_info(self) -> Dict[str, Any]:
        """
        Get information about the current integration setup.
        
        Returns:
            Dictionary containing integration details
        """
        return {
            "integration_method": self._integration_method,
            "server_config": self.mcp_server_config,
            "tool_count": len(self.tools),
            "tool_names": self.get_tool_names()
        }

# Convenience function for easy usage
async def get_calendar_tools(config: Optional[Dict[str, Any]] = None) -> tuple[List[BaseTool], CalendarMCPIntegration]:
    """
    Convenience function to quickly get calendar tools and integration instance.
    
    Args:
        config: Optional MCP server configuration
        
    Returns:
        Tuple of (tools_list, integration_instance)
        
    Example:
        tools, integration = await get_calendar_tools()
        
        # Use tools with LangChain
        agent = create_openai_functions_agent(llm, prompt, tools)
        
        # Clean up when done
        await integration.cleanup()
    """
    integration = CalendarMCPIntegration(config)
    tools = await integration.initialize()
    return tools, integration

# Example usage
if __name__ == "__main__":
    async def main():
        """Example usage of the MCP integration"""
        integration = CalendarMCPIntegration()
        
        try:
            # Initialize and get tools
            tools = await integration.initialize()
            
            print(f"Loaded {len(tools)} calendar tools:")
            for tool in tools:
                print(f"  - {tool.name}: {tool.description}")
            
            # Test a tool
            if tools:
                first_tool = tools[0]
                print(f"\nTesting tool: {first_tool.name}")
                result = first_tool.run("")
                print(f"Result: {result}")
            
        except Exception as e:
            print(f"Error: {e}")
        finally:
            await integration.cleanup()
    
    asyncio.run(main())