import pytest
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from main import (
    extract_tool_call,
    find_tool_call_start,
    find_tool_call_end,
    _parse_js_object,
    _parse_js_value,
    _split_js_values,
    _normalize_js_to_json,
)


class TestExtractToolCall:
    def test_code_fence_json(self):
        content = '```json\n{"tool": "read_file", "args": {"path": "test.txt"}}\n```'
        result = extract_tool_call(content)
        assert result == {"tool": "read_file", "args": {"path": "test.txt"}}

    def test_code_fence_no_lang(self):
        content = '```\n{"tool": "write_file", "args": {"path": "x", "content": "y"}}\n```'
        result = extract_tool_call(content)
        assert result["tool"] == "write_file"

    def test_tag_format_with_call_prefix(self):
        content = '<|tool_call|>call:write_file{"path":"x","content":"y"}'
        result = extract_tool_call(content)
        assert result is not None
        assert result["tool"] == "write_file"

    def test_bare_json_tool_key(self):
        content = 'Some text {"tool": "run_command", "args": {"command": "ls"}} more text'
        result = extract_tool_call(content)
        assert result == {"tool": "run_command", "args": {"command": "ls"}}

    def test_bare_json_tool_name_key(self):
        content = '{"tool_name": "read_file", "tool_args": {"path": "x"}}'
        result = extract_tool_call(content)
        assert result["tool"] == "read_file"
        assert result["args"]["path"] == "x"

    def test_tag_format_falls_through_to_bare_json(self):
        content = '<|tool_call|> read_file {"tool_name": "read_file", "tool_args": {"path": "test.txt"}}'
        result = extract_tool_call(content)
        assert result is not None
        assert result["tool"] == "read_file"

    def test_nested_args_in_bare_json(self):
        content = '{"tool": "write_file", "args": {"path": "a.py", "content": "def foo():\\n    pass"}}'
        result = extract_tool_call(content)
        assert result is not None
        assert result["tool"] == "write_file"

    def test_no_tool_call(self):
        content = "Just a regular message without any tool call."
        assert extract_tool_call(content) is None

    def test_empty_content(self):
        assert extract_tool_call("") is None

    def test_malformed_json_in_fence(self):
        content = '```json\n{"tool": "read_file" args: broken}\n```'
        result = extract_tool_call(content)
        assert result is None

    def test_multiple_tool_calls_returns_first(self):
        content = '{"tool": "first", "args": {}} some text {"tool": "second", "args": {}}'
        result = extract_tool_call(content)
        assert result["tool"] == "first"

    def test_empty_args(self):
        content = '{"tool": "finish_task", "args": {}}'
        result = extract_tool_call(content)
        assert result["tool"] == "finish_task"
        assert result["args"] == {}

    def test_tag_with_args_containing_tool_key_is_extracted(self):
        content = '<|tool_call|>call:run_command{"command":"ls"}'
        result = extract_tool_call(content)
        assert result is not None
        assert result["tool"] == "run_command"
        assert result["args"]["command"] == "ls"


class TestFindToolCallStart:
    def test_tag_format(self):
        content = 'Some text <|tool_call|> read_file {...}'
        pos = find_tool_call_start(content)
        assert pos == content.find("<|tool_call|>")

    def test_no_tool_call(self):
        assert find_tool_call_start("Just text") == -1


class TestFindToolCallEnd:
    def test_bare_json(self):
        content = 'Text {"tool": "run_command", "args": {"command": "ls"}} trailing'
        end = find_tool_call_end(content)
        assert end > 0
        assert end < len(content)

    def test_no_tool_returns_length(self):
        content = "Just text"
        assert find_tool_call_end(content) == len(content)


class TestParseJsObject:
    def test_valid_json(self):
        result = _parse_js_object('"path": "test.txt", "count": 42')
        assert result == {"path": "test.txt", "count": 42}

    def test_js_style_key_equals_value(self):
        result = _parse_js_object('path="test.txt", count=42')
        assert result == {"path": "test.txt", "count": 42}

    def test_mixed_syntax(self):
        result = _parse_js_object('"path": "test.txt", count=42')
        assert result == {"path": "test.txt", "count": 42}

    def test_boolean_values(self):
        result = _parse_js_object('flag=true, enabled=false')
        assert result == {"flag": True, "enabled": False}

    def test_null_value(self):
        result = _parse_js_object('value=null')
        assert result["value"] is None

    def test_none_value(self):
        result = _parse_js_object('value=None')
        assert result["value"] is None

    def test_array_values(self):
        result = _parse_js_object('items=[1,2,3]')
        assert result["items"] == [1, 2, 3]

    def test_array_string_values(self):
        result = _parse_js_object('items=["a","b","c"]')
        assert result["items"] == ["a", "b", "c"]

    def test_empty_object(self):
        result = _parse_js_object('')
        assert result == {}

    def test_nested_object(self):
        result = _parse_js_object('"outer": {"inner": "val"}')
        assert result["outer"]["inner"] == "val"

    def test_single_quoted_strings(self):
        result = _parse_js_object("path='test.txt'")
        assert result["path"] == "test.txt"

    def test_number_parsing(self):
        result = _parse_js_object('int_val=42, float_val=3.14')
        assert result["int_val"] == 42
        assert result["float_val"] == 3.14


class TestParseJsValue:
    def test_string(self):
        assert _parse_js_value('"hello"') == "hello"

    def test_single_quoted_string(self):
        assert _parse_js_value("'hello'") == "hello"

    def test_number(self):
        assert _parse_js_value("42") == 42
        assert _parse_js_value("3.14") == 3.14

    def test_boolean(self):
        assert _parse_js_value("true") is True
        assert _parse_js_value("false") is False

    def test_null(self):
        assert _parse_js_value("null") is None

    def test_plain_string(self):
        assert _parse_js_value("hello") == "hello"

    def test_empty_array(self):
        assert _parse_js_value("[]") == []


class TestSplitJsValues:
    def test_simple(self):
        assert _split_js_values("a, b, c") == ["a", "b", "c"]

    def test_nested_braces(self):
        result = _split_js_values('a={x:1}, b=2')
        assert len(result) == 2
        assert "a={x:1}" in result

    def test_nested_brackets(self):
        result = _split_js_values('a=[1,2], b=3')
        assert result == ["a=[1,2]", "b=3"]

    def test_strings_with_commas(self):
        result = _split_js_values('a="hello, world", b=2')
        assert len(result) == 2


class TestNormalizeJsToJson:
    def test_key_value(self):
        assert _normalize_js_to_json('name="test"') == '"name": "test"'

    def test_mixed(self):
        result = _normalize_js_to_json('path="x", count=42')
        assert '"path": "x"' in result
        assert '"count": 42' in result

    def test_already_json(self):
        result = _normalize_js_to_json('"path": "x"')
        assert result == '"path": "x"'

    def test_boolean_value(self):
        result = _normalize_js_to_json('flag=true')
        assert result == '"flag": true'
