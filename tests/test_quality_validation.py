import unittest
from pipeline.stages.stage_1_search import delivered_qualities

class DeliveredQualityTests(unittest.TestCase):
 def test_1080_file_cannot_verify_4k_slot(self):
  self.assertEqual(delivered_qualities('Chhaava.2025.Hindi.1080p.WEB-DL.mkv'),{'1080p'})
  self.assertNotIn('2160p',delivered_qualities('Chhaava.2025.Hindi.1080p.WEB-DL.mkv'))
 def test_video_dimensions_can_verify_quality(self):
  self.assertEqual(delivered_qualities('',1080),{'1080p'})
  self.assertEqual(delivered_qualities('',2160),{'2160p'})
 def test_unlabelled_document_does_not_verify_4k(self):
  self.assertEqual(delivered_qualities('',0),set())
