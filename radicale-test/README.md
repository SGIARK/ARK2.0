# LangChain MCP Calendar Integration

Natural language calendar operations using LangChain + MCP + Radicale CalDAV server.

## Quick Setup

### 1. Install Dependencies
```bash
# Core packages
pip install langchain langchain-openai python-dotenv caldav

# Optional MCP packages (automatic fallback if missing)
pip install langchain-mcp-adapters mcp
```

### 2. Install Radicale Server
```bash
sudo apt update
sudo apt install radicale
```

### 3. Configure Radicale
Edit `/etc/radicale/config`:
```ini
[server]
hosts = localhost:5232

[auth]
# Authentication method
# Value: none | htpasswd | remote_user | http_x_remote_user
type = htpasswd
# Htpasswd filename
htpasswd_filename = /etc/radicale/users

[storage]
type = multifilesystem
filesystem_folder = /var/lib/radicale/collections
```

Add a user:
```bash
sudo apt-get install apache2-utils
sudo htpasswd -B /etc/radicale/users your_username
```

Start Radicale:
```bash
sudo systemctl enable radicale
sudo systemctl start radicale
```

### 4. Set Environment Variables
```bash
# Required for OpenAI
export OPENAI_API_KEY=your_api_key_here

# Required for Radicale
export RADICALE_URL=http://localhost:5232
export RADICALE_USERNAME=your_username
export RADICALE_PASSWORD=your_password
```

### 5. Run Example
```bash
python langchain_example_mcp.py
```

## Alternative: Local LLM Setup

Instead of OpenAI, use local models:

```bash
# Install Ollama
pip install langchain-ollama

# Start Ollama and pull a model
ollama serve
ollama pull llama3.2
```

Set environment:
```bash
export USE_LOCAL_LLM=true
export LOCAL_MODEL=llama3.2
# Remove OPENAI_API_KEY
```

## Usage Examples

- "What meetings do I have today?"
- "Schedule a meeting with John tomorrow at 2pm"
- "Show me all events next week"
- "Create a dentist appointment next Friday at 10am"

## Files

- `langchain_example_mcp.py` - Main example script
- `langchain_mcp_integration.py` - MCP integration layer
- `mcp_radicale_server.py` - MCP server implementation
- `radicale_calendar_manager.py` - Core calendar operations

## Troubleshooting

**Connection refused**: Check if Radicale is running with `systemctl status radicale`

**No calendars found**: Create a calendar via web interface at `http://localhost:5232/`

**Import errors**: Install missing dependencies or use manual fallback tools

**OpenAI errors**: Use local LLM setup or check API key