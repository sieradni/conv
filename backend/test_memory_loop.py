"""Integration test for Phase 3: Memory System & Meta-Prompting"""

import asyncio
import sys
import os
import json

# Add the app directory to path
sys.path.insert(0, '/home/sieradni/conv/agent-framework/backend')

from app.orchestrator import run_agent


async def main():
    """Run the agent with a complex task involving memory management."""
    
    print("=" * 70)
    print("PHASE 3: MEMORY SYSTEM & META-PROMPTING INTEGRATION TEST")
    print("=" * 70)
    
    task_goal = """Build a lightweight bookstore stock checker in the sandbox. 
Before writing code, use the memory tools to set up your project design and TODOs. 
As you build the code, update your memory with facts discovered and decisions made. 
Furthermore, analyze the existing memory_rules.md. 
Refine the guidelines using the refine_memory_methodology tool to add a mandatory 
section called '### Known Architectural Constraints' to your memory, and write your 
first constraint to working memory about the bookstore schema or design.
Finally, run tests to verify everything passes."""
    
    print(f"\nTask Goal:\n{task_goal}\n")
    print("=" * 70)
    
    try:
        final_state = await run_agent(
            task_goal=task_goal,
            sandbox_dir="/home/sieradni/conv/agent-framework/sandbox",
            max_steps=25
        )
        
        # Additional verification
        print("\n" + "=" * 70)
        print("POST-EXECUTION VERIFICATION")
        print("=" * 70)
        
        if final_state.status == "COMPLETED":
            print("[✓] Task completed successfully")
        else:
            print(f"[!] Task status: {final_state.status}")
        
        # Check memory files
        try:
            memory_path = "/home/sieradni/conv/agent-framework/backend/app/working_memory.json"
            rules_path = "/home/sieradni/conv/agent-framework/backend/app/memory_rules.md"
            history_path = "/home/sieradni/conv/agent-framework/backend/app/meta_prompt_history.log"
            
            print("\n[*] Memory Files Status:")
            
            if os.path.exists(memory_path):
                with open(memory_path, 'r') as f:
                    memory = json.load(f)
                print(f"\n[✓] working_memory.json exists")
                print(f"  Keys: {list(memory.keys())}")
                print(f"  Todo items: {len(memory.get('todo_list', []))}")
                print(f"  Completed tasks: {len(memory.get('completed_tasks', []))}")
                print(f"  Facts discovered: {len(memory.get('facts_discovered', {}))}")
            
            if os.path.exists(rules_path):
                with open(rules_path, 'r') as f:
                    rules = f.read()
                print(f"\n[✓] memory_rules.md exists ({len(rules)} bytes)")
                if "### Known Architectural Constraints" in rules:
                    print(f"  [✓] Contains '### Known Architectural Constraints' section")
                else:
                    print(f"  [!] Missing '### Known Architectural Constraints' section")
                print(f"  Preview:\n{rules[:300]}...")
            
            if os.path.exists(history_path):
                with open(history_path, 'r') as f:
                    history = f.read()
                print(f"\n[✓] meta_prompt_history.log exists ({len(history)} bytes)")
                if history.strip():
                    print(f"  [✓] Contains meta-prompt refinement records")
                    # Count refinements
                    count = history.count("Timestamp:")
                    print(f"  Number of refinements: {count}")
            
            # Check sandbox files
            print("\n[*] Sandbox Files Created:")
            sandbox_path = "/home/sieradni/conv/agent-framework/sandbox"
            if os.path.exists(sandbox_path):
                files = [f for f in os.listdir(sandbox_path) if os.path.isfile(os.path.join(sandbox_path, f))]
                for f in sorted(files):
                    file_path = os.path.join(sandbox_path, f)
                    size = os.path.getsize(file_path)
                    print(f"  - {f} ({size} bytes)")
        
        except Exception as e:
            print(f"[!] Could not verify files: {e}")
    
    except Exception as e:
        print(f"[-] Error running agent: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
