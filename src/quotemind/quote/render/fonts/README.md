# Fonts (TASK-124)

Be Vietnam Pro, bundled. The quote template (`quote.html.j2`) declares it via `@font-face`:

    BeVietnamPro-Regular.ttf    400
    BeVietnamPro-SemiBold.ttf   600
    BeVietnamPro-Bold.ttf       700

They ship inside the wheel (`[tool.setuptools.package-data]` in `pyproject.toml` already declares
`fonts/*`), so the deployed function renders the branded face with no Dockerfile step.

They were deliberately left out for a while, on the reasoning that the repository should stay
source-only. That was the wrong call for this particular asset. WeasyPrint's fallback does keep the
Vietnamese diacritics byte-exact - `tests/unit/test_render_pdf.py` asserts exactly that, and it
holds - so nothing was *broken*. But a quotation is a customer-facing document, and rendering it in
whatever sans-serif the host machine happens to have is not a rendering detail. It is the difference
between a document that looks like it came from a company and one that looks like it came from a
script. WeasyPrint said so on every single render: `Font-face "Be Vietnam Pro" cannot be loaded`.

## Licence

SIL Open Font License 1.1 (`OFL.txt`, bundled). The OFL permits redistribution, including bundled
inside a larger work; it forbids selling the fonts on their own, and it requires the licence travel
with them - which is why `OFL.txt` sits here rather than being linked from somewhere.

Copyright 2021 The Be Vietnam Pro Project Authors - https://github.com/bettergui/BeVietnamPro
