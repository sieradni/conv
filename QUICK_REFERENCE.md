# Quick Reference: Setup & Common Tasks

## ⚡ 30-Second Setup

```bash
cd /home/sieradni/conv/agent-framework
./run.sh
```

Or manually:

```bash
cd /home/sieradni/conv/agent-framework/backend
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Then open **http://localhost:8000** in a browser.

**Expected:** Web UI loads. Configure a task, click launch, watch agent execute in real-time.

---

## 🚨 Critical Prerequisites

1. **LM Studio running**
   ```bash
   # Check it's alive
   curl http://localhost:1234/v1/models
   ```
   If not: Start LM Studio, load `gemma-4-12b-coder-fable5-composer2.5-v1`

2. **Python venv activated**
   ```bash
   source backend/venv/bin/activate
   which python  # Should show venv path
   ```

3. **Dependencies installed**
   ```bash
   pip install -r requirements.txt
   # Installs: httpx, pydantic, fastapi, uvicorn
   ```

---

## 📂 File Map (5-Minute Read)

**Start here:**
- `DEVELOPER_BRIEF.md` ← Full developer documentation
- `backend/app/main.py` ← FastAPI server + ReAct loop

**Core logic:**
- `backend/app/main.py` ← Main agent loop + all API endpoints
- `backend/app/tools.py` ← Tool implementations
- `backend/app/sandbox.py` ← File isolation

**Supporting:**
- `backend/app/session.py` ← Session + WebSocket management
- `backend/app/prompts.py` ← System prompts
- `backend/app/lm_client.py` ← LM Studio client (streaming)

**Testing:**
- `backend/test_sandbox.py` ← Sandbox security boundary tests

**Config:**
- `backend/app/memory.json` ← Agent's persistent memory
- `backend/app/memory_rules.md` ← Agent's memory guidelines

---

## 🔄 Common Workflows

### Run a Test
```bash
cd backend
source venv/bin/activate
python test_sandbox.py
```

### Check API Health
```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/lm/status
```

### Create a Session via API
```bash
curl -X POST http://localhost:8000/api/session/create
```

### Debug Agent Output
Watch the WebSocket stream in browser console, or check server logs.

### Check Memory State
```bash
cat backend/app/memory.json
# Shows what agent has learned
```

### Clear Memory (Fresh Start)
```bash
rm backend/app/memory.json
rm backend/app/memory_rules.md
# Next run will reinitialize
```

---

## ⚠️ Top 5 Gotchas

**1. LM Studio Not Running**
```
Error: Connection refused
Fix: Start LM Studio, ensure model is loaded
Check: curl http://localhost:1234/v1/models
```

**2. Wrong Python Interpreter**
```
Error: ModuleNotFoundError
Fix: source venv/bin/activate
Verify: which python (should be in backend/venv/)
```



**4. Timeout on run_command**
```
Error: Command timed out after 10 seconds
Fix: Increase timeout in tools.py run_command()
Or: Use simpler commands in task goal
```

**5. Sandbox Permission Denied**
```
Error: PermissionError in Path.is_relative_to()
Cause: Path escaping attempt blocked
This is correct behavior - security feature
```


---

## 🎯 Quick Command Reference

```bash
# Setup
cd /home/sieradni/conv/agent-framework/backend
source venv/bin/activate

# Test
cd backend
source venv/bin/activate
python test_sandbox.py

# Check LM Studio
curl http://localhost:1234/v1/models

# View memory
cat app/memory.json

# Reset memory
rm app/memory.json

# View logs (if added)
tail -f execution.log

# Git status
cd ..
git status
git log --oneline
```

---

