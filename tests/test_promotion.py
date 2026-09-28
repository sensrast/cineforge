import unittest
from pipeline.promotion import provider_caption

class PromotionTests(unittest.TestCase):
 def test_provider_caption_matches_requested_layout(self):
  link='https://t.me/+ExampleInvite'
  self.assertEqual(provider_caption(link),f'Channel link 🔗 👇👇\n\n{link}\n{link}')
