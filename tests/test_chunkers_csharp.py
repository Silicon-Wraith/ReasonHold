"""Tests for structure-aware C# chunking."""

import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from chunkers import chunk_csharp


class TestCSharpChunker:
    def test_splits_type_and_members(self):
        code = textwrap.dedent("""\
            namespace Nebulon.Core;

            public class Widget
            {
                public Widget(string id)
                {
                    Id = id;
                }

                public string Id { get; }

                public int Compute(int value)
                {
                    return value + 1;
                }
            }
        """)

        chunks = chunk_csharp(code, "src/Nebulon.Core/Widget.cs", max_chars=5000)

        assert any(chunk["chunk_type"] == "csharp_type" and chunk["type_name"] == "Widget" for chunk in chunks)
        assert any(
            chunk["member_kind"] == "constructor" and chunk["member_name"] == "Widget"
            for chunk in chunks
            if chunk["chunk_type"] == "csharp_member"
        )
        assert any(
            chunk["member_kind"] == "property" and chunk["member_name"] == "Id"
            for chunk in chunks
            if chunk["chunk_type"] == "csharp_member"
        )
        assert any(
            chunk["member_kind"] == "method" and chunk["member_name"] == "Compute"
            for chunk in chunks
            if chunk["chunk_type"] == "csharp_member"
        )

    def test_does_not_split_mid_method_when_under_budget(self):
        code = textwrap.dedent("""\
            public class Widget
            {
                public int Compute(int value)
                {
                    var first = value + 1;
                    var second = first + 2;
                    return second;
                }
            }
        """)

        chunks = chunk_csharp(code, "src/Nebulon.Core/Widget.cs", max_chars=5000)
        method_chunk = next(chunk for chunk in chunks if chunk.get("member_name") == "Compute")
        assert "var first = value + 1;" in method_chunk["content"]
        assert "return second;" in method_chunk["content"]

    def test_splits_large_single_member_only_when_needed(self):
        body = "\n".join(f"        value += {index};" for index in range(20))
        code = (
            "public class Widget\n"
            "{\n"
            "    public int Compute(int value)\n"
            "    {\n"
            f"{body}\n"
            "        return value;\n"
            "    }\n"
            "}\n"
        )

        chunks = chunk_csharp(code, "src/Nebulon.Core/Widget.cs", max_chars=120)
        compute_chunks = [chunk for chunk in chunks if str(chunk.get("member_name", "")).startswith("Compute")]
        assert len(compute_chunks) > 1
