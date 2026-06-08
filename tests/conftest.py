from __future__ import annotations

import pytest

from danaleo.core.session_store import WorkspaceStore, store


@pytest.fixture(autouse=True)
def reset_global_store():
    store.reset()
    yield
    store.reset()


@pytest.fixture
def csv_bytes() -> bytes:
    return (
        "age,income,city,segment,flag\n"
        "25,50000,Sydney,A,true\n"
        "34,65000,Melbourne,B,false\n"
        "41,72000,Sydney,A,true\n"
        "29,,Brisbane,C,false\n"
        "52,91000,Perth,B,true\n"
        "23,48000,Sydney,A,false\n"
        "38,81000,Melbourne,C,true\n"
        "45,88000,Brisbane,B,false\n"
    ).encode()


@pytest.fixture
def loaded_store(csv_bytes: bytes) -> WorkspaceStore:
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(csv_bytes, "customers.csv")
    return workspace_store
