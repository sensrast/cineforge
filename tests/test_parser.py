import unittest
from utils.text_parser import parse_results,extract_batch_link,clean_title,is_series
class ParserTests(unittest.TestCase):
 def test_multi_block_mapping(self):
  text='''Name:\nFilm Hindi 480p WebRip\nSize: 500 MB\nType: video\nClick Download 1\nName:\nFilm Dual Audio 1080p HEVC 10bit\nSize: 2.86 GB\nType: video\nClick Download 2'''
  buttons=[{'text':'Download 1 : 500 MB'},{'text':'Download 2 : 2.86 GB'}]
  found=parse_results([{'id':9,'text':text,'buttons':buttons}],{'480p','1080p'})
  self.assertEqual([x['quality'] for x in found],['480p','1080p'])
  self.assertEqual(found[1]['button_text'],'Download 2 : 2.86 GB')
 def test_links_titles(self):
  self.assertEqual(extract_batch_link('https://t.me/movieinhindibot?start=abc-2'),'https://t.me/movieinhindibot?start=abc-2')
  self.assertEqual(clean_title('Pushpa 2 in Hindi'),'Pushpa 2')
  self.assertTrue(is_series('Show Season 2'))
if __name__=='__main__':unittest.main()
