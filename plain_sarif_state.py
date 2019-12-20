# A SarifState that does little in order to test the parser itself.

import sarif_state

class PlainSarifState(sarif_state.SarifState):
    def __init__(self):
        self.parser = None
        self.ppass = 1

    # Taking the easy way out.
    # We need something in case a descendent wants to trigger
    # on change to ppass.
    def set_ppass(self, ppass):
        self.ppass = ppass

    def get_ppass(self):
        return self.ppass

    def set_parser(self, parser):
        self.parser = parser

    def get_parser(self):
        return self.parser

    # These functions are named for the handler they reside in
    # plus the function in that handler.
    # Only functions that called the state are here.
    def original_uri_base_id_add(self, uri, uriBaseId, key):
        print("executing SarifState.original_uri_base_id_add %s %s %s" % (str(uri), str(uriBaseId), str(key)))
    
    def resources_object_member_end(self, parser, key):
        print("executing SarifState.resources_object_member_end %s" % str(key))

    def rules_v1_object_member_end(self, parser, key):
        print("executing SarifState.rules_v1_object_member_end %s" % str(key))

    def rules_item_array_element_end(self, parser, idx):
        print("executing SarifState.rules_item_array_element_end %d" % idx)

    def run_object_member_end(self, tool_name, message_strings):
        print("executing SarifState.run_object_member_end %s %s" % (str(tool_name), str(message_strings)))

    def run_object_start(self, parser):
        print("executing SarifState.run_object_start")

    def results_item_array_element_end(self, parser, idx):
        print("executing SarifState.results_item_array_element_end %d" % idx)

    def file_item_add(self, file_item):
        print("executing SarifState.file_item_add %s" % str(file_item))
 
