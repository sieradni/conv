"""Verification script for LM Studio setup and basic functionality"""

import httpx
import asyncio
import time

LM_STUDIO_URL = "http://localhost:1234/v1"  # Adjust port if needed


async def verify_lm_studio():
    """Verify LM Studio connectivity and test basic functionality."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # 1. Check models
            print("Connecting to LM Studio...")
            response = await client.get(f"{LM_STUDIO_URL}/models")
            if response.status_code != 200:
                print(f"[-] Failed to fetch models. Status: {response.status_code}")
                return False
            
            models = response.json()
            model_name = models['data'][0]['id'] if 'data' in models and models['data'] else "Unknown"
            print(f"[+] Connected successfully. Active Model: {model_name}")

            # 2. Test chat completion
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": "Respond with the word 'ACKNOWLEDGE' and nothing else."}],
                "temperature": 0.1
            }
            
            start_time = time.time()
            chat_response = await client.post(f"{LM_STUDIO_URL}/chat/completions", json=payload)
            latency = time.time() - start_time
            
            if chat_response.status_code == 200:
                reply = chat_response.json()['choices'][0]['message']['content'].strip()
                print(f"[+] Chat Completion Success. Reply: '{reply}' (Latency: {latency:.2f}s)")
                return True
            else:
                print(f"[-] Chat completion failed. Status: {chat_response.status_code}")
                return False
                
        except httpx.ConnectError:
            print("[-] Error: Could not connect to LM Studio. Is the local server running on port 1234?")
            return False


if __name__ == "__main__":
    asyncio.run(verify_lm_studio())
