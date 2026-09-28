"""The domain layer — the centre of the architecture.

Nothing in this package may import Flask, SQLAlchemy, pdfplumber, fitz,
openpyxl, requests or any model SDK. That is not a style preference: it is
requirement NFR-06, and a test enforces it
(``tests/unit/domain/test_domain_is_pure.py``). If that test fails, the
layering has been breached and the sensitivity analysis of Part D is at risk
— it is only fast because this layer needs nothing to run.
"""
