"""Compile the prepared EX full ABC using the existing bounded AIR runner."""
import sys
import release_common as common
sys.modules['prepare'] = common
compiler = common.module('ex_release_air_compiler', common.HERE.parent/'ios-cumulative-login/compile_native.py')
if __name__ == '__main__': compiler.main()
