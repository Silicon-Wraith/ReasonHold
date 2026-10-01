"""Weaviate schema for docs-rag ProjectDoc collection."""

import weaviate.classes.config as wvc

EXPECTED_PROPERTIES = {
    "content",
    "file_path",
    "chunk_type",
    "file_type",
    "authority_level",
    "document_kind",
    "area",
    "project",
    "section_heading",
    "section_path",
    "semantic_label",
    "namespace",
    "type_name",
    "member_name",
    "member_kind",
    "decision_topic",
    "decision_status",
    "chunk_index",
    "last_modified",
    "retraction_summary",
    "retraction_decision",
    "retraction_date",
    "record_id",
}


def collection_matches_expected_schema(client, name: str) -> bool:
    if not client.collections.exists(name):
        return False
    config = client.collections.get(name).config.get(simple=False)
    return {prop.name for prop in config.properties} == EXPECTED_PROPERTIES


def collection_properties() -> list[wvc.Property]:
    return [
        wvc.Property(
            name="content",
            data_type=wvc.DataType.TEXT,
            description="The raw chunk text content.",
            index_searchable=True,
            index_filterable=False,
        ),
        wvc.Property(
            name="file_path",
            data_type=wvc.DataType.TEXT,
            description="Relative path to source file from project root.",
            index_searchable=False,
            index_filterable=True,
            # FIELD, not the WORD default. file_path is an identifier, and under
            # WORD tokenization an equality filter matches by token containment:
            # equal("docs/specs/worker-design.md") also matched
            # docs/specs/2026-03-16-analysis-worker-design.md, so indexing one
            # file deleted the other's chunks.
            tokenization=wvc.Tokenization.FIELD,
        ),
        wvc.Property(
            name="chunk_type",
            data_type=wvc.DataType.TEXT,
            description="Type: markdown_section, python_function, python_class, sql_table, sql_function, docker_service.",
            index_searchable=False,
            index_filterable=True,
        ),
        wvc.Property(
            name="file_type",
            data_type=wvc.DataType.TEXT,
            description="High-level source type such as markdown, csharp, yaml, or decisions.",
            index_searchable=False,
            index_filterable=True,
        ),
        wvc.Property(
            name="authority_level",
            data_type=wvc.DataType.TEXT,
            description="Authority classification such as architecture, implementation-spec, implementation, or test.",
            index_searchable=True,
            index_filterable=True,
        ),
        wvc.Property(
            name="document_kind",
            data_type=wvc.DataType.TEXT,
            description="Normalized document kind for retrieval context.",
            index_searchable=True,
            index_filterable=True,
        ),
        wvc.Property(
            name="area",
            data_type=wvc.DataType.TEXT,
            description="sync-doc manifest area when inferable.",
            index_searchable=True,
            index_filterable=True,
        ),
        wvc.Property(
            name="project",
            data_type=wvc.DataType.TEXT,
            description="Owning project when inferable from path or manifest.",
            index_searchable=True,
            index_filterable=True,
        ),
        wvc.Property(
            name="section_heading",
            data_type=wvc.DataType.TEXT,
            description="Heading hierarchy (markdown) or function/class name (code).",
            index_searchable=True,
            index_filterable=True,
        ),
        wvc.Property(
            name="section_path",
            data_type=wvc.DataType.TEXT,
            description="Full semantic path within the source file.",
            index_searchable=True,
            index_filterable=True,
        ),
        wvc.Property(
            name="semantic_label",
            data_type=wvc.DataType.TEXT,
            description="Semantic classification such as must_do, purpose, or manifest_area.",
            index_searchable=True,
            index_filterable=True,
        ),
        wvc.Property(
            name="namespace",
            data_type=wvc.DataType.TEXT,
            description="Namespace for code chunks where available.",
            index_searchable=True,
            index_filterable=True,
        ),
        wvc.Property(
            name="type_name",
            data_type=wvc.DataType.TEXT,
            description="Type name for code chunks where available.",
            index_searchable=True,
            index_filterable=True,
        ),
        wvc.Property(
            name="member_name",
            data_type=wvc.DataType.TEXT,
            description="Member name for code chunks where available.",
            index_searchable=True,
            index_filterable=True,
        ),
        wvc.Property(
            name="member_kind",
            data_type=wvc.DataType.TEXT,
            description="Member classification such as method, property, constructor, or field.",
            index_searchable=True,
            index_filterable=True,
        ),
        wvc.Property(
            name="decision_topic",
            data_type=wvc.DataType.TEXT,
            description="Decision topic for decision-log chunks.",
            index_searchable=True,
            index_filterable=True,
        ),
        wvc.Property(
            name="decision_status",
            data_type=wvc.DataType.TEXT,
            description="Decision status such as active or superseded.",
            index_searchable=True,
            index_filterable=True,
        ),
        wvc.Property(
            name="chunk_index",
            data_type=wvc.DataType.INT,
            description="Zero-based chunk position within the file.",
            index_filterable=True,
        ),
        wvc.Property(
            name="last_modified",
            data_type=wvc.DataType.DATE,
            description="Source file mtime at indexing time.",
            index_filterable=True,
        ),
        wvc.Property(
            name="retraction_summary",
            data_type=wvc.DataType.TEXT,
            description="One-line correction stating what now holds, when this chunk is superseded by an active decision.",
            index_searchable=True,
            index_filterable=True,
        ),
        wvc.Property(
            name="retraction_decision",
            data_type=wvc.DataType.TEXT,
            description="Decision topic that supersedes this chunk's content.",
            index_searchable=False,
            index_filterable=True,
        ),
        wvc.Property(
            name="retraction_date",
            data_type=wvc.DataType.DATE,
            description="Date of the superseding decision.",
            index_filterable=True,
        ),
        wvc.Property(
            name="record_id",
            data_type=wvc.DataType.TEXT,
            description="Decision or pending record id for record chunks; empty for document and code chunks.",
            index_searchable=False,
            index_filterable=True,
            tokenization=wvc.Tokenization.FIELD,
        ),
    ]
