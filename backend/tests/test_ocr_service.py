from PIL import Image

from app.services.cache_service import CacheService
from app.services.ocr_service import OcrService


class Vertex:
    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y


def _vertices(x1: int, y1: int, x2: int, y2: int):
    return [Vertex(x1, y1), Vertex(x2, y1), Vertex(x2, y2), Vertex(x1, y2)]


class BoundingPoly:
    def __init__(self, vertices):
        self.vertices = vertices


class Symbol:
    def __init__(self, text: str) -> None:
        self.text = text


class Word:
    def __init__(self, text: str) -> None:
        self.symbols = [Symbol(text)]


class Paragraph:
    def __init__(self, words, bbox):
        self.words = words
        self.bounding_box = bbox


class Block:
    def __init__(self, paragraphs):
        self.paragraphs = paragraphs


class Page:
    def __init__(self, blocks):
        self.blocks = blocks


class FullText:
    def __init__(self, pages):
        self.pages = pages


class FakeError:
    def __init__(self) -> None:
        self.message = ""


class FakeResponse:
    def __init__(self, full_text_annotation=None, text_annotations=None) -> None:
        self.full_text_annotation = full_text_annotation
        self.text_annotations = text_annotations or []
        self.error = FakeError()


class FakeClient:
    def __init__(self, response: FakeResponse) -> None:
        self._response = response

    def text_detection(self, image):  # noqa: ANN001
        return self._response


def test_ocr_merges_paragraphs(monkeypatch, tmp_path):
    img_path = tmp_path / "page.png"
    Image.new("RGB", (200, 200), color="white").save(img_path)

    para1 = Paragraph([Word("hola"), Word("mundo")], BoundingPoly(_vertices(10, 10, 90, 40)))
    para2 = Paragraph([Word("adios")], BoundingPoly(_vertices(92, 12, 160, 42)))
    full_text = FullText([Page([Block([para1, para2])])])
    response = FakeResponse(full_text_annotation=full_text)

    cache = CacheService(base_dir=tmp_path / "cache")
    service = OcrService(cache_service=cache)
    monkeypatch.setattr(service, "_get_client", lambda: FakeClient(response))

    regions = service.extract_text_regions(img_path)

    assert len(regions) == 1
    assert regions[0].text == "hola mundo adios"
    assert service.last_merged_region_count >= 1
    assert service.last_invalid_bbox_count == 0
    assert service.last_discarded_region_count == 0
    assert service.regions_detected_raw >= 1
    assert service.regions_after_paragraph_grouping >= 1
    assert service.regions_after_merge == 1


def test_ocr_discards_invalid_bbox(monkeypatch, tmp_path):
    img_path = tmp_path / "page2.png"
    Image.new("RGB", (100, 100), color="white").save(img_path)

    class Annotation:
        def __init__(self, description: str, vertices):
            self.description = description
            self.bounding_poly = BoundingPoly(vertices)

    # Primer elemento se ignora, segundo es inválido
    annotations = [Annotation("full", _vertices(0, 0, 0, 0)), Annotation("word", _vertices(50, 50, 50, 50))]
    response = FakeResponse(full_text_annotation=None, text_annotations=annotations)

    cache = CacheService(base_dir=tmp_path / "cache2")
    service = OcrService(cache_service=cache)
    monkeypatch.setattr(service, "_get_client", lambda: FakeClient(response))

    regions = service.extract_text_regions(img_path)

    assert regions == []
    assert service.last_invalid_bbox_count >= 1
    assert service.last_discarded_region_count >= 0


def test_ocr_reduces_word_regions(monkeypatch, tmp_path):
    img_path = tmp_path / "page3.png"
    Image.new("RGB", (400, 400), color="white").save(img_path)

    class Annotation:
        def __init__(self, description: str, vertices):
            self.description = description
            self.bounding_poly = BoundingPoly(vertices)

    annotations = [Annotation("full", _vertices(0, 0, 10, 10))]
    for i in range(100):
        line = i // 20
        col = i % 20
        x1 = 10 + col * 15
        y1 = 10 + line * 30
        annotations.append(Annotation(f"w{i}", _vertices(x1, y1, x1 + 10, y1 + 10)))

    response = FakeResponse(full_text_annotation=None, text_annotations=annotations)

    cache = CacheService(base_dir=tmp_path / "cache3")
    service = OcrService(cache_service=cache)
    monkeypatch.setattr(service, "_get_client", lambda: FakeClient(response))

    regions = service.extract_text_regions(img_path)

    assert len(regions) <= 10
    assert service.regions_detected_raw >= 100
    assert service.regions_after_merge <= 10
