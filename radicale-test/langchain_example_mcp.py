"""
Updated LangChain Example using MCP Integration

This example demonstrates how to use the new MCP-based LangChain integration
for calendar operations. It replaces the direct tool adapter approach with
the standardized MCP integration.

Features:
- MCP-based tool loading
- Async agent operations
- Comprehensive error handling
- Natural language calendar operations
- Automatic cleanup

Usage:
    python langchain_example_mcp.py

Dependencies:
    pip install langchain langchain-openai langchain-mcp-adapters
    # Set OPENAI_API_KEY in .env file
"""

import os
import asyncio
import logging
from typing import List, Dict, Any

# LangChain imports
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema import SystemMessage
from langchain_core.tools import BaseTool

# Environment configuration
from dotenv import load_dotenv

# Local imports
from langchain_mcp_integration import CalendarMCPIntegration, get_calendar_tools

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("langchain-mcp-example")

class MCPCalendarAgent:
    """
    LangChain agent with MCP-based calendar tools.
    
    This class provides a conversational interface for calendar operations
    using LangChain agents powered by MCP tools from the Radicale calendar server.
    """
    
    def __init__(self, model: str = "gpt-3.5-turbo", temperature: float = 0):
        """
        Initialize the MCP calendar agent.
        
        Args:
            model: OpenAI model to use for the agent
            temperature: Temperature setting for the LLM
        """
        load_dotenv()
        
        self.model = model
        self.temperature = temperature
        self.mcp_integration: CalendarMCPIntegration = None
        self.agent_executor: AgentExecutor = None
        self.tools: List[BaseTool] = []
        
        # Validate LLM configuration
        use_local = os.getenv("USE_LOCAL_LLM", "false").lower() == "true"
        if not use_local and not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY not found. Set USE_LOCAL_LLM=true to use local models.")
    
    async def initialize(self):
        """
        Initialize the MCP integration and create the LangChain agent.
        """
        logger.info("Initializing MCP calendar agent...")
        
        try:
            # Initialize MCP integration and get tools
            self.tools, self.mcp_integration = await get_calendar_tools()
            
            logger.info(f"Loaded {len(self.tools)} MCP tools: {[tool.name for tool in self.tools]}")
            
            # Create the system prompt
            system_prompt = self._create_system_prompt()
            
            # Create the prompt template
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=system_prompt),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ])
            
            # Initialize the LLM
            use_local = os.getenv("USE_LOCAL_LLM", "false").lower() == "true"
            if use_local:
                try:
                    from langchain_ollama import ChatOllama
                    local_model = os.getenv("LOCAL_MODEL", "llama3.2")
                    llm = ChatOllama(
                        model=local_model,
                        temperature=self.temperature
                    )
                except ImportError:
                    raise ImportError("Install langchain-ollama for local LLM support: pip install langchain-ollama")
            else:
                llm = ChatOpenAI(
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=4000,
                    api_key=os.getenv("OPENAI_API_KEY")
                )
            
            # Create the agent
            agent = create_openai_functions_agent(
                llm=llm,
                prompt=prompt,
                tools=self.tools
            )
            
            # Create the agent executor
            self.agent_executor = AgentExecutor(
                agent=agent,
                tools=self.tools,
                verbose=True,
                max_iterations=10,
                early_stopping_method="generate"
            )
            
            logger.info("MCP calendar agent initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize MCP calendar agent: {e}")
            raise
    
    def _create_system_prompt(self) -> str:
        """
        Create a comprehensive system prompt for the calendar agent.
        
        Returns:
            System prompt string
        """
        tool_descriptions = "\n".join([
            f"- {tool.name}: {tool.description}" 
            for tool in self.tools
        ])
        
        return f"""You are a helpful and efficient calendar assistant powered by MCP (Model Context Protocol) tools.

You can help users manage their calendar events using the following tools:
{tool_descriptions}

Guidelines for calendar operations:
1. Always confirm details before creating or modifying events
2. Use clear, natural language in your responses
3. When dates/times are ambiguous, ask for clarification
4. Provide helpful summaries after completing operations
5. Handle errors gracefully and suggest alternatives

Date/Time Format Guidelines:
- Accept natural language dates (e.g., "tomorrow", "next Friday", "June 1st")
- Convert them to ISO format (YYYY-MM-DDTHH:MM:SS) for tool calls
- Default to 1-hour duration if end time not specified
- Assume current timezone unless specified

Calendar Selection:
- If no calendar is specified, list available calendars first
- Ask user to choose if multiple calendars are available
- Remember user preferences within the conversation

Error Handling:
- If a tool operation fails, explain what went wrong
- Suggest corrections or alternatives
- Never expose technical error details to users

Example Interactions:
- "What meetings do I have tomorrow?" → Get events for tomorrow
- "Schedule a meeting with John at 2pm" → Create event (ask for date if missing)
- "Cancel my 3pm meeting" → Find and delete the event
- "Move my morning meeting to afternoon" → Update event time

Always be helpful, accurate, and efficient in your calendar management assistance."""
    
    async def run_operation(self, operation: str, chat_history: List[Dict[str, str]] = None) -> str:
        """
        Run a calendar operation using the MCP-based agent.
        
        Args:
            operation: Natural language description of the calendar operation
            chat_history: Previous conversation history
            
        Returns:
            Agent response as a string
        """
        if not self.agent_executor:
            await self.initialize()
        
        if chat_history is None:
            chat_history = []
        
        try:
            logger.info(f"Processing operation: {operation}")
            
            result = await self.agent_executor.ainvoke({
                "input": operation,
                "chat_history": chat_history
            })
            
            response = result["output"]
            logger.info(f"Operation completed successfully")
            return response
            
        except Exception as e:
            error_msg = f"Error performing calendar operation: {str(e)}"
            logger.error(error_msg)
            return error_msg
    
    async def run_interactive_session(self):
        """
        Run an interactive chat session with the calendar agent.
        """
        if not self.agent_executor:
            await self.initialize()
        
        print("\n🗓️  Welcome to the MCP Calendar Assistant!")
        print("Type your calendar requests in natural language.")
        print("Examples: 'What meetings do I have today?', 'Schedule a meeting with John tomorrow at 2pm'")
        print("Type 'quit', 'exit', or 'bye' to end the session.\n")
        
        chat_history = []
        
        while True:
            try:
                # Get user input
                user_input = input("You: ").strip()
                
                # Check for exit commands
                if user_input.lower() in ['quit', 'exit', 'bye', 'q']:
                    print("👋 Goodbye! Have a great day!")
                    break
                
                if not user_input:
                    continue
                
                # Process the request
                print("🤔 Processing your request...")
                response = await self.run_operation(user_input, chat_history)
                
                # Display response
                print(f"Assistant: {response}\n")
                
                # Update chat history
                chat_history.append({"role": "human", "content": user_input})
                chat_history.append({"role": "assistant", "content": response})
                
                # Keep chat history manageable
                if len(chat_history) > 10:
                    chat_history = chat_history[-10:]
                
            except KeyboardInterrupt:
                print("\n👋 Session interrupted. Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                print("Please try again or type 'quit' to exit.\n")
    
    async def cleanup(self):
        """Clean up MCP integration resources."""
        if self.mcp_integration:
            await self.mcp_integration.cleanup()
            logger.info("MCP integration cleaned up")
    
    def get_integration_info(self) -> Dict[str, Any]:
        """Get information about the MCP integration."""
        if self.mcp_integration:
            return self.mcp_integration.get_integration_info()
        return {"status": "not_initialized"}

# Predefined example operations
EXAMPLE_OPERATIONS = [
    "What calendars do I have access to?",
    "List my events for today",
    "Add a meeting with John tomorrow at 2pm for 1 hour in my work calendar",
    "Show me all events in my calendar for the next 7 days",
    "Create a dentist appointment next Friday at 10am"
]

async def run_examples():
    """Run predefined example operations."""
    print("🚀 Running MCP Calendar Agent Examples\n")
    
    agent = MCPCalendarAgent()
    
    try:
        await agent.initialize()
        
        # Display integration info
        info = agent.get_integration_info()
        print(f"📋 Integration Info:")
        print(f"   Method: {info.get('integration_method', 'unknown')}")
        print(f"   Tools: {info.get('tool_count', 0)} loaded")
        print(f"   Tool Names: {', '.join(info.get('tool_names', []))}\n")
        
        # Run example operations
        for i, operation in enumerate(EXAMPLE_OPERATIONS, 1):
            print(f"📝 Example {i}: {operation}")
            print("🤔 Processing...")
            
            try:
                result = await agent.run_operation(operation)
                print(f"✅ Result: {result}\n")
                
                # Add a small delay between operations
                await asyncio.sleep(1)
                
            except Exception as e:
                print(f"❌ Error: {e}\n")
        
        print("✨ All examples completed!")
        
    except Exception as e:
        print(f"❌ Failed to run examples: {e}")
    finally:
        await agent.cleanup()

async def main():
    """Main entry point with user choice of mode."""
    print("🗓️  MCP Calendar Agent")
    print("====================")
    print("Choose a mode:")
    print("1. Run interactive session")
    print("2. Run predefined examples")
    print("3. Quick test")
    
    try:
        choice = input("\nEnter your choice (1, 2, or 3): ").strip()
        
        if choice == "1":
            agent = MCPCalendarAgent()
            try:
                await agent.run_interactive_session()
            finally:
                await agent.cleanup()
                
        elif choice == "2":
            await run_examples()
            
        elif choice == "3":
            print("\n🧪 Running quick test...")
            agent = MCPCalendarAgent()
            try:
                await agent.initialize()
                result = await agent.run_operation("List my available calendars")
                print(f"✅ Quick test result: {result}")
            finally:
                await agent.cleanup()
                
        else:
            print("❌ Invalid choice. Please run the script again.")
            
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())