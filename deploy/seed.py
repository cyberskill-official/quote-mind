"""FR-011 seed: load the demo catalog and customers into the Tablestore KnowledgeStore.

    python deploy/seed.py

Idempotent - documents are keyed by SKU / customer_id, so a re-run overwrites in place. Embeddings
use the same text the store indexes (memory.store.catalog_text), so retrieval and seeding cannot
drift. Live cloud calls; not exercised by the offline suite.

The data lives in quotemind.seed.data so the eval harness can label against the same SKUs the store
was actually seeded with. A labelled dataset that disagrees with the catalog measures nothing.
"""

from __future__ import annotations

from quotemind.config.settings import require_settings
from quotemind.memory.embedding import embed_texts
from quotemind.memory.store import MemoryFacade, catalog_text
from quotemind.seed.data import CATALOG, CUSTOMERS


def main() -> None:
    settings = require_settings()
    facade = MemoryFacade.from_settings(settings)
    facade.init_tables()

    vectors = embed_texts([catalog_text(product) for product in CATALOG], settings)
    for product, vector in zip(CATALOG, vectors, strict=True):
        facade.put_catalog(product, vector)
    print(f"seed: {len(CATALOG)} catalog products written (dim {len(vectors[0])})")

    for customer in CUSTOMERS:
        facade.put_customer(customer)
    print(f"seed: {len(CUSTOMERS)} customers written")


if __name__ == "__main__":
    main()
