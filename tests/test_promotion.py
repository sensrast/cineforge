import unittest
from pipeline.promotion import provider_caption,formatted_promotion_caption,DEFAULT_PROMOTION_CAPTION

class PromotionTests(unittest.TestCase):
 def test_provider_caption_matches_requested_layout(self):
  link='https://t.me/+ExampleInvite'
  self.assertEqual(provider_caption(link),f'Channel link 🔗 👇👇\n\n{link}\n{link}')
 def test_updates_caption_is_bold_and_quoted(self):
  self.assertEqual(formatted_promotion_caption(DEFAULT_PROMOTION_CAPTION,'Iron Man'),'<b>❤️‍🔥 Iron Man</b>\n\n<blockquote><b>🥳 all qualities Added ....!🕺</b></blockquote>')
 def test_movie_title_is_html_escaped(self):
  self.assertIn('A &amp; B',formatted_promotion_caption(DEFAULT_PROMOTION_CAPTION,'A & B'))
