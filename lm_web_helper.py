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
    import datetime
    def log(msg):
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[lm-web-helper {ts}] {msg}")

    log(f"Q: {user_query}")
    
    # Since the model doesn't support function calling, do manual search first
    search_query = user_query
    if any(k in user_query.lower() for k in ["secretary","governor","senator","minister","president"]):
        search_query = f"{user_query} site:.gov"
    
    log(f"Searching: {search_query}")
    search_result = handle_tool_call("search_web", {"query": search_query, "top_k": 3})
    
    context = ""
    if search_result and "items" in search_result:
        context = "\n\nSearch results:\n"
        for item in search_result["items"]:
            context += f"- {item['title']}: {item['snippet']} ({item['url']})\n"
        log(f"Found {len(search_result['items'])} results")
    else:
        log(f"Search failed: {search_result}")
    
    # Simple chat without function calling
    headers = {"Content-Type":"application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    
    prompt = f"""Answer this question using ONLY the search results provided. If the information is not in the search results, say so.

Question: {user_query}

Instructions:
- Use only facts from the search results
- Cite 1-2 source URLs
- Include dates when available
- Prefer official .gov sources

{context}

Answer:"""
    
    resp = http_post_json(f"{LM_BASE}/chat/completions", {
        "model": MODEL_ID,
        "messages": [{"role": "user", "content": prompt}]
    }, headers=headers)
    
    choice = (resp.get("choices") or [{}])[0]
    answer = choice.get("message", {}).get("content", "(no content)")
    log(f"Answer length: {len(answer)}")
    return answer



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
