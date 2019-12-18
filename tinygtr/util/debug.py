# open-source version of gtr.utl.debug

import traceback
import warnings

def make_python_warnings_show_stack_traces():
    def handler(message, category, filename, lineno, file=None):
        print(warnings.formatwarning(message, category, filename, lineno, line))        
        traceback.print_stack()
    warnings.showwarning=handler

def print_exc(src):
    print(src)
    traceback.print_exc()
    traceback.print_stack()
