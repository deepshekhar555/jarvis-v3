"""
realtime_service.py — Realtime chat with Tavily web search + OpenAI GPT.
Handles streaming for /chat/realtime/stream endpoint.
"""
import logging
from typing import AsyncGenerator, List, Dict, Optional
import json

logger = logging.getLogger(__name__)


async def search_web(query: str) -> Dict:
    """Search the web using Tavily. Returns structured results."""
    from config import TAVILY_API_KEY
    if not TAVILY_API_KEY:
        return {"query": query, "answer": "", "results": []}
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=TAVILY_API_KEY)
        response = client.search(
            query=query,
            search_depth="basic",
            max_results=5,
            include_answer=True,
        )
        return {
            "query": query,
            "answer": response.get("answer", ""),
            "results": [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", "")[:500],
                }
                for r in response.get("results", [])
            ]
        }
    except ImportError:
        logger.warning("tavily-python not installed. Web search unavailable.")
        return {"query": query, "answer": "", "results": []}
    except Exception as e:
        logger.error("Tavily search error: %s", e)
        return {"query": query, "answer": "", "results": []}


async def stream_realtime_chat(
    message: str,
    history: List[Dict],
    session_id: str,
) -> AsyncGenerator[str, None]:
    """
    Stream a realtime chat response: search web, then stream GPT answer.
    Yields SSE-formatted JSON strings.
    """
    from config import (
        OPENAI_API_KEY, OPENAI_MODEL,
        JARVIS_SYSTEM_PROMPT, REALTIME_CHAT_ADDENDUM, TAVILY_API_KEY,
    )
    from app.utils.time_info import get_current_time_info
    from app.services.vector_store import retrieve_relevant_context
    from app.services.memory_service import get_memory_context
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

    # Yield activity: starting search
    yield f"data: {json.dumps({'type': 'activity', 'event': 'Routing', 'detail': 'Realtime mode — searching the web...'})}\n\n"

    # Perform web search
    search_data = await search_web(message)

    # Yield search results to frontend
    if search_data.get("results"):
        num_results = len(search_data["results"])
        query_str = search_data["query"]
        yield f"data: {json.dumps({'type': 'search_results', **search_data})}\n\n"
        yield f"data: {json.dumps({'type': 'activity', 'event': 'Web Search', 'detail': f'Found {num_results} results for: {query_str}'})}\n\n"
    else:
        yield f"data: {json.dumps({'type': 'activity', 'event': 'Web Search', 'detail': 'No search results (Tavily key not set). Answering from knowledge.'})}\n\n"

    # Build context
    time_info = get_current_time_info()
    relevant_context = retrieve_relevant_context(message)
    memory_context = get_memory_context()

    system_content = JARVIS_SYSTEM_PROMPT + REALTIME_CHAT_ADDENDUM
    system_content += f"\n\n{time_info}"

    # Inject search results
    if search_data.get("answer"):
        system_content += f"\n\n=== AI-SYNTHESIZED WEB ANSWER ===\n{search_data['answer']}"
    if search_data.get("results"):
        system_content += "\n\n=== WEB SEARCH RESULTS ==="
        for i, r in enumerate(search_data["results"][:4], 1):
            system_content += f"\n\n[{i}] {r['title']}\nURL: {r['url']}\n{r['content']}"
    if relevant_context:
        system_content += f"\n\n=== PERSONAL CONTEXT ===\n{relevant_context}"
    if memory_context:
        system_content += f"\n\n=== USER-SAVED MEMORY ===\n{memory_context}"

    # Build message history
    messages = [SystemMessage(content=system_content)]
    for msg in history[-20:]:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    messages.append(HumanMessage(content=message))

    from app.services.tools_service import ALL_TOOLS

    # Stream from OpenAI
    llm = ChatOpenAI(
        api_key=OPENAI_API_KEY,
        model=OPENAI_MODEL,
        streaming=True,
        temperature=0.7,
        max_tokens=612,
    )
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    full_response = ""
    try:
        response = await llm_with_tools.ainvoke(messages)

        if response.tool_calls:
            messages.append(response)
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                
                yield f"data: {json.dumps({'type': 'activity', 'event': 'Skill', 'detail': f'Executing {tool_name}...'})}\n\n"
                
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

            async for chunk in llm.astream(messages):
                token = chunk.content
                if token:
                    full_response += token
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        else:
            token = response.content
            if token:
                full_response = token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
    except Exception as e:
        from app.services.provider_errors import describe_provider_error

        logger.error(
            "OpenAI realtime streaming failed (%s, status %s)",
            type(e).__name__,
            getattr(e, "status_code", "unknown"),
        )
        error_msg = describe_provider_error(e)
        yield f"data: {json.dumps({'type': 'token', 'content': error_msg})}\n\n"
        full_response = error_msg

    yield f"data: {json.dumps({'type': 'done', 'session_id': session_id, 'full_response': full_response})}\n\n"
