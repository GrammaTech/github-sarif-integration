# open-source version of gtr
import re
import urllib
import json

def parse_data(src, parser):
    if isinstance(src, dict):
        parser.object_start()
        for key, value in src.items():
            parser.object_member_start(key)
            parse_data(value, parser)
            parser.object_member_end(key)
        parser.object_end()
    elif isinstance(src, list):
        parser.array_start()
        idx = 0
        for e in src:
            parser.array_element_start(idx)
            parse_data(e, parser)
            parser.array_element_end(idx)
            idx += 1
        parser.array_end()
    elif isinstance(src, int):
        parser.iteger_value(src)
        parser.integer_value_as_string(str(src))
    elif isinstance(src, unicode):
        parser.string_value(src)
    elif isinstance(src, bool):
        parser.boolean_value(src)
        if src == True:
            parser.true_value()
        if src == False:
            parser.false_value()
    elif isinstance(src, float):
        parser.float_value(src)
        parser.float_value_as_string(str(src))
    elif src == None:
        parser.null_value()
    else:
        # need more values here...
        print "Value %s"%src

def json_stream_parse_all(fobj, parser):
    data = json.load(fobj)
    parse_data(data, parser)

def xmlencode(src):
    src = src.replace("&", "&amp;")
    src = src.replace("<", "&lt;")
    src = src.replace(">", "&gt;")
    src = src.replace("\"", "&quot;")
    src = src.replace("'", "&apos;")
    ret = format(ord('\r'),'x').upper()
    src = src.replace("\r", "&#x{0};".format(ret))
    src = re.sub('[\x00-\x08\x0b-\x1f\x7f-\xff]','',src)
    return src

def urldecode(src):
    return urllib.unquote(src)

def urlencode(src):
    return urllib.quote(src)

class AbstractJsonParser(object):
    def object_start(self):
        pass

    def object_member_start(self, key):
        pass

    def object_member_end(self, key):
        pass

    def object_end(self):
        pass

    def array_start(self):
        pass

    def array_element_start(self, idx):
        pass

    def array_element_end(self, idx):
        pass

    def array_end(self):
        pass

   # the C code never calls this directly, but some clients might
   # prefer to override it instead of the type-specific methods.
    def value(self, x):
        pass

    def integer_value_as_string(self, x):
        return self.integer_value(int(x))

    def integer_value(self, x):
        return self.value(x)

    def string_value(self, x):
        return self.value(x)

    def boolean_value(self, x):
        return self.value(x)

    def false_value(self):
        return self.boolean_value(False)

    def true_value(self):
        return self.boolean_value(True)

    def float_value_as_string(self, x):
        return self.float_value(float(x))

    def float_value(self, x):
        return self.value(x)

    def null_value(self):
        return self.value(None)

import util

