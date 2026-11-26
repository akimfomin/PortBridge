"""Admit the one measured subgroup-sweep module to the existing checked NeRF fixture."""
import hashlib
import importlib.util
from pathlib import Path
import sys

SOURCE="1840c78e34583895860ddaf3029c28432106c29ff1265e4e6f3d3644709343d6"
BOUNDED="08add5ab2950ef52b92c98c606f7ef0c9674687904472e819e6564e74b711b28"

def main():
    if len(sys.argv)!=6:
        raise SystemExit("prepare_nerf_draw.py PREPARE_TRANSLATED.py SOURCE.spv OUTPUT.spv --tools SPIRV_TOOLS_DIR")
    script=Path(sys.argv.pop(1)).resolve()
    src,dst=map(Path,sys.argv[1:3])
    if hashlib.sha256(src.read_bytes()).hexdigest()!=SOURCE:
        raise ValueError("Unrecognized NeRF shader")
    spec=importlib.util.spec_from_file_location("nerf_fixture",script)
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.FRAGMENTS[SOURCE]="nerf71-unused-collectives"
    sys.argv.append("--diagnostics")
    m.main()
    if hashlib.sha256(dst.read_bytes()).hexdigest()!=BOUNDED:
        raise ValueError("Bounded module does not match the tested one")

if __name__=="__main__":
    main()
