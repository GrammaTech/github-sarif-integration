# The base class for application-specific states.

class SarifState(object):
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
        raise NotImplementedError("original_uri_base_id_add")
    
    def resources_object_member_end(self, parser, key):
        raise NotImplementedError("resources_object_member_end")

    def rules_v1_object_member_end(self, parser, key):
        raise NotImplementedError("rules_v1_object_member_end")

    def rules_item_array_element_end(self, parser, idx):
        raise NotImplementedError("rules_item_array_element_end")

    def run_object_member_end(self, tool_name):
        raise NotImplementedError("run_object_member_end")

    def run_object_start(self, parser):
        raise NotImplementedError("run_object_start")

    def results_item_array_element_end(self, parser, idx):
        raise NotImplementedError("results_item_array_element_end")

    def file_item_add(self, file_item):
        raise NotImplementedError("file_item_add")
 
