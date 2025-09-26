import json
import urllib.request

def test_lm_studio():
    url = "http://localhost:1234/v1/chat/completions"
    payload = {
        "model": "mistralai/mistral-7b-instruct-v0.3",
        "messages": [{"role": "user", "content": "Hello"}]
    }
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            print("✓ LM Studio is working!")
            print(f"Response: {result}")
    except Exception as e:
        print(f"✗ LM Studio test failed: {e}")

if __name__ == "__main__":
    test_lm_studio()