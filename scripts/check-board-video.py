"""Check that every original question is reachable and every movie is present."""
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
media = ROOT/'board'/'media'
html = (ROOT/'index.html').read_text()
bank = json.loads(re.search(r'<script id="embedded-bank" type="application/json">(.*?)</script>',html,re.S)[1])
groups = [group for index in sorted(media.glob('index-*.json')) for group in json.loads(index.read_text())]
assert len(groups) == 33, len(groups)
actual = []
for name, entries in groups:
    assert entries and entries[0][1] == 0, name
    path = media/name
    assert path.is_file() and path.stat().st_size > 10000, name
    probe = subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_name,width,height','-of','json',str(path)])
    data = json.loads(probe)
    assert {s['codec_name'] for s in data['streams']} == {'h264','aac'}, name
    duration = float(data['format']['duration'])
    last_answer = -1
    for number,start,answer in entries:
        assert duration > answer > start > last_answer, (name,number,start,answer,duration)
        last_answer = answer
        actual.append(number)
expected = [q['id'] for q in bank['questions']]
assert actual == expected == list(range(1,1308)), len(actual)
(media/'index.json').write_text(json.dumps(groups,separators=(',',':')))
for path in media.glob('index-*.json'):
    path.unlink()
total = sum(path.stat().st_size for path in media.glob('*.mp4'))
print(f'Validated {len(actual)} questions in {len(groups)} videos, {total/1024**2:.1f} MiB.')
