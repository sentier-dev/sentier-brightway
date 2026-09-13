import pandas as pd
import pytest

from sentier_brightway.methods import MethodSpec, load_methods
from tests.conftest import E1, E2, FLOWS

FOLDER = "sentier-methods/data/01-ef-3.1"


def test_one_spec_per_method_with_brightway_key(data_root):
    specs = load_methods(data_root)
    keys = {s.key for s in specs}
    assert ("sentier", "EF v3.1", "Climate change") in keys
    assert ("sentier", "EF v3.1", "Ionising radiation") in keys
    assert all(isinstance(s, MethodSpec) for s in specs)


def test_regionalized_rows_are_skipped_and_flow_is_bare_uuid(data_root):
    climate = next(s for s in load_methods(data_root) if s.key[-1] == "Climate change")
    assert climate.cfs == ((E1, 1.0),)
    assert climate.unit == "kg CO2 eq"
    assert climate.method_id == "ef-3.1:climate-change"


def test_flow_contexts_are_collected_for_biosphere_nodes(data_root):
    specs = load_methods(data_root)
    contexts = {}
    for s in specs:
        contexts.update(s.flow_context)
    assert contexts[E2] == ("Emissions", "Emissions to water", "Emissions to water, unspecified")
    assert contexts[E1][0] == "Emissions"


def test_cf_values_are_plain_python_floats(data_root):
    climate = next(s for s in load_methods(data_root) if s.key[-1] == "Climate change")
    code, factor = climate.cfs[0]
    assert type(code) is str
    assert type(factor) is float


def test_missing_methods_folder_is_an_error(tmp_path):
    (tmp_path / "sentier-methods" / "data").mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        load_methods(tmp_path)


def test_missing_characterization_factors_file_is_an_error(data_root):
    (data_root / FOLDER / "characterization-factors.parquet").unlink()
    with pytest.raises(FileNotFoundError):
        load_methods(data_root)


def test_methods_frame_missing_required_column_is_an_error(data_root):
    path = data_root / FOLDER / "methods.parquet"
    df = pd.read_parquet(path)
    df.drop(columns=["unit"]).to_parquet(path, index=False)
    with pytest.raises(ValueError):
        load_methods(data_root)


def test_cf_frame_missing_required_column_is_an_error(data_root):
    path = data_root / FOLDER / "characterization-factors.parquet"
    df = pd.read_parquet(path)
    df.drop(columns=["flow_context"]).to_parquet(path, index=False)
    with pytest.raises(ValueError):
        load_methods(data_root)


def test_string_factor_values_are_cast_to_float(data_root):
    path = data_root / FOLDER / "characterization-factors.parquet"
    df = pd.read_parquet(path)
    df["factor_value"] = df["factor_value"].astype(str)
    df.to_parquet(path, index=False)
    climate = next(s for s in load_methods(data_root) if s.key[-1] == "Climate change")
    assert climate.cfs == ((E1, 1.0),)


def test_null_flow_context_is_an_empty_tuple(data_root):
    path = data_root / FOLDER / "characterization-factors.parquet"
    df = pd.read_parquet(path)
    df.loc[df["flow"] == FLOWS + E1, "flow_context"] = None
    df.to_parquet(path, index=False)
    climate = next(s for s in load_methods(data_root) if s.key[-1] == "Climate change")
    assert climate.flow_context[E1] == ()
