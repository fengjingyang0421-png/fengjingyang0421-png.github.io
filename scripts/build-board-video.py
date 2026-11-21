"""Create the blackboard player assets from the repository's quiz and narration."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import io
import json
import re
from pathlib import Path
import subprocess
import tempfile
import wave

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'board' / 'media'
SAMPLE_RATE = 24000
FPS = 24
SAMPLES_PER_FRAME = SAMPLE_RATE // FPS
WIDTH, HEIGHT = 1280, 720
START_X, END_X = 215, 1122
LETTERS = 'ABCD'
WHITE = '#f4f5e2'
GOLD = '#ffdb91'
MINT = '#a1dcc2'
FONT_ROOT = Path('/usr/share/fonts/opentype/noto')
BACKGROUND = ROOT / 'board' / 'classroom.jpg'

SOURCE = (ROOT / 'index.html').read_text()
BANK = json.loads(re.search(r'<script id="embedded-bank" type="application/json">(.*?)</script>', SOURCE, re.S)[1])
QUESTIONS = BANK['questions']
EXPLANATIONS = json.loads((ROOT / 'board' / 'explanations.json').read_text())
EXPLANATION_AUDIO = ROOT / 'board-voice'


def font(size, bold=True):
    return ImageFont.truetype(str(FONT_ROOT / ('NotoSansCJK-Bold.ttc' if bold else 'NotoSansCJK-Regular.ttc')),
                              size=size, index=2)


def wrap(value, face, width):
    lines = []
    for paragraph in value.split('\n'):
        line = ''
        # Keep alphanumeric measurements intact when sensible.
        for part in re.findall(r'(?:[a-zA-Z0-9][a-zA-Z0-9.+/Ω%²³°-]*|[（(]\s*[）)]|.)[，。、；：？！？）】]*', paragraph):
            if line and face.getlength(line + part) > width:
                lines.append(line)
                line = ''
            line += part
        if line:
            lines.append(line)
    return lines or ['']


def text(draw, value, xy, face, fill=WHITE, anchor='lt'):
    draw.text(xy, value, font=face, fill=fill, anchor=anchor)


def illustration(canvas, value, box):
    x, y, right, bottom = box
    data = base64.b64decode(value.split(',', 1)[1])
    with Image.open(io.BytesIO(data)) as original:
        image = original.convert('RGBA')
        image.thumbnail((right-x-14, bottom-y-14), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(box, radius=8, fill='#f8f6ef')
    canvas.paste(image, (x+(right-x-image.width)//2, y+(bottom-y-image.height)//2), image)


def board(question, answer=False, reason=False):
    with Image.open(BACKGROUND) as original:
        canvas = original.convert('RGB')
    draw = ImageDraw.Draw(canvas)
    qid = question['id']
    options = question['options']
    pictures = question.get('optionImages') or []
    count = len(options)
    assert 2 <= count <= 4
    has_long_options = any(len(value) > max(9, 31//count) for value in options)
    columns = 2 if has_long_options and not pictures else count
    rows = (count+columns-1)//columns
    text(draw, f'第 {qid} 题', (START_X,115), font(24), MINT)
    draw.line((START_X,154,END_X,154), fill='#70957d')
    if question.get('image'):
        illustration(canvas, question['image'], (822, 170, END_X, 378))
    usable_width = 584 if question.get('image') else END_X-START_X-7
    stem_height = 190 if rows == 2 else 218
    for stem_size in range(46, 20, -1):
        stem_font = font(stem_size)
        stem_lines = wrap(question['stem'], stem_font, usable_width)
        if len(stem_lines) * (stem_size+9) <= stem_height:
            break
    assert len(stem_lines) * (stem_size+9) <= stem_height, qid
    assert all(stem_font.getlength(line) <= usable_width+stem_size for line in stem_lines), qid
    stem_y = 177
    for line in stem_lines:
        text(draw,line,(START_X,stem_y),stem_font)
        stem_y += stem_size+9

    # Keep short choices on one row and give long choices room for two lines.
    gap = 15
    card_width = (END_X-START_X-gap*(columns-1))//columns
    option_y = 419 if stem_y>335 or question.get('image') else max(309, stem_y+28)
    if pictures:
        option_y = max(392, stem_y+15)
    if rows == 2:
        option_y = 388 if question.get('image') else max(322,stem_y+20)
    card_height = 76 if rows==2 else 72
    if pictures:
        card_height = 102
    for index, value in enumerate(options):
        x = START_X + (card_width+gap)*(index%columns)
        y = option_y + (card_height+9)*(index//columns)
        selected = answer and index in question['answer']
        color = GOLD if selected else WHITE
        draw.rounded_rectangle((x,y,x+card_width,y+card_height),radius=12,
                               fill='#624f20' if selected else '#173a2e',
                               outline=GOLD if selected else '#83a895',width=3 if selected else 1)
        text(draw,LETTERS[index],(x+17,y+card_height//2),font(23),color,'lm')
        if pictures:
            illustration(canvas,pictures[index],(x+49,y+8,x+card_width-9,y+card_height-8))
            continue
        max_width = card_width-61
        for size in range(35, 13, -1):
            item_font = font(size)
            lines = wrap(value,item_font,max_width)
            if len(lines)*(size+3)<=card_height-11:
                break
        assert len(lines)*(size+3)<=card_height-11, (qid,index)
        for row,line in enumerate(lines):
            text(draw,line,(x+(card_width+37)//2,y+card_height/2+(row-(len(lines)-1)/2)*(size+3)),item_font,color,'mm')

    if reason:
        value = EXPLANATIONS[str(qid)]
        bottom = option_y+(rows-1)*(card_height+9)+card_height+15
        for size in range(30, 17, -1):
            face = font(size,False)
            lines = wrap(value,face,END_X-START_X-4)
            if bottom+len(lines)*(size+5)<=580:
                break
        if bottom+len(lines)*(size+5)>580:
            # On diagram questions the explanation also remains readable below the frame.
            bottom = 619
            draw.rounded_rectangle((195,606,1142,700),radius=12,fill='#17271f')
        for row,line in enumerate(lines):
            text(draw,line,(START_X,bottom+row*(size+5)),face,GOLD)
    return canvas


def read_pcm(path, speed):
    return subprocess.check_output(['ffmpeg','-nostdin','-v','error','-threads','1','-i',str(path),
                                    '-af',f'atempo={speed:.6f},silenceremove=start_periods=1:start_duration=0.012:start_threshold=-49dB:start_silence=0.10',
                                    '-ar',str(SAMPLE_RATE),'-ac','1','-f','s16le','-'])


def part(path, speed, pause):
    pcm = read_pcm(path,speed)
    if not pcm:
        raise ValueError(f'Empty audio: {path}')
    frames = (len(pcm)//2+round(pause*SAMPLE_RATE)+SAMPLES_PER_FRAME-1)//SAMPLES_PER_FRAME
    silence = frames*SAMPLES_PER_FRAME*2-len(pcm)
    return pcm+b'\0'*silence,frames


def render_group(number, questions):
    name=f'lesson-{number:02d}.mp4'
    entries=[]
    frame_number=0
    manifest=[]
    with tempfile.TemporaryDirectory(prefix='chalkboard-') as workdir:
        temp=Path(workdir)
        wav_path=temp/'voice.wav'
        with wave.open(str(wav_path),'wb') as narrator:
            narrator.setparams((1,2,SAMPLE_RATE,0,'NONE','not compressed'))
            for question in questions:
                qid=question['id']
                custom=(EXPLANATION_AUDIO/f'{qid}-stem.wav').is_file()
                sound_root=EXPLANATION_AUDIO if custom else ROOT/'voice-v1'
                suffix='wav' if custom else 'mp3'
                speed=.95 if custom else .96*.963*.95/.99
                stem_audio,stem_frames=part(sound_root/f'{qid}-stem.{suffix}',speed,1.18)
                has_reason=str(qid) in EXPLANATIONS
                answer_audio,answer_frames=part(sound_root/f'{qid}-answer.{suffix}',speed,.28 if has_reason else 1.10)
                entries.append([qid,frame_number/FPS,(frame_number+stem_frames)/FPS])
                segments=[(False,False,stem_audio,stem_frames),(True,False,answer_audio,answer_frames)]
                if has_reason:
                    reason_audio,reason_frames=part(EXPLANATION_AUDIO/f'{qid}-detail.wav',.95,1.10)
                    segments.append((True,True,reason_audio,reason_frames))
                for index,(is_answer,is_reason,audio,frames) in enumerate(segments):
                    filename=f'{qid}-{index}.png'
                    board(question,is_answer,is_reason).save(temp/filename,compress_level=1)
                    manifest.extend([f"file '{filename}'",f'option framerate {FPS}',f'duration {frames/FPS:.9f}'])
                    narrator.writeframesraw(audio)
                    frame_number+=frames
        # One final frame gives the preceding still its full duration.
        last_frames=frames-1
        manifest[-1]=f'duration {last_frames/FPS:.9f}'
        manifest.extend(manifest[-3:-1])
        (temp/'frames.ffconcat').write_text('ffconcat version 1.0\n'+'\n'.join(manifest)+'\n')
        result=DEST/name
        subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','concat','-safe','0','-i',str(temp/'frames.ffconcat'),
                        '-i',str(wav_path),'-t',f'{frame_number/FPS:.9f}','-fps_mode','vfr',
                        '-c:v','libx264','-threads','1','-preset','veryfast','-g','1','-crf','24',
                        '-profile:v','high','-level','3.1','-pix_fmt','yuv420p','-video_track_timescale','24000',
                        '-c:a','aac','-ar','48000','-b:a','40k','-movflags','+faststart',str(result)],check=True)
    assert result.stat().st_size<48_000_000, name
    print(name,len(questions),round(frame_number/FPS,2),result.stat().st_size,flush=True)
    return name,entries


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--workers',type=int,default=3)
    parser.add_argument('--from-group',type=int,default=0)
    parser.add_argument('--to-group',type=int,default=100)
    args=parser.parse_args()
    DEST.mkdir(parents=True,exist_ok=True)
    groups=[(offset//40,QUESTIONS[offset:offset+40]) for offset in range(0,len(QUESTIONS),40)]
    selected=[group for group in groups if args.from_group<=group[0]<=args.to_group]
    with ThreadPoolExecutor(max_workers=args.workers) as workers:
        result=list(workers.map(lambda pair:render_group(*pair),selected))
    (DEST/f'index-{args.from_group:02d}.json').write_text(json.dumps(result,separators=(',',':')))


if __name__=='__main__':
    main()
