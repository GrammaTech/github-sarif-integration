import string

def markdown_escape(x): # type: (str) -> str
    '''Escape any special characters in a markdown string.  This
    function likely is not perfect.  There are also github bugs that
    make escaping emojis like :100: impossible.'''
    return ''.join(['\\' + c if c in string.punctuation else c for c in x])

class CommentFormatter(object):
    def to_github_api_body_fragment(self, comment):
        if (isinstance(comment, PositionalComment)):
            return '* [%s](%s)`: %s:%d:` %s' % (
                comment.url.replace('`', ''),
                comment.url.replace('`', ''),
                comment.path.replace('`', ''),
                comment.line,
                markdown_escape(comment.body),
                )
        else:
            return '* [%s](%s)`:` %s' % (
                comment.url.replace('`', ''),
                comment.url.replace('`', ''),
                markdown_escape(comment.body),
                )
            
    def to_github_api_comment(self, ranges, comment):
        return dict(body=comment.to_github_api_body_fragment(),
                    path=comment.path,
                    position=ranges[comment.path][comment.line])

class Comment(object):
    def __init__(self, body, rank, class_name, significance, url, formatter=CommentFormatter()): # type: (str) -> str
        self.body = body
        self.rank = rank
        self.class_name = class_name
        self.significance = significance
        self.url = url
        self.formatter = formatter

    def to_github_api_body_fragment(self): # type: () -> str
        return self.formatter.to_github_api_body_fragment(self);

    def __repr__(self): # type: () -> str
        return '%s(%.2f, %r, %r, %r, %r)' % (type(self).__name__, self.rank, self.class_name, self.significance, self.url, self.body)

    def __cmp__(self, other):
        # Comment is greater than PositionalComment, and
        # we want Comments to sort first
        if type(self) != type(other):
            # other is PositionalComment
            return -1
        # Now compare both as Comments
        return cmp(self.rank, other.rank) or cmp(self.body, other.body)
    
class PositionalComment(Comment):
    def __init__(self, body, rank, class_name, significance, url, path, line, formatter=CommentFormatter()): # type: (str, str, int) -> None
        super(PositionalComment, self).__init__(body, rank, class_name, significance, url, formatter)
        self.path = path
        self.line = line

    def to_github_api_comment(self, ranges): # type: (dict[str, RangeMap[int, TargetToGitHubLineMap[int, int]]]) -> dict[str, union[str, int]]
        return self.formatter.to_github_api_comment(ranges, self)

    def __repr__(self): # type: () -> str
        return '%s(%.2f, %r, %r, %r, %r, %r, %r)' % (type(self).__name__, self.rank, self.class_name, self.significance, self.url, self.path, self.line, self.body)

    def __cmp__(self, other):
        # Comment is greater than PositionalComment, and
        # we want Comments to sort first
        if type(self) != type(other):
            # other is Comment
            return 1
        # Now compare both as PositionalComments
        return cmp(self.rank, other.rank) or cmp(self.path, other.path) or cmp(self.line, other.line) or cmp(self.body, other.body)
