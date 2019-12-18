import argparse
import sys
import shutil
import os

import sarif_parser
import github_sarif_state

def import_inputs(args, default_dir):
    """Mock the importation of Sarif files and optionally confirm they match baselines
    
    Return 0 on success, non-zero on failure.
    """
    import difflib
    nimports = 0
    ndiffs = []
    nfailures = []
    if not args.inputs:
        print(ZERO_MESSAGE)
        return 1
    for f in args.inputs:
        ofp = None
        try:
            print("****** Importing '{0}' *******".format(f))
            # Each imported file gets its own CodeSonar state
            state = github_sarif_state.GithubSarifState()
            sarif_parser.process_sarif(f, state)
            for comment in state.comments:
                print("Comment %s" % repr(comment))
            nimports += 1
        except sarif_parser.SarifImporterException as e:
            print("Failed to import '{}': {}".format(f, e))
            nfailures.append(f)
        finally:
            pass
    print("*** {0} files imported".format(nimports))
    exit_code = 0
    if len(nfailures) > 0:
        print(FAILURE_MESSAGE.format(len(nfailures), nfailures))
        exit_code = 1
    if exit_code == 0:
        print("*** TEST SUCCESS")
    return exit_code

FAILURE_MESSAGE = """*** TEST FAILURE: {} unsuccessful import(s) for these inputs: 
      {}.
"""

ZERO_MESSAGE = """*** TEST FAILURE: zero tests were specified."""

DIFF_MESSAGE = """*** TEST FAILURE: {} outputs failed to match baselines for these inputs:
      {}
    If these differences are expected and correct, you can re-generate the baselines
    by running 'python test_sarif_importer.py -G samples/X.sarif' for the samples of interest.
    Be sure to check that the new baselines are correct before committing them.
"""

def mock_cso_import():
    '''Mock the importing of a SARIF file. This is use in a unit-test environment
    '''
    parser = argparse.ArgumentParser(description='Run the CodeSonar SARIF importer in a mock environment')
    parser.add_argument('inputs', nargs='*',
                        default=None,
                        help='The names of the SARIF files; all files with suffix ".sarif" are used otherwise')
    parser.add_argument('-c', '--check-baselines', action='store_true',
                        help="Check that the results match the baseline files in the directory given by the '-b' argument")
    parser.add_argument('-G', '--generate-baselines', action='store_true',
                        help="Generate baselines, overwriting the baseline files in the directory given by the '-b' argument")
    parser.add_argument('-b', '--baseline-directory', default='baselines',
                        help="The directory in which to find the baseline results")

    args = parser.parse_args()

    return_code = import_inputs(args, '.')
    sys.exit(return_code)

if __name__ == '__main__':
    mock_cso_import()
