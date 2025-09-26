# server.py
from fastapi import FastAPI
from pydantic import BaseModel
import os
from lm_web_helper import chat_with_tools

app = FastAPI(title="LM Web Helper")

class Ask(BaseModel):
    question: str

@app.post("/ask")
def ask(q: Ask):
    # Uses env vars from lm_web_helper.py (LM_BASE, LM_MODEL, TAVILY_API_KEY)
    answer = chat_with_tools(q.question)
    return {"answer": answer}

# Note: run with:
#   uvicorn server:app --host 127.0.0.1 --port 5055
