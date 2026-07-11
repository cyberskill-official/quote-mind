"""FR-120: generate the 30-case labelled eval dataset (Appendix A.5).

    python -m quotemind.seed.generate

Deterministic: no RNG, no clock, no network. The same command produces byte-identical fixtures, so
a label can never silently drift away from the input it describes. Every label references a SKU that
actually exists in quotemind.seed.data - the generator asserts it, because a dataset that points at
phantom SKUs would score the matcher against a target it could never hit.

Composition per FR-120:
    10 vi text · 5 en text · 5 xlsx (3 vi / 2 en) · 5 vi scan · 3 en digital PDF · 2 adversarial

The scanned cases are *actually scanned*: rendered, rasterised at 200 DPI, skewed a degree or so,
given sensor noise and JPEG artefacts, then re-wrapped with no text layer. A "scan" fixture that
still carried extractable text would quietly take the digital-PDF path, the vision model would never
be called, and the OCR score would be the text parser's score wearing a hat.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from openpyxl import Workbook

from quotemind.models.eval import EvalCase, EvalInput, EvalLabelLine, EvalLabels
from quotemind.seed.data import BY_SKU

DATASET = Path(__file__).resolve().parents[3] / "eval" / "dataset"


@dataclass
class Case:
    """One authored case: the RFQ as a human would send it, plus what the right answer is."""

    case_id: str
    kind: str  # text | xlsx | pdf_digital | pdf_scan
    lang: str
    body: str
    lines: list[tuple[str, str, int]]  # (description as written, expected SKU, qty)
    customer_id: str | None = None
    expected_flags: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    blocked_on: str | None = None


_VI_TEXT: list[Case] = [
    Case(
        "vi_text_001",
        "text",
        "vi",
        "Kính gửi Quý công ty,\n"
        "Công ty TNHH Thành Công cần báo giá các mặt hàng sau:\n"
        "1. Laptop Dell Latitude 5450 Core i5 RAM 16GB SSD 512GB - số lượng 10 cái\n"
        "2. Màn hình Dell P2422H 24 inch - 10 cái\n"
        "Giao hàng tại TP.HCM. Đề nghị báo giá đã gồm VAT.\n"
        "Trân trọng, Chị Lan - mua.hang@thanhcong.vn",
        [
            ("Laptop Dell Latitude 5450 Core i5", "DELL-LAT-5450", 10),
            ("Màn hình Dell P2422H 24 inch", "DELL-P2422H", 10),
        ],
        customer_id="cust_thanhcong",
    ),
    Case(
        "vi_text_002",
        "text",
        "vi",
        "Chào anh/chị,\n"
        "Bên em cần báo giá 20 bộ Microsoft 365 Business Standard (1 năm) và "
        "5 bản quyền Adobe Acrobat Pro.\n"
        "Công ty Cổ phần An Phát - kinhdoanh@anphat.com.vn",
        [
            ("Microsoft 365 Business Standard", "MS-M365-BS", 20),
            ("Adobe Acrobat Pro", "ADOBE-ACROBAT", 5),
        ],
        customer_id="cust_anphat",
    ),
    Case(
        "vi_text_003",
        "text",
        "vi",
        "Kính gửi Quý công ty,\n"
        "Công ty TNHH Thành Công cần báo giá các mặt hàng sau:\n"
        "1. Laptop Dell Latitude 5450, Core i7, RAM 32GB, SSD 512GB - số lượng 20 cái\n"
        "2. Màn hình Dell 27 inch P2723DE - 20 cái\n"
        "3. Bản quyền Microsoft 365 Business Standard - 25 user/năm\n"
        "Giao hàng tại TP.HCM trong 2 tuần. Đề nghị báo giá gồm VAT.\n"
        "Trân trọng, Nguyễn Văn A - mua.hang@thanhcong.vn",
        [
            ("Laptop Dell Latitude 5450 Core i7 32GB", "DELL-LAT-5450-I7", 20),
            ("Màn hình Dell P2723DE 27 inch", "DELL-P2723DE", 20),
            ("Microsoft 365 Business Standard", "MS-M365-BS", 25),
        ],
        customer_id="cust_thanhcong",
        tags=["demo"],
    ),
    Case(
        "vi_text_004",
        "text",
        "vi",
        "Chào shop, cho mình xin báo giá:\n"
        "- 2 máy chủ Dell PowerEdge R650\n"
        "- 1 thiết bị lưu trữ Synology DS1522+\n"
        "Công ty TNHH Minh Long, ketoan@minhlong.vn",
        [("Máy chủ Dell PowerEdge R650", "DELL-R650", 2), ("Synology DS1522+", "SYN-DS1522", 1)],
        customer_id="cust_minhlong",
        expected_flags=["LEAD_TIME"],  # R650 is out of stock, 30-day lead time
    ),
    Case(
        "vi_text_005",
        "text",
        "vi",
        "Tập đoàn Xây dựng Hòa Bình cần trang bị cho văn phòng mới:\n"
        "1. Switch Cisco Catalyst 9200L 24 cổng PoE+ : 4 cái\n"
        "2. Thiết bị phát WiFi Ubiquiti UniFi U6 Pro : 12 cái\n"
        "3. Dịch vụ lắp đặt hệ thống mạng : 5 ngày công\n"
        "Liên hệ: it@hoabinh-corp.vn",
        [
            ("Switch Cisco Catalyst 9200L 24 cổng PoE+", "CISCO-C9200L-24P", 4),
            ("Ubiquiti UniFi U6 Pro", "UBNT-U6-PRO", 12),
            ("Dịch vụ lắp đặt hệ thống mạng", "SVC-INSTALL-NET", 5),
        ],
        customer_id="cust_hoabinh",
    ),
    Case(
        "vi_text_006",
        "text",
        "vi",
        "Cần báo giá gấp 15 laptop Lenovo ThinkPad T14 Gen 5 core i5 và "
        "15 dock Dell WD19S.\nCông ty TNHH Đại Việt - contact@daiviet.net.vn",
        [
            ("Lenovo ThinkPad T14 Gen 5 core i5", "LEN-T14-G5", 15),
            ("Dock Dell WD19S", "DELL-WD19S", 15),
        ],
        customer_id="cust_daiviet",
    ),
    Case(
        "vi_text_007",
        "text",
        "vi",
        "Kính gửi anh/chị,\n"
        "Báo giá giúp em 30 bộ Windows 11 Pro và 30 gói Kaspersky Endpoint Security.\n"
        "An Phát - kinhdoanh@anphat.com.vn",
        [
            ("Windows 11 Pro", "MS-WIN11-PRO", 30),
            ("Kaspersky Endpoint Security", "KAS-ENDPOINT", 30),
        ],
        customer_id="cust_anphat",
    ),
    Case(
        "vi_text_008",
        "text",
        "vi",
        "Chào anh, công ty em cần:\n"
        "- 8 máy tính để bàn Dell OptiPlex 7010 SFF\n"
        "- 8 màn hình Samsung 24 inch S24C\n"
        "- 8 dịch vụ cài đặt máy tính\n"
        "Minh Long - ketoan@minhlong.vn",
        [
            ("Dell OptiPlex 7010 SFF", "DELL-OPT-7010", 8),
            ("Màn hình Samsung S24C 24 inch", "SAMSUNG-S24C", 8),
            ("Dịch vụ cài đặt máy tính", "SVC-INSTALL-PC", 8),
        ],
        customer_id="cust_minhlong",
    ),
    Case(
        "vi_text_009",
        "text",
        "vi",
        "Báo giá 5 tường lửa Fortinet FortiGate 60F và 2 bộ lưu điện APC Smart-UPS 1500VA.\n"
        "Thành Công - mua.hang@thanhcong.vn",
        [
            ("Tường lửa Fortinet FortiGate 60F", "FORTI-FG-60F", 5),
            ("Bộ lưu điện APC Smart-UPS 1500VA", "APC-UPS-1500", 2),
        ],
        customer_id="cust_thanhcong",
    ),
    Case(
        "vi_text_010",
        "text",
        "vi",
        "Cần báo giá 40 thuê bao gói cước dữ liệu di động doanh nghiệp (1 tháng) "
        "và 10 dịch vụ bảo trì cơ bản.\n"
        "Hòa Bình - it@hoabinh-corp.vn",
        # The telecom SKU is the one excluded from the 8% reduction - it must come out at 10%.
        [
            ("Gói cước dữ liệu di động doanh nghiệp", "VIET-SIM-DATA", 40),
            ("Dịch vụ bảo trì cơ bản", "SVC-MAINT-BASIC", 10),
        ],
        customer_id="cust_hoabinh",
        tags=["vat_10_percent"],
    ),
]

_EN_TEXT: list[Case] = [
    Case(
        "en_text_001",
        "text",
        "en",
        "Dear Sales team,\n"
        "Sunrise Manufacturing Vietnam would like a quotation for:\n"
        "1. Dell Latitude 7450 laptop (i7, 16GB, 512GB) - 12 units\n"
        "2. Dell UltraSharp U3223QE 32 inch 4K monitor - 12 units\n"
        "Please quote in VND with a USD reference.\n"
        "Best regards, David Tan - purchasing@sunrise-mfg.vn",
        [
            ("Dell Latitude 7450 laptop i7", "DELL-LAT-7450", 12),
            ("Dell UltraSharp U3223QE 32 inch 4K", "DELL-U3223QE", 12),
        ],
        customer_id="cust_sunrise",
    ),
    Case(
        "en_text_002",
        "text",
        "en",
        "Hello,\nPlease quote 25 seats of Microsoft 365 Business Premium (1 year) and "
        "25 seats of Bitdefender GravityZone Business.\n"
        "VietSoft Solutions - admin@vietsoft.io",
        [
            ("Microsoft 365 Business Premium", "MS-M365-BP", 25),
            ("Bitdefender GravityZone Business", "BIT-GRAVITYZONE", 25),
        ],
        customer_id="cust_vietsoft",
    ),
    Case(
        "en_text_003",
        "text",
        "en",
        "Hi team,\nWe need a quotation for 3 x Dell PowerEdge R750 servers and "
        "2 x VMware vSphere Standard licences (1 CPU, 1 year).\n"
        "Sunrise Manufacturing - purchasing@sunrise-mfg.vn",
        [
            ("Dell PowerEdge R750 server", "DELL-R750", 3),
            ("VMware vSphere Standard licence", "VMW-VSPHERE", 2),
        ],
        customer_id="cust_sunrise",
        expected_flags=["LEAD_TIME"],
    ),
    Case(
        "en_text_004",
        "text",
        "en",
        "Please quote:\n"
        "- 6 x HP EliteBook 840 G11 (Ultra 5, 16GB)\n"
        "- 6 x LG 27QN880 27 inch QHD monitor\n"
        "- 6 x Kingston DDR5 16GB memory\n"
        "VietSoft Solutions - admin@vietsoft.io",
        [
            ("HP EliteBook 840 G11", "HP-ELITE-840", 6),
            ("LG 27QN880 27 inch QHD monitor", "LG-27QN880", 6),
            ("Kingston DDR5 16GB", "KING-DDR5-16", 6),
        ],
        customer_id="cust_vietsoft",
    ),
    Case(
        "en_text_005",
        "text",
        "en",
        "Quotation request: 2 x Cisco Catalyst 9200L 48-port PoE+ switch, "
        "4 x Ubiquiti UniFi U7 Pro access point, 3 man-days of server deployment service.\n"
        "Sunrise Manufacturing - purchasing@sunrise-mfg.vn",
        [
            ("Cisco Catalyst 9200L 48-port PoE+ switch", "CISCO-C9200L-48P", 2),
            ("Ubiquiti UniFi U7 Pro access point", "UBNT-U7-PRO", 4),
            ("Server deployment service", "SVC-DEPLOY-SRV", 3),
        ],
        customer_id="cust_sunrise",
        expected_flags=["LEAD_TIME"],
    ),
]

_XLSX: list[Case] = [
    Case(
        "vi_xlsx_001",
        "xlsx",
        "vi",
        "",
        [
            ("Laptop Dell Latitude 5450 Core i5", "DELL-LAT-5450", 25),
            ("Màn hình Dell P2423D 24 inch QHD", "DELL-P2423D", 25),
            ("Dock Dell WD19S", "DELL-WD19S", 25),
        ],
        customer_id="cust_thanhcong",
    ),
    Case(
        "vi_xlsx_002",
        "xlsx",
        "vi",
        "",
        [
            ("Switch TP-Link Omada SG3428 24 cổng", "TPLINK-SG3428", 6),
            ("Thiết bị phát WiFi Ubiquiti UniFi U6 Pro", "UBNT-U6-PRO", 20),
            ("Dịch vụ lắp đặt hệ thống mạng", "SVC-INSTALL-NET", 8),
        ],
        customer_id="cust_hoabinh",
    ),
    Case(
        "vi_xlsx_003",
        "xlsx",
        "vi",
        "",
        [
            ("Máy trạm Dell Precision 3680", "DELL-PREC-3680", 4),
            ("Màn hình Dell UltraSharp U3223QE 32 inch", "DELL-U3223QE", 8),
            ("Bản quyền Adobe Creative Cloud All Apps", "ADOBE-CC-ALL", 4),
        ],
        customer_id="cust_anphat",
    ),
    Case(
        "en_xlsx_001",
        "xlsx",
        "en",
        "",
        [
            ("Lenovo ThinkPad X1 Carbon Gen 12", "LEN-X1-C12", 8),
            ("Samsung ViewFinity S27C 27 inch QHD", "SAMSUNG-S27C", 8),
            ("Office LTSC Standard 2024", "MS-OFFICE-LTSC", 8),
        ],
        customer_id="cust_sunrise",
    ),
    Case(
        "en_xlsx_002",
        "xlsx",
        "en",
        "",
        [
            ("Synology RS2423+ NAS 12-bay", "SYN-RS2423", 2),
            ("APC Smart-UPS 1500VA", "APC-UPS-1500", 4),
            ("Premium maintenance service", "SVC-MAINT-PREM", 12),
        ],
        customer_id="cust_vietsoft",
    ),
]

_PDF_DIGITAL: list[Case] = [
    Case(
        "en_pdf_001",
        "pdf_digital",
        "en",
        "REQUEST FOR QUOTATION\n\n"
        "Sunrise Manufacturing Vietnam Co., Ltd.\n"
        "purchasing@sunrise-mfg.vn\n\n"
        "Item 1: Dell XPS 14 9440 laptop (Ultra 7, 32GB, 1TB) - quantity 5\n"
        "Item 2: Dell WD19S 130W USB-C dock - quantity 5\n\n"
        "Please respond within 5 working days.",
        [
            ("Dell XPS 14 9440 laptop", "DELL-XPS-9440", 5),
            ("Dell WD19S 130W USB-C dock", "DELL-WD19S", 5),
        ],
        customer_id="cust_sunrise",
    ),
    Case(
        "en_pdf_002",
        "pdf_digital",
        "en",
        "REQUEST FOR QUOTATION\n\n"
        "VietSoft Solutions JSC\nadmin@vietsoft.io\n\n"
        "Item 1: HP Z2 Tower G9 workstation (i7, 32GB, T1000) - quantity 3\n"
        "Item 2: Samsung 990 EVO 1TB NVMe SSD - quantity 6\n"
        "Item 3: End-user training session - quantity 2\n",
        [
            ("HP Z2 Tower G9 workstation", "HP-Z2-G9", 3),
            ("Samsung 990 EVO 1TB NVMe SSD", "SAM-SSD-1TB", 6),
            ("End-user training session", "SVC-TRAINING", 2),
        ],
        customer_id="cust_vietsoft",
    ),
    Case(
        "en_pdf_003",
        "pdf_digital",
        "en",
        "REQUEST FOR QUOTATION\n\n"
        "Sunrise Manufacturing Vietnam Co., Ltd.\npurchasing@sunrise-mfg.vn\n\n"
        "Item 1: Cisco Business CBS350 24-port Gigabit switch - quantity 4\n"
        "Item 2: Fortinet FortiGate 60F firewall - quantity 2\n",
        [
            ("Cisco Business CBS350 24-port Gigabit switch", "CISCO-CBS350-24", 4),
            ("Fortinet FortiGate 60F firewall", "FORTI-FG-60F", 2),
        ],
        customer_id="cust_sunrise",
    ),
]


def _cong_van(sender: str, email: str, rows: list[tuple[str, int, str]]) -> str:
    """A Vietnamese công văn as a human would send it - letterhead, table, signature block."""
    items = "\n".join(
        f"{index}. {description} - số lượng: {qty} {unit}"
        for index, (description, qty, unit) in enumerate(rows, start=1)
    )
    return (
        "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\n"
        "Độc lập - Tự do - Hạnh phúc\n\n"
        f"{sender}\n\n"
        "V/v: Đề nghị báo giá thiết bị công nghệ thông tin\n\n"
        "Kính gửi: Quý công ty,\n\n"
        "Chúng tôi đề nghị Quý công ty báo giá các mặt hàng sau:\n\n"
        f"{items}\n\n"
        "Đề nghị báo giá đã bao gồm thuế GTGT. Giao hàng tại TP.HCM.\n\n"
        f"Liên hệ: {email}\n\n"
        "Trân trọng,\nTRƯỞNG PHÒNG MUA HÀNG"
    )


# FR-031/032: these are real scans - rendered, rasterised, rotated and noised - not text PDFs with a
# "scanned" label. A fixture that still had a text layer would pass the vision path without ever
# exercising OCR, and the eval would be measuring nothing.
_PDF_SCAN: list[Case] = [
    Case(
        "vi_scan_001",
        "pdf_scan",
        "vi",
        _cong_van(
            "CÔNG TY TNHH THÀNH CÔNG",
            "mua.hang@thanhcong.vn",
            [
                ("Laptop Dell Latitude 5450, Core i5, RAM 16GB, SSD 512GB", 20, "cái"),
                ("Màn hình Dell P2723DE 27 inch", 20, "cái"),
            ],
        ),
        [
            ("Laptop Dell Latitude 5450 Core i5", "DELL-LAT-5450", 20),
            ("Màn hình Dell P2723DE 27 inch", "DELL-P2723DE", 20),
        ],
        customer_id="cust_thanhcong",
    ),
    Case(
        "vi_scan_002",
        "pdf_scan",
        "vi",
        _cong_van(
            "CÔNG TY CỔ PHẦN AN PHÁT",
            "kinhdoanh@anphat.com.vn",
            [
                ("Laptop HP ProBook 450 G10, Core i5, RAM 16GB", 15, "cái"),
                ("Dock Dell WD19S 130W USB-C", 15, "cái"),
            ],
        ),
        [
            ("Laptop HP ProBook 450 G10", "HP-PROBOOK-450", 15),
            ("Dock Dell WD19S", "DELL-WD19S", 15),
        ],
        customer_id="cust_anphat",
        tags=["demo"],  # the vetted demo scan (UJ-02)
    ),
    Case(
        "vi_scan_003",
        "pdf_scan",
        "vi",
        _cong_van(
            "TẬP ĐOÀN XÂY DỰNG HÒA BÌNH",
            "it@hoabinh-corp.vn",
            [
                ("Switch Cisco Catalyst 9200L 24 cổng PoE+", 2, "cái"),
            ],
        ),
        [("Switch Cisco Catalyst 9200L 24 cổng PoE+", "CISCO-C9200L-24P", 2)],
        customer_id="cust_hoabinh",
    ),
    Case(
        "vi_scan_004",
        "pdf_scan",
        "vi",
        _cong_van(
            "CÔNG TY TNHH MINH LONG",
            "ketoan@minhlong.vn",
            [
                ("Máy chủ Dell PowerEdge R650", 1, "cái"),
                ("Thiết bị lưu trữ Synology DS1522+", 2, "cái"),
            ],
        ),
        [("Máy chủ Dell PowerEdge R650", "DELL-R650", 1), ("Synology DS1522+", "SYN-DS1522", 2)],
        customer_id="cust_minhlong",
    ),
    Case(
        "vi_scan_005",
        "pdf_scan",
        "vi",
        _cong_van(
            "CÔNG TY TNHH ĐẠI VIỆT",
            "contact@daiviet.net.vn",
            [
                ("Bản quyền Microsoft 365 Business Premium (1 năm)", 50, "license"),
            ],
        ),
        [("Bản quyền Microsoft 365 Business Premium", "MS-M365-BP", 50)],
        customer_id="cust_daiviet",
    ),
]

_ADVERSARIAL: list[Case] = [
    Case(
        "adv_001",
        "text",
        "vi",
        "Cần báo giá 3 máy tính bảng vẽ Wacom Cintiq 22 và 2 laptop Dell Latitude 5450.\n"
        "Thành Công - mua.hang@thanhcong.vn",
        # The Wacom is not in the catalog. The right behaviour is to price the laptop and surface
        # the tablet to the human - NOT to substitute something plausible and hope nobody checks.
        [("Laptop Dell Latitude 5450", "DELL-LAT-5450", 2)],
        customer_id="cust_thanhcong",
        tags=["adversarial", "out_of_catalog"],
    ),
    Case(
        "adv_002",
        "text",
        "vi",
        "Báo giá 10 laptop Dell Latitude 5450 RAM 64GB SSD 2TB.\nAn Phát - kinhdoanh@anphat.com.vn",
        # The catalog's 5450 tops out at 32GB. A confident 64GB quote would be a lie; the expected
        # behaviour is to match the closest SKU and flag the spec conflict for a human.
        [("Laptop Dell Latitude 5450 RAM 64GB", "DELL-LAT-5450-I7", 10)],
        customer_id="cust_anphat",
        tags=["adversarial", "spec_conflict"],
    ),
]

ALL_CASES: list[Case] = [*_VI_TEXT, *_EN_TEXT, *_XLSX, *_PDF_DIGITAL, *_PDF_SCAN, *_ADVERSARIAL]

_XLSX_HEADERS = {
    "vi": ["STT", "Mô tả", "Số lượng", "Đơn vị"],
    "en": ["No.", "Description", "Quantity", "Unit"],
}


def _write_xlsx(case: Case, path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(_XLSX_HEADERS[case.lang])
    for index, (description, sku, qty) in enumerate(case.lines, start=1):
        sheet.append([index, description, qty, BY_SKU[sku].unit])
    workbook.save(path)


def _render_pdf_bytes(case: Case, *, serif: bool = False) -> bytes:
    from weasyprint import HTML  # noqa: PLC0415 - optional heavy dep, only needed here

    font = "Times New Roman, serif" if serif else "sans-serif"
    body = "".join(f"<p>{line}</p>" for line in case.body.splitlines() if line.strip())
    style = f"font-family:{font};font-size:13pt;line-height:1.6"
    pdf = HTML(string=f"<html><body style='{style}'>{body}</body></html>").write_pdf()
    assert pdf is not None
    return pdf


def _write_pdf(case: Case, path: Path) -> None:
    path.write_bytes(_render_pdf_bytes(case))


def _write_scan(case: Case, path: Path, *, seed: int) -> None:
    """A real scan: rasterise the page, skew it, add sensor noise, and re-wrap as an image-only PDF.

    The result has no text layer at all - which is the point. A "scan" fixture that still carried
    extractable text would sail through the digital-PDF path and the vision model would never be
    called, so the OCR metric would be measuring the text parser and reporting it as OCR.
    """
    import io  # noqa: PLC0415
    import random  # noqa: PLC0415

    import pypdfium2  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    document = pypdfium2.PdfDocument(_render_pdf_bytes(case, serif=True))
    try:
        image = document[0].render(scale=200 / 72).to_pil().convert("L")
    finally:
        document.close()

    rng = random.Random(seed)  # noqa: S311 - fixture generation, not cryptography
    image = image.rotate(
        rng.uniform(-1.2, 1.2), resample=Image.Resampling.BICUBIC, expand=False, fillcolor=255
    )

    # Gaussian-ish sensor noise, deterministic per case so the fixture is reproducible.
    pixels = image.load()
    assert pixels is not None
    for y in range(image.height):
        for x in range(image.width):
            value = pixels[x, y] + int(rng.gauss(0, 9))
            pixels[x, y] = max(0, min(255, value))

    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=72)  # JPEG artefacts, like a real scan

    pdf = pypdfium2.PdfDocument.new()
    page_image = pypdfium2.PdfImage.new(pdf)
    page_image.load_jpeg(io.BytesIO(buffer.getvalue()))
    width, height = image.size
    page = pdf.new_page(width / 200 * 72, height / 200 * 72)
    page_image.set_matrix(pypdfium2.PdfMatrix().scale(page.get_width(), page.get_height()))
    page.insert_obj(page_image)
    page.gen_content()
    pdf.save(str(path))


def build_case(case: Case) -> EvalCase:
    """Turn an authored case into DM-13, asserting every labelled SKU really exists."""
    for _, sku, _ in case.lines:
        if sku not in BY_SKU:
            raise ValueError(f"{case.case_id}: labelled SKU {sku} is not in the catalog")
    tags = [*case.tags, case.kind, case.lang]
    if case.blocked_on:
        tags.append(f"blocked_on:{case.blocked_on}")
    return EvalCase(
        case_id=case.case_id,
        input=EvalInput(
            text=case.body if case.kind == "text" else None,
            file=None if case.kind == "text" else _filename(case),
        ),
        labels=EvalLabels(
            lines=[
                EvalLabelLine(description_canon=description, sku=sku, qty=Decimal(qty))
                for description, sku, qty in case.lines
            ],
            customer_id=case.customer_id,
            expected_flags=case.expected_flags,
        ),
        tags=tags,
    )


def _filename(case: Case) -> str:
    suffix = {"xlsx": ".xlsx", "pdf_digital": ".pdf", "pdf_scan": ".pdf"}[case.kind]
    return f"{case.case_id}{suffix}"


def main() -> None:
    DATASET.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, Any]] = []
    written = 0

    for case in ALL_CASES:
        built = build_case(case)
        cases.append(built.model_dump(mode="json"))
        if case.kind == "text":
            continue
        path = DATASET / _filename(case)
        if case.kind == "xlsx":
            _write_xlsx(case, path)
        elif case.kind == "pdf_digital":
            _write_pdf(case, path)
        else:  # pdf_scan
            _write_scan(case, path, seed=abs(hash(case.case_id)) % 10_000)
        written += 1

    labels = DATASET / "labels.json"
    labels.write_text(
        json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )  # ensure_ascii=False: Vietnamese stays Vietnamese on disk

    runnable = [case for case in ALL_CASES if case.blocked_on is None]
    print(f"dataset: {len(ALL_CASES)} cases labelled -> {labels}")
    print(
        f"dataset: {written} input files written; {len(runnable)} runnable, "
        f"{len(ALL_CASES) - len(runnable)} blocked"
    )


if __name__ == "__main__":
    main()
