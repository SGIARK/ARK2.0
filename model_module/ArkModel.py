from typing import Any, Dict, List, Optional, Union, AsyncIterator

from pydantic import BaseModel, Field
from langchain_core.language_models import BaseChatModel
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.messages import BaseMessage, AIMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.tools import BaseTool
from huggingface_hub import InferenceClient
import pprint 
pp = pprint.PrettyPrinter()




class ArkModelLink(BaseChatModel, BaseModel):
    """A custom chat model which interfaces with Hugging Face TGI and supports tool calling."""

    model_name: str = Field(default="tgi")
    base_url: str = Field(default="http://localhost:8080/v1")
    max_tokens: int = Field(default=1024)
    temperature: float = Field(default=0.7)
    tools: Optional[List[BaseTool]] = Field(default_factory=list)

    def _convert_tools(self) -> Optional[List[Dict[str, Any]]]:
        if not self.tools:
            return None

        def convert_tool(tool: BaseTool) -> Dict[str, Any]:
            properties = {'properties': {}}
            required = []
            for arg in tool.args:
                # print(tool.args[arg])
                title = tool.args[arg]['title']
                var_type = tool.args[arg]['type']
                properties['properties'][title] = {}
                properties['properties'][title]["type"] = str(var_type)
                required.append(title)
            

            converted_tool =  {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": {
                        "type": "object" ,
                        
                        "properties": properties,
                       }, 
                    "required" : required, 
                },

            }


            pp.pprint(converted_tool)


            exit()

            return converted_tool
        converted  =  [convert_tool(tool) for tool in self.tools]
        
        return converted 
    def _get_tool_by_name(self, name: str) -> Optional[BaseTool]:
        return next((tool for tool in self.tools if tool.name == name), None)

    def make_llm_call(self, messages: List[BaseMessage], tools: Optional[List[Dict[str, Any]]] = None) -> Union[str, Dict[str, Any]]:
        client = InferenceClient(base_url=self.base_url)

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": messages[0].content},
                {"role": "user", "content": messages[-1].content},
            ],
            "stream": False,
            "max_tokens": self.max_tokens,
        }

        if tools:
            payload["tools"] = tools
        print("********************PAYLOAD******************")
        pp.pprint(payload)
        print("********************PAYLOAD******************")

        output = client.chat.completions.create(**payload)
        choice = output.choices[0]
        print(choice)
        exit()
        tool_calls = getattr(choice.message, "tool_calls", None)
        if tool_calls:
            tool_call = tool_calls[0]
            function_call = getattr(tool_call, "function", {})

            if isinstance(function_call, dict):
                name = function_call.get("name", "")
                arguments = function_call.get("arguments", function_call.get("parameters", {}))
            else:
                name = getattr(function_call, "name", "")
                arguments = getattr(function_call, "arguments", getattr(function_call, "parameters", {}))

            return {
                "tool_name": name,
                "arguments": arguments,
                "tool_call_id": getattr(tool_call, "id", "tool_call_1")
            }

        return choice.message.content

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any
    ) -> ChatResult:

        tool_schemas = self._convert_tools()
        response = self.make_llm_call(messages, tools=tool_schemas)



        if isinstance(response, dict) and "tool_name" in response:

        
            tool = self._get_tool_by_name(response["tool_name"])
            if not tool:
                raise ValueError(f"Tool '{response['tool_name']}' was requested but not found")

            tool_output = tool.invoke(response["arguments"])
            content = str(tool_output)
        else:
            content = str(response)

        message = AIMessage(
            content=content,
            usage_metadata={
                "input_tokens": 123,
                "output_tokens": 456,
                "total_tokens": 579
            }
        )

        generation = ChatGeneration(message=message)
        return ChatResult(generations=[generation], llm_output=None)

    def bind_tools(self, tools: List[BaseTool]) -> "ArkModelLink":
        return self.copy(update={"tools": self.tools + tools})

    @property
    def _llm_type(self) -> str:
        return "hugging-face-tgi-server"

    async def _astream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any
    ) -> AsyncIterator[ChatGenerationChunk]:
        from sseclient import SSEClient
        import json

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": messages[0].content},
                {"role": "user", "content": messages[-1].content},
            ],
            "stream": True,
            "max_tokens": self.max_tokens,
        }

        tool_schemas = self._convert_tools()
        if tool_schemas:
            payload["tools"] = tool_schemas

        import requests
        headers = {"Accept": "text/event-stream", "Content-Type": "application/json"}
        response = requests.post(
            url=self.base_url + "chat/completions",
            headers=headers,
            json=payload,
            stream=True,
        )

        client = SSEClient(response)
        for event in client.events():
            if event.data.strip() == "[DONE]":
                break
            try:
                chunk_data = json.loads(event.data)
                delta = chunk_data["choices"][0].get("delta", {})
                if delta.get("content"):
                    yield ChatGenerationChunk(
                        message=AIMessage(content=delta["content"])
                    )
            except Exception:
                continue

