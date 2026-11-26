
import collections, functools, glob, json, pathlib, re, sys

V = r'(?:%\d+|-?\d+|true|false|undef|poison)'
M = (1 << 32) - 1
MAX = 1 << 32
D = pathlib.Path(sys.argv[1])
DATA, TOTAL = [], collections.Counter()
KNOWN = collections.Counter()

def binary(d, v, kinds, width='i32'):
    m = re.fullmatch(rf'({"|".join(kinds)}) {width} ({V}), ({V})', d.get(v,''))
    return m.groups() if m else None

def cmp(d, v, pred):
    m = re.fullmatch(rf'icmp {pred} i32 ({V}), ({V})', d.get(v,''))
    return m.groups() if m else None

def zext(d, v):
    m = re.fullmatch(rf'zext i1 ({V}) to i32',d.get(v,''))
    return m[1] if m else None

def select(d, v, width):
    m = re.fullmatch(rf'select i1 ({V}), {width} ({V}), {width} ({V})',d.get(v,''))
    return m.groups() if m else None

def cint(s):
    return int(s) & M if re.fullmatch(r'-?\d+',s) else None

def token32(x):
    n = cint(x)
    return n if n is not None else x

def carry(d, flag):
    co = cmp(d,flag,'ult')
    if not co:
        return None
    a,b = co
    add = binary(d,a,['add'])
    if add and b in add[1:]:
        return (b, 'carry', add[2] if add[1]==b else add[1])
    if cint(b) is not None:
        return (a, 'borrow', b)
    return None

def hi_shape(d, hi):
    flag=zext(d,hi)
    if flag and carry(d,flag):
        return ('0', *carry(d, flag))
    expr=binary(d,hi,['add','sub'])
    if expr:
        op,k,v=expr
        for base, choice in [(k,v)] if op=='sub' else [(k,v),(v,k)]:
            flag=zext(d,choice)
            c=carry(d,flag) if flag else None
            if c and c[1]==('borrow' if op=='sub' else 'carry'):
                return (base,*c)
    return None

def selector(d, s):
    alias=select(d,s,'i32')
    if alias and alias[1]=='0':
        c,_,diff=alias
        z=cmp(d,c,'eq')
        if z and '0' in z:
            h=z[1] if z[0]=='0' else z[0]
            ds=binary(d,diff,['sub'])
            if ds and ds[1]==h:
                return (h, ds[2], True)
    ds=binary(d,s,['sub'])
    return (ds[1],ds[2],False) if ds else None

def heap_guard(d,v):
    cond=binary(d,v,['and'],'i1')
    pair=[(cond[1],cond[2]),(cond[2],cond[1])] if cond else [(v,'true')]
    for test,exec in pair:
        ul=cmp(d,test,'ult')
        if ul and ul[1]=='4':
            sel=selector(d,ul[0])
            if sel:
                return (exec, *sel)
    return None

def parse(p):
    txt=p.read_text()
    s=txt.split('define void @main() {',1)[1].split('\n}',1)[0]
    d={}
    blocks=collections.defaultdict(list)
    cur='0'
    for line in s.splitlines():
        line=line.strip()
        m=re.match(r'^; <label>:(\d+)',line)
        if m:
            cur=m[1]
            continue
        code=line.split('  ;',1)[0].strip()
        if not code:
            continue
        blocks[cur].append(code)
        m=re.match(r'(%\d+) = (.*)',code)
        if m:
            d[m[1]]=m[2]
    return d,blocks

def readnum(block):
    return sum(' @dx.op.rawBufferLoad.i32(' in l for l in block)

def term(blocks,v):
    return blocks.get(v,('missing',))[-1]

def regions(d,blocks,mode):
    out=[]
    for pos,(src, block) in enumerate(blocks.items()):
        if mode=='heap':
            m=re.fullmatch(r'br i1 (%\d+), label %(\d+), label %(\d+)',block[-1])
            if not m:
                continue
            cond, arm, end=m.groups()
            reads=readnum(blocks[arm]) if arm in blocks else 0
            if term(blocks,arm)!=f'br label %{end}' or reads==0:
                continue
            ordered=any('@dx.op.' in v and not re.search(r'@dx\.op\.(?:createHandleFromBinding|createHandleFromHeap|annotateHandle|rawBufferLoad\.i32)\(',v) for v in blocks[arm])
            guard=heap_guard(d,cond)
        else:
            if not any(v.startswith('switch i32 ') for v in block):
                continue
            ss=next(i for i,v in enumerate(block) if v.startswith('switch i32 '))
            m=re.fullmatch(r'switch i32 (%\d+), label %(\d+) \[',block[ss])
            if not m:
                continue
            cond,end=m.groups()
            arms=[item[1] for v in block[ss+1:] if (item:=re.fullmatch(r'i32 [0-3], label %(\d+)',v))]
            if len(arms)!=4 or any(term(blocks,a)!=f'br label %{end}' or readnum(blocks.get(a,[]))==0 for a in arms):
                continue
            ordered=any('@dx.op.' in v and not re.search(r'@dx\.op\.(?:createHandleFromBinding|createHandleFromHeap|annotateHandle|rawBufferLoad\.i32)\(',v) for a in arms for v in blocks[a])
            reads=sum(readnum(blocks[a]) for a in arms)
            raw=select(d,cond,'i32')
            if raw and raw[2]=='4':
                exe,sel,_=raw
            else:
                exe,sel='true',cond
            shape=selector(d,sel)
            guard=(exe,*shape) if shape else None
        out.append({'pos':pos,'src':src,'end':end,'read_calls':reads,'guard':guard,'pred':cond,'has_nonread_effect':ordered})
    return out

def range_bits(d,x,search=()):
    # Each unknown leaf is truly unconstrained; phi cycles lose precision.
    if x in search or len(search)>20:
        return (0,M,0,0)
    c=cint(x)
    if c is not None:
        return (c,c,c,~c&M)
    expr=d.get(x,'')
    child=lambda y: range_bits(d,y,(*search,x))
    if expr.startswith('zext i1 '):
        return (0,1,0,~1&M)
    bb=binary(d,x,['and','or','xor','shl','lshr','add','sub','mul'])
    if bb:
        op,l,r=bb
        lmin,lmax,l1,l0=child(l)
        rmin,rmax,r1,r0=child(r)
        rcon=cint(r)
        if op=='and':
            above,beneath=l1&r1,l0|r0
        elif op=='or':
            above,beneath=l1|r1,l0&r0
        elif op=='xor':
            above,beneath=(l1&r0)|(l0&r1),(l1&r1)|(l0&r0)
        elif op=='lshr' and rcon is not None and rcon<32:
            return (lmin>>rcon,lmax>>rcon,l1>>rcon,(l0>>rcon)|((M<<(32-rcon))&M))
        elif op=='shl' and rcon is not None and rcon<32:
            above,beneath=(l1<<rcon)&M,((l0<<rcon)|((1<<rcon)-1))&M
        elif op=='add' and lmax+rmax<=M:
            return (lmin+rmin,lmax+rmax,0,0)
        elif op=='sub' and lmin>=rmax:
            return (lmin-rmax,lmax-rmin,0,0)
        elif op=='mul' and lmax*rmax<=M:
            return (lmin*rmin,lmax*rmax,0,0)
        else:
            return (0,M,0,0)
        return (above,M^beneath,above,beneath)
    sel=select(d,x,'i32')
    args=list(sel[1:]) if sel else re.findall(r'\[\s*('+V+r'),\s*%\d+\s*\]',expr) if expr.startswith('phi i32 ') else []
    if args:
        rs=[child(a) for a in args]
        ones=zeroes=M
        for _,_,o,z in rs:
            ones&=o
            zeroes&=z
        return min(i[0] for i in rs),max(i[1] for i in rs),ones,zeroes
    return (0,M,0,0)

def exists(lo,hi,ones,zeroes):
    @functools.lru_cache(None)
    def walk(pos,lt,gt):
        if pos<0:
            return True
        _,u,v,oo,zz=(1<<pos, (lo>>pos)&1,(hi>>pos)&1,(ones>>pos)&1,(zeroes>>pos)&1)
        for b in (0,1):
            if (b==0 and oo) or (b==1 and zz) or (not lt and b<v and not gt and b<u):
                continue
            if (not lt and b>v) or (not gt and b<u):
                continue
            if walk(pos-1,lt or b<v,gt or b>u):
                return True
        return False
    return lo<=hi and walk(31,False,False)

def possible(d,x,lo,hi,cache):
    mi,ma,ones,zeros=cache(x)
    return exists(max(mi,lo),min(ma,hi),ones,zeros)

doc = json.loads((D/'open-pixel-census-final/open-pixel.json').read_text())
for mode, pattern in [('heap','open-pixel-census-final/*/4w-off.ll'),('root','switch-census-final/*/off.ll')]:
    for p in sorted(D.glob(pattern)):
        d,b=parse(p)
        cache=functools.lru_cache(None)(lambda v: range_bits(d,v))
        rr=regions(d,b,mode)
        count=collections.Counter()
        by_start={x['src']:x for x in rr}
        per_lo=collections.Counter()
        this=[]
        count['generated_read_regions']+=len(rr)
        count['all_native_raw_calls']+=sum(readnum(x) for x in b.values())
        count['all_control_switches_or_branches']+=sum(v.startswith('switch i32 ' if mode=='root' else 'br i1 ') for x in b.values() for v in x)
        for x in rr:
            if x['has_nonread_effect']:
                count['nonmatching_ops_in_read_arm']+=1
            if not x['guard']:
                continue
            ex,hi,base,alias = x['guard']
            count['recognized_selector']+=1
            s=hi_shape(d,hi)
            if s is not None:
                count['hi_carry_or_borrow']+=1
                hib,low,op,k=s
                if hib=='0' and op=='carry':
                    count['high_bit_from_single_carry'] += 1
                    count['raw_calls_with_single_carry_high'] += x['read_calls']
                    count['load_ops_in_single_carry_high'] += x['read_calls'] // (4 if mode=='root' else 1)
                if hib=='0' and op=='borrow':
                    count['high_bit_neg_delta'] += 1
                kc=cint(k)
                if kc is not None:
                    count['constant_carry_or_borrow']+=1
                    per_lo[(hib,low,op)]+=1
                    always = not possible(d,low,MAX-kc,M,cache) if op=='carry' else not possible(d,low,0,kc-1,cache)
                    if always:
                        count['constant_delta_always_zero']+=1
            y=by_start.get(x['end'])
            if not y or x['has_nonread_effect'] or y['has_nonread_effect']:
                continue
            count['strict_adjacent_pure_pairs']+=1
            if x['pred']==y['pred']:
                count['strict_adjacent_equal_pred']+=1
            if not y['guard']:
                continue
            ey,hiy,basey,aliasy=y['guard']
            if ex!=ey or base!=basey or alias!=aliasy:
                continue
            count['strict_adjacent_equal_exec_base_alias']+=1
            sy=hi_shape(d,hiy)
            if s and sy and s[:3]==sy[:3]:
                count['strict_adjacent_same_carry_base']+=1
                hib,low,op,k=s
                ky=sy[3]
                k0,k1=cint(k),cint(ky)
                if k0 is None or k1 is None:
                    continue
                count['strict_adjacent_same_carry_base_const_offsets']+=1
                if hib=='0' and op=='carry':
                    count['strict_adjacent_from_zero_high'] += 1
                lowbound,highbound=sorted((k0,k1))
                div=(MAX-highbound,MAX-lowbound-1) if op=='carry' else (lowbound,highbound-1)
                if not possible(d,low,*div,cache):
                    count['strict_adjacent_carries_provably_equal']+=1
                this.append({"source_block":x['src'],"next_block":y['src'],"base_high":hib,"base_low":low,"type":op,"offsets":[k0,k1],"low_summary":cache(low),"between_offset_equivalence_proof":not possible(d,low,*div,cache)})
        count['nonadjacent_repeated_constant_groups']=sum(v>1 for v in per_lo.values())
        read_percent=count['generated_read_regions']/max(1,count['all_control_switches_or_branches'])
        DATA.append({'mode':mode,'id':p.parent.name, 'counters':dict(count), 'consecutive_same_carry_context':this})
        TOTAL.update({(mode,k):v for k,v in count.items()})
        KNOWN.update((mode,k) for k,v in count.items() if v)
print("TOTALS")
for (mode,key),v in sorted(TOTAL.items()):
    print(f"{mode:4} {key:48} {v:4} in {KNOWN[(mode,key)]} shaders")
print("NONZERO CASES")
for z in DATA:
    c=z['counters']
    if c.get('strict_adjacent_same_carry_base_const_offsets') or c.get('constant_delta_always_zero'):
        print(z['mode'],z['id'],c.get('strict_adjacent_same_carry_base_const_offsets'),c.get('strict_adjacent_carries_provably_equal',0),c.get('constant_delta_always_zero',0))
summary={'cases':DATA,'totals':[{ 'mode':mode, 'counter':key, 'count':v, 'shaders':KNOWN[(mode,key)]} for (mode,key),v in sorted(TOTAL.items())]}
(pathlib.Path.cwd()/'xcl-address-corpus-census.json').write_text(json.dumps(summary,indent=2)+'\n')
