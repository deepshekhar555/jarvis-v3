"""
openai_service.py — General chat using OpenAI GPT with LangChain.
Handles streaming responses for the /chat/stream endpoint.
"""
import logging
from typing import AsyncGenerator, List, Dict, Optional

logger = logging.getLogger(__name__)


async def stream_general_chat(
    message: str,
    history: List[Dict],
    session_id: str,
) -> AsyncGenerator[str, None]:
    """
    Stream a general chat response from OpenAI GPT with Tool calling support.
    Yields SSE-formatted JSON strings.
    """
    from config import (
        OPENAI_API_KEY, OPENAI_MODEL,
        JARVIS_SYSTEM_PROMPT, GENERAL_CHAT_ADDENDUM,
    )
    from app.utils.time_info import get_current_time_info
    from app.services.vector_store import retrieve_relevant_context
    from app.services.memory_service import get_memory_context
    from app.services.tools_service import ALL_TOOLS
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
    import json

    # Build system prompt with time and context
    time_info = get_current_time_info()
    relevant_context = retrieve_relevant_context(message)
    memory_context = get_memory_context()
    system_content = JARVIS_SYSTEM_PROMPT + GENERAL_CHAT_ADDENDUM
    system_content += f"\n\n{time_info}"
    if relevant_context:
        system_content += f"\n\n=== PERSONAL CONTEXT ===\n{relevant_context}"
    if memory_context:
        system_content += f"\n\n=== USER-SAVED MEMORY ===\n{memory_context}"

    # Build message list
    messages = [SystemMessage(content=system_content)]
    for msg in history[-20:]:  # Last 20 messages for context
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    messages.append(HumanMessage(content=message))

    # Stream from OpenAI with Tools
    llm = ChatOpenAI(
        api_key=OPENAI_API_KEY,
        model=OPENAI_MODEL,
        streaming=True,
        temperature=0.7,
        max_tokens=1024,
    )
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    full_response = ""
    try:
        # Initial check for tool calls
        response = await llm_with_tools.ainvoke(messages)
        
        if response.tool_calls:
            messages.append(response)
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                
                yield f"data: {json.dumps({'type': 'activity', 'event': 'Skill', 'detail': f'Executing {tool_name}...'})}\n\n"
                
                # Execute the tool
                tool_obj = next((t for t in ALL_TOOLS if t.name == tool_name), None)
                if tool_obj:
                    result = await tool_obj.ainvoke(tool_args)
                    from app.services.action_approval_service import get_approval_event

                    approval = get_approval_event(result)
                    if approval:
                        yield f"data: {json.dumps({'type': 'approval_required', 'approval': approval})}\n\n"
                        result = (
                            "This action is awaiting the user's explicit approval. "
                            "It has not been executed."
                        )
                    
                    # Handle special tool results like image paths
                    if (
                        tool_name == "generate_image"
                        and not approval
                        and result
                        and not result.startswith("Error")
                    ):
                        yield f"data: {json.dumps({'type': 'image', 'path': result})}\n\n"
                    
                    messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))
                else:
                    messages.append(ToolMessage(content=f"Error: Tool {tool_name} not found.", tool_call_id=tool_call["id"]))

            # Stream second call
            async for chunk in llm.astream(messages):
                token = chunk.content
                if token:
                    full_response += token
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        else:
            # No tools, just content
            token = response.content
            if token:
                full_response = token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

    except Exception as e:
        from app.services.provider_errors import describe_provider_error

        logger.error(
            "OpenAI streaming failed (%s, status %s)",
            type(e).__name__,
            getattr(e, "status_code", "unknown"),
        )
        error_msg = describe_provider_error(e)
        yield f"data: {json.dumps({'type': 'token', 'content': error_msg})}\n\n"
        full_response = error_msg

    yield f"data: {json.dumps({'type': 'done', 'session_id': session_id, 'full_response': full_response})}\n\n"


async def classify_query(message: str) -> str:
    """
    Use the brain model to classify a query as 'general' or 'realtime'.
    Returns 'general' or 'realtime'.
    """
    from config import OPENAI_API_KEY, OPENAI_BRAIN_MODEL, BRAIN_SYSTEM_PROMPT
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage

    try:
        llm = ChatOpenAI(
            api_key=OPENAI_API_KEY,
            model=OPENAI_BRAIN_MODEL,
            streaming=False,
            temperature=0,
            max_tokens=5,
        )
        messages = [
            SystemMessage(content=BRAIN_SYSTEM_PROMPT),
            HumanMessage(content=message),
        ]
        response = await llm.ainvoke(messages)
        result = response.content.strip().lower()
        if "realtime" in result:
            return "realtime"
        return "general"
    except Exception as e:
        logger.warning(
            "Brain classification failed (%s, status %s). Defaulting to general.",
            type(e).__name__,
            getattr(e, "status_code", "unknown"),
        )
        return "general"
