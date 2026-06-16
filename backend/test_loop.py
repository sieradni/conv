"""End-to-end integration test for the agent loop"""

import asyncio
import sys
import os

# Add the app directory to path
sys.path.insert(0, '/home/sieradni/conv/agent-framework/backend')

from app.orchestrator import run_agent


async def main():
    """Run the agent with a complex task."""
    
    print("=" * 70)
    print("PHASE 2: AGENT LOOP INTEGRATION TEST")
    print("=" * 70)
    
    task_goal = """Create a file named math_utils.py containing a function that returns the 
factorial of a number recursively. Then, create a unit test file named 
test_math.py that tests at least three edge cases (including 0, 1, and a 
larger number like 5). Finally, run the tests to verify they pass, and fix 
any bugs if needed."""
    
    print(f"\nTask Goal:\n{task_goal}\n")
    print("=" * 70)
    
    try:
        final_state = await run_agent(
            task_goal=task_goal,
            sandbox_dir="/home/sieradni/conv/agent-framework/sandbox",
            max_steps=20
        )
        
        # Additional verification
        print("\n" + "=" * 70)
        print("POST-EXECUTION VERIFICATION")
        print("=" * 70)
        
        if final_state.status == "COMPLETED":
            print("[✓] Task completed successfully")
            
            # Check if files were created
            try:
                from app.sandbox import LocalSandbox
                sandbox = LocalSandbox(workspace_dir="/home/sieradni/conv/agent-framework/sandbox")
                
                print("\nFiles in sandbox:")
                files = sandbox.list_files(".")
                for f in files:
                    print(f"  - {f}")
                
                # Try to read the created files
                if "math_utils.py" in files:
                    print("\n[✓] math_utils.py was created")
                    content = sandbox.read_file("math_utils.py")
                    print(f"  Content preview:\n{content[:200]}...")
                
                if "test_math.py" in files:
                    print("\n[✓] test_math.py was created")
                    content = sandbox.read_file("test_math.py")
                    print(f"  Content preview:\n{content[:200]}...")
            
            except Exception as e:
                print(f"[!] Could not verify files: {e}")
        
        else:
            print(f"[-] Task did not complete successfully. Status: {final_state.status}")
    
    except Exception as e:
        print(f"[-] Error running agent: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
