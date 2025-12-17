from app.models.text import BBox
from app.services.region_filter import RegionKind, classify_region


def test_classify_region_heuristics():
    page_w, page_h = 1000, 1000
    mid_bbox = BBox(x_min=0.1, y_min=0.1, x_max=0.2, y_max=0.2)

    assert (
        classify_region("33 1103", mid_bbox, 0.9, page_w, page_h)
        == RegionKind.NON_DIALOGUE
    )
    assert classify_region("CAFÉ", mid_bbox, 0.9, page_w, page_h) == RegionKind.NON_DIALOGUE
    assert classify_region("BAM!", mid_bbox, 0.9, page_w, page_h) == RegionKind.NON_DIALOGUE

    dialogue_bbox = BBox(x_min=0.3, y_min=0.3, x_max=0.6, y_max=0.35)
    assert classify_region(
        "Hello, are you ok?", dialogue_bbox, 0.9, page_w, page_h
    ) == RegionKind.DIALOGUE
    assert classify_region(
        "THE NOT WAY?", dialogue_bbox, 0.6, page_w, page_h
    ) in {RegionKind.UNKNOWN, RegionKind.DIALOGUE}
