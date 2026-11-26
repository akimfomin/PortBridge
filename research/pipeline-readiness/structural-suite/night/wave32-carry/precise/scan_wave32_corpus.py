# SPDX-License-Identifier: MIT
"""Replay licensed inputs in an explicit Wave32 PAL pipeline; compare both HLSL emitters."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def ballot_sites(hlsl):
    sites = {}
    pc = None
    for line in hlsl.splitlines():
        head = re.search(r"//\s+([0-9a-f]+): (.*)$", line)
        if head:
            pc = (int(head[1], 16), head[2])
        ballot = re.search(r"\buint2 \w+ = (ballot_px(?:_quad|_local)?)\(", line)
        if ballot and pc is not None:
            sites.setdefault(pc, []).append(ballot[1])
    return sites

def run(args, **kwargs):
    return subprocess.run(args, capture_output=True, timeout=45, check=True, **kwargs)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('manifest','llpc','readobj','tools','stock','fixed','out'):
        p.add_argument('--'+arg, type=lambda s:Path(s).resolve(), required=True)
    a=p.parse_args()
    sys.path.insert(0,str(a.tools))
    from open_pixel_census import pixel_code, ps_config, LLPC
    assert digest(a.llpc) == LLPC
    source=json.loads(a.manifest.read_bytes())
    a.out.mkdir(parents=True,exist_ok=False)
    rows=[]
    for idx, inp in enumerate(source['observations']):
        row={k:inp[k] for k in ('group','source','entry','source_sha256')}
        row['index']=idx; rows.append(row)
        if not inp.get('rdna') or inp.get('error'):
            row['exclusion']='source manifest: '+str(inp.get('error'))
            continue
        spv=a.manifest.parent/f'{idx:03d}'/'source.spv'
        wanted = inp.get('spirv_sha256') or inp.get('spirv',{}).get('sha256')
        if not spv.exists() or not wanted or digest(spv)!=wanted:
            row['exclusion']='validated SPIR-V unavailable'
            continue
        case=a.out/f'{idx:03d}'; case.mkdir()
        elf=case/'wave32.elf'; dump=case/'pipeline'; code=case/'shader.rdna2'
        cfg=[a.llpc,'--gfxip=10.3.0','--filetype=obj','--shader-cache-mode=0']
        try:
            run([*cfg,'--auto-layout-desc','--enable-pipeline-dump',f'--pipeline-dump-dir={dump}','-o',elf,f'{spv},{inp["entry"]}'])
            original,=dump.glob('*.pipe'); other=dump/'wave32.pipe'
            txt,n=re.subn(r'(?m)^options\.waveSize = 0$', 'options.waveSize = 32',original.read_text(encoding='utf-8'))
            if n!=1: raise ValueError('Expected exactly one standalone fragment option')
            other.write_text(txt,encoding='utf-8')
            run([*cfg,'-o',elf,other])
            notes=run([a.readobj,'--notes',elf]).stdout.decode('utf-8')
            meta=ps_config(notes); assert meta['wave']==32
            code.write_bytes(pixel_code(elf.read_bytes()))
            row['guest_sha256']=digest(code); row['abi']=meta
            args=[str(meta[k]) for k in ('wave','spi_ps_input_ena','interpolants','color_mask','depth_mode')]
            anns=[]
            for arm in ('stock','fixed'):
                hlsl=case/(arm+'.hlsl')
                run([getattr(a,arm),code,hlsl,*args,'root-4','generic','hlsl'])
                text=hlsl.read_text(encoding='utf-8'); sites=ballot_sites(text); anns.append(sites)
                row[arm]={'hlsl_sha256':digest(hlsl),'calls':dict(Counter(v for values in sites.values() for v in values))}
            if set(anns[0])!=set(anns[1]): raise ValueError('Different recorded ballot source PCs')
            row['changed_sites']=[{'pc':pc,'assembly':ins,'stock':anns[0][pc,ins],'fixed':anns[1][pc,ins]} for pc,ins in anns[0] if anns[0][pc,ins]!=anns[1][pc,ins]]
        except (subprocess.SubprocessError, ValueError, AssertionError, OSError) as ex:
            row['exclusion']=(getattr(ex,'stderr',b'') or str(ex).encode())[:350].decode('utf-8',errors='replace')
        with (a.out/'progress.jsonl').open('a',encoding='utf-8') as out: out.write(json.dumps(row)+'\n')
    valid=[r for r in rows if 'changed_sites' in r]
    result={'source_manifest_sha256':digest(a.manifest),'source':source.get('source',source.get('sources')),'llpc_sha256':LLPC,
            'xcl_stock':'e1d84b7d9153f86a97d2ec5d209d196046fc0bea','xcl_fixed':'ca5b5daa6e07b3488993840d9aec46ccafde0f36',
            'matched':len(valid),'changed_programs':sum(bool(r['changed_sites']) for r in valid),'changed_sites':sum(len(r['changed_sites']) for r in valid),'rows':rows}
    (a.out/'results.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print({k:result[k] for k in ('matched','changed_programs','changed_sites')})

if __name__=='__main__': main()
