"""Simplified integration test for Phase 3: Memory System (Part 1)"""

import asyncio
import sys
import os
import json

# Add the app directory to path
sys.path.insert(0, '/home/sieradni/conv/agent-framework/backend')

from app.orchestrator import run_agent


async def main():
    """Run the agent with a simplified memory-focused task."""
    
    print("=" * 70)
    print("PHASE 3: MEMORY SYSTEM INTEGRATION TEST (SIMPLIFIED)")
    print("=" * 70)
    
    task_goal = """Build a simple bookstore stock checker application in the sandbox.

IMPORTANT: Before writing any code, you MUST:
1. Use read_memory to check current state
2. Use write_memory with key "project_overview" to set: "Bookstore Stock Checker - A simple app to track book inventory"
3. Use write_memory with key "active_decisions" to add decision: "Using a dict to map book titles to quantities"
4. Use write_memory with key "todo_list" to set the list of tasks

Then write the code to create:
- bookstore.py: A Bookstore class with check_stock() method
- test_bookstore.py: Unit tests with at least 2 test cases

Run the tests to verify they pass, then finish."""
    
    print(f"\nTask Goal:\n{task_goal}\n")
    print("=" * 70)
    
    try:
        final_state = await run_agent(
            task_goal=task_goal,
            sandbox_dir="/home/sieradni/conv/agent-framework/sandbox",
            max_steps=20
        )
        
        # Verification
        print("\n" + "=" * 70)
        print("POST-EXECUTION VERIFICATION")
        print("=" * 70)
        
        print(f"[*] Task Status: {final_state.status}")
        print(f"[*] Steps Executed: {len(final_state.history)}")
        
        # Check memory files
        try:
            memory_path = "/home/sieradni/conv/agent-framework/backend/app/working_memory.json"
            
            if os.path.exists(memory_path):
                with open(memory_path, 'r') as f:
                    memory = json.load(f)
                
                print(f"\n[✓] working_memory.json successfully created and updated:")
                print(f"    - project_overview: {memory.get('project_overview', 'Not set')[:60]}")
                print(f"    - active_decisions: {memory.get('active_decisions', [])}")
                print(f"    - todo_list items: {len(memory.get('todo_list', []))}")
                print(f"    - completed_tasks: {len(memory.get('completed_tasks', []))}")
                
                print(f"\n[*] Full Memory State:")
                print(json.dumps(memory, indent=2))
            
            # Check sandbox files
            print("\n[*] Sandbox Files Created:")
            sandbox_path = "/home/sieradni/conv/agent-framework/sandbox"
            if os.path.exists(sandbox_path):
                files = [f for f in os.listdir(sandbox_path) 
                        if os.path.isfile(os.path.join(sandbox_path, f)) 
                        and not f.startswith('.')]
                
                if files:
                    for f in sorted(files):
                        if not f.endswith('.pyc'):
                            file_path = os.path.join(sandbox_path, f)
                            size = os.path.getsize(file_path)
                            print(f"  ✓ {f} ({size} bytes)")
                else:
                    print("  (No files created)")
        
        except Exception as e:
            print(f"[!] Error during verification: {e}")
    
    except Exception as e:
        print(f"[-] Error running agent: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
