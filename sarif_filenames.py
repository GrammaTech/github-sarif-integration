'''Sarif Filenames interface

Sarif and CodeSonar have different ways to refer to files. In CodeSonar
given a cs.sfile sf, sf.normalized_name() yields something like:
  c:/cygwin/home/paul/sarif/hello/hello.c
whereas sf.name() gives:
  C:\cygwin\home\paul\Sarif\hello\hello.c
In Sarif, the same files might be:
file:///C:/cygwin/home/paul/Sarif/hello/hello.c, or plain old
hello.c, or a uri "hello.c" with a uriBaseId "SRCROOT"
where SRCROOT is given in a uriBaseIdMap. Note that the relative reference is
with respect to the location of the top-level sarif file.

The purpose of the following code is to convert SARIF file names to
the CodeSonar form so that they can be looked up by name.
'''

import re
import os

uriAbsoluteRe = re.compile(r"^(/|([a-z]([a-z0-9\+\-\.]*):))", re.IGNORECASE)
def uriIsAbsolute(uri):
    """Return True if the uri is absolute, #f otherwise
    """
    match = uriAbsoluteRe.match(uri)
    return match is not None

def resolve_file_location(fileLoc, originalUriBaseIdMap):
    """Resolve a file location with respect to base ID map

    The fileLoc is a pair of uri, uriBaseId
    """
    (uri, uriBaseId) = fileLoc
    if uriBaseId is None or uriIsAbsolute(uri):
        return uri
    resolution = resolve_uri_baseid(uriBaseId, originalUriBaseIdMap)
    if resolution is None:
        return None
    return resolution + uri

def resolve_uri_baseid(uriBaseId, originalUriBaseIdMap):
    """Resolve a uriBaseId to an absolute reference

    This closely follows the algorithm given in the SARIF specification in the section
    describing run.originalUriBaseIds.  The steps refer to the steps therein.
    """
    # Step 1
    resolvedUri = ''
    visitedUriBaseIds = []
    while True:
        # Step 2
        fileLoc = originalUriBaseIdMap.get(uriBaseId)
        if fileLoc is None:
            print("Failed to find '{0}' in originalUriBaseId".format(uriBaseId))
            return None
        # Step 3
        resolvedUri = fileLoc[0] + resolvedUri
        # Step 4
        if uriIsAbsolute(resolvedUri):
            return resolvedUri
        # Step 5
        if uriBaseId is None:
            return None
        # Step 6
        if uriBaseId in visitedUriBaseIds:
            return None
        visitedUriBaseIds.append(uriBaseId)
        # Step 7
        uriBaseId = fileLoc[1]


driveSpecRe = re.compile("^/([A-Z]):", re.IGNORECASE)
def normalize_filename(fname, original_dir, default=None):
    """Normalize a file so that it matches the CodeSonar cs.sfile.normalized_name()

    Return the default value if it can't be normalized.
    Examples:
       'file:///C:/one' => 'c:/one'
       'file:///tmp/bob.c' => '/tmp/bob.c'
    Here is something we don't handle right now:
       'file://xyz.com/one/two/three' => default
    """
    if not fname.lower().startswith('file://'):
        # It must be a relative name, resolve wrt its origin
        result = os.path.realpath(os.path.join(original_dir, fname)).lower()
    else:
        result = fname[7:]
        if result.lower().startswith('localhost'):
            result = result[9:]
        if result[0] != '/':
            return default
        match = driveSpecRe.match(result)
        if match is not None:
            # It was something like '/C:/one/two'
            result = result[1:]
        # else it was already a unix-style pathname
    # Finally, replace backslashes with slashes
    result = re.sub(r"\\", "/", result)
    return result.lower()

def test_resolution_and_normalization():
    """Call this to test that the resolution and normalization works
    """
    # This is a map of strings to pairs, where the first item of the pair is
    # the uri, and the second is a uriBaseId. The second can be None.
    originalUriBaseIdMap = {
        'SRCROOT': ('file:///c:/browser/src/', None),
        'INCLUDE': ('include/', 'SRCROOT'),
        'EDITOR': ('editor/', 'SRCROOT'),
        'BUFFERS': ('buffers/', 'EDITOR'),
        'TMPDIR': ('FILE:///tmp/', None)
    }
    def check_resolve(fileLoc, answer):
        result = resolve_file_location(fileLoc, originalUriBaseIdMap)
        if result == answer:
            print("RESOLUTION OK: '{0}".format(answer))
        else:
            print("RESOLUTION FAIL: got '{0}', expected '{1}'".format(result, answer))

    check_resolve(('scratch/foo.c', 'TMPDIR'), 'FILE:///tmp/scratch/foo.c')
    check_resolve(('ui/window.cpp', 'EDITOR'), 'file:///c:/browser/src/editor/ui/window.cpp')
    check_resolve(('file:///c:/My Documents/', None), 'file:///c:/My Documents/')
    check_resolve(('buffers.c', 'BUFFERS'), 'file:///c:/browser/src/editor/buffers/buffers.c')

    def check_normalization(fileLoc, answer):
        fname = resolve_file_location(fileLoc, originalUriBaseIdMap)
        if fname is None:
            print("RES FAIL: got '{0}', expected '{1}'".format(fname, answer))
            return
        result = normalize_filename(fname, '.')
        if result == answer:
            print("NORMALIZATION OK: '{0}".format(answer))
        else:
            print("NORMALIZATION FAIL: got '{0}', expected '{1}'".format(result, answer))


    check_normalization(('scratch/foo.c', 'TMPDIR'), '/tmp/scratch/foo.c')
    check_normalization(('ui/window.cpp', 'EDITOR'), 'c:/browser/src/editor/ui/window.cpp')
    check_normalization(('file:///c:/My Documents/', None), 'c:/my documents/')
    check_normalization(('buffers.c', 'BUFFERS'), 'c:/browser/src/editor/buffers/buffers.c')
    check_normalization(('file://localhost/u1/buffers.c', None), '/u1/buffers.c')

if __name__ == '__main__':
    test_resolution_and_normalization()