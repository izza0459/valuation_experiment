"""Reading a title deed into the lead (OCR, entirely on our server).

When a document typed "Title Deed" is uploaded, its text is read and the
lead's empty fields are filled in from it: the title-document numbers, the
building and community, the owners and the area. Nothing is sent anywhere:

- A digital PDF (what DLD and the banks usually send) has its text read
  straight from the file with pdfium, exactly.
- A scan or a photo is read with Tesseract OCR, run on this server, when it
  is installed (it is in the production image; see the Dockerfile).

Only empty fields are filled, through the same save path as a person's edit,
so each value is validated and audited. A value the deed gives that differs
from what is already entered is reported, never overwritten.
"""

from __future__ import annotations

import io
import logging
import re
import shutil
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

import pypdfium2 as pdfium
from PIL import Image

logger = logging.getLogger(__name__)

TITLE_DEED = "title_deed"
MAX_PAGES = 3  # a title deed is one or two pages; the rest is attachments
OCR_DPI = 300
# Fewer letters and digits than this on a page means there's no text layer.
MIN_TEXT = 40


# --- reading the text --------------------------------------------------------------------------------------


def _ocr(image: Image.Image) -> str:
    """Tesseract on one image, English and Arabic when both are installed."""
    if not shutil.which("tesseract"):
        return ""
    try:
        import pytesseract

        langs = pytesseract.get_languages(config="")
        lang = "+".join(lang for lang in ("eng", "ara") if lang in langs) or "eng"
        return pytesseract.image_to_string(image.convert("L"), lang=lang, timeout=60)
    except Exception:  # OCR is a convenience: never let it break an upload
        logger.warning("OCR failed", exc_info=True)
        return ""


def ocr_available() -> bool:
    return bool(shutil.which("tesseract"))


def read_text(data: bytes, content_type: str) -> str:
    """The document's text: the PDF's own text layer, else OCR of the page."""
    if content_type == "application/pdf":
        try:
            pdf = pdfium.PdfDocument(data)
        except pdfium.PdfiumError:
            return ""
        try:
            pages = []
            for index in range(min(len(pdf), MAX_PAGES)):
                page = pdf[index]
                text = page.get_textpage().get_text_range()
                if len(re.sub(r"\W", "", text)) < MIN_TEXT:
                    text = _ocr(page.render(scale=OCR_DPI / 72).to_pil())
                pages.append(text)
            return "\n".join(pages)
        finally:
            pdf.close()
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            return _ocr(image)
    except Exception:
        return ""


# --- finding the fields ---------------------------------------------------------------------------------------

# "Label : value", "Label value", or the value on the next line. Labels are the
# English side of a DLD title deed; each lists the spellings seen in practice.
_SEP = r"\s*(?:[:\-–]\s*|\n\s*)?"
_CODE = r"([A-Z0-9][A-Z0-9/\-]*)"
_LINE = r"([^\n:]{2,80})"


def _first(patterns, text):
    for pattern in patterns:
        if m := re.search(pattern, text, re.IGNORECASE):
            return m.group(1).strip(" .,:-–")
    return ""


def _number(value: str) -> Decimal | None:
    try:
        return Decimal(value.replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None


@dataclass
class DeedFields:
    """What a title deed says. Empty strings / None for what wasn't found."""

    is_title_deed: bool = False
    property_no: str = ""
    plot_no: str = ""
    municipality_no: str = ""
    building_no: str = ""
    building_name: str = ""
    community: str = ""
    unit_area_sqm: Decimal | None = None
    land_area_sqm: Decimal | None = None
    owners: list[str] = field(default_factory=list)

    def found(self) -> bool:
        return any([self.property_no, self.plot_no, self.municipality_no, self.building_no, self.building_name,
                    self.community, self.unit_area_sqm, self.land_area_sqm, self.owners])


def parse(text: str) -> DeedFields:
    """The title deed's fields from its text."""
    t = re.sub(r"[ \t ]+", " ", (text or "").replace("\r\n", "\n").replace("\r", "\n"))
    deed = DeedFields(is_title_deed=bool(re.search(r"title\s*deed|سند\s*ملكية", t, re.IGNORECASE)))
    deed.property_no = _first([r"\b(?:Property|Unit)\s*(?:No\.?|Number)" + _SEP + _CODE], t)
    deed.plot_no = _first([r"\b(?:Plot|Land)\s*(?:No\.?|Number)" + _SEP + _CODE], t)
    deed.municipality_no = _first([r"\bMunicipality\s*(?:No\.?|Number)" + _SEP + _CODE], t)
    deed.building_no = _first([r"\bBuilding\s*(?:No\.?|Number)" + _SEP + _CODE], t)
    deed.building_name = _first([r"\bBuilding\s*Name" + _SEP + _LINE, r"\bProject\s*Name" + _SEP + _LINE], t)
    deed.community = _first([r"\b(?:Community|Area\s*Name|Location)" + _SEP + _LINE], t)

    unit = r"(?:sq\.?\s*m(?:eters?|etres?)?|sqm|m2|m²|square\s*met(?:er|re)s?)"
    amount = r"([\d,]+(?:\.\d+)?)"
    deed.unit_area_sqm = _number(_first([
        r"\b(?:Suite|Unit|Built[\s-]*up|Property)\s*Area" + rf"\s*(?:\(\s*{unit}\s*\)|in\s*{unit})?" + _SEP + amount,
        r"\bArea\s*" + rf"(?:\(\s*{unit}\s*\)|in\s*{unit}|{unit})" + _SEP + amount,
        r"\bArea" + _SEP + amount + rf"\s*{unit}",
    ], t))
    deed.land_area_sqm = _number(_first([
        r"\b(?:Land|Plot)\s*Area" + rf"\s*(?:\(\s*{unit}\s*\)|in\s*{unit})?" + _SEP + amount,
    ], t))

    owner_label = r"\bOwner(?:s|'s)?\s*(?:Name)?\s*(?:\((?:English|En)\))?"
    owners = re.findall(owner_label + _SEP + r"([A-Za-z][A-Za-z .'\-]{2,60})", t, re.IGNORECASE)
    seen = []
    for name in owners:
        name = re.sub(r"\s+", " ", name).strip(" .'-")
        # Stop at the next label on the same line ("Share", "Nationality" ...).
        name = re.split(r"\b(?:Share|Nationality|Percentage|ID|Passport)\b", name, flags=re.IGNORECASE)[0].strip()
        if len(name) > 2 and name.lower() not in {"name", "details", "information"} and name not in seen:
            seen.append(name)
    deed.owners = seen
    return deed


# --- filling the lead -------------------------------------------------------------------------------------------


@dataclass
class FillResult:
    read: bool = False  # any text came out of the document
    filled: list[str] = field(default_factory=list)  # the labels of the fields filled in
    different: list[str] = field(default_factory=list)  # the deed says otherwise; left as entered

    def as_dict(self):
        return {"read": self.read, "filled": self.filled, "different": self.different}


def _empty(value) -> bool:
    return value in (None, "", []) or (isinstance(value, str) and not value.strip())


def _same(a, b) -> bool:
    if isinstance(a, Decimal) or isinstance(b, Decimal):
        return _number(str(a)) == _number(str(b))
    return str(a).strip().lower() == str(b).strip().lower()


def fill_from_document(job_id: int, user, document) -> FillResult:
    """Reads `document` and fills the lead's empty fields from it."""
    from django.core.files.storage import default_storage

    from apps.jobs.constants import PLOT_BEARING_CATEGORIES
    from apps.jobs.field_config import get_tab
    from apps.jobs.models import Job, JobTabVersion
    from apps.jobs.tabs import TabError, patch_tab

    result = FillResult()
    try:
        with default_storage.open(document.s3_key) as f:
            text = read_text(f.read(), document.content_type)
    except Exception:
        logger.warning("Couldn't read document %s", document.pk, exc_info=True)
        return result
    deed = parse(text)
    result.read = bool(text.strip())
    if not deed.found():
        return result

    job = Job.objects.select_related("property", "summary").get(pk=job_id)
    prop, summary = job.property, job.summary
    plot_bearing = summary.property_category in PLOT_BEARING_CATEGORIES
    labels = {f["key"]: f["label"] for key in ("address", "summary") for f in get_tab(key)["fields"]}

    # (tab, field, the lead's current value, the deed's value)
    wanted = [
        ("address", "title_doc_property_no", prop.title_doc_property_no, deed.property_no),
        ("address", "title_doc_plot_no", prop.title_doc_plot_no, deed.plot_no),
        ("address", "title_doc_municipality_no", prop.title_doc_municipality_no, deed.municipality_no),
        ("address", "title_doc_building_no", prop.title_doc_building_no, deed.building_no),
        ("address", "ownership_name", prop.ownership_name, deed.owners),
    ]
    # The building and community go in the main fields when those are empty;
    # otherwise in the "as per document" ones, when the deed spells them differently.
    for main, per_doc, value in (("building_name", "title_doc_building_name", deed.building_name),
                                 ("community_name", "title_doc_community_name", deed.community)):
        current = getattr(prop, main)
        if _empty(current):
            wanted.append(("address", main, current, value))
        elif value and not _same(current, value):
            wanted.append(("address", per_doc, getattr(prop, per_doc), value))
    area = deed.land_area_sqm if plot_bearing else (deed.unit_area_sqm or deed.land_area_sqm)
    if plot_bearing:
        wanted.append(("summary", "plot_area_sqm", summary.plot_area_sqm, deed.land_area_sqm))
        wanted.append(("summary", "bua_sqm", summary.bua_sqm, deed.unit_area_sqm))
    else:
        wanted.append(("summary", "bua_sqm", summary.bua_sqm, area))

    by_tab: dict[str, dict] = {}
    for tab, key, current, value in wanted:
        if _empty(value):
            continue
        if _empty(current):
            by_tab.setdefault(tab, {})[key] = [str(v) for v in value] if isinstance(value, list) else str(value)
            result.filled.append(labels.get(key, key))
        elif not _same(current if not isinstance(current, list) else ", ".join(current),
                       ", ".join(value) if isinstance(value, list) else value):
            result.different.append(labels.get(key, key))
    if not by_tab:
        return result
    # Where the deed's figures came from, and what the document is.
    if "address" in by_tab and _empty(prop.title_doc_type):
        by_tab["address"]["title_doc_type"] = TITLE_DEED
    if "bua_sqm" in by_tab.get("summary", {}) and _empty(summary.bua_source):
        by_tab["summary"]["bua_source"] = TITLE_DEED
    if "plot_area_sqm" in by_tab.get("summary", {}) and _empty(summary.plot_area_source):
        by_tab["summary"]["plot_area_source"] = TITLE_DEED

    for tab, values in by_tab.items():
        version = (JobTabVersion.objects.filter(job_id=job_id, tab_key=tab)
                   .values_list("version", flat=True).first() or 0)
        try:
            # Whoever may upload the instruction's documents may have them read
            # in: the same allowance as the New instruction form.
            patch_tab(job_id, tab, user, values, base_version=version, intake=True)
        except TabError:
            logger.warning("Title deed fill refused on %s", tab, exc_info=True)
            result.filled = [x for x in result.filled if x not in {labels.get(k, k) for k in values}]
    return result
