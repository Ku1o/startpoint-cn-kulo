"""Use the bounded headless compiler with this task's pinned AOT input."""
import importlib.util
import prepare

spec=importlib.util.spec_from_file_location('bounded_compiler',prepare.HERE.parent/'ios-cumulative-login/compile_native.py')
compiler=importlib.util.module_from_spec(spec);spec.loader.exec_module(compiler)
if __name__=='__main__':compiler.main()
