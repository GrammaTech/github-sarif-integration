# open-source gtr.util

class UserError(Exception):
    '''An error for which we should show the user the message without
    emitting a stack trace'''
    pass

import debug
