"""Test script for sandbox boundary protection"""

import sys
import os

# Add the app directory to the path so we can import sandbox module
sys.path.insert(0, '/home/sieradni/conv/agent-framework/backend/app')

from sandbox import LocalSandbox

def test_sandbox():
    """Test sandbox security boundaries."""
    print("=" * 60)
    print("SANDBOX BOUNDARY PROTECTION TEST")
    print("=" * 60)
    
    # Initialize sandbox pointing to absolute path
    sandbox = LocalSandbox(workspace_dir="/home/sieradni/conv/agent-framework/sandbox")
    print(f"\n[*] Sandbox workspace: {sandbox.workspace_path}")
    
    # Test 1: Write a file inside sandbox
    print("\n[TEST 1] Writing file INSIDE sandbox...")
    try:
        result = sandbox.write_file("test_file.txt", "This is a test file inside the sandbox.")
        print(f"[+] SUCCESS: {result}")
    except Exception as e:
        print(f"[-] FAILED: {e}")
    
    # Test 2: Read the file back
    print("\n[TEST 2] Reading file from sandbox...")
    try:
        content = sandbox.read_file("test_file.txt")
        print(f"[+] SUCCESS: Read content: '{content}'")
    except Exception as e:
        print(f"[-] FAILED: {e}")
    
    # Test 3: Attempt directory traversal with ../
    print("\n[TEST 3] Attempting directory traversal with ../...")
    try:
        result = sandbox.write_file("../backend/app/malicious.py", "MALICIOUS CODE")
        print(f"[-] SECURITY FAILURE: Write succeeded when it should have been blocked!")
    except PermissionError as e:
        print(f"[+] SUCCESS: Blocked directory traversal - {e}")
    except Exception as e:
        print(f"[-] UNEXPECTED ERROR: {e}")
    
    # Test 4: Attempt absolute path escape
    print("\n[TEST 4] Attempting escape with absolute path...")
    try:
        result = sandbox.write_file("/etc/passwd", "MALICIOUS")
        print(f"[-] SECURITY FAILURE: Write succeeded when it should have been blocked!")
    except PermissionError as e:
        print(f"[+] SUCCESS: Blocked absolute path - {e}")
    except Exception as e:
        print(f"[-] UNEXPECTED ERROR: {e}")
    
    # Test 5: Attempt multiple traversal attempts
    print("\n[TEST 5] Attempting complex traversal (../../home/...)...")
    try:
        result = sandbox.write_file("../../home/sieradni/dangerous.txt", "MALICIOUS")
        print(f"[-] SECURITY FAILURE: Write succeeded when it should have been blocked!")
    except PermissionError as e:
        print(f"[+] SUCCESS: Blocked complex traversal - {e}")
    except Exception as e:
        print(f"[-] UNEXPECTED ERROR: {e}")
    
    # Test 6: List files in sandbox
    print("\n[TEST 6] Listing files in sandbox...")
    try:
        files = sandbox.list_files(".")
        print(f"[+] SUCCESS: Found files: {files}")
    except Exception as e:
        print(f"[-] FAILED: {e}")
    
    # Test 7: Create nested file structure
    print("\n[TEST 7] Creating nested directory structure...")
    try:
        result = sandbox.write_file("subdir/nested/file.txt", "Nested file content")
        print(f"[+] SUCCESS: {result}")
    except Exception as e:
        print(f"[-] FAILED: {e}")
    
    # Test 8: Read nested file
    print("\n[TEST 8] Reading nested file...")
    try:
        content = sandbox.read_file("subdir/nested/file.txt")
        print(f"[+] SUCCESS: Read nested file: '{content}'")
    except Exception as e:
        print(f"[-] FAILED: {e}")
    
    print("\n" + "=" * 60)
    print("TEST SUITE COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    test_sandbox()
