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
    ).encode("utf-8")


@pytest.fixture
def edge_csv_bytes() -> bytes:
    return (
        "Age Years,income,city,segment,flag,label,notes\n"
        "18,0,Sydney,A,true,old,\"comma, inside\"\n"
        "21,1000,,B,false,old,\n"
        "21,1000,Melbourne,B,false,keep,text\n"
        "35,,Perth,,true,,text\n"
        "44,99000,Sydney,C,false,OLD,text\n"
    ).encode("utf-8")


@pytest.fixture
def loaded_store(csv_bytes: bytes) -> WorkspaceStore:
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(csv_bytes, "customers.csv")
    return workspace_store


@pytest.fixture
def edge_store(edge_csv_bytes: bytes) -> WorkspaceStore:
    workspace_store = WorkspaceStore()
    workspace_store.load_csv(edge_csv_bytes, "edge_customers.csv")
    return workspace_store