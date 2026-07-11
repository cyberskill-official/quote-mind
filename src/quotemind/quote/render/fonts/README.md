# Fonts

The quote template (`quote.html.j2`) declares Be Vietnam Pro via `@font-face`:

    fonts/BeVietnamPro-Regular.ttf
    fonts/BeVietnamPro-SemiBold.ttf
    fonts/BeVietnamPro-Bold.ttf

Drop those three TTFs here to get the branded typeface in the PDF. They are not committed: they are
binary assets under the SIL Open Font License, and the repository stays source-only.

Without them WeasyPrint falls back to the system sans-serif. **Vietnamese diacritics still render
correctly** - that is verified in `tests/unit/test_render_pdf.py`, which asserts the extracted PDF
text keeps its accents byte-exact. The only thing missing without the TTFs is the brand face.

For the serverless image, add them in `deploy/Dockerfile.pdf` alongside the WeasyPrint system
libraries (pango, cairo).
