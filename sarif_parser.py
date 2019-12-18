# The application agnostic version.
# For now, assumes the gtr json parser...

import os
import re
import sys

# We'll still need the alternate parser at some time.
try:
    import gtr
except:
    import tinygtr as gtr

__doc__='''
'''

class SarifImporterException(Exception):
    '''Generic exception triggered when the SARIF is not what is expected
    '''
    def __init__(self, value):
        super(SarifImporterException, self).__init__()
        self.parameter = value
    def __str__(self):
        return repr(self.parameter)

class SarifVersionDone(Exception):
    '''Version string found, so throw this to terminate further potentially costly parsing
    '''
    pass

class SarifVersionExtractor(gtr.AbstractJsonParser):
    '''Special class that just extracts the version number
    '''
    def __init__(self):
        super(SarifVersionExtractor, self).__init__()
        self.version = None
        self.version_seen = False
        self.depth = 0
    def object_start(self):
        self.depth += 1
    def object_end(self):
        self.depth -= 1
    def object_member_start(self, key):
        # The version string of the file appears at the top level.
        # There is tool.version too, and maybe other "version" properties,
        # so ignore those.
        if key == "version" and self.depth == 1:
            self.version_seen = True
    def string_value(self, str):
        if self.version_seen is True:
            self.version = str
            raise SarifVersionDone()

def check_support_for_version(version):
    '''Check that the version is one that is supported.

    The versions are a tuple of integers; e.g.: (2,1,5) indicating
    major, minor, patch.
    '''
    if (version == (2,0,0) or
        version == (2,1,0)):
        return
    raise SarifImporterException("Unsupported SARIF version: {0}".format(version))

# Error handling

def sarif_assert(condition, msg):
    """Report a sarif error if the condition is not satisfied
    """
    if not condition:
        raise SarifImporterException(msg)

def sarif_error(s):
    """Report an error with what was found in the Sarif object
    """
    raise SarifImporterException("Sarif error: {0}".format(s))

def unhandled_warning(s):
    """Report that the importer cannot handle something about the Sarif input
    """
    print("WARNING: Sarif Importer: Unhandled construct: {0}".format(s))

def general_warning(s):
    """Report a general warning
    """
    print("WARNING: Sarif importer: {0}".format(s))

# End of Error handling

class SarifParser(gtr.AbstractJsonParser):
    '''This is the main SARIF parser
    '''
    def __init__(self, version, state):
        super(SarifParser, self).__init__()
        check_support_for_version(version)
        self.version = version
        self.state = state
        self.estack = [SarifTopHandler(self, state)]
    def object_start(self):
        self.estack[-1].object_start(self)
    def object_end(self):
        self.estack[-1].object_end(self)
    def object_member_start(self, key):
        h = self.estack[-1].object_member_start(self, key)
        self.estack.append(h)
    def object_member_end(self, key):
        self.estack[-2].object_member_end(self, key)
        self.estack.pop()
    def array_start(self):
        h = self.estack[-1].array_start(self)
        self.estack.append(h)
    def array_end(self):
        self.estack[-2].array_end(self)
        self.estack.pop()
    def array_element_start(self, idx):
        h = self.estack[-1].array_element_start(self, idx)
        self.estack.append(h)
    def array_element_end(self, idx):
        self.estack[-2].array_element_end(self, idx)
        self.estack.pop()
    def string_value(self, value):
        self.estack[-1].do_string(self, value)
    def integer_value(self, value):
        self.estack[-1].do_integer(self, value)
    def handle_float(self, value):
        self.estack[-1].do_float(self, value)
    def __str__(self):
        return "<SarifParser {0}>".format(self.estack)

class Handler(object):
    '''Handlers are objects that are pushed and popped from the stack maintained
    when the JSON object is processed.

    For each action in the parser, there is a corresponding handler action.
    This actions in this class are the default actions. Subclasses should specialize
    these if necessary.
    '''
    def __init__(self, parser):
        '''Subclasses should NOT re-define __init__(). Instead, they should
        define initialize()'''
        self.property_handlers = {}
        # All objects may have a properties bag. This causes them all to be skipped.
        # The initialize() method of a subclass should override this if those properties
        # are important.
        self.set_property_handler("properties", SkipHandler)
        self.initialize(parser)
    def initialize(self, parser):
        pass
    def object_start(self, parser):
        pass
    def object_end(self, parser):
        pass
    def object_member_start(self, parser, key):
        return self.parse_property(parser, key)
    def object_member_end(self, parser, key):
        if key in self.property_handlers:
            try:
                setattr(self, key, parser.estack[-1].value)
            except AttributeError:
                pass
    def array_start(self, parser):
        return SkipHandler(parser)
    def array_end(self, parser):
        pass
    def array_element_start(self, parser, idx):
        return SkipHandler(parser)
    def array_element_end(self, parser, idx):
        pass
    def do_string(self, parser, value):
        pass
    def do_integer(self, parser, value):
        pass
    def do_float(self, parser, value):
        pass
    def syntax_error(self, parser, msg):
        raise SarifImporterException(msg)
    def parse_property(self, parser, key):
        if key not in self.property_handlers:
            self.syntax_error(parser, "With stack {0}, property '{1}' was not expected".format(parser.estack, key))
        return self.property_handlers[key](parser)
    def set_property_handler(self, key, klass, default=None):
        # This method takes care of assigning a default value to what will be
        # returned too. This is only done if the attribute is not already present.
        try:
            getattr(self, key)
        except AttributeError:
            setattr(self, key, default)
        self.property_handlers[key] = klass
    def set_skip_handlers(self, keys):
        for key in keys:
            if key in self.property_handlers:
                general_warning("property {0} of {1} already has a handler".format(key, self))
            self.set_property_handler(key, SkipHandler)
    def set_properties_handler(self, keys, klass):
        for key in keys:
            self.set_property_handler(key, klass)
    def __repr__(self):
        return type(self).__name__

class SkipHandler(Handler):
    '''SkipHandler causes the parser to ignore all subterms
    '''
    def object_member_start(self, parser, key):
        return SkipHandler(parser)

class SarifTopHandler(Handler):
    '''This is the top-level object that will contain the state of the parse.

    This parser is called twice. Note that this is necessary
    because the JSON can be encountered in any order (the standard does not 
    specify an order, other than to say that "version" is recommended to come
    early.)

    The first pass is to create and store information that will be needed to
    submit warnings later.
    This includes the warning classes, the file table, etc. Roughly speaking,
    if anything is a reference to another part of hte JSON file, it should be
    read in pass 1 and stored in the sarif_state object at the base of the
    stack.

    The second pass will submit warnings.

    Note that this class is the topmost class that takes the version of the
    SARIF into consideration. For example, in v1 you have:
       {'rules': { ... }}
    whereas in v2 you have:
       {'resources': {'rules': { ... }}}
    Note how the initialize method switches on the version of the parser.
    (Although this part is commented out because we don't support v1)
    Other handlers that are sensitive to the version number should operate
    in a similar manner.
    '''
    def __init__(self, parser, state):
        self.state = state
        super(SarifTopHandler, self).__init__(parser)
    def initialize(self, parser):
        self.properties = {}
        self.set_skip_handlers(['version', '$schema'])
        self.set_property_handler('runs', RunsHandler)
        #   if parser.version[0] == 1:
        #       self.set_property_handler('rules', RulesHandlerv1)
        if self.state.get_ppass() == 1:
            self.set_property_handler('properties', PropertiesHandler)
    def object_member_end(self, parser, key):
        if key == "properties" and self.state.get_ppass() == 1:
            self.properties = parser.estack[-1].value
    def object_start(self, parser):
        print("*** Parser pass {0} is beginning".format(self.state.get_ppass()))
    def object_end(self, parser):
        print("*** Parser pass {0} is now complete".format(self.state.get_ppass()))

class PropertiesHandler(Handler):
    """This is for handling generic property bags
    """
    def initialize(self, parser):
        self.value = None
        self.cur_key = None
    def object_start(self, parser):
        self.value = {}
    def object_member_start(self, parser, key):
        self.cur_key = key
        return PropertiesHandler(parser)
    def object_member_end(self, parser, key):
        parser.estack[-2].value[parser.estack[-2].cur_key] = parser.estack[-1].value
    def array_start(self, parser):
        self.value = []
        return PropertiesHandler(parser)
    def array_element_start(self, parser, idx):
        self.cur_key = idx
        return PropertiesHandler(parser)
    def array_element_end(self, parser, idx):
        parser.estack[-3].value.append(parser.estack[-1].value)
    def do_string(self, parser, value):
        self.value = value
    def do_integer(self, parser, value):
        self.value = value
    def do_float(self, parser, value):
        self.value = value

class OriginalUriBaseIdsHandler(Handler):
    def object_member_start(self, parser, key):
        return FileLocationHandler(parser)
    def object_member_end(self, parser, key):
        parser.state.original_uri_base_id_add(parser.estack[-1].uri, parser.estack[-1].uriBaseId, key)

class ResourcesHandler(Handler):
    def initialize(self, parser):
        self.set_property_handler("rules", RulesHandler)
        self.set_property_handler("messageStrings", PropertiesHandler)
    def object_member_end(self, parser, key):
        parser.state.resources_object_member_end(parser, key)

class RulesHandler(Handler):
    def array_start(self, parser):
        return RulesItemHandler(parser)

class RulesItemHandler(Handler):
    def array_element_start(self, parser, idx):
        return RuleHandler(parser)
    def array_element_end(self, parser, idx):
        parser.state.rules_item_array_element_end(parser, idx)

class RuleHandler(Handler):
    def initialize(self, parser):
        self.defaultLevel = None
        self.defaultRank = None
        self.properties = None
        self.set_property_handler("id", StringHandler)
        self.set_property_handler("name", MessageHandler)
        self.set_property_handler("shortDescription", MessageHandler)
        self.set_property_handler("fullDescription", MessageHandler)
        self.set_property_handler("messageStrings", PropertiesHandler)
        self.set_skip_handlers(["richMessageStrings"])
        self.set_property_handler("helpUri", StringHandler)
        self.set_property_handler("help", MessageHandler)
        self.set_property_handler("configuration", RuleConfigurationHandler)
        self.set_property_handler("properties", PropertiesHandler)
    def object_member_end(self, parser, key):
        if key == "configuration":
            self.defaultLevel = parser.estack[-1].defaultLevel
            self.defaultRank = parser.estack[-1].defaultRank
        elif key == "properties":
            self.properties = parser.estack[-1].value
        else:
            super(RuleHandler, self).object_member_end(parser, key)

class RuleConfigurationHandler(Handler):
    def initialize(self, parser):
        self.set_property_handler("defaultLevel", StringHandler)
        self.set_property_handler("defaultRank", FloatHandler)
        self.set_skip_handlers(["enabled", "parameters"])

class ArtifactsHandler(Handler):
    def initialize(self, parser):
        self.artifacts = []
    def array_start(self, parser):
        return ArtifactsItemHandler(parser)

class ArtifactsItemHandler(Handler):
    def array_element_start(self, parser, idx):
        return ArtifactHandler(parser)
    def array_element_end(self, parser, idx):
        parser.state.file_item_add(parser.estack[-1])

class ArtifactHandler(Handler):
    def initialize(self, parser):
        self.set_property_handler("location", ArtifactLocationHandler)
        self.set_skip_handlers(
            ["description", "parentIndex", "offset", "length", "roles", "mimeType",
             "contents", "encoding", "sourceLanguage", "hashes", "lastModifiedTimeUtc"])
    def object_member_end(self, parser, key):
        if key == "location":
            self.uri = parser.estack[-1].uri
            self.uriBaseId = parser.estack[-1].uriBaseId
        else:
            super(ArtifactHandler, self).object_member_end(parser, key)

class ArtifactLocationHandler(Handler):
    def initialize(self, parser):
        self.set_property_handler("uri", StringHandler)
        self.set_property_handler("uriBaseId", StringHandler)
        self.set_property_handler("index", IntegerHandler)
        self.set_property_handler("description", MessageHandler)
    def object_member_end(self, parser, key):
        if key == "uri":
            self.uri = gtr.urldecode(parser.estack[-1].value)
        else:
            super(ArtifactLocationHandler, self).object_member_end(parser, key)

class RunsHandler(Handler):
    def initialize(self, parser):
        self.runs = []
    def array_start(self, parser):
        return RunsItemHandler(parser)

class RunsItemHandler(Handler):
    def array_element_start(self, parser, idx):
        return RunHandler(parser)

class RunHandler(Handler):
    def initialize(self, parser):
        ppass = parser.estack[0].state.get_ppass()
        if is_legacy_version(parser.version):
            if ppass == 1:
                self.set_property_handler("files", FilesHandler)
                self.set_property_handler("resources", ResourcesHandler)
                self.set_property_handler("originalUriBaseIds", OriginalUriBaseIdsHandler)
                self.set_property_handler("tool", ToolHandler)
                self.set_skip_handlers(["results"])
            if ppass == 2:
                self.set_property_handler("results", ResultsHandler)
                self.set_skip_handlers(["tool", "resources", "files", "originalUriBaseIds"])
            # Skipped in all passes
            self.set_skip_handlers(
                ["id", "aggregateIds", "baselineInstanceGuid", "invocations", "conversion",
                 "versionControlProvenance", "logicalLocations", "graphs", "defaultFileEncoding",
                 "newlineSequences", "columnKind", "richMessageMimeType", "redactionToken"]
            )
        else:
            if ppass == 1:
                self.set_property_handler("tool", ToolHandler)
                self.set_property_handler("artifacts", ArtifactsHandler)
                self.set_property_handler("originalUriBaseIds", OriginalUriBaseIdsHandler)
                self.set_skip_handlers(["results"])
            if ppass == 2:
                self.set_property_handler("results", ResultsHandler)
                self.set_skip_handlers(["artifacts", "tool", "originalUriBaseIds"])
            self.set_skip_handlers(
                ["invocations", "conversion", "language", "versionControlProvenance",
                 "logicalLocations", "graphs", "automationDetails", "runAggregates",
                 "baselineGuid", "redactionTokens", "defaultEncoding", "defaultSourceLanguage",
                 "newlineSequences", "columnKind", "externalPropertyFileReferences",
                 "threadFlowLocations", "taxonomies", "addresses", "translations", "policies",
                 "webRequests", "webResponses", "specialLocations"])

    def object_member_end(self, parser, key):
        ppass = parser.estack[0].state.get_ppass()
        if ppass == 1:
            if key == "tool":
                parser.state.run_object_member_end(parser.estack[-1].name, parser.estack[-1].globalMessageStrings)
    def object_start(self, parser):
        parser.state.run_object_start(parser)

class ToolHandler(Handler):
    def initialize(self, parser):
        if is_legacy_version(parser.version):
            self.globalMessageStrings = {}
            self.set_property_handler("name", StringHandler)
            self.set_skip_handlers(
                ["fullName", "semanticVersion", "version", "fileVersion",
                 "downloadUri", "language", "resourceLocation", "sarifLoggerVersion"]
            )
        else:
            self.name = None
            self.set_property_handler("driver", ToolComponentHandler)
            self.set_skip_handlers(["extensions"])
    def object_member_end(self, parser, key):
        if not is_legacy_version(parser.version) and key == "driver":
            self.name = parser.estack[-1].name
            self.globalMessageStrings = parser.estack[-1].globalMessageStrings
        else:
            super(ToolHandler, self).object_member_end(parser, key)

class ToolComponentHandler(Handler):
    def initialize(self, parser):
        self.set_property_handler("name", StringHandler)
        self.set_property_handler("globalMessageStrings", PropertiesHandler)
        if is_legacy_version(parser.version):
            self.set_property_handler("rules", RulesHandler)
        else:
            self.set_property_handler("rules", ReportingDescriptorsHandler)
        self.set_skip_handlers(
            ["guid", "organization", "product", "productSuite", "shortDescription", "fullDescription",
             "fullName", "version", "semanticVersion", "dottedQuadFileVersion", "releaseDateUtc", "downloadUri",
             "informationUri", "notifications", "taxa", "locations", "language",
             "contents", "isComprehensive", "localizedDataSemanticVersion", "minimumRequiredLocalizedDataSemanticVersion",
             "associatedComponent", "translationMetadata", "supportedTaxonomies"]
        )
    def object_member_end(self, parser, key):
        super(ToolComponentHandler, self).object_member_end(parser, key)

class ReportingDescriptorsHandler(Handler):
    def array_start(self, parser):
        return ReportingDescriptorsItemHandler(parser)

class ReportingDescriptorsItemHandler(Handler):
    def array_element_start(self, parser, idx):
        return ReportingDescriptorHandler(parser)
    def array_element_end(self, parser, idx):
        parser.state.rules_item_array_element_end(parser, idx)

class ReportingDescriptorHandler(Handler):
    def initialize(self, parser):
        self.level = "warning"
        self.rank = -1
        self.properties = None
        self.set_property_handler("id", StringHandler)
        self.set_property_handler("name", StringHandler)
        self.set_property_handler("shortDescription", MessageHandler)
        self.set_property_handler("fullDescription", MessageHandler)
        self.set_property_handler("messageStrings", PropertiesHandler)
        self.set_property_handler("helpUri", StringHandler)
        self.set_property_handler("help", MessageHandler)
        self.set_property_handler("defaultConfiguration", ReportingConfigurationHandler)
        self.set_property_handler("properties", PropertiesHandler)
        self.set_skip_handlers(
            ["richMessageStrings", "deprecatedIds", "guid", "deprecatedNames", "relationships"]
        )
    def object_member_end(self, parser, key):
        if key == "defaultConfiguration":
            self.level = parser.estack[-1].level
            self.rank = parser.estack[-1].rank
        elif key == "properties":
            self.properties = parser.estack[-1].value
        else:
            super(ReportingDescriptorHandler, self).object_member_end(parser, key)

class ReportingConfigurationHandler(Handler):
    def initialize(self, parser):
        self.set_property_handler("level", StringHandler)
        self.set_property_handler("rank", FloatHandler)
        self.set_skip_handlers(["enabled", "parameters"])

class ResultsHandler(Handler):
    def initialize(self, parser):
        pass
    def array_start(self, parser):
        return ResultsItemHandler(parser)

class ResultsItemHandler(Handler):
    def array_element_start(self, parser, idx):
        return ResultHandler(parser)
    def array_element_end(self, parser, idx):
        parser.state.results_item_array_element_end(parser, idx)

class ResultHandler(Handler):
    def initialize(self, parser):
        self.message = None
        self.messageId = None
        self.locations = []
        self.relatedLocations = []
        self.codeFlows = []
        self.properties = None
        self.set_property_handler("ruleId", StringHandler)
        self.set_property_handler("ruleIndex", IntegerHandler, -1)
        self.set_property_handler("level", StringHandler)
        self.set_property_handler("message", MessageHandler)
        self.set_property_handler("locations", LocationsHandler)
        self.set_property_handler("relatedLocations", LocationsHandler)
        self.set_property_handler("codeFlows", CodeFlowsHandler)
        self.set_property_handler("properties", PropertiesHandler)
        self.set_property_handler("hostedViewerUri", StringHandler)
        self.set_property_handler("rank", FloatHandler)
        if is_legacy_version(parser.version):
            self.set_skip_handlers(
                ["instanceGuid", "correlationGuid", "analysisTarget", "fingerprints",
                "partialFingerprints", "graphs", "graphTraversals", "stacks", "suppressionStates",
                "baselineState", "attachments", "workItemUris", "resultProvenance",
                "conversionProvenance", "fixes", "occurrenceCount"]
            )
        else:
            self.set_skip_handlers(
                ["kind", "analysisTarget", "guid", "correlationGuid", "occurrenceCount", "partialFingerprints",
                 "fingerprints", "stacks", "graphs", "graphTraversals", "suppressions", "baselineState",
                 "attachments", "workItemUris", "provenance", "fixes", "taxa",
                 "webRequest", "webResponse"]
            )


    def object_member_end(self, parser, key):
        if key == "message":
            self.message = parser.estack[-1].value
            self.messageId = parser.estack[-1].id
        elif key == "locations":
            self.locations = parser.estack[-1].locations
        elif key == "relatedLocations":
            self.relatedLocations = parser.estack[-1].locations
        elif key == "codeFlows":
            self.codeFlows = parser.estack[-1].codeFlows
        elif key == "properties":
            self.properties = parser.estack[-1].value
        else:
            super(ResultHandler, self).object_member_end(parser, key)

class CodeFlowsHandler(Handler):
    def array_start(self, parser):
        self.codeFlows = []
        return CodeFlowsItemHandler(parser)

class CodeFlowsItemHandler(Handler):
    def array_element_start(self, parser, idx):
        return CodeFlowHandler(parser)
    def array_element_end(self, parser, idx):
        parser.estack[-3].codeFlows.append(parser.estack[-1])

class CodeFlowHandler(Handler):
    def initialize(self, parser):
        self.threadFlows = []
        self.set_property_handler("message", MessageHandler)
        self.set_property_handler("threadFlows", ThreadFlowsHandler)
    def object_member_end(self, parser, key):
        if key == "threadFlows":
            self.threadFlows = parser.estack[-1].threadFlows
        else:
            super(CodeFlowHandler, self).object_member_end(parser, key)

class ThreadFlowsHandler(Handler):
    def array_start(self, parser):
        self.threadFlows = []
        return ThreadFlowsItemHandler(parser)

class ThreadFlowsItemHandler(Handler):
    def array_element_start(self, parser, idx):
        return ThreadFlowHandler(parser)
    def array_element_end(self, parser, idx):
        parser.estack[-3].threadFlows.append(parser.estack[-1])

class ThreadFlowHandler(Handler):
    def initialize(self, parser):
        self.locations = []
        self.set_property_handler("id", StringHandler)
        self.set_property_handler("message", MessageHandler)
        self.set_property_handler("locations", ThreadFlowLocationsHandler)
    def object_member_end(self, parser, key):
        if key == "locations":
            self.locations = parser.estack[-1].locations
        else:
            super(ThreadFlowHandler, self).object_member_end(parser, key)

class ThreadFlowLocationsHandler(Handler):
    def array_start(self, parser):
        self.locations = []
        return ThreadFlowLocationsItemHandler(parser)

class ThreadFlowLocationsItemHandler(Handler):
    def array_element_start(self, parser, idx):
        return ThreadFlowLocationHandler(parser)
    def array_element_end(self, parser, idx):
        parser.estack[-3].locations.append(parser.estack[-1])

class ThreadFlowLocationHandler(Handler):
    def initialize(self, parser):
        self.location = None
        self.set_property_handler("location", LocationHandler)
        self.set_property_handler("importance", StringHandler)
        if is_legacy_version(parser.version):
            self.set_skip_handlers(["kind"])
        self.set_skip_handlers(
            ["module", "stack", "kinds", "state", "nestingLevel",
             "executionOrder", "executionTimeUtc"]
        )
    def object_member_end(self, parser, key):
        if key == "location":
            self.location = parser.estack[-1]
        else:
            super(ThreadFlowLocationHandler, self).object_member_end(parser, key)

class LocationsHandler(Handler):
    def array_start(self, parser):
        self.locations = []
        return LocationsItemHandler(parser)

class LocationsItemHandler(Handler):
    def array_element_start(self, parser, idx):
        return LocationHandler(parser)
    def array_element_end(self, parser, idx):
        parser.estack[-3].locations.append(parser.estack[-1])

class LocationHandler(Handler):
    def initialize(self, parser):
        self.physicalLocation = None
        self.properties = {}
        self.set_property_handler("physicalLocation", PhysicalLocationHandler)
        self.set_property_handler("message", MessageHandler)
        if is_legacy_version(parser.version):
            self.set_skip_handlers(["fullyQualifiedLogicalName", "logicalLocationIndex", "annotations"])
        else:
            self.set_property_handler("id", IntegerHandler)
            self.set_skip_handlers(["logicalLocations", "relationships", "annotations"])
        self.set_property_handler("properties", PropertiesHandler)
    def object_member_end(self, parser, key):
        if key == "physicalLocation":
            self.physicalLocation = parser.estack[-1]
        else:
            super(LocationHandler, self).object_member_end(parser, key)

class PhysicalLocationHandler(Handler):
    def initialize(self, parser):
        if is_legacy_version(parser.version):
            self.set_property_handler("fileLocation", FileLocationHandler)
        else:
            self.set_property_handler("artifactLocation", ArtifactLocationHandler)
            self.set_skip_handlers(["address"])
            self.set_property_handler("contextRegion", RegionHandler)
        self.set_property_handler("region", RegionHandler)
        self.set_skip_handlers(["id"])
        self.region = None
        self.fileLocation = None
    def object_member_end(self, parser, key):
        if (is_legacy_version(parser.version) and key == "fileLocation" or 
            is_latest_version(parser.version) and key == "artifactLocation"):
            self.fileLocation = parser.estack[-1]
        elif key == "region":
            self.region = parser.estack[-1]
        else:
            super(PhysicalLocationHandler, self).object_member_end(parser, key)

class RegionHandler(Handler):
    # These are all the fields that are integer typed.
    int_fields = ['startLine', 'startColumn', 'endLine', 'endColumn',
                  'charOffset', 'charLength', 'byteOffset', 'byteLength']
    def initialize(self, parser):
        # A bit of metaprogramming on field names reduces risk of CPEs
        for fld_name in RegionHandler.int_fields:
            self.__dict__[fld_name] = None
            self.set_property_handler(fld_name, IntegerHandler)
        self.message = None
        self.set_property_handler("message", MessageHandler)
        self.set_property_handler("snippet", SkipHandler)
    def object_member_end(self, parser, key):
        for fld_name in RegionHandler.int_fields:
            if key == fld_name:
                self.__dict__[fld_name] = parser.estack[-1].value
        if key == "message":
            self.message = parser.estack[-1].value

class FilesHandler(Handler):
    def array_start(self, parser):
        return FilesItemHandler(parser)

class FilesItemHandler(Handler):
    def array_element_start(self, parser, idx):
        return FileHandler(parser)
    def array_element_end(self, parser, idx):
        parser.state.file_item_add(parser.estack[-1])

class FileHandler(Handler):
    def initialize(self, parser):
        self.uri = None
        self.uriBaseId = None
        self.set_property_handler("fileLocation", FileLocationHandler)
        self.set_property_handler("mimeType", StringHandler)
        self.set_property_handler("parentIndex", IntegerHandler)
        self.set_skip_handlers(
            ["offset", "length", "roles",
             "contents", "encoding", "hashes",
             "lastModifiedTimeUtc"]
        )
    def object_member_end(self, parser, key):
        if key == "fileLocation":
            self.uri = parser.estack[-1].uri
            self.uriBaseId = parser.estack[-1].uriBaseId
        else:
            super(FileHandler, self).object_member_end(parser, key)

class FileLocationHandler(Handler):
    def initialize(self, parser):
        self.set_property_handler("uri", StringHandler)
        self.set_property_handler("uriBaseId", StringHandler)
        self.set_property_handler("fileIndex", IntegerHandler, -1)
    def object_member_end(self, parser, key):
        if key == "uri":
            self.uri = gtr.urldecode(parser.estack[-1].value)
        else:
            super(FileLocationHandler, self).object_member_end(parser, key)

##########################################################################################
# ANY PASS classes
class StringHandler(Handler):
    def initialize(self, parser):
        self.value = None
    def do_string(self, parser, value):
        self.value = value

class IntegerHandler(Handler):
    def initialize(self, parser):
        self.value = None
    def do_integer(self, parser, value):
        self.value = value

class FloatHandler(Handler):
    def initialize(self, parser):
        self.value = None
    def do_float(self, parser, value):
        self.value = value

class RuleIdHandler(Handler):
    def initialize(self, parser):
        self.rule = None
    def do_string(self, value, stack):
        self.rule.id = value

class MessageHandler(Handler):
    def initialize(self, parser):
        self.value = None
        self.id = None
        self.set_property_handler("text", StringHandler)
        if is_legacy_version(parser.version):
            self.set_property_handler("messageId", StringHandler)
            self.set_skip_handlers(["richText", "richMessageId", "arguments"])
        else:
            self.set_property_handler("id",StringHandler)
            self.set_skip_handlers(["markdown", "arguments"])
    def object_member_end(self, parser, key):
        if key == "text":
            self.value = parser.estack[-1].value
        elif key == "messageId":
            self.id = parser.estack[-1].value
        else:
            super(MessageHandler, self).object_member_end(parser, key)

###### END OF HANDLERS

##########################################################################################

##### MISCELLANY

def get_version(sfile):
    '''Extract the version of the Sarif file

    As of September 2019, the official version of SARIF is 2.1.0.

    CodeSonar originally supported a version that was identified as
    "2.0.0-beta.2018-11-14". This was a snapshot of the as-yet unfinished
    standard on that date. This is referred to in this code as the legacy
    version. Unfortunately the Sarif generators from that time were not
    good at identifying the version precisely, but at least they all begin
    with 2.0.0.
    The assumption in this code is that anything prior to 2.1.0
    is legacy. The parser will assume that the happy path is 2.1.0,
    and that anything labeled as 2.0.0 is the same schema.
    '''
    vstr = None
    try:
        parser = SarifVersionExtractor()
        with open(sfile) as fp:
            gtr.json_stream_parse_all(fp, parser)
    except SarifVersionDone:
        # This regexp must be capable of recognizing strings that have additional
        # version information after the three digits. E.g., "2.0.0-csd-Beta3".
        # The final version won't have these, but we won't always have that.
        VRE = re.compile('^([0-9]+).([0-9]+)\.([0-9]+)')
        vstr = parser.version
        m = VRE.match(vstr)
        if m is not None:
            return (vstr, (int(m.group(1)), int(m.group(2)), int(m.group(3))))
    return (vstr, None)

def is_legacy_version(version):
    return version == (2,0,0)

def is_latest_version(version):
    return version == (2,1,0)

def process_sarif(sfile, state):
    '''Import a single sarif file, given the parser state given by 'state'

    Sarif files original directory must be known if they 
    are to be interpreted correctly.

    Returns void, and may raise SarifImporterException() on failure.
    '''
    (vstr, version) = get_version(sfile)
    if version is None:
        raise SarifImporterException("Cannot extract SARIF version number from version string '{}' in Sarif file '{}'".format(vstr, sfile))

    state.set_ppass(1)
    pass1_parser = SarifParser(version, state)
    state.set_parser(pass1_parser)
    with open(sfile) as fp:
        gtr.json_stream_parse_all(fp, pass1_parser)

    state.set_ppass(2)
    pass2_parser = SarifParser(version, state)
    state.set_parser(pass2_parser)
    with open(sfile) as fp:
        gtr.json_stream_parse_all(fp, pass2_parser)
