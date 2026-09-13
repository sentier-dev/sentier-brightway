"""Names shared by every module. Change here, nowhere else."""

INVENTORY_DB = "bafu-2026"
BIOSPHERE_DB = "ef-3.1-biosphere"
RESIDUAL_DB = "bafu-2026-residual"
METHOD_PREFIX = ("sentier", "EF v3.1")

EF_SOURCE_IRI = "https://vocab.sentier.dev/sources/ef-3.1"
BAFU_SOURCE_IRI = "https://vocab.sentier.dev/sources/bafu-2026"
FLOW_IRI_PREFIX = "https://vocab.sentier.dev/flows/"

BRIDGE_FOLDER = "bafu-2026-v1__ef-3.1"
NOMENCLATURE_KIND_ORDER = 4  # package order whose targets carry no EF factor
METHODS_FOLDER = "01-ef-3.1"

CITATION = "Source: Life Cycle Inventory database of the Swiss Federal Administration, BAFU:2026."

# folder names under a data root, matching the ~/dds checkout layout
REPO_INVENTORY = "sentier-inventory"
REPO_VOCAB = "sentier-vocab"
REPO_METHODS = "sentier-methods"
REPO_MAPPINGS = "sentier-mappings"
