# Developer Brief: Autonomous Agent Framework
**Technology Stack:** Python 3.14 | FastAPI | LM Studio (local) | Pydantic | asyncio

---

## 🎯 What This Project Does

Autonomous agent system that can:
- Execute tasks autonomously in a sandboxed environment
- Read/write files, run commands, manage memory
- Maintain long-term state without context bloat
- Refine its own behavior via meta-prompting

**Current Scope:** Full-stack agent framework with HSWM memory, WebSocket streaming, self-development pipeline, and web UI

---

## 📁 Project Structure

```
/home/sieradni/conv/agent-framework/
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI server + chat ReAct loop
│   │   ├── lm_client.py          # LM Studio HTTP client (async)
│   │   ├── sandbox.py            # Secure file system isolation
│   │   ├── tools.py              # ToolExecutor (file I/O, commands, memory)
│   │   ├── prompts.py            # System prompts & tool definitions
│   │   ├── session.py            # Multi-session + WebSocket manager
│   │   ├── memory_graph.py       # HSWM flat graph with linked nodes
│   │   ├── sleep_flow.py         # Background memory optimization
│   │   ├── overseer.py           # QA agent for tool call review
│   │   ├── self_dev.py           # Shadow sandbox for self-modification
│   │   ├── memory.json   # Persistent agent memory
│   │   ├── memory_rules.md       # Memory guidelines (editable by agent)
│   │   └── todo.json             # Standalone todo list
│   ├── requirements.txt
│   ├── venv/                     # Python virtual environment
│   └── test_sandbox.py           # Sandbox security tests
├── frontend/
│   └── index.html                # Single-page SPA (Tailwind CSS)
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

### Run Tests
```bash
cd backend
source venv/bin/activate
python test_sandbox.py            # Sandbox security boundary tests
```

### Start Server
```bash
cd /home/sieradni/conv/agent-framework
./run.sh
# Opens web UI at http://localhost:8000
```

---

## 🏗️ Architecture Overview

```
User (WebSocket / HTTP)
   ↓
stream_chat_response() in main.py [FastAPI endpoint]
   ├─→ Compile system prompt with memory injection
   ├─→ Call LM Studio /v1/chat/completions (streaming)
   ├─→ Parse JSON tool call from response
   ├─→ Execute tool via execute_chat_tool()
   │   ├─→ read_file / write_file (sandbox)
   │   ├─→ run_command (sandbox subprocess)
   │   ├─→ read_detail / create_memory / update_memory (HSWM graph)
    │   ├─→ update_todo (todo.json — todo list auto-injected into context)
   │   ├─→ propose_change / run_self_test / deploy_change (self-dev)
   │   └─→ finish_task / ask_user / set_goal
   ├─→ Approval gate: AUTO_APPROVE | CHECK_WITH_OVERSEER | WAIT_FOR_USER
   └─→ Loop until finish_task or max rounds (50)
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

### 3. **tools.py** - Tool Executor
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

### 4. **main.py** - FastAPI Server & ReAct Loop
- All API endpoints (session, chat, memory, self-dev, notes, todos, diagnostics)
- `stream_chat_response()` — the ReAct loop with streaming LLM calls
- Tool call extraction & execution
- Approval modes: AUTO_APPROVE, CHECK_WITH_OVERSEER, WAIT_FOR_USER

---

## 🔑 Additional Components

### **session.py** - Session Management
- Multi-session registry with WebSocket manager
- Per-session chat history, approval queue, pause/resume/stop controls

### **memory_graph.py** - HSWM Graph
- `MemoryGraph` with linked nodes, current node tracking
- `read_detail()`, `create_memory()`, `update_memory()`, `current_context()`

### **overseer.py** - QA Agent
- Reviews tool calls before execution in CHECK_WITH_OVERSEER mode
- Returns APPROVED/REJECTED with reasoning

### **self_dev.py** - Self-Development Pipeline
- `ShadowSandbox` — copies framework to temp dir, applies changes, runs tests, deploys

### **sleep_flow.py** - Background Optimization
- Periodic memory consolidation (HSWM graph optimization)

## 💾 Memory System

The framework uses a **Hierarchical Small-World Memory (HSWM)** graph:

### Components
1. **memory_graph.py** — Graph of linked memory nodes, each with title, detail, linked_ids
2. **memory.json** — Serialized graph state (nodes + current_node_id)
3. **memory_rules.md** — Guidelines for memory updates (editable by agent)

### Key Operations
- `read_detail(key)` — Retrieve a node by ID or title prefix
- `create_memory(title, detail, linked_ids, is_root)` — Add a new node
- `update_memory(node_id, title, detail, linked_ids)` — Modify existing node
- `current_context()` — Returns overview of recent nodes for prompt injection

### Sleep Flow
Background optimization cycle that consolidates and prunes memory nodes:
- Runs automatically every 3600s (configurable)
- Can be triggered manually via `/api/memory/optimize`
- Uses a dedicated LLM call with SLEEP_SYSTEM_PROMPT

---

## ⚠️ Important Gotchas

### 1. **LM Studio Must Be Running**
```bash
# If you get "Connection refused" on port 1234
# Make sure LM Studio is started and model is loaded
curl http://localhost:1234/v1/models
```

### 2. **JSON Escaping Issues**
- Local model struggles with JSON escaping of backslashes in markdown
- **Workaround:** Pass simpler text to avoid escaping issues
- **Not a blocker:** Core memory ops work perfectly

### 3. **Markdown Wrapper in LM Studio Responses**
- Model sometimes wraps JSON in ```json ... ```
- **Already handled:** main.py strips these automatically

### 4. **Max Steps Default is 50**
- Prevents infinite loops in chat ReAct loop
- Configurable per session

### 5. **Sandbox is Path-Based, Not OS-Level**
- Uses `Path.is_relative_to()` for validation
- Not true container isolation
- Sufficient for preventing accidental traversal, not malicious actors

---

## 🧪 Testing Workflows

### Run Sandbox Tests
```bash
cd backend
source venv/bin/activate
python test_sandbox.py
```
**Expects:** 8 sandbox security boundary tests pass ✅

### Manual API Testing
```bash
# Check server health
curl http://localhost:8000/api/health

# Check LM Studio connection
curl http://localhost:8000/api/lm/status

# Create a session
curl -X POST http://localhost:8000/api/session/create
```

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
3. **Run tests**: Executes `test_sandbox.py` inside the shadow
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
- `backend/app/main.py` — FastAPI server, all endpoints + ReAct loop
- `backend/app/tools.py` — Tool implementations
- `backend/app/sandbox.py` — File system isolation
- `backend/app/session.py` — Multi-session management + WebSocket manager

**Memory:**
- `backend/app/memory_graph.py` — HSWM graph store
- `backend/app/sleep_flow.py` — Background memory optimization
- `backend/app/memory.json` — Current memory graph state
- `backend/app/memory_rules.md` — Memory guidelines

**AI:**
- `backend/app/lm_client.py` — LM Studio client (streaming)
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
- [ ] Run `python backend/test_sandbox.py` to verify sandbox isolation
- [ ] Check settings panel for self-dev pipeline controls
- [ ] Review `backend/app/self_dev.py` for shadow sandbox API
- [ ] Review `frontend/index.html` for complete UI
