import argparse
import sys
import shutil
import os

import sarif_parser
import plain_sarif_state

def import_inputs(args, default_dir, use_stdout=True):
    """Mock the importation of Sarif files
    
    Return 0 on success, non-zero on failure.
    """
    nimports = 0
    nfailures = []
    comments = []
    if not args.inputs:
        print(ZERO_MESSAGE)
        return 1
    for f in args.inputs:
        try:
            print("****** Importing '{0}' *******".format(f))
            # Each imported file gets its own CodeSonar state
            cso = plain_sarif_state.PlainSarifState()
            sarif_parser.process_sarif(f, cso)
            nimports += 1
            #comments.extend(cso.comments)
        except sarif_parser.SarifImporterException as e:
            print("Failed to import '{}': {}".format(f, e))
            nfailures.append(f)
    print("*** {0} files imported".format(nimports))
    exit_code = 0
    if len(nfailures) > 0:
        print(FAILURE_MESSAGE.format(len(nfailures), nfailures))
        exit_code = 1

    # Now print the comments
    #print("Comments:")
    #for c in comments:
    #    print(c)

    if exit_code == 0:
        print("*** TEST SUCCESS")
    return exit_code

FAILURE_MESSAGE = """*** TEST FAILURE: {} unsuccessful import(s) for these inputs: 
      {}.
"""

ZERO_MESSAGE = """*** TEST FAILURE: zero tests were specified."""

def mock_cso_import():
    '''Mock the importing of a SARIF file. This is used in a unit-test environment
    '''
    parser = argparse.ArgumentParser(description='Run the CodeSonar SARIF importer in a mock environment')
    parser.add_argument('-i','--inputs', nargs='+',
                        dest='inputs',
                        default=None,
                        help='The names of the SARIF files; all files with suffix ".sarif" are used otherwise')
    args = parser.parse_args()

    return_code = import_inputs(args, '.')
    sys.exit(return_code)

if __name__ == '__main__':
    mock_cso_import()
