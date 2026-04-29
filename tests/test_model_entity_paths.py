from __future__ import annotations

import pytest
from dplib.error import Error
from dplib.models import Catalog, Package, Resource


def test_model_iter_entity_paths_includes_json_pointers_and_types() -> None:
    resource = Resource(name="sales-table", path="sales.csv")
    package = Package(name="sales-dataset", resources=[resource])
    archive = Catalog(name="archive", resources=[Resource(name="notes", path="notes.md")])
    catalog = Catalog(name="warehouse", packages=[package], catalogs=[archive])

    references = {
        reference.name_path: reference
        for reference in catalog.iter_entity_paths(include_self=True)
    }

    assert references["warehouse"].json_pointer == ""
    assert references["warehouse"].entity_type == "catalog"
    assert references["warehouse.sales-dataset"].json_pointer == "/packages/0"
    assert references["warehouse.sales-dataset"].entity_type == "package"
    assert (
        references["warehouse.sales-dataset.sales-table"].json_pointer
        == "/packages/0/resources/0"
    )
    assert references["warehouse.archive.notes"].json_pointer == "/catalogs/0/resources/0"


def test_model_iter_entity_paths_without_self_keeps_existing_relative_selectors() -> None:
    resource = Resource(name="sales-table", path="sales.csv")
    package = Package(name="sales-dataset", resources=[resource])
    catalog = Catalog(name="warehouse", packages=[package])

    references = {
        reference.name_path: reference for reference in catalog.iter_entity_paths()
    }

    assert "warehouse" not in references
    assert "sales-dataset" in references
    assert "sales-dataset.sales-table" in references
    assert catalog.get_entity("sales-dataset.sales-table") is resource
    assert catalog.get_entity("warehouse.sales-dataset.sales-table") is resource


def test_model_validate_entity_paths_rejects_duplicate_full_paths() -> None:
    catalog = Catalog(
        resources=[
            Resource(name="duplicate", path="a.csv"),
            Resource(name="duplicate", path="b.csv"),
        ]
    )

    errors = catalog.validate_entity_paths()

    assert len(errors) == 1
    assert "duplicate" in errors[0]
    assert "/resources/0" in errors[0]
    assert "/resources/1" in errors[0]


def test_model_validate_entity_paths_allows_repeated_leaf_names_when_qualified() -> None:
    catalog = Catalog(
        catalogs=[
            Catalog(name="first", resources=[Resource(name="table", path="a.csv")]),
            Catalog(name="second", resources=[Resource(name="table", path="b.csv")]),
        ]
    )

    assert catalog.validate_entity_paths() == []


def test_model_validate_entity_paths_rejects_selector_unsafe_names() -> None:
    catalog = Catalog(resources=[Resource(name="bad.name", path="a.csv")])

    errors = catalog.validate_entity_paths()

    assert len(errors) == 1
    assert "bad.name" in errors[0]
    assert "letters, numbers, hyphens, and underscores" in errors[0]


def test_model_assert_valid_entity_paths_raises_actionable_error() -> None:
    catalog = Catalog(resources=[Resource(name="bad.name", path="a.csv")])

    with pytest.raises(Error, match="Invalid entity paths"):
        catalog.assert_valid_entity_paths()
