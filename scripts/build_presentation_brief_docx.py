"""
Build STI-EpiForecast_Presentation_Brief.docx — short document suitable for presenting.
"""
from __future__ import annotations

import html
import zipfile
from datetime import date
from pathlib import Path


def _p(text: str, bold: bool = False) -> str:
    esc = html.escape(text, quote=False)
    b = "<w:b/>" if bold else ""
    return f'<w:p><w:r><w:rPr>{b}</w:rPr><w:t xml:space="preserve">{esc}</w:t></w:r></w:p>'


def _build_body(paragraphs: list[tuple[str, bool]]) -> str:
    return "".join(_p(t, b) for t, b in paragraphs)


def write_docx(out_path: Path, paragraphs: list[tuple[str, bool]], doc_title: str) -> None:
    body = _build_body(paragraphs)
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {body}
    <w:sectPr>
      <w:pgSz w:w="12240" w:h="15840"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>
    </w:sectPr>
  </w:body>
</w:document>"""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    doc_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>
"""
    core_props = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:dcterms="http://purl.org/dc/terms/"
  xmlns:dcmitype="http://purl.org/dc/dcmitype/"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{html.escape(doc_title)}</dc:title>
  <dc:creator>STI-EpiForecast</dc:creator>
  <dcterms:created xsi:type="dcterms:W3CDTF">{date.today().isoformat()}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{date.today().isoformat()}</dcterms:modified>
</cp:coreProperties>"""
    app_props = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
  xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>STI-EpiForecast</Application>
</Properties>"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/_rels/document.xml.rels", doc_rels)
        zf.writestr("docProps/core.xml", core_props)
        zf.writestr("docProps/app.xml", app_props)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out = root / "STI-EpiForecast_Presentation_Brief.docx"
    doc_title = "STI-EpiForecast — presentation brief"
    today = date.today().isoformat()

    paras: list[tuple[str, bool]] = [
        ("STI-EpiForecast", True),
        ("Uganda disease intelligence and forecast lab", False),
        (f"Document date: {today}", False),
        ("", False),
        ("Purpose", True),
        (
            "STI-EpiForecast brings together historical incident data, open-web and official health "
            "feeds, and simple forecast tools so decision-makers can see risk, trend, and context in one place.",
            False,
        ),
        ("", False),
        ("What we use", True),
        (
            "Line-list style records: disease, date, and (where available) district — typically from a spreadsheet such as diseases_incidents.xlsx.",
            False,
        ),
        (
            "Live signals: media and health-site feeds (for example GDELT, WHO/CDC-style RSS) to show what is being reported now.",
            False,
        ),
        (
            "Optional AI: helps validate which feed items are real outbreak-relevant signals before they drive dashboards and long-run history.",
            False,
        ),
        ("", False),
        ("Two ways to work with the numbers", True),
        (
            "In R (for example Uganda_Incident.R): explore the dataset — charts, top diseases, time trends, and maps when boundary data is available. "
            "A Random Forest can summarise yearly patterns and run a “what if we double the latest year” style scenario for total burden.",
            False,
        ),
        (
            "In the EpiForecast app: a browser dashboard for day-to-day monitoring, travel and action views, and a forecast lab. "
            "The lab can learn from validated signal history as it grows; a separate engine in code can still mirror the Excel Random Forest when that path is used.",
            False,
        ),
        ("", False),
        ("Key message for stakeholders", True),
        (
            "The spreadsheet and the dashboard answer different time horizons: the file is strong for long-run analysis and publication-style figures; "
            "the app is strong for operational rhythm, transparency about sources, and rapid what-if planning.",
            False,
        ),
        ("", False),
        ("Closing", True),
        (
            "STI-EpiForecast is a bridge between static analysis in R and live monitoring in the browser — same mission, complementary tools.",
            False,
        ),
    ]

    write_docx(out, paras, doc_title=doc_title)
    print(f"Wrote: {out}")


if __name__ == "__main__":
    main()
