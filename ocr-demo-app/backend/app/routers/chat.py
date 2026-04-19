from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from ..models.chat import ChatRequest, ChatResponse
from ..services.chat_service import ask_question

router = APIRouter()


@router.post("/ask", response_model=ChatResponse)
async def ask_chat_question(request: ChatRequest) -> ChatResponse:
    return ask_question(request.session_id, request.question)


@router.get("/assistant/{session_id}", response_class=HTMLResponse)
async def assistant_page(session_id: str) -> HTMLResponse:
    html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>OCR Assistant</title>
  <style>
    body {{
      font-family: Arial, sans-serif;
      margin: 0;
      background: #f5f7fb;
      color: #222;
    }}
    .wrap {{
      max-width: 900px;
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
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Ask AI</h1>
    <div class="meta">Session ID: <code>{session_id}</code></div>

    <textarea id="question" placeholder="Ask about this OCR session or the legal documents"></textarea>
    <br />
    <button onclick="askQuestion()">Ask</button>

    <div class="panel">
      <div class="label">Answer</div>
      <div id="answer">No question asked yet.</div>
    </div>

    <div class="panel">
      <div class="label">Sources</div>
      <div id="sources">No sources yet.</div>
    </div>
  </div>

  <script>
    async function askQuestion() {{
      const question = document.getElementById("question").value.trim();
      if (!question) {{
        alert("Enter a question first.");
        return;
      }}

      document.getElementById("answer").innerText = "Thinking...";
      document.getElementById("sources").innerText = "Loading sources...";

      const response = await fetch("/api/chat/ask", {{
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
