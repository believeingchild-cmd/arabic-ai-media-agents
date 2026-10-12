import tempfile
import unittest
from pathlib import Path
from scripts.quality_gate import validate

class QualityGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.video = Path(self.tmp.name) / "sample.mp4"
        self.video.write_bytes(b"x" * 60000)
        self.base = {
            "channel": "public", "title": "خبر موثق عن التقنية",
            "script": "هذا نص عربي تجريبي طويل بما يكفي حتى يمر من فحص الطول الأساسي، لكنه لا يثبت وحده صحة المعلومات الواردة في المحتوى.",
            "video_path": str(self.video),
            "sources": [{"url": "https://example.com/a"}, {"url": "https://news.example.org/b"}],
            "rights_review": True, "editorial_review": True
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_public_content_passes_baseline(self):
        self.assertEqual(validate(self.base), [])

    def test_missing_sources_blocks_public_content(self):
        payload = dict(self.base, sources=[])
        self.assertTrue(any("two HTTPS source domains" in e for e in validate(payload)))

    def test_missing_video_blocks(self):
        payload = dict(self.base, video_path=str(Path(self.tmp.name) / "missing.mp4"))
        self.assertTrue(any("existing file" in e for e in validate(payload)))

    def test_blocked_phrase_blocks(self):
        payload = dict(self.base, script=self.base["script"] + " علاج مضمون")
        self.assertTrue(any("blocked phrase" in e for e in validate(payload)))

    def test_children_requires_references_and_safety_review(self):
        payload = dict(self.base, channel="children", sources=[], religious_references=[], child_safety_review=False)
        errors = validate(payload)
        self.assertTrue(any("religious_references" in e for e in errors))
        self.assertTrue(any("child_safety_review" in e for e in errors))

if __name__ == "__main__":
    unittest.main()
