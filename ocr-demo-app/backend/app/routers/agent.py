from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from ..models.agent import AgentRequest, AgentResponse
from ..services.agent_service import ask_agent

router = APIRouter()


@router.post("/ask", response_model=AgentResponse)
async def ask_agent_question(request: AgentRequest) -> AgentResponse:
    return ask_agent(request)


@router.get("/assistant/{session_id}", response_class=HTMLResponse)
async def agent_assistant_page(session_id: str) -> HTMLResponse:
    html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>OCR Agent Assistant</title>
  <style>
    body {{
      font-family: Arial, sans-serif;
      margin: 0;
      background: #f5f7fb;
      color: #222;
    }}
    .wrap {{
      max-width: 980px;
      margin: 30px auto;
      background: white;
      border-radius: 12px;
      padding: 24px;
      box-shadow: 0 8px 24px rgba(0,0,0,0.08);
    }}
    h1 {{
      margin-top: 0;
    }}
    .meta {{
      color: #666;
      margin-bottom: 16px;
    }}
    textarea {{
      width: 100%;
      min-height: 120px;
      border-radius: 8px;
      border: 1px solid #d0d7de;
      padding: 12px;
      font-size: 15px;
      box-sizing: border-box;
    }}
    button {{
      margin-top: 12px;
      padding: 10px 18px;
      border: none;
      border-radius: 8px;
      background: #1f6feb;
      color: white;
      font-size: 15px;
      cursor: pointer;
    }}
    button:hover {{
      background: #1859c9;
    }}
    .panel {{
      margin-top: 20px;
      padding: 16px;
      background: #fafbfc;
      border-radius: 10px;
      border: 1px solid #e5e7eb;
      white-space: pre-wrap;
    }}
    .source {{
      margin-top: 10px;
      padding: 10px;
      border-radius: 8px;
      background: #fff;
      border: 1px solid #e5e7eb;
    }}
    .label {{
      font-weight: 700;
      margin-bottom: 6px;
    }}
    .tool {{
      margin-top: 10px;
      padding: 10px;
      border-radius: 8px;
      background: #fff;
      border: 1px solid #e5e7eb;
    }}
    code {{
      background: #f0f2f5;
      padding: 1px 4px;
      border-radius: 4px;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Ask AI Agent</h1>
    <div class="meta">Session ID: <code>{session_id}</code></div>

    <textarea id="question" placeholder="Ask about this OCR session or the legal documents"></textarea>
    <br />
    <button onclick="askAgent()">Ask Agent</button>

    <div class="panel">
      <div class="label">Answer</div>
      <div id="answer">No question asked yet.</div>
    </div>

    <div class="panel">
      <div class="label">Tool Calls</div>
      <div id="tools">No tool calls yet.</div>
    </div>

    <div class="panel">
      <div class="label">Sources</div>
      <div id="sources">No sources yet.</div>
    </div>
  </div>

  <script>
    async function askAgent() {{
      const question = document.getElementById("question").value.trim();
      if (!question) {{
        alert("Enter a question first.");
        return;
      }}

      document.getElementById("answer").innerText = "Thinking...";
      document.getElementById("tools").innerText = "Planning tool calls...";
      document.getElementById("sources").innerText = "Loading sources...";

      const response = await fetch("/api/agent/ask", {{
        method: "POST",
        headers: {{
          "Content-Type": "application/json"
        }},
        body: JSON.stringify({{
          session_id: "{session_id}",
          question: question
        }})
      }});

      const data = await response.json();

      document.getElementById("answer").innerText = data.answer || "No answer returned.";

      const toolsContainer = document.getElementById("tools");
      toolsContainer.innerHTML = "";

      if (data.tool_calls && data.tool_calls.length > 0) {{
        data.tool_calls.forEach(tc => {{
          const div = document.createElement("div");
          div.className = "tool";
          div.innerHTML = `
            <div><strong>Tool:</strong> ${tc.tool_name}</div>
            <div><strong>Arguments:</strong> <pre>${JSON.stringify(tc.arguments, null, 2)}</pre></div>
          `;
          toolsContainer.appendChild(div);
        }});
      }} else {{
        toolsContainer.innerText = "No tool calls returned.";
      }}

      const sourcesContainer = document.getElementById("sources");
      sourcesContainer.innerHTML = "";

      if (!data.sources || data.sources.length === 0) {{
        sourcesContainer.innerText = "No sources returned.";
        return;
      }}

      data.sources.forEach(src => {{
        const div = document.createElement("div");
        div.className = "source";
        div.innerHTML = `
          <div><strong>Type:</strong> ${src.source_type}</div>
          <div><strong>Source:</strong> ${src.source_name}</div>
          <div><strong>Page:</strong> ${src.page ?? ""}</div>
          <div><strong>Snippet:</strong> ${src.snippet}</div>
        `;
        sourcesContainer.appendChild(div);
      }});
    }}
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html)
