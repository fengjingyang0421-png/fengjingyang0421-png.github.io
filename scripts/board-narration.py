"""Render short explanations and the four sample questions in the same Mandarin voice."""
import argparse
import json
from pathlib import Path
import re

import numpy as np
import soundfile
import torch
from kokoro import KModel, KPipeline

ROOT = Path(__file__).resolve().parents[1]
REPO = 'hexgrad/Kokoro-82M-v1.1-zh'
VOICE = 'zf_001'
RATE = 24000
SAMPLES = {
    1: (('第一题。', '导线接头缠绝缘胶布时，后一圈压在前一圈胶布宽度的多少？'), '选B，二分之一。'),
    2: (('第二题。','使用脚扣时，应将脚掌穿入脚扣的皮带与脚扣踏板之间。','再在皮带扣的扣压两侧，接上一段适当长度的橡胶带。','将橡胶带扣在哪里？'), '选C，脚后跟。'),
    3: (('第三题。','短时定额表示，电动机按铭牌值工作时，只能在规定时间内短时运行。','我国规定的短时运行时间为十分钟、三十分钟、六十分钟，还有多少分钟？'), '选B，九十分钟。'),
    4: (('第四题。','线路单相短路，是指什么？'), '选C，零火线直接接通。'),
}
UNITS = {'min':'分钟','MΩ':'兆欧','kΩ':'千欧','Ω':'欧姆','mm':'毫米','kV':'千伏','V':'伏','℃':'摄氏度'}
PHRASING = {'1':'后一圈压住前一圈的一半，让每一圈都有搭接。',
             '2':'橡胶带扣住脚后跟，能把脚固定住，减少脚往后滑脱。',
             '3':'顺着记，十、三十、六十、九十，单位都是分钟。',
             '4':'这道题说的是，火线和零线直接接通，电流绕过了用电器。'}


def spoken(note):
    for key, val in UNITS.items():
        note = note.replace(key,val)
    return note.replace('%','百分比').replace('Ⅰ','一').replace('Ⅱ','二').replace('Ⅲ','三').replace('∞','无穷大')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-dir',type=Path,required=True)
    parser.add_argument('--first',type=int,default=1)
    parser.add_argument('--last',type=int,default=1307)
    parser.add_argument('--threads',type=int,default=2)
    args=parser.parse_args()
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    model_dir=args.model_dir
    english=KPipeline(lang_code='a',repo_id=REPO,model=False)
    model=KModel(repo_id=REPO,config=str(model_dir/'config.json'),model=str(model_dir/'kokoro-v1_1-zh.pth')).cpu().eval()
    pipeline=KPipeline(lang_code='z',repo_id=REPO,model=model,en_callable=lambda phrase:next(english(phrase)).phonemes,device='cpu')
    pipeline.voices[VOICE]=torch.load(model_dir/'voices'/f'{VOICE}.pt',weights_only=True)
    output=ROOT/'board-voice'
    output.mkdir(exist_ok=True)

    def render(phrases,path):
        if path.exists():
            return
        clips=[]
        with torch.inference_mode():
            for phrase in phrases:
                wave=np.concatenate([part.audio.numpy() for part in pipeline(phrase,voice=VOICE,speed=.96*.963) if part.audio is not None])
                peaks=np.flatnonzero(np.abs(wave)>.007)
                wave=wave[max(0,int(peaks[0]) - int(.048*RATE)):min(len(wave),int(peaks[-1]) + int(.090*RATE))].copy()
                fade=int(.008*RATE)
                wave[:fade]*=np.linspace(0,1,fade)
                wave[-fade:]*=np.linspace(1,0,fade)
                clips.extend((wave,np.zeros(round((.36 if not clips and len(phrases)>1 else .19)*RATE),np.float32)))
        tmp=path.with_suffix('.tmp.wav')
        soundfile.write(tmp,np.concatenate(clips[:-1]),RATE,subtype='PCM_16')
        tmp.replace(path)

    notes=json.loads((ROOT/'board'/'explanations.json').read_text())
    for qid,note in notes.items():
        if not args.first<=int(qid)<=args.last:
            continue
        detail=PHRASING.get(qid,spoken(note))
        render(tuple(v for v in re.findall(r'[^。！？]+[。！？]?',detail) if v),output/f'{qid}-detail.wav')
        if int(qid) in SAMPLES:
            stem,answer=SAMPLES[int(qid)]
            render(stem,output/f'{qid}-stem.wav')
            render((answer,),output/f'{qid}-answer.wav')
        print(qid,flush=True)


if __name__=='__main__':
    main()
