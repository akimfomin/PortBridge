import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
from portbridge.github import _technical
from portbridge.matching import RelatedIndex,canonical_url
input_data=json.loads(Path(__file__).with_name('discovery-input.json').read_text(encoding='utf-8'))
results={}
for mode in ("title_only", "with_body"):
    observed=[]
    for repo,num,title,body in input_data:
        meta=_technical({"title":title,"body":body if mode=="with_body" else ""},[],{})
        if mode=="title_only":
            meta["mechanisms"]=[]
        observed.append(dict(url=f"https://github.com/{repo}/pull/{num}",project=repo,kind="pr",title=title,metadata={"technical":meta}))
    idx=RelatedIndex(observed)
    u=canonical_url(observed[0]["url"])
    results[mode]={"tags":{row["url"]:sorted(idx.mechanisms[canonical_url(row["url"])]) for row in observed},
                  "candidates":[(u,b,n) for u,_,b,n in idx.candidates(u)]}
print(json.dumps(results))
