"""Names shared by every module. Change here, nowhere else.

The inventory and residual database names are derived from the selected inventory
``source`` (the ``processes.source`` datasource id in sentier-inventory) at build time;
only the biosphere database and the method prefix are fixed.
"""

#: Inventory source installed when none is requested (``processes.source`` id).
DEFAULT_SOURCE = "bafu-2026"

BIOSPHERE_DB = "ef-3.1-biosphere"
METHOD_PREFIX = ("sentier", "EF v3.1")

EF_SOURCE_IRI = "https://vocab.sentier.dev/sources/ef-3.1"
SOURCE_IRI_PREFIX = "https://vocab.sentier.dev/sources/"
FLOW_IRI_PREFIX = "https://vocab.sentier.dev/flows/"

BRIDGE_FOLDER = "bafu-2026-v1__ef-3.1"
NOMENCLATURE_KIND_ORDER = 4  # package order whose targets carry no EF factor
METHODS_FOLDER = "01-ef-3.1"

#: Citation sentence the user must carry, per inventory source (publisher terms).
CITATIONS = {
    "bafu-2026": (
        "Source: Life Cycle Inventory database of the Swiss Federal Administration, BAFU:2026."
    ),
}

# folder names under a data root, matching the ~/dds checkout layout
REPO_INVENTORY = "sentier-inventory"
REPO_VOCAB = "sentier-vocab"
REPO_METHODS = "sentier-methods"
REPO_MAPPINGS = "sentier-mappings"


def inventory_db(source: str) -> str:
    """bw2data database name holding the processes of ``source``: the source id itself."""
    return source


def residual_db(source: str) -> str:
    """Database for ``source`` flows with no EF counterpart in the bridge."""
    return f"{source}-residual"


def source_iri(source: str) -> str:
    """Vocab Source IRI whose slug is the inventory source id."""
    return f"{SOURCE_IRI_PREFIX}{source}"


def citation(source: str) -> str:
    """Registered citation sentence, or a plain attribution for an unregistered source."""
    return CITATIONS.get(source, f"Source: {source}.")
