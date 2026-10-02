"""Headless, bounded AIR arm64 compilation for the pinned public port."""
import sys
from common import HERE, WORK, load

def main():
    sys.path.insert(0,str(HERE.parent/'ios-cumulative-login'))
    import prepare
    prepare.WORK=WORK/'ios'
    compiler=load('author_compile_native',HERE.parent/'ios-cumulative-login/compile_native.py')
    compiler.WORK=WORK/'ios'
    sys.argv=['compile_native','--attempt',sys.argv[1] if len(sys.argv)>1 else 'compile-final','--optimization','1']
    compiler.main()

if __name__=='__main__':main()
