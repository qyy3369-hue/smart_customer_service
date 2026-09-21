"""Offline checks for the two-book pgvector ingestion pipeline."""

import unittest

from scripts.book_vector_ingest import clean_text, contiguous_spans, needs_ocr


class TestBookVectorIngest(unittest.TestCase):
    def test_clean_text_removes_pdf_control_characters(self):
        self.assertEqual(clean_text("内科\x12\x0e学  测试\n\n\n内容"), "内科学 测试\n\n内容")

    def test_sparse_or_garbled_text_layer_needs_ocr(self):
        self.assertTrue(needs_ocr("短页"))
        self.assertTrue(needs_ocr("JOEE 1234 " * 30))
        self.assertFalse(needs_ocr("药理学正文，介绍药物作用机制。" * 15))

    def test_contiguous_ocr_spans(self):
        self.assertEqual(contiguous_spans([1, 2, 4, 7, 8]), [(1, 2), (4, 1), (7, 2)])
        self.assertEqual(contiguous_spans([]), [])


if __name__ == "__main__":
    unittest.main()
