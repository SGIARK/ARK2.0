# example radicale-mcp bridge server
# reads radicale auth info from .env
# deps: pip install websockets caldav asyncio 
# use mcp_client_test.py for testing
# see mcp-radicale.service for installation

import json
import asyncio
import websockets
import caldav
import os
import logging
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("mcp-radicale-bridge")

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Radicale connection settings from .env file
RADICALE_URL = os.getenv("RADICALE_URL", "http://localhost:5232")
RADICALE_USERNAME = os.getenv("RADICALE_USERNAME", "")
RADICALE_PASSWORD = os.getenv("RADICALE_PASSWORD", "")

# MCP Server settings
MCP_HOST = "localhost"
MCP_PORT = 8765

class MCPRadicaleBridge:
    def __init__(self):
        self.client = caldav.DAVClient(url=RADICALE_URL, username=RADICALE_USERNAME, password=RADICALE_PASSWORD)
        
    async def connect(self):
        """Establish connection to Radicale server"""
        try:
            self.principal = self.client.principal()
            self.calendars = self.principal.calendars()
            if not self.calendars:
                logger.warning("No calendars found in Radicale")
                return False
            logger.info(f"Connected to Radicale, found {len(self.calendars)} calendars")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Radicale: {e}")
            return False
    
    async def handle_mcp_request(self, message):
        """Process an incoming MCP request"""
        try:
            data = json.loads(message)
            
            # Handle different MCP request types
            if data.get("type") == "query":
                return await self.handle_query(data)
            elif data.get("type") == "create":
                return await self.handle_create(data)
            elif data.get("type") == "update":
                return await self.handle_update(data)
            elif data.get("type") == "delete":
                return await self.handle_delete(data)
            else:
                return {"status": "error", "message": "Unknown request type"}
                
        except json.JSONDecodeError:
            return {"status": "error", "message": "Invalid JSON"}
        except Exception as e:
            logger.error(f"Error handling request: {e}")
            return {"status": "error", "message": str(e)}
    
    async def handle_query(self, data):
        """Handle query requests"""
        calendar_name = data.get("calendar", None)
        start_date = data.get("start_date", None)
        end_date = data.get("end_date", None)
        
        calendar = self._find_calendar(calendar_name)
        if not calendar:
            return {"status": "error", "message": "Calendar not found"}
        
        # Convert string dates to datetime objects if provided
        if start_date:
            start_date = datetime.fromisoformat(start_date)
        else:
            start_date = datetime.now()
            
        if end_date:
            end_date = datetime.fromisoformat(end_date)
        else:
            end_date = start_date + timedelta(days=30)  # Default: next 30 days
        
        try:
            # Get events in the date range
            events = calendar.date_search(start=start_date, end=end_date)
            
            # Format events for MCP response
            event_list = []
            for event in events:
                event_data = event.data
                event_list.append({
                    "id": event.id,
                    "summary": self._extract_property(event_data, "SUMMARY"),
                    "start": self._extract_property(event_data, "DTSTART"),
                    "end": self._extract_property(event_data, "DTEND"),
                    "location": self._extract_property(event_data, "LOCATION"),
                    "description": self._extract_property(event_data, "DESCRIPTION")
                })
                
            return {
                "status": "success", 
                "calendar": calendar.name,
                "events": event_list
            }
            
        except Exception as e:
            logger.error(f"Error searching events: {e}")
            return {"status": "error", "message": str(e)}
    
    async def handle_create(self, data):
        """Handle event creation requests"""
        calendar_name = data.get("calendar", None)
        event_data = data.get("event", {})
        
        if not event_data:
            return {"status": "error", "message": "No event data provided"}
            
        calendar = self._find_calendar(calendar_name)
        if not calendar:
            return {"status": "error", "message": "Calendar not found"}
        
        try:
            # Parse event details
            summary = event_data.get("summary", "New Event")
            location = event_data.get("location", "")
            description = event_data.get("description", "")
            
            # Parse dates
            start_time = datetime.fromisoformat(event_data.get("start"))
            
            if "end" in event_data:
                end_time = datetime.fromisoformat(event_data.get("end"))
            else:
                # Default to 1 hour duration
                end_time = start_time + timedelta(hours=1)
            
            # Create the event
            event = calendar.save_event(
                dtstart=start_time,
                dtend=end_time,
                summary=summary,
                location=location,
                description=description
            )
            
            return {
                "status": "success",
                "message": f"Event '{summary}' created successfully",
                "event_id": event.id
            }
            
        except Exception as e:
            logger.error(f"Error creating event: {e}")
            return {"status": "error", "message": str(e)}
    
    async def handle_update(self, data):
        """Handle event update requests"""
        calendar_name = data.get("calendar", None)
        event_id = data.get("event_id", None)
        event_data = data.get("event", {})
        
        if not event_id or not event_data:
            return {"status": "error", "message": "Event ID and data are required"}
            
        calendar = self._find_calendar(calendar_name)
        if not calendar:
            return {"status": "error", "message": "Calendar not found"}
        
        try:
            # Find the event by ID
            event = None
            for e in calendar.events():
                if e.id == event_id:
                    event = e
                    break
            
            if not event:
                return {"status": "error", "message": "Event not found"}
            
            # Parse and update event details
            ical_data = event.data
            
            # Build updated iCalendar data
            # (This is a simplified approach - a full implementation would need
            # to properly parse and update the iCalendar data)
            
            # Create the event with updated fields
            if "summary" in event_data:
                ical_data = self._update_property(ical_data, "SUMMARY", event_data["summary"])
            if "location" in event_data:
                ical_data = self._update_property(ical_data, "LOCATION", event_data["location"])
            if "description" in event_data:
                ical_data = self._update_property(ical_data, "DESCRIPTION", event_data["description"])
            
            # Update the event
            event.data = ical_data
            
            return {
                "status": "success",
                "message": f"Event '{event_id}' updated successfully"
            }
            
        except Exception as e:
            logger.error(f"Error updating event: {e}")
            return {"status": "error", "message": str(e)}
    
    async def handle_delete(self, data):
        """Handle event deletion requests"""
        calendar_name = data.get("calendar", None)
        event_id = data.get("event_id", None)
        
        if not event_id:
            return {"status": "error", "message": "Event ID is required"}
            
        calendar = self._find_calendar(calendar_name)
        if not calendar:
            return {"status": "error", "message": "Calendar not found"}
        
        try:
            # Find the event by ID
            event = None
            for e in calendar.events():
                if e.id == event_id:
                    event = e
                    break
            
            if not event:
                return {"status": "error", "message": "Event not found"}
            
            # Delete the event
            event.delete()
            
            return {
                "status": "success",
                "message": f"Event '{event_id}' deleted successfully"
            }
            
        except Exception as e:
            logger.error(f"Error deleting event: {e}")
            return {"status": "error", "message": str(e)}
    
    def _find_calendar(self, calendar_name):
        """Find a calendar by name"""
        if not calendar_name:
            # Use first calendar if name not specified
            return self.calendars[0] if self.calendars else None
            
        for calendar in self.calendars:
            if calendar.name.lower() == calendar_name.lower():
                return calendar
        return None
    
    def _extract_property(self, ical_data, property_name):
        """Extract a property from iCalendar data (simplified)"""
        # This is a very simplified property extractor
        # A real implementation would use an iCalendar parser
        for line in ical_data.splitlines():
            if line.startswith(property_name + ":"):
                return line.split(":", 1)[1]
        return ""
    
    def _update_property(self, ical_data, property_name, new_value):
        """Update a property in iCalendar data (simplified)"""
        # This is a very simplified property updater
        # A real implementation would use an iCalendar parser
        new_lines = []
        found = False
        
        for line in ical_data.splitlines():
            if line.startswith(property_name + ":"):
                new_lines.append(f"{property_name}:{new_value}")
                found = True
            else:
                new_lines.append(line)
                
        if not found:
            # Add the property if it doesn't exist
            # (This is a simplification - proper placement in the iCal structure would be needed)
            new_lines.append(f"{property_name}:{new_value}")
            
        return "\n".join(new_lines)

async def websocket_handler(websocket, path):
    """Handle WebSocket connections"""
    logger.info(f"New connection from {websocket.remote_address}")
    
    # Create a bridge instance for this connection
    bridge = MCPRadicaleBridge()
    if not await bridge.connect():
        await websocket.send(json.dumps({"status": "error", "message": "Failed to connect to Radicale"}))
        return
    
    try:
        async for message in websocket:
            logger.info(f"Received message: {message}")
            
            # Process the request
            response = await bridge.handle_mcp_request(message)
            
            # Send response back to client
            await websocket.send(json.dumps(response))
    except websockets.exceptions.ConnectionClosed:
        logger.info("Connection closed")
    except Exception as e:
        logger.error(f"Error handling websocket: {e}")

async def main():
    """Start the MCP server"""
    logger.info(f"Starting MCP server on {MCP_HOST}:{MCP_PORT}")
    
    async with websockets.serve(websocket_handler, MCP_HOST, MCP_PORT):
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())
