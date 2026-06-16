# Developer Brief: Autonomous Agent Framework
**Status:** Phase 3 Complete | Phase 4 Ready  
**Technology Stack:** Python 3.14 | FastAPI | LM Studio (local) | Pydantic | asyncio

---

## 🎯 What This Project Does

Autonomous agent system that can:
- Execute tasks autonomously in a sandboxed environment
- Read/write files, run commands, manage memory
- Maintain long-term state without context bloat
- Refine its own behavior via meta-prompting

**Current Scope:** Single-task execution loop with memory persistence  
**Next Phase:** Multi-task API with web UI

---

## 📁 Project Structure

```
/home/sieradni/conv/agent-framework/
├── backend/
│   ├── app/
│   │   ├── lm_client.py          # LM Studio HTTP client (async)
│   │   ├── sandbox.py            # Secure file system isolation
│   │   ├── state.py              # StepLog, AgentState schemas
│   │   ├── tools.py              # ToolExecutor (file I/O, commands, memory)
│   │   ├── prompts.py            # System prompts & tool definitions
│   │   ├── orchestrator.py       # Main agent loop (async)
│   │   ├── working_memory.json   # Persistent agent memory
│   │   ├── memory_rules.md       # Memory guidelines (editable by agent)
│   │   └── main.py               # Entry point (WIP)
│   ├── requirements.txt
│   ├── venv/                     # Python virtual environment
│   ├── test_loop.py              # Phase 2 test (factorial task)
│   ├── test_memory_loop.py       # Phase 3 test (memory system)
│   └── test_memory_simple.py     # Phase 3 simplified test
├── frontend/                     # Phase 5 (placeholder)
└── [docs/reports - see below]
```

---

## 🔧 Quick Start

### Prerequisites
- **LM Studio** running on `http://localhost:1234`
- Model: `gemma-4-12b-coder-fable5-composer2.5-v1` (or compatible)
- Python 3.10+

### Setup
```bash
cd /home/sieradni/conv/agent-framework/backend
source venv/bin/activate
pip install -r requirements.txt
```

### Run a Test
```bash
# Phase 2: Simple factorial task (4 steps, proven working)
python test_loop.py

# Phase 3: Memory system test
python test_memory_loop.py        # Full integration test
python test_memory_simple.py      # Simplified memory test
```

### Run Agent Programmatically
```python
import asyncio
from app.orchestrator import run_agent

result = asyncio.run(run_agent(
    task_goal="Create a Python function that calculates Fibonacci numbers",
    lm_studio_url="http://localhost:1234",
    sandbox_dir="/tmp/agent_work",
    max_steps=15
))
```

---

## 🏗️ Architecture Overview

```
User/API
   ↓
run_agent() [async wrapper]
   ↓
AgentOrchestrator.run_loop()
   ├─→ Compile system prompt with memory injection
   ├─→ Call LM Studio /v1/chat/completions
   ├─→ Parse JSON response (strips markdown wrappers)
   ├─→ Validate action schema
   ├─→ Execute tool via ToolExecutor
   │   ├─→ write_file (sandbox)
   │   ├─→ read_file (sandbox)
   │   ├─→ run_command (sandbox subprocess)
   │   ├─→ read_memory (working_memory.json)
   │   ├─→ write_memory (working_memory.json)
   │   └─→ refine_memory_methodology (memory_rules.md)
   ├─→ Log step to AgentState
   └─→ Loop until finish_task or max_steps
```

---

## 🔑 Core Components

### 1. **lm_client.py** - LM Studio Interface
```python
async def chat_completion(model, messages, temperature)
async def get_models()
```
- Simple async wrapper around LM Studio API
- Returns raw model responses
- Test: verified 1.34s latency

### 2. **sandbox.py** - File System Isolation
```python
class LocalSandbox:
    def read_file(relative_path)
    def write_file(relative_path, content)
    def list_files(relative_path)
    def run_command(command, cwd)
```
- Prevents directory traversal via `Path.is_relative_to()`
- All paths validated against workspace_dir
- All 8 security tests passing

### 3. **state.py** - Execution History
```python
class StepLog: step_number, thought, tool_name, tool_args, observation, timestamp
class AgentState: task_goal, status, current_step, max_steps, history[]
```
- Tracks every decision and tool call
- Enables debugging and audit trails

### 4. **tools.py** - Tool Executor
```python
class ToolExecutor:
    write_file(path, content)
    read_file(path)
    run_command(command, timeout=10)
    read_memory()
    write_memory(key, value)
    refine_memory_methodology(new_rules, reflection)
```
- Single interface for all agent actions
- Delegates to sandbox for file/command ops
- Uses Path-based sandbox isolation

### 5. **orchestrator.py** - Main Agent Loop
```python
class AgentOrchestrator:
    async def run_loop()         # Main execution loop
    def _compile_prompt_with_memory()  # Dynamic memory injection
    def _build_messages()        # Context pruning (5→2 steps)
    def _execute_tool()          # Tool dispatcher
```
- Drives the complete agent lifecycle
- Handles JSON parsing & validation
- Recovers from errors gracefully

---

## 💾 Memory System (Phase 3)

### How It Works
1. **working_memory.json** - Agent reads/writes structured data
   ```json
   {
     "project_overview": "string",
     "facts_discovered": {},
     "active_decisions": [],
     "todo_list": [],
     "completed_tasks": []
   }
   ```

2. **memory_rules.md** - Guidelines for memory updates (editable by agent)

3. **Meta-prompt History** - Audit trail of memory refinements

### Dynamic Injection
Every step:
```
System Prompt = Base Prompt + Memory Guidelines + Working Memory JSON
```

### Context Pruning
- **Before:** Message history included 5 previous steps
- **After:** Message history includes only 2 previous steps
- **Result:** ~60% token reduction per step

### Key Workflow
```
Agent reads memory → Plans next action → Calls write_memory → Updates JSON → 
Next step loads updated JSON → Continues with fresh context
```

---

## ⚠️ Important Gotchas

### 1. **LM Studio Must Be Running**
```bash
# If you get "Connection refused" on port 1234
# Make sure LM Studio is started and model is loaded
curl http://localhost:1234/v1/models
```

### 2. **JSON Escaping Issues with refine_memory_methodology**
- Local model struggles with JSON escaping of backslashes in markdown
- **Workaround:** Pass simpler text or use `write_memory` to store constraints directly
- **Not a blocker:** Core memory ops (read/write) work perfectly

### 3. **Markdown Wrapper in LM Studio Responses**
- Model sometimes wraps JSON in ```json ... ```
- **Already handled:** orchestrator.py strips these automatically
- Pattern: Checks for ```json, ```, and removes them before json.loads()

### 4. **Max Steps Default is 15**
- Prevents infinite loops
- Set higher for complex tasks
- Current tests use 15 (sufficient for most tasks)

### 5. **Sandbox is Path-Based, Not OS-Level**
- Uses `Path.is_relative_to()` for validation
- Not true container isolation
- Sufficient for preventing accidental traversal, not malicious actors

### 6. **Working Memory Not Auto-Initialized**
- First call to write_memory creates the file
- read_memory returns empty structure if file missing
- Memory files in `backend/app/` (not in sandbox)

---

## 🧪 Testing Workflows

### Test Phase 2: Basic Agent Loop
```bash
cd backend
python test_loop.py
```
**Expects:** Factorial task completed in 4 steps ✅

### Test Phase 3: Memory System
```bash
python test_memory_loop.py    # Full test with all tools
python test_memory_simple.py  # Simplified memory test
```
**Expects:** write_memory updates todo_list, read_memory retrieves it ✅

### Manual Testing
```python
# In Python REPL
from app.orchestrator import run_agent
import asyncio

result = asyncio.run(run_agent(
    task_goal="Print hello world",
    sandbox_dir="/tmp/test",
    max_steps=10
))
print(result.state.status)
```

---

## 📊 Current Status

| Phase | Task | Status |
|-------|------|--------|
| 1 | Env setup, LM client, sandbox | ✅ Complete |
| 2 | Agent loop, tool execution | ✅ Complete |
| 3 | Memory system, context pruning | ✅ Complete |
| 4 | FastAPI endpoints, session management, web UI | ✅ Complete |
| 5 | HSWM memory graph, sleep flow | ✅ Complete |
| 6 | Self-Development Pipeline, frontend UX polish | ✅ Complete |

---

## 🚀 Running the Server

### Quick Start (one command)

```bash
cd /home/sieradni/conv/agent-framework
./run.sh
```

This checks prerequisites, activates the venv, installs deps, and starts uvicorn on `http://localhost:8000`.

### Manual Start

```bash
cd /home/sieradni/conv/agent-framework/backend
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Prerequisites

1. **LM Studio** running on `http://localhost:1234` with a model loaded
2. **Python 3.10+** with virtual environment
3. Open `http://localhost:8000` in a browser

---

## 🧭 Application Sections

### Console View (default)
- **Configure tab**: Set task goal, approval mode, max steps
- **Diagnostics dashboard**: Real-time gen time, tokens/s, token count
- **Terminal**: Live agent output with copy buttons on each step
- **Overseer panel**: Review logs from the Overseer agent
- **State viewer**: HSWM graph, rules, neighborhood tabs
- **Controls**: Stop, pause-after-step, direct messaging to agent
- **Approval banner**: Appears when agent needs user input (WAIT_FOR_USER mode or ask_user tool)

### Memory View
- Full HSWM memory graph display
- Neighborhood viewer
- Run optimization (sleep flow) button

### Notes View
- Persistent user scratchpad (markdown)
- Agent can read notes via `read_user_notes` tool
- Auto-saves to `backend/app/user_notes.md`

### Settings View
- Self-Development Pipeline controls
- Session management

---

## 🔄 Agent Ask User Flow

The agent can stop and ask the user a question using the `ask_user` tool:

```
Agent asks: "What port should I use for the server?"
├─ User types answer in approval banner
├─ Answer returned as observation
└─ Agent continues with the answer
```

This works in ALL approval modes (AUTO_APPROVE, CHECK_WITH_OVERSEER, WAIT_FOR_USER).

---

## 🛠 Self-Development Pipeline

The agent can safely modify its own codebase through a **shadow sandbox**:

1. **Init shadow**: Copies the framework to a temp directory
2. **Propose change**: Applies a file modification in the shadow
3. **Run tests**: Executes `test_loop.py` and `test_sandbox.py` inside the shadow
4. **Deploy**: Copies approved changes to the live codebase

Agent tools: `propose_change`, `run_self_test`, `deploy_change`
Settings panel buttons: Init, Run Tests, Deploy, Status

---

## 🔑 Key API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/session/create` | Create or get a session |
| POST | `/api/task/start` | Start a new task |
| POST | `/api/task/approve` | Submit user approval/answer |
| POST | `/api/task/stop` | Abort current task |
| POST | `/api/task/talk` | Send direct message to agent |
| POST | `/api/task/override` | Override Overseer rejection |
| POST | `/api/self-dev/init` | Init shadow sandbox |
| POST | `/api/self-dev/propose` | Propose change in shadow |
| POST | `/api/self-dev/test` | Run tests in shadow |
| POST | `/api/self-dev/deploy` | Deploy shadow to live |
| GET | `/api/notes` | Read user notes |
| PUT | `/api/notes` | Update user notes |
| GET | `/api/memory` | Get HSWM graph state |
| POST | `/api/memory/optimize` | Run sleep flow optimization |
| GET | `/api/diagnostics` | Get diagnostics history |
| WS | `/ws/{session_id}` | Session-scoped WebSocket |

---

## 📁 File Map

**Core:**
- `backend/app/main.py` — FastAPI server, all endpoints
- `backend/app/orchestrator.py` — Agent execution loop
- `backend/app/tools.py` — Tool implementations
- `backend/app/sandbox.py` — File system isolation
- `backend/app/session.py` — Multi-session management
- `backend/app/state.py` — Data schemas

**Memory:**
- `backend/app/memory_graph.py` — HSWM graph store
- `backend/app/sleep_flow.py` — Offline memory optimization
- `backend/app/working_memory.json` — Current memory graph state
- `backend/app/memory_rules.md` — Memory guidelines

**AI:**
- `backend/app/lm_client.py` — LM Studio client
- `backend/app/overseer.py` — Quality assurance agent
- `backend/app/prompts.py` — Agent system prompts

**Self-Development:**
- `backend/app/self_dev.py` — Shadow sandbox and hot-swap

**Frontend:**
- `frontend/index.html` — Single HTML file SPA (Tailwind CSS)

---

## 💬 Example Agent Execution

```
Task: "Create a hello world script and run it"

[Step 1] Agent writes Python file
  Tool: write_file
  Args: {"path": "hello.py", "content": "print('Hello, World!')"}
  Observation: ✓ File written

[Step 2] Agent runs the script
  Tool: run_command
  Args: {"command": "python hello.py"}
  Observation: Hello, World!

[Step 3] Agent asks before finishing
  Tool: ask_user
  Args: {"question": "Should I add error handling?"}
  [User answers "yes"]
  Observation: User answered: yes

[Step 4] Agent improves and finishes
  Tool: finish_task
  Args: {"summary": "Created hello.py with error handling"}
  Status: COMPLETED ✅
```

---

## 🎯 Handoff Checklist

Before continuing development:

- [ ] Run `./run.sh` to start the server
- [ ] Open `http://localhost:8000` in a browser
- [ ] Run `python backend/test_loop.py` to verify agent loop
- [ ] Check settings panel for self-dev pipeline controls
- [ ] Review `backend/app/self_dev.py` for shadow sandbox API
- [ ] Review `frontend/index.html` for complete UI

---

## ❓ FAQ

**Q: How do I add a new tool?**
A: Add method to ToolExecutor in tools.py, register in prompts.py under "Available Tools", add dispatch case in orchestrator._execute_tool()

**Q: How do I debug a failed step?**
A: Check orchestrator logs for error_feedback. Failed JSON shows the parse error. Check working_memory.json for agent's context.

**Q: Can I increase max_steps?**
A: Yes, change in run_agent() call. Be aware: cost = steps × tokens. Recommend 15-25 for complex tasks.

**Q: Why only 2 steps in message history?**
A: Context window optimization for local models. Long-term info stored in working_memory.json instead.

**Q: How do I test my changes?**
A: Create test_xyz.py in backend/, run `python test_xyz.py`. Use test_memory_loop.py as template.

---

**Ready to start Phase 4!** 🚀

