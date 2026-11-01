# Prospect Brief Engine

Enter a prospect's **name, company and role**. A ReAct agent researches them on the web
and writes a brief (intro header, basic info, professional summary, recent activities,
sources). The agent's reasoning, searches and the brief stream live over a WebSocket.

```
Browser (static/index.html)
   │  WebSocket /ws/brief
   ▼
main.py ──► agent.py  (OpenAI gpt-5.6-luna – the reasoner, ReAct loop)
                │  tool call: web_search(query)
                ▼
            tools/web_search.py  (OpenAI gpt-5.6-luna + web_search) ──► the web
```

## Files

| File | What it does |
|---|---|
| `main.py` | FastAPI app: serves the page and the `/ws/brief` WebSocket |
| `agent.py` | ReAct loop: Reason → Act (search) → Observe, streams events |
| `tools/web_search.py` | The `web_search` tool, backed by an OpenAI model with web search |
| `prompts.py` | System prompt (research rules + brief format) and the user prompt |
| `config.py` | Settings from env vars |
| `static/index.html` | Input form, live reasoning panel, rendered brief |

## Run

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # then put your real keys in .env
uvicorn main:app --reload
```

Open http://localhost:8000.

## WebSocket protocol

Send:
```json
{"name": "Jane Doe", "company": "Acme", "role": "VP Sales", "notes": "optional"}
```
Receive a stream of events:

| type | fields | meaning |
|---|---|---|
| `status` | `message` | step progress |
| `thinking` | `text` | reasoner's thinking, streamed |
| `tool_call` | `id`, `query` | agent started a web search |
| `tool_result` | `id`, `findings`, `sources` (or `error`) | search finished |
| `text` | `text` | brief text, streamed |
| `done` | `brief` | final brief (Markdown) |
| `error` | `message` | something failed |

## History
The reasoner used to be Claude (Anthropic API). The previous version is archived in
`../archive/anthropic-reasoner/` (see its `NOTES.md` for how to restore it).
Only `OPENAI_API_KEY` is needed now.
