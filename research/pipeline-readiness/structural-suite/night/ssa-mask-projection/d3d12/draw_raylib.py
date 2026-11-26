# SPDX-License-Identifier: MIT
"""Run already-validated direct pixel variants with a pinned open raylib scene."""
import argparse,hashlib, json,os, re,subprocess,time
from pathlib import Path
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('guard','renderer','dxc_dir','corpus','scene_root','out'):
        p.add_argument('--'+k.replace('_','-'), type=lambda a:Path(a).resolve(),required=True)
    p.add_argument('--rounds',type=int,choices=range(1,6),default=2)
    a=p.parse_args(); a.out.mkdir(parents=True,exist_ok=True)
    for block in range(a.rounds):
        for view in (('primary','secondary') if block%2==0 else ('secondary','primary')):
            source=a.scene_root/f'ray800-{view}'; meta=json.loads((source/'scene.json').read_bytes())
            sg=source/'sgprs.bin'; assert digest(sg)==meta['sgprs_sha256']
            for arm in (('whole','project') if (block+(view=='secondary'))%2==0 else ('project','whole')):
                tag=f'{block:02}-{view}-{arm}'
                rec=a.out/(tag+'.json')
                if rec.exists() and json.loads(rec.read_bytes()).get('complete'): continue
                log=a.out/(tag+f'-{time.time_ns()}.log'); raw=a.out/(tag+'.rgba32f')
                ps=a.corpus/'raylib-procedural'/'000'/(arm+'.dxil')
                env={k:v for k,v in os.environ.items() if not k.startswith(('XCL_','PB_SCENE_'))}
                env.update(XCL_DXC_DIR=str(a.dxc_dir),PB_SCENE_PS=str(ps),PB_SCENE_IMAGE=str(raw),PB_SCENE_SGPRS=str(sg),PB_SCENE_SIZE='800',PB_SCENE_HEIGHT='450',XCL_READ_GUARD_TEST_ROOT_WINDOWS='1',XCL_READ_GUARD_TEST_GPU_DRAWS='8')
                run=subprocess.run([a.guard,a.renderer,log,'gpu::dxil::aperture_tests::open_procedural_pixel_draw','--512-mib'],env=env,capture_output=True,timeout=40)
                result={'arm':arm,'view':view,'block':block,'complete':False,'process':(run.stdout+run.stderr).decode(errors='replace').strip(),'guard_exit':run.returncode,'log':log.name,'dxil_sha256':digest(ps),'guest_sgpr_sha256':digest(sg),'controls':meta['controls']}
                if run.returncode==0 and log.exists():
                    txt=log.read_text(encoding='utf-8',errors='replace')
                    assert '1 passed; 0 failed' in txt and 'SKIPPED' not in txt and 'NVIDIA GeForce RTX 4070 Ti SUPER' in txt
                    assert raw.stat().st_size==800*450*16
                    result['raw_sha256']=digest(raw)
                    result['native_create_ms']=float(re.search(r'native_create_ms=([\d.]+)',txt)[1])
                    result['gpu_ms_per_draw']=float(re.search(r'gpu_ms_per_draw=([\d.]+)',txt)[1])
                    result['setup_submit_readback_ms']=float(re.search(r'scene_native_setup_submit_readback_ms=([\d.]+)',txt)[1])
                    result['complete']=True
                rec.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
                print(tag,result['complete'],result.get('gpu_ms_per_draw'),result['process'],flush=True)
                if not result['complete']: raise SystemExit(2)
if __name__=='__main__':main()
