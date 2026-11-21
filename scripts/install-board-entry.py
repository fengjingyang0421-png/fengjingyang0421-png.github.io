from pathlib import Path

path = Path('index.html')
source = path.read_text()
entry = '<a class="btn video-top" href="./board/">视频讲题</a>'
anchor = '<button class="btn share-top" data-act="share">分享</button>'
if entry not in source:
    if source.count(anchor) != 1:
        raise SystemExit('Expected listening page header')
    source = source.replace(anchor, entry + anchor)
    source = source.replace('</style>', '\n.video-top{margin-left:auto;font-size:13px;text-decoration:none;white-space:nowrap}.brand .share-top{margin-left:0}\n</style>', 1)
    path.write_text(source)
