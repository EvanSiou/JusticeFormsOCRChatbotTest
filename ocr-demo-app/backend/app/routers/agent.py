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
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      font-family: Arial, sans-serif;
      background: #f4f7fb;
      color: #1f2937;
    }}

    .page {{
      max-width: 1200px;
      margin: 24px auto;
      padding: 0 16px;
    }}

    .header {{
      background: white;
      border-radius: 16px;
      padding: 20px 24px;
      box-shadow: 0 8px 24px rgba(0,0,0,0.06);
      margin-bottom: 20px;
    }}

    .title {{
      margin: 0;
      font-size: 28px;
      font-weight: 700;
    }}

    .subtitle {{
      margin-top: 8px;
      color: #6b7280;
      font-size: 14px;
    }}

    .layout {{
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
      gap: 20px;
    }}

    .card {{
      background: white;
      border-radius: 16px;
      padding: 20px;
      box-shadow: 0 8px 24px rgba(0,0,0,0.06);
    }}

    .card h2 {{
      margin-top: 0;
      font-size: 20px;
    }}

    .session-box {{
      background: #f9fafb;
      border: 1px solid #e5e7eb;
      border-radius: 10px;
      padding: 12px;
      margin-bottom: 14px;
      font-size: 14px;
    }}

    textarea {{
      width: 100%;
      min-height: 140px;
      border: 1px solid #d1d5db;
      border-radius: 12px;
      padding: 14px;
      font-size: 15px;
      resize: vertical;
      outline: none;
    }}

    textarea:focus {{
      border-color: #2563eb;
      box-shadow: 0 0 0 3px rgba(37,99,235,0.12);
    }}

    .actions {{
      display: flex;
      gap: 10px;
      margin-top: 14px;
      flex-wrap: wrap;
    }}

    button {{
      border: none;
      border-radius: 10px;
      padding: 11px 18px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
    }}

    .primary {{
      background: #2563eb;
      color: white;
    }}

    .primary:hover {{
      background: #1d4ed8;
    }}

    .secondary {{
      background: #e5e7eb;
      color: #111827;
    }}

    .secondary:hover {{
      background: #d1d5db;
    }}

    .section-title {{
      font-size: 15px;
      font-weight: 700;
      margin-bottom: 10px;
    }}

    .answer {{
      white-space: pre-wrap;
      line-height: 1.6;
      background: #f9fafb;
      border: 1px solid #e5e7eb;
      border-radius: 12px;
      padding: 14px;
      min-height: 120px;
    }}

    .tool, .source {{
      background: #f9fafb;
      border: 1px solid #e5e7eb;
      border-radius: 12px;
      padding: 12px;
      margin-bottom: 10px;
    }}

    .tool pre {{
      white-space: pre-wrap;
      word-break: break-word;
      margin: 8px 0 0 0;
      font-size: 12px;
      background: white;
      padding: 10px;
      border-radius: 8px;
      border: 1px solid #e5e7eb;
    }}

    .examples {{
      margin-top: 14px;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}

    .chip {{
      border: 1px solid #d1d5db;
      background: white;
      border-radius: 999px;
      padding: 8px 12px;
      font-size: 13px;
      cursor: pointer;
    }}

    .chip:hover {{
      background: #f3f4f6;
    }}

    .muted {{
      color: #6b7280;
      font-size: 13px;
    }}

    @media (max-width: 900px) {{
      .layout {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <div class="header">
      <h1 class="title">Ask AI Agent</h1>
      <div class="subtitle">
        Session-based assistant for OCR results + legal reference documents
      </div>
    </div>

    <div class="layout">
      <div class="card">
        <h2>Ask a Question</h2>

        <div class="session-box">
          <strong>Session ID:</strong> <code>{session_id}</code>
        </div>

        <textarea id="question" placeholder="Ask about extracted fields, charges, defendant information, quality issues, or legal guidance"></textarea>

        <div class="actions">
          <button class="primary" onclick="askAgent()">Ask Agent</button>
          <button class="secondary" onclick="clearQuestion()">Clear</button>
        </div>

        <div class="examples">
          <button class="chip" onclick="setQuestion('What charges are on this document?')">Charges</button>
          <button class="chip" onclick="setQuestion('What defendant information was extracted?')">Defendant info</button>
          <button class="chip" onclick="setQuestion('What quality issues were detected?')">Quality issues</button>
          <button class="chip" onclick="setQuestion('What does the legal guidance say about this form?')">Legal guidance</button>
          <button class="chip" onclick="setQuestion('Summarize this OCR session.')">Summarize session</button>
        </div>

        <div style="margin-top: 20px;">
          <div class="section-title">Answer</div>
          <div id="answer" class="answer">No question asked yet.</div>
        </div>
      </div>

      <div class="card">
        <h2>Agent Activity</h2>

        <div class="section-title">Tool Calls</div>
        <div id="tools" class="muted">No tool calls yet.</div>

        <div style="margin-top: 18px;" class="section-title">Sources</div>
        <div id="sources" class="muted">No sources yet.</div>
      </div>
    </div>
  </div>

  <script>
    function setQuestion(text) {{
      document.getElementById("question").value = text;
    }}

    function clearQuestion() {{
      document.getElementById("question").value = "";
    }}

    async function askAgent() {{
      const question = document.getElementById("question").value.trim();
      if (!question) {{
        alert("Enter a question first.");
        return;
      }}

      document.getElementById("answer").innerText = "Thinking...";
      document.getElementById("tools").innerHTML = "<div class='muted'>Planning tool calls...</div>";
      document.getElementById("sources").innerHTML = "<div class='muted'>Loading sources...</div>";

      try {{
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
              <pre>${JSON.stringify(tc.arguments, null, 2)}</pre>
            `;
            toolsContainer.appendChild(div);
          }});
        }} else {{
          toolsContainer.innerHTML = "<div class='muted'>No tool calls returned.</div>";
        }}

        const sourcesContainer = document.getElementById("sources");
        sourcesContainer.innerHTML = "";

        if (data.sources && data.sources.length > 0) {{
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
        }} else {{
          sourcesContainer.innerHTML = "<div class='muted'>No sources returned.</div>";
        }}
      }} catch (err) {{
        document.getElementById("answer").innerText = "Request failed.";
        document.getElementById("tools").innerHTML = "<div class='muted'>Tool call display unavailable.</div>";
        document.getElementById("sources").innerHTML = `<div class='muted'>Error: ${err}</div>`;
      }}
    }}
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html)
