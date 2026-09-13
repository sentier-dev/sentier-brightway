import pandas as pd
import pytest

from sentier_brightway.flows import load_bafu_flows, load_ef_flows
from tests.conftest import B1, B2, E1, E2, FLOWS


def test_ef_flows_filtered_by_source_and_keyed_by_uuid(data_root):
    ef = load_ef_flows(data_root)
    assert sorted(ef.code) == sorted([E1, E2])
    row = ef.set_index("code").loc[E1]
    assert row["name"] == "carbon dioxide (fossil)"
    assert row["categories"] == ("air",)
    assert row["cas_number"] == "124-38-9"


def test_bafu_flows_carry_compartment_and_subcompartment(data_root):
    bafu = load_bafu_flows(data_root)
    assert B1 in set(bafu.code) and B2 in set(bafu.code)
    assert bafu.set_index("code").loc[B2, "categories"] == ("emissions to water", "lake")


def test_ef_and_bafu_do_not_leak_into_each_other(data_root):
    assert not set(load_ef_flows(data_root).code) & set(load_bafu_flows(data_root).code)


def test_missing_cas_number_is_none_not_nan(data_root):
    ef = load_ef_flows(data_root)
    value = ef.set_index("code").loc[E2, "cas_number"]
    assert value is None


def test_shard_missing_source_column_is_an_error(data_root):
    path = data_root / "sentier-vocab/data/elementary-flows/air-01.parquet"
    pd.read_parquet(path).drop(columns=["source"]).to_parquet(path, index=False)
    with pytest.raises(ValueError, match="missing required columns") as exc_info:
        load_ef_flows(data_root)
    assert "source" in str(exc_info.value)


def test_no_vocab_shards_is_an_error(tmp_path):
    (tmp_path / "sentier-vocab" / "data" / "elementary-flows").mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        load_ef_flows(tmp_path)


def test_flow_iri_not_matching_prefix_is_an_error(data_root):
    path = data_root / "sentier-vocab/data/elementary-flows/air-01.parquet"
    df = pd.read_parquet(path)
    bad_iri = "urn:uuid:" + E1
    df.loc[df["iri"] == FLOWS + E1, "iri"] = bad_iri
    df.to_parquet(path, index=False)
    with pytest.raises(ValueError, match="urn:uuid"):
        load_ef_flows(data_root)


def test_duplicate_flow_code_is_an_error(data_root):
    path = data_root / "sentier-vocab/data/elementary-flows/air-01.parquet"
    df = pd.read_parquet(path)
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    df.to_parquet(path, index=False)
    with pytest.raises(ValueError, match=E1):
        load_ef_flows(data_root)
