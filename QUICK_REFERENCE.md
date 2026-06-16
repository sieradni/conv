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
- `DEVELOPER_BRIEF.md` ← You are here
- `PHASE_3_REPORT.md` ← Architecture deep-dive

**Core logic:**
- `backend/app/orchestrator.py` ← Main agent loop (START HERE for Phase 4)
- `backend/app/tools.py` ← Tool implementations
- `backend/app/sandbox.py` ← File isolation

**Supporting:**
- `backend/app/state.py` ← Data schemas
- `backend/app/prompts.py` ← System prompts
- `backend/app/lm_client.py` ← LM Studio client

**Testing:**
- `backend/test_loop.py` ← Phase 2 test (factorial)
- `backend/test_memory_loop.py` ← Phase 3 test (memory)

**Config:**
- `backend/app/working_memory.json` ← Agent's persistent memory
- `backend/app/memory_rules.md` ← Agent's memory guidelines

---

## 🔄 Common Workflows

### Run a Test
```bash
python test_loop.py
# or
python test_memory_loop.py
```

### Create a New Test
```python
# new_test.py
import asyncio
from app.orchestrator import run_agent

result = asyncio.run(run_agent(
    task_goal="Your task here",
    sandbox_dir="/tmp/test",
    max_steps=15
))

print(f"Status: {result.state.status}")
print(f"Steps: {len(result.state.history)}")
```

### Debug Agent Output
```python
# In test file after run_agent() completes:
for step in result.state.history:
    print(f"Step {step.step_number}: {step.tool_name}")
    print(f"  Thought: {step.thought[:100]}...")
    print(f"  Observation: {step.observation[:100]}...")
```

### Check Memory State
```bash
cat backend/app/working_memory.json
# Shows what agent has learned
```

### Clear Memory (Fresh Start)
```bash
rm backend/app/working_memory.json
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

**3. JSON Parsing Fails**
```
Error: Invalid \escape in JSON
Cause: Model generated invalid JSON escaping
Fix: Model limitation - not your code. Usually refine_memory_methodology
Workaround: Use simpler input to that tool
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

## 📊 Project Status At-A-Glance

```
Phase 1: Environment Setup
  Status: ✅ COMPLETE
  What: LM Studio client, sandbox, verification
  Files: lm_client.py, sandbox.py, verify_setup.py

Phase 2: Core Agent Loop  
  Status: ✅ COMPLETE
  What: Orchestrator, tool execution, state tracking
  Files: orchestrator.py, tools.py, state.py, test_loop.py
  Tests: Factorial task ✅ PASSING

Phase 3: Memory & Context
  Status: ✅ COMPLETE
  What: Persistent memory, dynamic prompts, context pruning
  Files: working_memory.json, memory_rules.md, updated orchestrator.py
  Tests: Memory ops ✅ PASSING (with known JSON escaping limitation)

Phase 4: API & Queue
  Status: 🔄 READY TO START
  What: FastAPI endpoints, task queue, concurrent execution
  Next: Create backend/app/api.py with POST /tasks, GET /tasks/{id}
```

---

## 🎯 Quick Command Reference

```bash
# Setup
cd /home/sieradni/conv/agent-framework/backend
source venv/bin/activate

# Test
python test_loop.py
python test_memory_loop.py

# Check LM Studio
curl http://localhost:1234/v1/models

# View memory
cat app/working_memory.json

# Reset memory
rm app/working_memory.json

# View logs (if added)
tail -f execution.log

# Git status
cd ..
git status
git log --oneline
```

---

## 🚀 Phase 4 Quickstart

When ready to build API:

1. Copy `test_loop.py` as template
2. Create `app/api.py` with FastAPI app
3. Use `run_agent()` as task executor
4. Add routes:
   ```python
   @app.post("/tasks")
   async def submit_task(goal: str, max_steps: int = 15):
       # Call run_agent() async
       
   @app.get("/tasks/{task_id}")
   async def get_status(task_id: str):
       # Return task status from queue
   ```
5. Details in DEVELOPER_BRIEF.md "Phase 4 Next Steps"

---

## 📞 Need Help?

1. **Check test_loop.py** - Example of complete run
2. **Read orchestrator.py run_loop()** - Core logic
3. **Review PHASE_3_REPORT.md** - Detailed architecture
4. **Look at error messages** - Usually very clear
5. **Check working_memory.json** - Shows agent's context

---

**Good luck! 🚀**

