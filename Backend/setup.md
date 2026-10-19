# Backend setup

```bash
pip install -r requirements.txt       # from the project root
cp .env.example .env                  # then put your key in ANTHROPIC_API_KEY
```

## Run the router

```bash
python Backend/SupportAgent/run_pipeline.py                  # the four demo queries
python Backend/SupportAgent/run_pipeline.py "your question"  # one of your own
```

Each run calls the Claude API, so it costs money.

## Test

```bash
python Backend/SupportAgent/test_schemas.py   # offline, no API key needed
```

## Layout

`Backend/` is the package root, so every import starts with `SupportAgent.`.

| Path | Holds |
|---|---|
| `SupportAgent/config.py` | paths, model name, turn limit (reads `.env`) |
| `SupportAgent/Retrieval/catalogue.py` | reads `KnowledgeBase/`, allowlists filenames |
| `SupportAgent/Router/find_md_agent.py` | `find_md(query)` -> `(RouteDecision, {filename: text})` |
| `SupportAgent/Router/schemas.py` | `RouteDecision` and its rules |
| `KnowledgeBase/Catalog.md` | the routing index the model reads every call |
