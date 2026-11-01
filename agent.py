"""
ReAct agent that researches a prospect and writes the brief (OpenAI Responses API).

Loop:  Reason (model thinks)  ->  Act (calls web_search)  ->  Observe (reads results)
Repeats until the model stops calling tools and writes the brief.

Everything that happens is pushed to the caller through `emit(event)`, so the
WebSocket can show it live. Event types:
    status       {"message"}
    thinking     {"text"}            - streamed reasoning summary
    text         {"text"}            - streamed answer text (the brief)
    tool_call    {"id", "query"}
    tool_result  {"id", "findings", "sources"} or {"id", "error"}

The previous Anthropic version is archived in archive/anthropic-reasoner/.
"""
import asyncio
import json
from typing import Awaitable, Callable

from openai import AsyncOpenAI

from config import settings
from prompts import FINAL_STEP_NOTE, SYSTEM_PROMPT, build_user_prompt
from tools import WEB_SEARCH_TOOL, web_search

Emit = Callable[[dict], Awaitable[None]]


class ProspectBriefAgent:
    def __init__(self) -> None:
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def run(self, name: str, company: str, role: str, notes: str, emit: Emit) -> str:
        """Research the prospect and return the brief as Markdown."""
        next_input: list | str = build_user_prompt(name, company, role, notes)
        previous_id: str | None = None  # server keeps the conversation; we send only new items

        for step in range(1, settings.max_steps + 1):
            is_last_step = step == settings.max_steps
            await emit({"type": "status", "message": f"Step {step}: reasoning"})

            # --- Reason ---
            response = await self._stream_turn(next_input, previous_id, emit, allow_tools=not is_last_step)
            previous_id = response.id

            if _refused(response):
                raise RuntimeError("The model declined to research this prospect.")

            calls = [item for item in response.output if item.type == "function_call"]
            if not calls:
                if response.status == "incomplete":
                    raise RuntimeError("Response was cut off (max output tokens). Try again.")
                return response.output_text.strip()  # done: the brief

            # --- Act + Observe (independent searches run in parallel) ---
            results = await asyncio.gather(*(self._run_tool(call, emit) for call in calls))
            next_input = list(results)
            if step + 1 == settings.max_steps:
                next_input.append({"role": "user", "content": FINAL_STEP_NOTE})

        raise RuntimeError("Agent stopped without producing a brief.")

    async def _stream_turn(self, new_input, previous_id: str | None, emit: Emit, allow_tools: bool):
        """Make one model call, streaming reasoning summary + text to the client as it arrives."""
        async with self.client.responses.stream(
            model=settings.reasoner_model,
            max_output_tokens=settings.reasoner_max_tokens,
            instructions=SYSTEM_PROMPT,  # not carried over by previous_response_id, so resend
            reasoning={"summary": "auto"},
            tools=[WEB_SEARCH_TOOL],
            tool_choice="auto" if allow_tools else "none",
            input=new_input,
            previous_response_id=previous_id,
        ) as stream:
            async for event in stream:
                if event.type == "response.reasoning_summary_text.delta":
                    await emit({"type": "thinking", "text": event.delta})
                elif event.type == "response.output_text.delta":
                    await emit({"type": "text", "text": event.delta})
            return await stream.get_final_response()

    async def _run_tool(self, call, emit: Emit) -> dict:
        """Execute one web_search call and return the function_call_output item for the model."""
        try:
            args = json.loads(call.arguments)
        except ValueError:
            args = None
        query = args.get("query") if isinstance(args, dict) else None
        if not isinstance(query, str) or not query.strip():
            return _tool_output(call.call_id, "INVALID_INPUT: expected {\"query\": \"<string>\"}")

        await emit({"type": "tool_call", "id": call.call_id, "query": query})
        try:
            result = await web_search(query)
        except Exception as exc:  # feed the failure back so the agent can adapt
            await emit({"type": "tool_result", "id": call.call_id, "error": str(exc)})
            return _tool_output(call.call_id, f"Search failed: {exc}")

        await emit({"type": "tool_result", "id": call.call_id, **result})
        return _tool_output(call.call_id, json.dumps(result))


def _tool_output(call_id: str, output: str) -> dict:
    return {"type": "function_call_output", "call_id": call_id, "output": output}


def _refused(response) -> bool:
    return any(
        part.type == "refusal"
        for item in response.output if item.type == "message"
        for part in item.content
    )
