"""Compile the two account methods and shared record writer for arm64."""
import importlib.util
import prepare
spec=importlib.util.spec_from_file_location('ios_record_bounded_compiler',prepare.HERE.parent/'ios-cumulative-login/compile_native.py')
compiler=importlib.util.module_from_spec(spec);spec.loader.exec_module(compiler)
if __name__=='__main__':compiler.main()
