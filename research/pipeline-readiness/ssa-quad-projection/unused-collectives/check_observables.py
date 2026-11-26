"""Compare the complete SSA input graphs reachable from emitted effects and control flow."""
import re

NUMERIC = re.compile(r"%(\d+)\b")
LABEL = re.compile(r"; <label>:(\d+)\b")
ASSIGN = re.compile(r"%(\d+) = (.+)")
CALL = re.compile(r"\bcall\b.*?@([-.$\w]+)\(")
COLLECTIVES={"dx.op.waveActiveBallot", "dx.op.quadReadLaneAt.i32", "dx.op.quadOp.i32"}

def parse(ir):
    lines=ir.splitlines()
    start=next(i for i,line in enumerate(lines) if line.startswith("define void @main()"))
    labels={"0":0}
    blocks=[[]]
    definitions={}
    root_groups=[[]]
    for raw in lines[start+1:]:
        if raw=="}":
            break
        label=LABEL.match(raw)
        if label:
            labels[label[1]]=len(blocks)
            blocks.append([])
            root_groups.append([])
            continue
        text=raw.split(";",1)[0].strip()
        if not text:
            continue
        if blocks[-1] and blocks[-1][-1][1].startswith("switch ") and not blocks[-1][-1][1].endswith("]"):
            blocks[-1][-1][1]+=" "+text
            continue
        assign=ASSIGN.fullmatch(text)
        ident,body=assign.groups() if assign else (None,text)
        inst=[ident,body]
        blocks[-1].append(inst)
        if ident is not None:
            definitions[ident]=inst
        call=CALL.search(body)
        if ident is None or (call and call[1] not in COLLECTIVES) or body.startswith(("load ","atomicrmw ","cmpxchg ")):
            root_groups[-1].append(inst)
    return labels,definitions,root_groups,blocks

def compare(old_ir,new_ir):
    a,adef,ar,ab=parse(old_ir)
    b,bdef,br,bb=parse(new_ir)
    if len(ar)!=len(br) or any(len(x)!=len(y) for x,y in zip(ar,br)):
        raise ValueError("Changed the number of blocks or ordered root operations per block")
    todo=[(x,y) for aa,bb in zip(ar,br) for x,y in zip(aa,bb)]
    seen=set()
    forward,back={},{}
    while todo:
        (ix,x),(iy,y)=todo.pop()
        if (ix is None)!=(iy is None):
            raise ValueError("Changed value or statement kind")
        if ix is not None:
            if (ix,iy) in seen:
                continue
            if forward.setdefault(ix,iy)!=iy or back.setdefault(iy,ix)!=ix:
                raise ValueError("Cloned, merged or reordered an observable operand")
            seen.add((ix,iy))
        ox=NUMERIC.findall(x)
        oy=NUMERIC.findall(y)
        if NUMERIC.sub("%id",x)!=NUMERIC.sub("%id",y) or len(ox)!=len(oy):
            raise ValueError(f"Changed observable operation: {x[:120]} / {y[:120]}")
        for l,r in zip(ox,oy):
            if l in a or r in b:
                if a.get(l)!=b.get(r):
                    raise ValueError("Changed a branch, switch or phi block reference")
            else:
                todo.append((adef[l],bdef[r]))
    for old_block,new_block in zip(ab,bb):
        left=[forward[i] if i is not None else None for i,_ in old_block if i is None or i in forward]
        right=[i for i,_ in new_block if i is None or i in back]
        if left!=right:
            raise ValueError("Moved an observed instruction relative to its block or another effect")
    return dict(blocks=len(ar),roots=sum(map(len,ar)),reachable_value_definitions=len(seen))

