import os

os.environ["OPENAI_API_KEY"] = "sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf"
os.environ["OPENAI_BASE_URL"] = "https://lab.iwhalecloud.com/gpt-proxy/v1"

from langchain.chat_models import init_chat_model
from langchain_core.tools import tool


@tool
def know(query: str) -> str:
    """Knowledge retrieval tool."""
    return f"Knowledge about: {query}"


print("Initializing model...")
model = init_chat_model(
    "openai:qwen3.5-plus",
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
    use_responses_api=False,
)

print(f"Model type: {type(model)}")
print(f"Model class: {model.__class__.__name__}")

# Check if model supports tool calling
print("\nChecking tool calling support:")
print(f"  Has 'bind_tools' method? {hasattr(model, 'bind_tools')}")
if hasattr(model, "bind_tools"):
    print(
        f"  bind_tools signature: {model.bind_tools.__doc__[:200] if model.bind_tools.__doc__ else 'No doc'}"
    )
    # Try to bind tools
    try:
        bound_model = model.bind_tools([know])
        print("  Successfully bound tools")
        print(f"  Bound model type: {type(bound_model)}")
    except Exception as e:
        print(f"  Error binding tools: {e}")

# Check if model supports function calling via other attributes
print(f"\n  Has 'bind' method? {hasattr(model, 'bind')}")
if hasattr(model, "bind"):
    print(f"  bind signature: {model.bind.__doc__[:200] if model.bind.__doc__ else 'No doc'}")

# Check if model is an OpenAI model
print(f"\n  Is OpenAI model? {'openai' in model.__class__.__module__.lower()}")
print(f"  Module: {model.__class__.__module__}")

# Let's also inspect the model's default parameters
print(f"\nModel parameters:")
for attr in ["model_name", "model", "temperature", "max_tokens"]:
    if hasattr(model, attr):
        print(f"  {attr}: {getattr(model, attr)}")

# Try a simple prompt to see if tool calls are returned
print("\nTesting simple prompt without tool binding:")
from langchain_core.messages import HumanMessage

messages = [HumanMessage(content="What is Python?")]
try:
    response = model.invoke(messages)
    print(f"Response type: {type(response)}")
    print(f"Response content: {response.content[:200]}")
    print(f"Response has tool_calls? {hasattr(response, 'tool_calls')}")
    if hasattr(response, "tool_calls"):
        print(f"Tool calls: {response.tool_calls}")
except Exception as e:
    print(f"Error invoking model: {e}")

# Now test with tool binding
print("\nTesting with tool binding (if supported):")
if hasattr(model, "bind_tools"):
    bound_model = model.bind_tools([know])
    messages = [HumanMessage(content="Use the know tool to query about Python.")]
    try:
        response = bound_model.invoke(messages)
        print(f"Response type: {type(response)}")
        print(f"Response content: {response.content[:200] if response.content else 'None'}")
        print(f"Response has tool_calls? {hasattr(response, 'tool_calls')}")
        if hasattr(response, "tool_calls") and response.tool_calls:
            print(f"Tool calls: {response.tool_calls}")
        else:
            print("No tool calls generated.")
    except Exception as e:
        print(f"Error invoking bound model: {e}")
else:
    print("Model does not support bind_tools.")
