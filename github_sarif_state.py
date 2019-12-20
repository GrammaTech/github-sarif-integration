# The Github-specific SarifState

import sarif_filenames

from sarif_state import SarifState
from sarif_parser import sarif_assert
from sarif_parser import unhandled_warning
from sarif_parser import is_legacy_version

from comment import Comment
from comment import PositionalComment

class GithubSarifState(SarifState):
    def __init__(self):
        super(GithubSarifState, self).__init__()

        self.comments = []

        self.reset_for_run()

    def reset_for_run(self):
        self.sarif_run = SarifRun()

    def original_uri_base_id_add(self, uri, uriBaseId, key):
        self.sarif_run.originalUriBaseIdMap[key] = (uri, uriBaseId)

    def resources_object_member_end(self, parser, key):
        if key == "messageStrings":
            self.sarif_run.messageStrings = self.parser.estack[-1].value

    def rules_v1_object_member_end(self, parser, key):
        rule = parser.estack[-1]
        self.sarif_run.add_new_warning_class(rule)

    def rules_item_array_element_end(self, parser, idx):
        rule = self.parser.estack[-1]
        self.sarif_run.add_new_warning_class(rule)

    def run_object_member_end(self, tool_name, message_strings):
        if self.ppass == 1:
            self.sarif_run.tool = tool_name
            self.sarif_run.messageStrings = message_strings

    def run_object_start(self, parser):
        '''Clear out any state that might remain from a previous run'''
        if self.ppass == 1:
            self.reset_for_run()

    def results_item_array_element_end(self, parser, idx):
        # This is a good time to issue the warning
        sarif_result_to_cso_warning(self, parser.version, parser.estack[-1])

    def file_item_add(self, file_item):
        self.sarif_run.files.append(file_item)

class warning_significance(object):
    UNSPECIFIED = 0
    DIAGNOSTIC = 1
    FROM_MANIFEST = 2
    RELIABILITY = 4
    REDUNDANCY = 8
    SECURITY = 16
    STYLE = 32

class WarningClass(object):
    significance_map = {
        warning_significance.UNSPECIFIED:'Unspecified',
        warning_significance.DIAGNOSTIC:'Diagnistic',
        warning_significance.FROM_MANIFEST:'From Manifest',
        warning_significance.RELIABILITY:'Reliability',
        warning_significance.REDUNDANCY:'Redundancy',
        warning_significance.SECURITY:'Security',
        warning_significance.STYLE:'Style',}

    def __init__(self, rule_id, name, rank, categories, significance, short_description=None, long_description=None, help_uri=None, help=None,
                 message_strings = {}):
        self.wc = None
        self.rule_id = rule_id
        self.rank = rank
        self.name = name
        self.categories = categories
        self.significance = significance
        self.short_description = short_description
        self.long_description = long_description
        self.help_uri = help_uri
        self.help = help
        self.message_strings = message_strings

    @staticmethod
    def make_warning_class(rule, tool):
        sarif_assert(rule.id != None, "Rule object does not specify a ruleId")
        id = rule.id.encode('utf-8')
        name = rule.name
        if name is None:
            name = id
        name = name.encode('utf-8')
        significance = extract_significance(rule.properties, tool, warning_significance.RELIABILITY)
        rule.defaultRank = extract_rank(rule.properties, tool, rule.rank)
        rank = mk_rank(None, rule.defaultRank, rule.level)
        categories = augment_categories(rule.properties, [])
        warning_class = WarningClass(rule.id, name, rank, categories, significance,
                                     rule.shortDescription, rule.fullDescription,
                                     rule.helpUri, rule.help, rule.messageStrings)
        return warning_class

    def augment_warning_class_from_result(self, state, result):
        '''Some Sarif producers put information about the warning class in with
        the result, instead of with the rule. This method allows us to add that
        information before the actual CodeSonar warning class is created.
        '''
        self.categories = augment_categories(result.properties, self.categories)
        self.significance = extract_significance(result.properties,
                                                 state.sarif_run.tool,
                                                 self.significance)
        sarif_rank = extract_rank(result.properties, state.sarif_run.tool, None)
        if sarif_rank is not None:
            self.rank = mk_rank(sarif_rank, None, result.level)

    def get_messagestring(self, key, sarif_run):
        result = self.message_strings.get(key)
        if result is not None:
            return result
        return sarif_run.messageStrings.get(key)

    # Some Sarif files do not specify all the necessary information in the
    # rule object, but instead have it present at the result. This can include
    # information such as the significance and the score. Consequently
    # it is necessary to create the warning classes lazily.
    def report(self, state, closure):
        if self.wc is None:
            self.create_wc(state.sarif_run)
        state.report_warning(closure)

    def get_significancestring(self):
        return self.significance_map[self.significance]

    def create_wc(self, sarif_run):
        category = "{}.{}".format("Tool" if sarif_run.tool is None else sarif_run.tool, self.rule_id)
        self.categories = [category] + self.categories
        categories_str = ";".join(self.categories).encode('utf-8')

class SarifRun(object):
    """Information specific to a single run is maintained here.
    """
    def __init__(self):
        # originalUriBaseIdMap: a map of string to pairs of (uri, uriBaseId)
        # e.g: { 'SRCROOT': ('file:///C:/one/two/', None),
        #        'INC': ('include/', 'SRCROOT')}
        self.originalUriBaseIdMap = {}
        self.files = []
        # Warning classes are stored in this array
        self.wcs = []
        # Maintain a map from ruleId to the index into self.wcs.
        self.wcs_map = {}
        self.tool = None
        self.messageStrings = {}

    def add_new_warning_class(self, rule):
        self.add_warning_class(WarningClass.make_warning_class(rule, self.tool))

    def add_warning_class(self, warning_class):
        self.wcs_map[warning_class.rule_id] = len(self.wcs)
        self.wcs.append(warning_class)

##### GITHUB-SPECIFIC FUNCTIONS

def codeflows_to_locations(cso, codeFlows):
    """Take a list of codeFlows and convert it to a list of locations_nodes
    """
    version = cso.parser.version
    locations = []
    if not codeFlows:
        return []
    if len(codeFlows) > 1:
        unhandled_warning("codeFlows property has more than one item. Only the first will be shown.")
    for threadflow in codeFlows[0].threadFlows:
        for tfl in threadflow.locations:
            if tfl.location is None:
                unhandled_warning("codeFlow object has no location")
                continue
            coords = location_to_coords(cso, version, tfl.location)
            if coords is None:
                continue
            (endbox_sf, region) = coords
            if endbox_sf is None:
                continue
            message = tfl.location.message
            if message is None:
                message = ""
            locations.append({"file":endbox_sf,"region":region,
                              "message":to_reml(message)})
    return locations

def mk_locations_node(sfi, region, message, flags=None):
    if region[0] == region[1] and region[3] is None:
        lnode = cs.locations_node(sfi, region[0], message, flags)
    else:
        if region[3] is None:
            region[3] = 1000
        lnode = cs.locations_node(sfi, region[0], region[1], region[2], region[3], message, flags)
    return lnode

def extract_rank(properties, tool, default):
    '''Extract a rank value from a property bag associated with a result.

    This returns the default value if nothing in the property bag is relevant
    '''
    if properties is None:
        return default
    if tool[:5] == 'Julia':
        return julia_rank(properties, default)
    return default

def julia_rank(properties, default):
    '''Return a Sarif rank, which is a number in the range 0.0 .. 100.0.
    '''
    rank = properties.get("rank")
    if rank is None:
        return default
    # These choices yield scores of 24, 52, 67, and 73
    ldict = {'minor': 40.0, 'major': 55.0, 'error': 70.0, 'critical': 95.0}
    return ldict.get(rank.lower(), 55.0)

def extract_significance(properties, tool, default):
    """Extract a significance value from the property bag associated with a rule

    A property bag that is recognized by CodeSonar will be something like:
      "CodeSonar": {
          "significance": "security"
      }

    Other tools encode significance in different ways.
    """
    if properties is None:
        return default
    significance = codesonar_significance(properties)
    if significance is not None:
        return significance
    if tool[:5] == "Julia":
        return julia_significance(properties, default)
    return default

def julia_significance(properties, default):
    """With Julia, there are property bags associated with results that may
    have entries like { "category": "Efficiency" }
    """
    cat = properties.get("category")
    if cat is None:
        return default
    sdict = {
        'Bug': warning_significance.RELIABILITY,
        'Style': warning_significance.STYLE,
        'Efficiency': warning_significance.REDUNDANCY
    }
    return sdict.get(cat, default)

def codesonar_significance(properties):
    csobag = properties.get("CodeSonar")
    if csobag is None:
        return None
    sdict = {
        'reliability': warning_significance.RELIABILITY,
        'diagnostic': warning_significance.DIAGNOSTIC,
        'from_manifest': warning_significance.FROM_MANIFEST,
        'redundancy': warning_significance.REDUNDANCY,
        'security': warning_significance.SECURITY,
        'style': warning_significance.STYLE,
        'unspecified': warning_significance.UNSPECIFIED
    }
    return sdict.get(csobag.get('significance'), warning_significance.RELIABILITY)

def augment_categories(properties, categories):
    """Extract a list of categories from a Sarif property bag

    Add to the categories passed in and return that.
    """
    if properties is None:
        return categories
    cwe = properties.get("CWEid")
    if cwe is not None:
        item = "CWE:{}".format(cwe)
        if item not in categories:
            categories.append(item)
    return categories

# BUG: It ought to be possible to escape a string that contains double quotes,
# but after 20 minutes, I failed to find an incantation that worked.
# gtr.xmlencode('"') -> '&aquot;', which is as expected, but by the time
# it gets interpreted on the hub, that has been decoded back to a double
# quote, which yields incorrect ReML. The temporary fix is to just replace
# with a single quote.
def to_reml(str):
    return str.replace('"',"'")

def addComment(state, comment):
    state.comments.append(comment)

def sarif_result_to_cso_warning(state, version, result):
    """Report a CodeSonar warning

    The specific warning report will depend on the contents of the sarif
    result as follows:

    The locations list is expected to be a singleton. This will form the
    endbox of the CodeSonar warning.

    If the list of related code locations is empty, then report using one
    of the following options, expressed in terms of the arguments to the report
    function:
     - at a code location: first three arguments are sfileinst, int, str
     - at a code span in a specified file instance: first five arguments are sfileinst, int, int, int, int

    If there are related locations or code flows:
     - with a list of code locations: first argument is a list of locations_node

    If there are no locations:
     - associated with a file instance first argument is sfileinst
     - with no association to a file or procedure there are no location arguments
    """
    sarif_assert(not (result.ruleId is None and result.ruleIndex == -1), "Neither of ruleId or ruleIndex are specified")
    sarif_assert(not (result.message is not None and result.messageId is not None), "Neither of message or messageId are specified")

    locations = result.locations
    relatedLocations = result.relatedLocations
    codeFlows = result.codeFlows
    properties = result.properties
    hostedViewerUri = result.hostedViewerUri
    if result.ruleIndex != -1:
        warning_class = state.sarif_run.wcs[result.ruleIndex]
    else:
        # We have to create a new warning class. There's not much to go on here
        # The warning class may already have been encountered, so look it up
        # first.
        ruleId = result.ruleId.encode('utf-8')
        warning_class_index = state.sarif_run.wcs_map.get(ruleId)
        if warning_class_index is not None:
            # It's been encountered before. Use that.
            warning_class = state.sarif_run.wcs[warning_class_index]
        else:
            # Create a new one and put it in the table with the run
            warning_class = WarningClass(
                ruleId,
                ruleId,
                mk_rank(result.rank, None, result.level),
                [],
                warning_significance.RELIABILITY)
            state.sarif_run.add_warning_class(warning_class)

    warning_class.augment_warning_class_from_result(state, result)

    if result.message is not None:
        warning_message = result.message
    else:
        warning_message = warning_class.get_messagestring(result.messageId, state.sarif_run)
        if warning_message is None:
            unhandled_warning("Could not find a messageStrings entry for key '{}' for rule '{}'".format(result.messageId, warning_class.name))
            warning_message = "None"

#    warning_message = warning_class.get_significancestring() + ': ' + warning_class.name + ': '+ warning_message

    message = to_reml(warning_message)
    if len(locations) == 0:
        unhandled_warning("locations list is empty")
        return
    if len(locations) > 1:
        unhandled_warning("locations list is not a singleton; only the first location will be shown as the endbox in the CodeSonar warning")
    coords = location_to_coords(state, version, locations[0])
    if coords is None:
        return
    (endbox_sf, region) = coords
    # No source file at all? Report at project level
    if endbox_sf is None:
        addComment(state, Comment(message, warning_class.rank, warning_class.name, warning_class.get_significancestring(), hostedViewerUri))
        return
    # If no region is available just report it at the file level
    if region is None:
        addComment(state, PositionalComment(message, warning_class.rank, warning_class.name, warning_class.get_significancestring(), hostedViewerUri, endbox_sf, 1))
        return
    extra_locations = codeflows_to_locations(state, codeFlows)
    # If there are no other locations, then we can report the warning at the given region
    if len(extra_locations) == 0:
        # Precondition: we know that region[0] is not None
        # If the endColumn is not specified and if the startLine is the same
        # as the endLine, just report this as a single line warning
        if region[0] == region[1] and region[3] is None:
            addComment(state, PositionalComment(message, warning_class.rank, warning_class.name, warning_class.get_significancestring(), hostedViewerUri, endbox_sf, region[0]))
            return
        # if the endColumn is None, then max it out to 1000. TODO: is this OK?
        if region[3] is None:
            addComment(state, PositionalComment(message, warning_class.rank, warning_class.name, warning_class.get_significancestring(), hostedViewerUri, endbox_sf, region[0]))
        return
    # If we get to here, then we have vector of locations nodes
    # And we have to report the warning at all locations
    if len(extra_locations) > 0:
        addComment(state, PositionalComment(message, warning_class.rank, warning_class.name, warning_class.get_significancestring(), hostedViewerUri, endbox_sf, region[0]))
# keeping this around instead of just deleting it because
# turning it on tests the size-limiting feature
#        for x in extra_locations:
#            addComment(cso, PositionalComment(x["message"], x["file"], x["region"][0]))

def location_to_coords(state, version, location):
    """Return a pair consisting of the sfile embedded within the LocationHandler instance, and the coordinates
    """
    if location.physicalLocation is None:
        unhandled_warning("location does not specify a physicalLocation")
        return None
    fileLoc = location.physicalLocation.fileLocation
    if fileLoc is None:
        unhandled_warning("physicalLocation does not specify a fileLocation")
        return None
    if is_legacy_version(version):
        fileIndex = fileLoc.fileIndex
    else:
        fileIndex = fileLoc.index
    if fileIndex != -1 and fileIndex is not None:
        fileLoc = state.sarif_run.files[fileIndex]
    if fileLoc.uri is None:
        unhandled_warning("fileLocation does not specify a uri")
        return None
    fname = sarif_filenames.resolve_file_location((fileLoc.uri, fileLoc.uriBaseId), state.sarif_run.originalUriBaseIdMap)
    if fname is None:
        unhandled_warning("could not resolve file with uri '{}' and uriBaseId '{}'".format(fileLoc.uri, fileLoc.uriBaseId))
        return None
    # Note that the normalization may not be able to normalize the file. In that case, just try the original name instead.
    # Although the file is unlikely to be found in a "real" program model, it might be in a mock one.
#    fname = sarif_filenames.normalize_filename(fname, cso.sarif_state.original_dir, default=fname)
#    sfile = cso.sfiles.get(fname)

    region = location.physicalLocation.region
    if region is None:
        return (fname, None)
    for fldname in ["charOffset", "charLength", "byteOffset", "byteLength"]:
        if region.__dict__[fldname] is not None:
            unhandled_warning("region.{} is specified, but not currently handled".format(fldname))
    if region.startLine is None:
        unhandled_warning("region.startLine is not specified")
        return (fname, None)
    # Set the defaults according to the standard
    if region.startColumn is None:
        region.startColumn = 1
    if region.endLine is None:
        region.endLine = region.startLine
    # The default is for region.endColumn is expected to be the last column on the given line,
    # but this is not possible to know unless we look at the file contents, which is odious.
    return (fname, (region.startLine, region.endLine, region.startColumn, region.endColumn))


def mk_rank(rank, default_rank, level):
    """Create a rank from a result rank, a default rank, and a level

    level can be one of: "pass", "warning", "error", "open", "notApplicable", or "note".
    These don't correspond very well to traditional scoring, but they're all we've got.

    Note that the Sarif "rank" is a float in the range 0.0..100.0, where larger
    values mean higher severity, whereas the CodeSonar notion of rank is the opposite.
    Also, the CodeSonar rank is heavily skewed. For example:
      base_rank  score
       0.0        73
       0.1        73
       0.5        72
       1.0        71
       2.0        69
       4.0        65
       8.0        55
      16.0        35
      32.0        10
      50.0         2
      80.0         0
    Consequently we must transform the Sarif rank to get the CodeSonar base rank.
    Note that we need to truncate the precision of this number, otherwise we risk
    returning different values on different platforms. Two digits after the
    decimal should be adequate.
    """
    def sarif_rank_to_cso_rank(rank):
        r = (100.0-rank)/100.0
        return (100.0*r*r*r)
    if rank is not None:
        return sarif_rank_to_cso_rank(rank)
    if default_rank is not None:
        return sarif_rank_to_cso_rank(default_rank)
    ldict = {None: 10.0, 'note': 16.0, 'warning': 8.0, 'error': 1.0}
    return ldict.get(level, 32.0)
