import json,sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from portbridge.github import _technical
from portbridge.matching import RelatedIndex, canonical_url
records=[]
for repo,number,title in json.loads(Path(__file__).with_name("search-titles.json").read_text(encoding="utf-8")):
    url=f"https://github.com/{repo}/pull/{number}"
    records.append(dict(url=url,project=repo,kind="pr",title=title,metadata={"technical":_technical({"title":title,"body":""},[],{})}))
index=RelatedIndex(records)
out={}
for repo,number in [("LooperSalty/AnyXboxX",574),("shadps4-emu/shadPS4",5434),("PastiiJay/klbf-lab",59),("TaynanGT/Vice-Tay",392)]:
    url=canonical_url(f"https://github.com/{repo}/pull/{number}")
    out[url]=sorted(index.candidates(url),key=lambda item:(-item[1],item[0]))[:8] if url in index.rows else []
print(json.dumps(out))
