"""Structure-aware chunkers for docs-rag."""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass

import yaml

from reasonhold.decisions import DecisionLog, record_id

Chunk = dict[str, object]

HEADING_LABELS = {
    "purpose": "purpose",
    "scope": "scope",
    "must-do": "must_do",
    "must not do": "must_not_do",
    "must-not-do": "must_not_do",
    "success criteria": "success_criteria",
    "design assertions": "design_assertions",
}


def chunk_markdown(text: str, file_path: str) -> list[Chunk]:
    """Split markdown on heading boundaries with semantic labels."""
    if not text.strip():
        return []

    lines = text.splitlines()
    sections: list[tuple[str, list[str], str | None]] = []
    heading_stack: list[str] = []
    current_heading = ""
    current_lines: list[str] = []
    current_label: str | None = None

    for line in lines:
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            if current_lines or current_heading:
                sections.append((current_heading, current_lines, current_label))
                current_lines = []

            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            heading_stack = heading_stack[: level - 1]
            heading_stack.append(title)
            current_heading = " > ".join(heading_stack)
            current_label = _semantic_label_for_heading(title)
            current_lines.append(line)
            continue

        current_lines.append(line)

    if current_lines or current_heading:
        sections.append((current_heading, current_lines, current_label))

    chunks: list[Chunk] = []
    for index, (heading, section_lines, label) in enumerate(sections):
        content = "\n".join(section_lines).strip()
        if not content:
            continue
        chunks.append(
            {
                "content": content,
                "chunk_type": "markdown_section",
                "section_heading": heading,
                "section_path": heading,
                "semantic_label": label or "general",
                "chunk_index": index,
                "file_path": file_path,
            }
        )

    return chunks


def chunk_python(text: str, file_path: str) -> list[Chunk]:
    """Split Python source on class and function boundaries using AST."""
    if not text.strip():
        return []

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [
            {
                "content": text.strip(),
                "chunk_type": "python_module",
                "section_heading": file_path.split("/")[-1],
                "section_path": file_path,
                "chunk_index": 0,
                "file_path": file_path,
            }
        ]

    lines = text.splitlines()
    chunks: list[Chunk] = []
    chunk_idx = 0

    nodes: list[tuple[str, str, int, int]] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            nodes.append((node.name, "python_class", node.lineno, node.end_lineno or node.lineno))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            nodes.append((node.name, "python_function", node.lineno, node.end_lineno or node.lineno))

    if not nodes:
        return [
            {
                "content": text.strip(),
                "chunk_type": "python_module",
                "section_heading": file_path.split("/")[-1],
                "section_path": file_path,
                "chunk_index": 0,
                "file_path": file_path,
            }
        ]

    first_start = nodes[0][2]
    if first_start > 1:
        preamble = "\n".join(lines[: first_start - 1]).strip()
        if preamble:
            chunks.append(
                {
                    "content": preamble,
                    "chunk_type": "python_module",
                    "section_heading": file_path.split("/")[-1],
                    "section_path": file_path,
                    "chunk_index": chunk_idx,
                    "file_path": file_path,
                }
            )
            chunk_idx += 1

    for name, node_type, start, end in nodes:
        content = "\n".join(lines[start - 1 : end]).strip()
        if not content:
            continue
        chunks.append(
            {
                "content": content,
                "chunk_type": node_type,
                "section_heading": name,
                "section_path": name,
                "chunk_index": chunk_idx,
                "file_path": file_path,
            }
        )
        chunk_idx += 1

    return chunks


def chunk_csharp(text: str, file_path: str, max_chars: int = 12000) -> list[Chunk]:
    """Chunk C# source by type and member boundaries."""
    if not text.strip():
        return []

    lines = text.splitlines()
    namespace_name = _find_namespace(text)
    types = _find_csharp_types(lines)
    if not types:
        return [
            {
                "content": text.strip(),
                "chunk_type": "csharp_file",
                "section_heading": file_path.split("/")[-1],
                "section_path": file_path,
                "namespace": namespace_name,
                "chunk_index": 0,
                "file_path": file_path,
            }
        ]

    chunks: list[Chunk] = []
    chunk_index = 0

    for type_block in types:
        declaration = "\n".join(lines[type_block.start - 1 : type_block.body_start - 1]).strip()
        if declaration:
            chunks.append(
                {
                    "content": declaration,
                    "chunk_type": "csharp_type",
                    "section_heading": type_block.name,
                    "section_path": type_block.name,
                    "namespace": namespace_name,
                    "type_name": type_block.name,
                    "member_kind": "type",
                    "chunk_index": chunk_index,
                    "file_path": file_path,
                }
            )
            chunk_index += 1

        for member in _find_csharp_members(lines, type_block, max_chars=max_chars):
            member["chunk_index"] = chunk_index
            member["file_path"] = file_path
            member["namespace"] = namespace_name
            member["type_name"] = type_block.name
            member["section_path"] = f"{type_block.name} > {member['member_name']}"
            member["section_heading"] = member["member_name"]
            chunks.append(member)
            chunk_index += 1

    return chunks


def chunk_sql(text: str, file_path: str) -> list[Chunk]:
    """Split SQL on CREATE TABLE and CREATE [OR REPLACE] FUNCTION boundaries."""
    if not text.strip():
        return []

    pattern = re.compile(
        r"(?:^|\n)"
        r"(CREATE\s+(?:OR\s+REPLACE\s+)?(?:CONSTRAINT\s+)?(?:TABLE|FUNCTION|TRIGGER|INDEX|TYPE)\s+"
        r"(?:IF\s+NOT\s+EXISTS\s+)?"
        r"(\w+))",
        re.IGNORECASE,
    )

    matches = list(pattern.finditer(text))
    if not matches:
        return [
            {
                "content": text.strip(),
                "chunk_type": "sql_table",
                "section_heading": file_path.split("/")[-1],
                "section_path": file_path,
                "chunk_index": 0,
                "file_path": file_path,
            }
        ]

    chunks: list[Chunk] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        content = text[start:end].strip()

        header_upper = match.group(1).upper()
        if "FUNCTION" in header_upper:
            chunk_type = "sql_function"
        elif "TRIGGER" in header_upper:
            chunk_type = "sql_trigger"
        elif "INDEX" in header_upper:
            chunk_type = "sql_index"
        elif "TYPE" in header_upper:
            chunk_type = "sql_type"
        else:
            chunk_type = "sql_table"

        chunks.append(
            {
                "content": content,
                "chunk_type": chunk_type,
                "section_heading": match.group(2),
                "section_path": match.group(2),
                "chunk_index": index,
                "file_path": file_path,
            }
        )

    return chunks


def chunk_yaml(text: str, file_path: str) -> list[Chunk]:
    """Chunk YAML with semantic handling for sync-doc.yaml."""
    if not text.strip():
        return []
    if file_path == "sync-doc.yaml":
        return chunk_sync_doc_yaml(text, file_path)

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return [
            {
                "content": text.strip(),
                "chunk_type": "yaml_document",
                "section_heading": file_path.split("/")[-1],
                "section_path": file_path,
                "chunk_index": 0,
                "file_path": file_path,
            }
        ]

    services = data.get("services", {}) if isinstance(data, dict) else {}
    if not isinstance(services, dict) or not services:
        return [
            {
                "content": text.strip(),
                "chunk_type": "yaml_document",
                "section_heading": file_path.split("/")[-1],
                "section_path": file_path,
                "chunk_index": 0,
                "file_path": file_path,
            }
        ]

    chunks: list[Chunk] = []
    for index, (name, config) in enumerate(services.items()):
        service_yaml = yaml.dump({name: config}, default_flow_style=False, sort_keys=False)
        chunks.append(
            {
                "content": service_yaml.strip(),
                "chunk_type": "docker_service",
                "section_heading": name,
                "section_path": f"services > {name}",
                "chunk_index": index,
                "file_path": file_path,
            }
        )
    return chunks


def chunk_sync_doc_yaml(text: str, file_path: str) -> list[Chunk]:
    """Chunk sync-doc.yaml by global scope, areas, and checks."""
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        return []

    chunks: list[Chunk] = []
    chunk_index = 0

    global_section = data.get("global")
    if isinstance(global_section, dict):
        chunks.append(
            {
                "content": yaml.dump({"global": global_section}, default_flow_style=False, sort_keys=False).strip(),
                "chunk_type": "sync_doc_global",
                "section_heading": "global",
                "section_path": "global",
                "semantic_label": "manifest_global",
                "chunk_index": chunk_index,
                "file_path": file_path,
            }
        )
        chunk_index += 1

    areas = data.get("areas", {})
    if isinstance(areas, dict):
        for name, area in areas.items():
            chunks.append(
                {
                    "content": yaml.dump({name: area}, default_flow_style=False, sort_keys=False).strip(),
                    "chunk_type": "sync_doc_area",
                    "section_heading": name,
                    "section_path": f"areas > {name}",
                    "semantic_label": "manifest_area",
                    "chunk_index": chunk_index,
                    "file_path": file_path,
                    "area": name,
                }
            )
            chunk_index += 1

    checks = data.get("checks", {})
    if isinstance(checks, dict):
        for name, check in checks.items():
            chunks.append(
                {
                    "content": yaml.dump({name: check}, default_flow_style=False, sort_keys=False).strip(),
                    "chunk_type": "sync_doc_check",
                    "section_heading": name,
                    "section_path": f"checks > {name}",
                    "semantic_label": "manifest_check",
                    "chunk_index": chunk_index,
                    "file_path": file_path,
                }
            )
            chunk_index += 1

    return chunks


def chunk_decisions(text: str, file_path: str) -> list[Chunk]:
    """Split JSONL decision records into one enriched chunk per record."""
    if not text.strip():
        return []

    log = DecisionLog.from_text(text)
    chunks: list[Chunk] = []
    for index, line in enumerate(text.strip().splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        rid = record_id(record)
        status = log.status(rid)
        topic = record.get("topic", "unknown")
        alternatives = record.get("alternatives_considered", [])
        tags = record.get("tags", [])
        supersedes = record.get("supersedes", []) or []

        lines = [
            f"Decision: {record.get('decision', '')}",
            f"Topic: {topic}",
            f"Rationale: {record.get('rationale', '')}",
            f"Alternatives considered: {', '.join(alternatives) if alternatives else 'none'}",
            f"Context: {record.get('session_context', '')}",
            f"Tags: {', '.join(tags) if tags else 'none'}",
            f"Date: {record.get('datetime', '')}",
            f"Status: {status}",
        ]
        if supersedes:
            lines.append("Supersedes:")
            for entry in supersedes:
                path = entry.get("path", "")
                summary = entry.get("retraction_summary", "")
                lines.append(f"  - {path}: {summary}")
        content = "\n".join(lines)

        chunks.append(
            {
                "content": content,
                "chunk_type": "decision",
                "section_heading": topic,
                "section_path": topic,
                "decision_topic": topic,
                "decision_status": status,
                "record_id": rid,
                "semantic_label": "decision_record",
                "chunk_index": index,
                "file_path": file_path,
            }
        )

    return chunks


@dataclass
class CSharpTypeBlock:
    name: str
    kind: str
    start: int
    body_start: int
    end: int


def _semantic_label_for_heading(heading: str) -> str | None:
    normalized = heading.strip().lower()
    return HEADING_LABELS.get(normalized)


def _find_namespace(text: str) -> str | None:
    match = re.search(r"^\s*namespace\s+([A-Za-z_][\w\.]*)", text, re.MULTILINE)
    return match.group(1) if match else None


def _find_csharp_types(lines: list[str]) -> list[CSharpTypeBlock]:
    blocks: list[CSharpTypeBlock] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        match = re.match(
            r"^\s*(?:file\s+)?(?:public|private|protected|internal|sealed|abstract|static|partial|readonly|\s)*"
            r"\b(class|record|interface|struct|enum)\s+([A-Za-z_][\w]*)",
            line,
        )
        if not match:
            index += 1
            continue

        body_start = _find_next_line_with_char(lines, index, "{")
        if body_start is None:
            index += 1
            continue
        end = _find_block_end(lines, body_start)
        blocks.append(
            CSharpTypeBlock(
                name=match.group(2),
                kind=match.group(1),
                start=index + 1,
                body_start=body_start + 1,
                end=end + 1,
            )
        )
        index = end + 1
    return blocks


def _find_csharp_members(lines: list[str], type_block: CSharpTypeBlock, max_chars: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    start = type_block.body_start
    end = type_block.end - 1
    line_index = start

    while line_index < end:
        relative_depth = _relative_depth_for_line(lines, start - 1, line_index)
        if relative_depth != 1:
            line_index += 1
            continue

        member_start = _find_member_start(lines, line_index, end)
        if member_start is None:
            line_index += 1
            continue

        member = _extract_member(lines, member_start, start - 1, end, type_block.name, max_chars)
        if member is None:
            line_index = member_start + 1
            continue

        chunks.extend(member["chunks"])
        line_index = member["next_line"]

    return chunks


def _find_member_start(lines: list[str], line_index: int, end: int) -> int | None:
    current = line_index
    while current < end:
        stripped = lines[current].strip()
        if not stripped:
            current += 1
            continue
        if stripped.startswith("["):
            current += 1
            continue
        return current
    return None


def _extract_member(
    lines: list[str],
    member_start: int,
    type_body_start_index: int,
    type_end: int,
    type_name: str,
    max_chars: int,
) -> dict[str, object] | None:
    line = lines[member_start].strip()
    if re.match(r"^(class|record|interface|struct|enum)\b", line):
        return None

    member_name, member_kind = _classify_member(line, type_name)
    if not member_name:
        return None

    next_nonempty = _next_nonempty_line(lines, member_start + 1, type_end)

    if "=>" in line and ";" in line:
        member_end = member_start
    elif "{" in line:
        member_end = _find_block_end(lines, member_start)
    elif next_nonempty is not None and "{" in lines[next_nonempty]:
        member_end = _find_block_end(lines, next_nonempty)
    else:
        member_end = _find_statement_end(lines, member_start, type_end)

    content = "\n".join(lines[member_start : member_end + 1]).strip()
    if not content:
        return None

    raw_chunk = {
        "content": content,
        "chunk_type": "csharp_member",
        "member_name": member_name,
        "member_kind": member_kind,
    }

    if len(content) <= max_chars:
        return {"chunks": [raw_chunk], "next_line": member_end + 1}

    split_chunks = []
    for split_index, part in enumerate(_split_large_member(lines[member_start : member_end + 1], max_chars)):
        split_chunks.append(
            {
                "content": part,
                "chunk_type": "csharp_member",
                "member_name": member_name if split_index == 0 else f"{member_name} (part {split_index + 1})",
                "member_kind": member_kind,
            }
        )

    return {"chunks": split_chunks, "next_line": member_end + 1}


def _classify_member(line: str, type_name: str) -> tuple[str | None, str | None]:
    constructor_match = re.search(rf"\b{re.escape(type_name)}\s*\(", line)
    if constructor_match:
        return type_name, "constructor"

    method_match = re.search(r"([A-Za-z_][\w]*)\s*\(", line)
    if method_match and not re.search(r"\b(if|for|foreach|while|switch|catch|using|lock)\s*\(", line):
        return method_match.group(1), "method"

    property_match = re.search(r"([A-Za-z_][\w]*)\s*{\s*(?:get|init|set)", line)
    if property_match:
        return property_match.group(1), "property"

    field_match = re.search(r"([A-Za-z_][\w]*)\s*(?:=|;)$", line)
    if field_match:
        return field_match.group(1), "field"

    return None, None


def _find_block_end(lines: list[str], start_index: int) -> int:
    depth = 0
    seen_open = False
    for index in range(start_index, len(lines)):
        for char in lines[index]:
            if char == "{":
                depth += 1
                seen_open = True
            elif char == "}":
                depth -= 1
                if seen_open and depth == 0:
                    return index
    return len(lines) - 1


def _find_statement_end(lines: list[str], start_index: int, type_end: int) -> int:
    for index in range(start_index, type_end):
        if ";" in lines[index]:
            return index
    return start_index


def _split_large_member(lines: list[str], max_chars: int) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    current_len = 0

    for line in lines:
        line_len = len(line) + 1
        if current and current_len + line_len > max_chars:
            parts.append("\n".join(current).strip())
            current = [line]
            current_len = line_len
            continue
        current.append(line)
        current_len += line_len

    if current:
        parts.append("\n".join(current).strip())
    return parts


def _relative_depth_for_line(lines: list[str], block_start_index: int, target_line_index: int) -> int:
    depth = 0
    for index in range(block_start_index, target_line_index):
        depth += lines[index].count("{")
        depth -= lines[index].count("}")
    return depth


def _find_next_line_with_char(lines: list[str], start_index: int, char: str) -> int | None:
    for index in range(start_index, len(lines)):
        if char in lines[index]:
            return index
    return None


def _next_nonempty_line(lines: list[str], start_index: int, end_index: int) -> int | None:
    for index in range(start_index, min(end_index, len(lines))):
        if lines[index].strip():
            return index
    return None


CHUNKER_MAP = {
    "markdown": chunk_markdown,
    "python": chunk_python,
    "csharp": chunk_csharp,
    "sql": chunk_sql,
    "yaml": chunk_yaml,
    "decisions": chunk_decisions,
}
