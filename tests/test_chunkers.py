"""Tests for structure-aware chunkers."""

import sys
import textwrap
from pathlib import Path

# Add parent directory to path so we can import chunkers
sys.path.insert(0, str(Path(__file__).parent.parent))

from chunkers import chunk_markdown, chunk_python, chunk_sql, chunk_yaml


class TestMarkdownChunker:
    def test_splits_on_h2(self):
        md = textwrap.dedent("""\
            # Top Title

            Intro paragraph.

            ## Section A

            Content A.

            ## Section B

            Content B.
        """)
        chunks = chunk_markdown(md, "test.md")
        assert len(chunks) == 3  # intro + section A + section B
        assert chunks[0]["chunk_type"] == "markdown_section"
        assert chunks[1]["section_heading"] == "Top Title > Section A"
        assert chunks[1]["section_path"] == "Top Title > Section A"
        assert "Content A." in chunks[1]["content"]

    def test_preserves_heading_hierarchy(self):
        md = textwrap.dedent("""\
            # Main

            ## Parent

            ### Child

            Child content.
        """)
        chunks = chunk_markdown(md, "test.md")
        child_chunk = [c for c in chunks if "Child content" in c["content"]][0]
        assert "Parent" in child_chunk["section_heading"]

    def test_empty_file(self):
        chunks = chunk_markdown("", "empty.md")
        assert chunks == []


class TestPythonChunker:
    def test_splits_on_functions(self):
        code = textwrap.dedent("""\
            import os

            def foo():
                return 1

            def bar():
                return 2
        """)
        chunks = chunk_python(code, "test.py")
        names = [c["section_heading"] for c in chunks]
        assert "foo" in names
        assert "bar" in names
        assert all(c["chunk_type"] in ("python_function", "python_class", "python_module") for c in chunks)

    def test_splits_on_classes(self):
        code = textwrap.dedent("""\
            class MyClass:
                def method(self):
                    pass
        """)
        chunks = chunk_python(code, "test.py")
        class_chunks = [c for c in chunks if c["chunk_type"] == "python_class"]
        assert len(class_chunks) == 1
        assert class_chunks[0]["section_heading"] == "MyClass"

    def test_empty_file(self):
        chunks = chunk_python("", "empty.py")
        assert chunks == []


class TestSqlChunker:
    def test_splits_on_create_table(self):
        sql = textwrap.dedent("""\
            CREATE TABLE users (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL
            );

            CREATE TABLE orders (
                id SERIAL PRIMARY KEY,
                user_id INT REFERENCES users(id)
            );
        """)
        chunks = chunk_sql(sql, "test.sql")
        names = [c["section_heading"] for c in chunks]
        assert "users" in names
        assert "orders" in names
        assert all(c["chunk_type"] in ("sql_table", "sql_function") for c in chunks)

    def test_splits_on_create_function(self):
        sql = textwrap.dedent("""\
            CREATE OR REPLACE FUNCTION my_func()
            RETURNS void AS $$
            BEGIN
                RETURN;
            END;
            $$ LANGUAGE plpgsql;
        """)
        chunks = chunk_sql(sql, "test.sql")
        assert len(chunks) >= 1
        assert chunks[0]["section_heading"] == "my_func"
        assert chunks[0]["chunk_type"] == "sql_function"


class TestYamlChunker:
    def test_splits_on_services(self):
        yml = textwrap.dedent("""\
            services:
              postgres:
                image: postgres:16
                ports:
                  - "5432:5432"

              redis:
                image: redis:7
                ports:
                  - "6379:6379"

            volumes:
              pgdata:
                driver: local
        """)
        chunks = chunk_yaml(yml, "docker-compose.yml")
        names = [c["section_heading"] for c in chunks]
        assert "postgres" in names
        assert "redis" in names
        assert all(c["chunk_type"] == "docker_service" for c in chunks)

    def test_non_compose_yaml_falls_back_to_document(self):
        yml = textwrap.dedent("""\
            key: value
            nested:
              child: true
        """)
        chunks = chunk_yaml(yml, "config.yaml")
        assert len(chunks) == 1
        assert chunks[0]["chunk_type"] == "yaml_document"
