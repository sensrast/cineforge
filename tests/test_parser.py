import unittest
from utils.text_parser import parse_results,extract_batch_link,clean_title,is_series,title_matches,format_template,explicit_non_hindi
class ParserTests(unittest.TestCase):
 def test_multi_block_mapping(self):
  text='''Name:\nFilm Hindi 480p WebRip\nSize: 500 MB\nType: video\nClick Download 1\nName:\nFilm Dual Audio 1080p HEVC 10bit\nSize: 2.86 GB\nType: video\nClick Download 2'''
  buttons=[{'text':'Download 1 : 500 MB'},{'text':'Download 2 : 2.86 GB'}]
  found=parse_results([{'id':9,'text':text,'buttons':buttons}],{'480p','1080p'})
  self.assertEqual([x['quality'] for x in found],['480p','1080p'])
  self.assertEqual(found[1]['button_text'],'Download 2 : 2.86 GB')
 def test_page_level_hindi_context_applies_to_all_blocks(self):
  text=('Name:\nFilm Hindi 720p WebRip\nSize: 1 GB\nClick Download 1\n'
        'Name:\nFilm 480pHEVC WebRip\nSize: 500 MB\nClick Download 2')
  buttons=[{'text':'Download 1 : 1 GB'},{'text':'Download 2 : 500 MB'}]
  found=parse_results([{'id':11,'text':text,'buttons':buttons}],{'480p','720p'})
  self.assertEqual({item['quality'] for item in found},{'480p','720p'})
 def test_all_page_one_qualities_are_detected(self):
  blocks=[]; buttons=[]
  for index, quality in enumerate(('480p','720p','1080p','2160p'),1):
   blocks.append(f'Name:\nFilm Hindi {quality} WebRip\nSize: {index}.0 GB\nType: video\nClick Download {index}')
   buttons.append({'text':f'Download {index} : {index}.0 GB'})
  found=parse_results([{'id':10,'text':'\n'.join(blocks),'buttons':buttons}],{'480p','720p','1080p','2160p'})
  self.assertEqual({item['quality'] for item in found},{'480p','720p','1080p','2160p'})
 def test_exact_title_rejects_sequel_collision(self):
  self.assertFalse(title_matches('Pushpa','Pushpa 2 The Rule 2024 Hindi 1080p'))
  self.assertTrue(title_matches('Pushpa 2','Pushpa 2 The Rule 2024 Hindi 1080p'))
  self.assertTrue(title_matches('Pushpa','Pushpa The Rise 2021 Hindi 720p'))
 def test_result_parser_filters_wrong_sequel(self):
  text=('Name:\nPushpa 2 The Rule Hindi 720p\nSize: 1 GB\nClick Download 1\n'
        'Name:\nPushpa The Rise Hindi 720p\nSize: 900 MB\nClick Download 2')
  buttons=[{'text':'Download 1 : 1 GB'},{'text':'Download 2 : 900 MB'}]
  found=parse_results([{'id':12,'text':text,'buttons':buttons}],{'720p'},title_query='Pushpa')
  self.assertEqual(found[0]['button_text'],'Download 2 : 900 MB')
 def test_branding_placeholder_case_aliases(self):
  self.assertEqual(format_template('@{Owner_username}',owner_username='MyChannel'),'@MyChannel')
 def test_series_order_and_grouping(self):
  text=('Name:\nMoney Heist S01E01 Hindi 720p\nSize: 1 GB\nClick Download 2\n'
        'Name:\nMoney Heist S01E01 Hindi 480pHEVC\nSize: 500 MB\nClick Download 01')
  buttons=[{'text':'Download 01 : 500 MB'},{'text':'Download 2 : 1 GB'}]
  found=parse_results([{'id':20,'text':text,'buttons':buttons}],{'480p','720p'},title_query='Money Heist')
  self.assertEqual([(x['season'],x['episode'],x['quality']) for x in found],[(1,1,'480p'),(1,1,'720p')])
 def test_delivered_media_language_aliases(self):
  self.assertTrue(explicit_non_hindi('Pushpa.2021.480p.KAN.Dub.mkv'))
  self.assertTrue(explicit_non_hindi('Pushpa Tamil 480p.mkv'))
  self.assertFalse(explicit_non_hindi('Pushpa Hindi Kannada Dual Audio 480p.mkv'))
 def test_hindi_page_rejects_explicit_kannada_file(self):
  text=('Name:\nPushpa Hindi 720p\nSize: 1 GB\nClick Download 1\n'
        'Name:\nPushpa Kannada 480p\nSize: 500 MB\nClick Download 2')
  buttons=[{'text':'Download 1 : 1 GB'},{'text':'Download 2 : 500 MB'}]
  found=parse_results([{'id':40,'text':text,'buttons':buttons}],{'480p','720p'},title_query='Pushpa',content_type='movie')
  self.assertEqual([item['quality'] for item in found],['720p'])
 def test_movie_mode_rejects_episodic_animal_results(self):
  text=('Name:\nAnimal 2023 Hindi 720p\nSize: 1 GB\nClick Download 1\n'
        'Name:\nAnimal Kingdom S01E01 Hindi 720p\nSize: 900 MB\nClick Download 2')
  buttons=[{'text':'Download 1 : 1 GB'},{'text':'Download 2 : 900 MB'}]
  found=parse_results([{'id':30,'text':text,'buttons':buttons}],{'720p'},title_query='Animal',content_type='movie')
  self.assertEqual(len(found),1)
  self.assertIn('Animal 2023',found[0]['source_name'])
 def test_links_titles(self):
  self.assertEqual(extract_batch_link('https://t.me/movieinhindibot?start=abc-2'),'https://t.me/movieinhindibot?start=abc-2')
  self.assertEqual(clean_title('Pushpa 2 in Hindi'),'Pushpa 2')
  self.assertTrue(is_series('Show Season 2'))
if __name__=='__main__':unittest.main()
