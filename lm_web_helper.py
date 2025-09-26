# lm_web_helper.py
import json, os, sys, time, urllib.parse, urllib.request

LM_BASE = os.getenv("LM_BASE", "http://localhost:1234/v1")
MODEL_ID = os.getenv("LM_MODEL", "mistralai/mistral-7b-instruct-v0.3")
API_KEY  = os.getenv("LM_API_KEY", "")  # leave empty unless you set one in LM Studio

def http_post_json(url, payload, headers=None):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if hasattr(e, 'read') else str(e)
        raise Exception(f"HTTP {e.code}: {error_body}")
    except Exception as e:
        raise Exception(f"Request failed: {str(e)}")

def http_get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")

# --- Web helpers -------------------------------------------------------------

def tavily_search(query, max_results=3):
    key = os.getenv("TAVILY_API_KEY", "")
    if not key:
        return None
    url = "https://api.tavily.com/search"
    payload = {
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
        "include_images": False,
        "include_answer": False,
    }
    try:
        res = http_post_json(
            url,
            payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            },
        )
        items = []
        for r in (res.get("results") or [])[:max_results]:
            items.append({
                "title": r.get("title") or "",
                "url": r.get("url") or "",
                "snippet": (r.get("content") or "")[:500]
            })
        return {"source": "tavily", "items": items}
    except Exception as e:
        return {"source": "tavily", "error": str(e)}

def wikipedia_search(query, max_results=3):
    try:
        q = urllib.parse.quote(query)
        search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={q}&format=json&srlimit={max_results}"
        data = json.loads(http_get(search_url))
        items = []
        for hit in data.get("query",{}).get("search",[])[:max_results]:
            title = hit.get("title","")
            slug  = urllib.parse.quote(title.replace(" ", "_"))
            sum_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}"
            summary = {}
            try:
                summary = json.loads(http_get(sum_url))
            except Exception:
                pass
            items.append({
                "title": title,
                "url": f"https://en.wikipedia.org/wiki/{slug}",
                "snippet": (summary.get("extract") or "")[:500]
            })
        return {"source":"wikipedia", "items": items}
    except Exception as e:
        return {"source":"wikipedia", "error": str(e)}

def fetch_url_basic(url, max_bytes=20000):
    try:
        html = http_get(url, headers={"User-Agent":"Mozilla/5.0"})
        text = html[:max_bytes]
        return {"url": url, "snippet": text}
    except Exception as e:
        return {"url": url, "error": str(e)}

# --- Tool dispatcher ---------------------------------------------------------

def handle_tool_call(name, args):
    if name == "search_web":
        q = (args or {}).get("query","").strip()
        k = int((args or {}).get("top_k", 3))
        out = tavily_search(q, k)
        if not out or "error" in out:
            out = wikipedia_search(q, k)
        return out or {"error":"no search backend available"}
    if name == "fetch_url":
        url = (args or {}).get("url","")
        return fetch_url_basic(url)
    return {"error": f"unknown tool: {name}"}

# --- Chat loop with tool calls ----------------------------------------------

def chat_with_tools(user_query):
    system_prompt = (
        "You are a local assistant with web tools. "
        "For any question that could be time-sensitive or fact-based, first call the `search_web` tool. "
        "Use at most one search_web call per query unless results are empty. "
        "Optionally call `fetch_url` to read one promising link. "
        "Then write a concise answer with 1-3 source URLs and dates if present."
    )

    messages = [
        {"role":"system", "content": system_prompt},
        {"role":"user",   "content": user_query}
    ]

    # Define tools once
    tools = [
        {
            "type":"function",
            "function":{
                "name":"search_web",
                "description":"Search the web for up-to-date information.",
                "parameters":{
                    "type":"object",
                    "properties":{
                        "query":{"type":"string"},
                        "top_k":{"type":"integer","minimum":1,"maximum":10}
                    },
                    "required":["query"]
                }
            }
        },
        {
            "type":"function",
            "function":{
                "name":"fetch_url",
                "description":"Fetch a URL and return basic content snippet.",
                "parameters":{
                    "type":"object",
                    "properties":{
                        "url":{"type":"string"}
                    },
                    "required":["url"]
                }
            }
        }
    ]
    # Old-style 'functions' array for models that use function_call instead of tool_calls
    functions = [t["function"] for t in tools]

    headers = {"Content-Type":"application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    def completions(body):
        # include both modern tools and legacy functions to maximize compatibility
        body.setdefault("tools", tools)
        body.setdefault("functions", functions)
        body.setdefault("tool_choice", "auto")
        body.setdefault("function_call", "auto")
        return http_post_json(f"{LM_BASE}/chat/completions", body, headers=headers)

    # ---- First round: let the model decide to call a tool/function
    resp = completions({
        "model": MODEL_ID,
        "messages": messages
    })
    choice = (resp.get("choices") or [{}])[0]
    msg = choice.get("message") or {}

    # Case A: modern tool_calls array
    tool_calls = msg.get("tool_calls") or []

    # Case B: legacy function_call object
    func_call = msg.get("function_call")

    # Case C: some models dump JSON text of the call into content
    def parse_inline_call(s):
        try:
            obj = json.loads(s)
            if isinstance(obj, dict) and "name" in obj and ("arguments" in obj or "parameters" in obj):
                # normalize to function_call shape
                args = obj.get("arguments", obj.get("parameters", {}))
                if isinstance(args, str):
                    try: args = json.loads(args)
                    except Exception: args = {}
                return {"name": obj["name"], "arguments": json.dumps(args)}
        except Exception:
            pass
        return None

    inline_call = None
    if not tool_calls and not func_call and isinstance(msg.get("content"), str):
        inline_call = parse_inline_call(msg["content"])

    # Normalize to a list of calls to execute
    calls_to_run = []
    if tool_calls:
        for tc in tool_calls:
            calls_to_run.append({
                "kind": "tool",
                "id": tc.get("id","tool-call-1"),
                "name": tc.get("function",{}).get("name",""),
                "args_json": tc.get("function",{}).get("arguments","{}")
            })
    elif func_call:
        calls_to_run.append({
            "kind": "function",
            "id": "function-call-1",
            "name": func_call.get("name",""),
            "args_json": func_call.get("arguments","{}")
        })
    elif inline_call:
        calls_to_run.append({
            "kind": "function",
            "id": "function-call-1",
            "name": inline_call["name"],
            "args_json": inline_call["arguments"]
        })

    if calls_to_run:
        # Keep the assistant message that requested the call(s)
        messages.append({
            "role":"assistant",
            "content": msg.get("content") or "",
            **({"tool_calls": tool_calls} if tool_calls else {}),
            **({"function_call": func_call} if (func_call and not tool_calls) else {})
        })

        # Execute at most one call (our policy says 1 unless empty)
        call = calls_to_run[0]
        try:
            args = json.loads(call["args_json"]) if isinstance(call["args_json"], str) else (call["args_json"] or {})
        except Exception:
            args = {}

        result = handle_tool_call(call["name"], args)

        # Hand results back using the correct role for each style
        if call["kind"] == "tool":
            messages.append({
                "role":"tool",
                "tool_call_id": call["id"],
                "name": call["name"],
                "content": json.dumps(result)[:8000]
            })
        else:
            # legacy function_call reply
            messages.append({
                "role":"function",
                "name": call["name"],
                "content": json.dumps(result)[:8000]
            })

        # Second round: ask the model to produce the final answer
        resp2 = completions({
            "model": MODEL_ID,
            "messages": messages
        })
        choice2 = (resp2.get("choices") or [{}])[0]
        return choice2.get("message",{}).get("content","(no content)")

    # No tool call; return whatever the model said
    return msg.get("content","(no content)")


if __name__ == "__main__":
    query = "Who is the current U.S. Secretary of Labor today? Include 1-2 sources."
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    
    print(f"Query: {query}")
    print(f"LM Base: {LM_BASE}")
    print(f"Model: {MODEL_ID}")
    
    t0 = time.time()
    try:
        out = chat_with_tools(query)
        dt = time.time() - t0
        print("\n=== ASSISTANT ===")
        print(out)
        print(f"\n(elapsed {dt:.2f}s)")
    except Exception as e:
        print(f"\nError: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure LM Studio is running")
        print("2. Load a model in LM Studio")
        print("3. Start the server in LM Studio")
        print("4. Check if the model supports function calling")
