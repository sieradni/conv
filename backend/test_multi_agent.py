import asyncio
import os
import shutil
from app.orchestrator import run_agent

async def test_multi_agent_division():
    print("=== Phase 4: Multi-Agent Verification Test ===")
    
    # Setup sandbox - absolute path to be safe
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sandbox_dir = os.path.join(current_dir, "sandbox_multi")
    
    # Clear previous runs
    if os.path.exists(sandbox_dir):
        try:
            shutil.rmtree(sandbox_dir)
        except Exception as e:
            print(f"Warning: Could not clear sandbox: {e}")
            
    if not os.path.exists(sandbox_dir):
        os.makedirs(sandbox_dir)
    
    # Goal designed to be "too simple", inviting Overseer rejection on finish_task
    task_goal = "Write a python function in math_utils.py called divide(a, b) that divides a by b. Write tests for it in test_math.py using unittest. Execute the code and verify it passes."
    
    print(f"Task: {task_goal}")
    print(f"Approval Mode: CHECK_WITH_OVERSEER")
    print("-" * 50)
    
    try:
        # Run the agent
        result = await run_agent(
            task_goal=task_goal,
            sandbox_dir=sandbox_dir,
            max_steps=25,
            approval_mode="CHECK_WITH_OVERSEER"
        )
        
        print("\n=== Test Final Summary ===")
        print(f"Goal: {task_goal}")
        print(f"Status: {result.status}")
        print(f"Total Steps: {len(result.history)}")
        
        # Verify if zero division was handled
        math_utils_path = os.path.join(sandbox_dir, "math_utils.py")
        if os.path.exists(math_utils_path):
            with open(math_utils_path, 'r') as f:
                content = f.read()
                print("\n--- math_utils.py final content ---")
                print(content)
                if any(x in content for x in ["ZeroDivisionError", "raise", "if b == 0", "if b==0"]):
                    print("\n[SUCCESS] Zero division edge case was handled and verified!")
                else:
                    print("\n[FAILURE] Zero division edge case was NOT handled.")
        else:
            print("\n[FAILURE] math_utils.py not found.")
            
        # Check logs for Overseer rejection
        rejections = [step for step in result.history if "Action REJECTED by OVERSEER" in step.observation]
        if rejections:
            print(f"\n[SUCCESS] Found {len(rejections)} Overseer rejections. The multi-agent dynamic is working!")
            for i, r in enumerate(rejections):
                print(f"  Rejection {i+1} at step {r.step_number}: {r.observation[:200]}...")
        else:
            print("\n[WARNING] No Overseer rejections found. The Actor might have gotten it right on the first try or Overseer was too lenient.")

    except Exception as e:
        print(f"\n[ERROR] Test failed with exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_multi_agent_division())
