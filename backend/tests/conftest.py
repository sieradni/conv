import pytest
import tempfile
import shutil
import json
import os
import sys
from pathlib import Path


def pytest_configure(config):
    config.addinivalue_line("filterwarnings", "ignore::DeprecationWarning")
    config.addinivalue_line("filterwarnings", "ignore::Warning:fastapi")
    config.addinivalue_line("filterwarnings", "ignore::Warning:starlette")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))


@pytest.fixture
def tmp_workspace():
    path = Path(tempfile.mkdtemp(prefix="sandbox_test_"))
    yield path
    if path.exists():
        shutil.rmtree(path)


@pytest.fixture
def sandbox_instance(tmp_workspace):
    from app.sandbox import LocalSandbox
    sb = LocalSandbox(workspace_dir=str(tmp_workspace))
    return sb


@pytest.fixture
def sandbox_with_scopes(tmp_workspace):
    from app.sandbox import LocalSandbox
    sb = LocalSandbox(workspace_dir=str(tmp_workspace / "default"))
    sb.add_scope("framework", tmp_workspace / "framework")
    sb.add_scope("shadow", tmp_workspace / "shadow")
    return sb


@pytest.fixture
def memory_graph_path(tmp_workspace):
    path = tmp_workspace / "memory.json"
    yield path
    if path.exists():
        path.unlink()


@pytest.fixture
def memory_graph(memory_graph_path):
    from app.memory_graph import MemoryGraph, set_memory_graph
    g = MemoryGraph(str(memory_graph_path))
    set_memory_graph(g)
    return g


@pytest.fixture(autouse=True)
def clean_state():
    from app.memory_graph import set_memory_graph
    set_memory_graph(None)
    from app.core.events import manager as core_manager
    core_manager._global.clear()
    core_manager._by_session.clear()
    from app.core.session import reset_conversation
    reset_conversation()
    from app.core.config import TODO_FILE, DIAG_FILE, NOTES_FILE
    for f in (TODO_FILE, DIAG_FILE, NOTES_FILE):
        if f.exists():
            f.unlink()
    yield
