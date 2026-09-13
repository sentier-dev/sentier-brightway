from sentier_brightway.flows import load_bafu_flows, load_ef_flows
from tests.conftest import B1, B2, E1, E2


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
