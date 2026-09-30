"""Manual-upload metadata detection and deterministic quality inference."""
from __future__ import annotations
import re

QUALITY_RE=re.compile(r'(?<!\d)(2160p?|1080p?|720p?|480p?)(?!\d)|\b(?:4k|uhd)\b',re.I)
EPISODE_PATTERNS=(
 re.compile(r'\bS(?:eason)?[ ._-]?(\d{1,2})[ ._-]*E(?:p(?:isode)?)?[ ._-]?(\d{1,3})\b',re.I),
 re.compile(r'\bE(?:p(?:isode)?)?[ ._-]?(\d{1,3})\b',re.I),
)
ORDER={'480p':0,'720p':1,'1080p':2,'2160p':3}

def detect_quality(text:str)->str|None:
 match=QUALITY_RE.search(text or '')
 if not match:return None
 value=(match.group(0) or '').lower()
 if value in {'4k','uhd'} or value.startswith('2160'):return '2160p'
 for quality in ('1080p','720p','480p'):
  if value.startswith(quality[:-1]):return quality
 return None

def detect_episode(text:str)->tuple[int|None,int|None]:
 text=text or ''
 match=EPISODE_PATTERNS[0].search(text)
 if match:return int(match.group(1)),int(match.group(2))
 match=EPISODE_PATTERNS[1].search(text)
 if match:return 1,int(match.group(1))
 return None,None

def _labels(count:int)->list[str]:
 if count==1:return ['1080p']
 if count==2:return ['720p','1080p']
 if count==3:return ['480p','720p','1080p']
 if count==4:return ['480p','720p','1080p','2160p']
 raise ValueError('More than four files belong to the same movie/episode. Add season/episode labels to series filenames or split the upload.')

def assign_qualities(rows:list[dict],content_type:str='movie')->list[dict]:
 """Preserve explicit labels and infer missing labels by size within each episode."""
 prepared=[dict(row) for row in rows]
 groups={}
 for row in prepared:
  key=(row.get('season'),row.get('episode')) if content_type=='series' and row.get('episode') is not None else (None,None)
  groups.setdefault(key,[]).append(row)
 for key,items in groups.items():
  ranked=sorted(items,key=lambda item:(int(item.get('file_size') or 0),int(item.get('id') or 0)))
  labels=_labels(len(ranked))
  for index,item in enumerate(ranked):
   item['quality']=item.get('explicit_quality') or labels[index]
  seen={}
  for item in ranked:
   quality=item['quality']
   if quality in seen:
    label=(f'S{int(key[0] or 1):02d}E{int(key[1]):02d}' if key[1] is not None else 'this title')
    raise ValueError(f'Duplicate {quality} files detected for {label}. Add correct quality text to the filename/caption or remove one file.')
   seen[quality]=item
 return sorted(prepared,key=lambda item:(item.get('season') or 0,item.get('episode') or 0,ORDER.get(item['quality'],99)))

def summary(rows:list[dict],content_type:str='movie')->str:
 assigned=assign_qualities(rows,content_type)
 lines=[]
 for index,row in enumerate(assigned,1):
  size=int(row.get('file_size') or 0);size_text=f'{size/1024/1024/1024:.2f} GB' if size>=1024**3 else f'{size/1024/1024:.0f} MB'
  episode=f" S{int(row.get('season') or 1):02d}E{int(row['episode']):02d}" if row.get('episode') is not None else ''
  source='caption' if row.get('explicit_quality') else 'size inference'
  lines.append(f"{index}. {row['quality']}{episode} — {size_text} ({source})")
 return '\n'.join(lines)
