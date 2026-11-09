import pandas as pd
import pytest

from sentier_brightway.flows import load_bafu_flows, load_ef_flows
from tests.conftest import B1, B2, B3, E1, E2, EF_TERMS, FLOWS, VOCAB_TERMS


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


def test_only_elementary_flow_terms_are_flows(data_root):
    # the fixture term files also hold an impact category and a process term
    assert sorted(load_ef_flows(data_root).code) == sorted([E1, E2])
    assert sorted(load_bafu_flows(data_root).code) == sorted([B1, B2, B3])


def test_flow_without_attributes_has_no_categories(data_root):
    path = data_root / EF_TERMS
    df = pd.read_parquet(path)
    df.loc[df["iri"] == FLOWS + E2, "attributes"] = None
    df.to_parquet(path, index=False)
    row = load_ef_flows(data_root).set_index("code").loc[E2]
    assert row["categories"] == ()
    assert row["cas_number"] is None


def test_term_file_missing_source_column_is_an_error(data_root):
    path = data_root / EF_TERMS
    pd.read_parquet(path).drop(columns=["source"]).to_parquet(path, index=False)
    with pytest.raises(ValueError, match="missing required columns") as exc_info:
        load_ef_flows(data_root)
    assert "source" in str(exc_info.value)


def test_no_vocab_term_files_is_an_error(tmp_path):
    (tmp_path / VOCAB_TERMS).mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="terms"):
        load_ef_flows(tmp_path)


def test_flow_iri_not_matching_prefix_is_an_error(data_root):
    path = data_root / EF_TERMS
    df = pd.read_parquet(path)
    bad_iri = "urn:uuid:" + E1
    df.loc[df["iri"] == FLOWS + E1, "iri"] = bad_iri
    df.to_parquet(path, index=False)
    with pytest.raises(ValueError, match="urn:uuid"):
        load_ef_flows(data_root)


def test_duplicate_flow_code_is_an_error(data_root):
    path = data_root / EF_TERMS
    df = pd.read_parquet(path)
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    df.to_parquet(path, index=False)
    with pytest.raises(ValueError, match=E1):
        load_ef_flows(data_root)
