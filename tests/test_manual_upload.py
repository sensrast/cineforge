from control.manual_upload import detect_quality,detect_episode,assign_qualities

def rows(count):
 return [{'id':i+1,'file_size':(i+1)*1000,'explicit_quality':None,'season':None,'episode':None} for i in range(count)]

def test_quality_detection():
 assert detect_quality('Movie.1080p.Hindi.mkv')=='1080p'
 assert detect_quality('Movie UHD release')=='2160p'
 assert detect_quality('no label.mkv') is None

def test_size_inference_three_and_four_files():
 assert [x['quality'] for x in assign_qualities(rows(3))]==['480p','720p','1080p']
 assert [x['quality'] for x in assign_qualities(rows(4))]==['480p','720p','1080p','2160p']

def test_explicit_quality_wins():
 items=rows(3);items[-1]['explicit_quality']='1080p'
 assert [x['quality'] for x in assign_qualities(items)]==['480p','720p','1080p']

def test_series_infers_each_episode_separately():
 items=[]
 for episode in (1,2):
  for i in range(3):items.append({'id':episode*10+i,'file_size':1000*(i+1),'explicit_quality':None,'season':1,'episode':episode})
 assigned=assign_qualities(items,'series')
 assert [x['quality'] for x in assigned[:3]]==['480p','720p','1080p']
 assert [x['quality'] for x in assigned[3:]]==['480p','720p','1080p']

def test_episode_detection():
 assert detect_episode('Show.S02E07.1080p.mkv')==(2,7)
 assert detect_episode('Episode 12 720p.mkv')==(1,12)
