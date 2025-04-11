# used for testing mcp_radicale_bridge.py

import asyncio
import websockets
import json

async def test_mcp_client():
    uri = "ws://localhost:8765"
    async with websockets.connect(uri) as websocket:
        # Query events
        query = {
            "type": "query",
            "calendar": "Default Calendar",
            "start_date": "2025-04-12T00:00:00",
            "end_date": "2025-05-12T00:00:00"
        }
        
        print(f"Sending query: {json.dumps(query, indent=2)}")
        await websocket.send(json.dumps(query))
        response = await websocket.recv()
        print(f"Response: {json.dumps(json.loads(response), indent=2)}")
        
        # Create an event
        create = {
            "type": "create",
            "calendar": "Default Calendar",
            "event": {
                "summary": "MCP Test Meeting",
                "location": "Virtual",
                "description": "Testing MCP integration with Radicale",
                "start": "2025-04-15T10:00:00",
                "end": "2025-04-15T11:00:00"
            }
        }
        
        print(f"\nSending create: {json.dumps(create, indent=2)}")
        await websocket.send(json.dumps(create))
        response = await websocket.recv()
        print(f"Response: {json.dumps(json.loads(response), indent=2)}")
        
        # Extract event ID from response for update and delete tests
        create_response = json.loads(response)
        if create_response["status"] == "success":
            event_id = create_response["event_id"]
            
            # Update the event
            update = {
                "type": "update",
                "calendar": "Default Calendar",
                "event_id": event_id,
                "event": {
                    "summary": "Updated MCP Test Meeting",
                    "description": "This event was updated through MCP"
                }
            }
            
            print(f"\nSending update: {json.dumps(update, indent=2)}")
            await websocket.send(json.dumps(update))
            response = await websocket.recv()
            print(f"Response: {json.dumps(json.loads(response), indent=2)}")
            
            # Delete the event
            delete = {
                "type": "delete",
                "calendar": "Default Calendar",
                "event_id": event_id
            }
            
            print(f"\nSending delete: {json.dumps(delete, indent=2)}")
            await websocket.send(json.dumps(delete))
            response = await websocket.recv()
            print(f"Response: {json.dumps(json.loads(response), indent=2)}")

asyncio.run(test_mcp_client())
