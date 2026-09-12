"""Compile the bounded, pinned iOS record/name delta."""
import importlib.util
import prepare
spec=importlib.util.spec_from_file_location('bounded_compiler',prepare.HERE.parent/'ios-cumulative-login/compile_native.py')
compiler=importlib.util.module_from_spec(spec);spec.loader.exec_module(compiler)
if __name__=='__main__':compiler.main()
