"""FR-011 seed: load the demo catalog and customers into the Tablestore KnowledgeStore.

    python deploy/seed.py

Idempotent - documents are keyed by SKU / customer_id, so a re-run overwrites in place. Embeddings
use the same text the store indexes (memory.store.catalog_text), so retrieval and seeding cannot
drift. Live cloud calls; not exercised by the offline suite.
"""

from __future__ import annotations

from quotemind.config.settings import require_settings
from quotemind.memory.embedding import embed_texts
from quotemind.memory.store import MemoryFacade, catalog_text
from quotemind.models import BilingualText, CatalogProduct, CustomerProfile
from quotemind.models.common import Category, Currency, Language, StockStatus, Tier


def _product(
    sku: str,
    brand: str,
    category: Category,
    vi: str,
    en: str,
    specs: dict[str, str],
    unit: str,
    list_price: int,
    dealer_price: int,
    cost_price: int,
    *,
    stock: StockStatus = StockStatus.IN_STOCK,
    lead_time_days: int = 7,
    warranty_months: int = 12,
    vat_rate: int = 8,
) -> CatalogProduct:
    return CatalogProduct(
        sku=sku,
        brand=brand,
        category=category,
        name=BilingualText(vi=vi, en=en),
        specs=specs,
        unit=unit,
        list_price_vnd=list_price,
        dealer_price_vnd=dealer_price,
        cost_price_vnd=cost_price,
        vat_rate=vat_rate,
        stock_status=stock,
        lead_time_days=lead_time_days,
        warranty_months=warranty_months,
    )


CATALOG: list[CatalogProduct] = [
    _product("DELL-LAT-5450", "Dell", Category.LAPTOP,
             "Laptop Dell Latitude 5450", "Dell Latitude 5450 laptop",
             {"cpu": "i5-1345U", "ram": "16GB", "ssd": "512GB", "screen": "14 inch"}, "cái",
             22_000_000, 19_800_000, 17_500_000),
    _product("DELL-LAT-5450-I7", "Dell", Category.LAPTOP,
             "Laptop Dell Latitude 5450 i7", "Dell Latitude 5450 i7 laptop",
             {"cpu": "i7-1365U", "ram": "32GB", "ssd": "1TB", "screen": "14 inch"}, "cái",
             31_000_000, 28_500_000, 25_800_000),
    _product("HP-PROBOOK-450", "HP", Category.LAPTOP,
             "Laptop HP ProBook 450 G10", "HP ProBook 450 G10 laptop",
             {"cpu": "i5-1335U", "ram": "16GB", "ssd": "512GB", "screen": "15.6 inch"}, "cái",
             20_500_000, 18_600_000, 16_900_000),
    _product("DELL-P2723DE", "Dell", Category.MONITOR,
             "Màn hình Dell P2723DE 27 inch 2K", "Dell P2723DE 27 inch 2K monitor",
             {"size": "27 inch", "resolution": "2560x1440", "panel": "IPS"}, "cái",
             7_200_000, 6_400_000, 5_700_000),
    _product("DELL-P2422H", "Dell", Category.MONITOR,
             "Màn hình Dell P2422H 24 inch", "Dell P2422H 24 inch monitor",
             {"size": "24 inch", "resolution": "1920x1080", "panel": "IPS"}, "cái",
             4_300_000, 3_850_000, 3_400_000),
    _product("CISCO-C9200L-24P", "Cisco", Category.NETWORK,
             "Switch Cisco Catalyst 9200L 24 cổng PoE+",
             "Cisco Catalyst 9200L 24-port PoE+ switch",
             {"ports": "24", "poe": "PoE+", "uplink": "4x1G"}, "cái",
             52_000_000, 47_000_000, 42_500_000, lead_time_days=21),
    _product("DELL-R650", "Dell", Category.SERVER,
             "Máy chủ Dell PowerEdge R650", "Dell PowerEdge R650 server",
             {"cpu": "Xeon Silver 4310", "ram": "64GB", "raid": "H755"}, "cái",
             165_000_000, 152_000_000, 140_000_000,
             stock=StockStatus.OUT_OF_STOCK, lead_time_days=30, warranty_months=36),
    _product("MS-M365-BP", "Microsoft", Category.SOFTWARE_LICENSE,
             "Bản quyền Microsoft 365 Business Premium (1 năm)",
             "Microsoft 365 Business Premium licence (1 year)",
             {"term": "12 months", "seats": "1"}, "license",
             6_600_000, 6_100_000, 5_700_000, lead_time_days=1),
]

CUSTOMERS: list[CustomerProfile] = [
    CustomerProfile(
        customer_id="cust_thanhcong",
        name="Công ty TNHH Thành Công",
        mst="0301234567",
        emails=["mua.hang@thanhcong.vn"],
        domains=["thanhcong.vn"],
        tier=Tier.DEALER,
        project_discount_pct=3.0,
        preferred_currency=Currency.VND,
        preferred_language=Language.VI,
        address="12 Nguyễn Huệ, Quận 1, TP.HCM",
        contact="Chị Lan",
    ),
    CustomerProfile(
        customer_id="cust_fpt_project",
        name="FPT Information System",
        mst="0302345678",
        emails=["procurement@fpt-is.com"],
        domains=["fpt-is.com"],
        tier=Tier.PROJECT,
        project_discount_pct=5.0,
        preferred_currency=Currency.VND,
        preferred_language=Language.VI,
        address="17 Duy Tân, Cầu Giấy, Hà Nội",
        contact="Anh Minh",
    ),
]


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
