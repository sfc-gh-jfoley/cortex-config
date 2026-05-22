# Orchestration Instructions

Route queries based on intent:
- Investigation requests ("investigate", "why", "analyze") → use search_tool first, then analyze_tool
- Data lookup requests ("show", "list", "get") → use query_tool directly
- Help requests → respond directly without tools

If a tool returns an error, retry once before reporting failure.
