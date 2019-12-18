import argparse
import sys
try:
    from gtr.util import UserError
except ImportError:
    from tinygtr.util import UserError
import github_connection
from comment import Comment, PositionalComment, CommentFormatter
from comment import markdown_escape
import sarif_parser
import github_sarif_state
try:
    import gtr.util.debug as Debug
except ImportError:
    import tinygtr.util.debug as Debug
import platform

class AnnotateFormatter(CommentFormatter):
    def __init__(self, options):
        self.options = options

    def to_github_api_body_fragment(self, comment, no_context=False):
        rv = ''
        # the class and significance if any
        if comment.class_name != '':
            rv = rv + comment.class_name + ' ' 
        # first comes file/line, if any...
        if no_context == False:
            if (isinstance(comment, PositionalComment)):
                rv = rv + '`%s:%d` ' % (comment.path.replace('`', ''), comment.line)
        # then url
        url = comment.url
        if self.options.hosted_viewer_uri != None:
            url = self.options.hosted_viewer_uri
        if url != '':
            rv = rv + '[:link:](%s) ' % url.replace('`', '')
        # we can do a cutesy thing here where we can alt text an emoji
        # by [:emoji:](fake_link "text")
#        if comment.significance != '':
#            rv = rv + comment.significance + ': '
#            rv = rv + '[:boom:](https://www.grammatech.com "%s") ' % comment.significance
        # temp, score if any, just to see how it looks
        # we may mess with formatting later...
#        rv = rv + '%2.2f ' % comment.rank 
#        score = ':small_red_triangle:'
#        if comment.rank < 8:
#            score = ':small_orange_diamond:'
#        rv = rv + '[%s](https://www.grammatech.com "%2.2f")' % (score, comment.rank)
        # then the body
#        import pdb
#        pdb.set_trace()
        text = comment.body
        if text.startswith('  - '):
            text = text[4:]
        position = text.find(' - ')
        if position != -1:
            rv = rv + '\n><sup>' + markdown_escape(text[:position]) + '[...](%s "%s")' % (url if url != '' else 'https://www.grammatech.com', markdown_escape(text.replace(' - ', ' '))) +'</sup>\n'
        else:
            rv = rv + '\n><sup>' + markdown_escape(text) + '</sup>\n'
#        rv = rv + '\n><sup>' + markdown_escape(text) + '</sup>\n'
#        rv = rv + '\n><sup>' + markdown_escape(comment.body) + '</sup>\n'
        return rv

    def to_github_api_comment(self, ranges, comment):
        return dict(body=comment.formatter.to_github_api_body_fragment(comment, True),
                    path=comment.path,
                    position=ranges[comment.path][comment.line])

class LeadFormatter(CommentFormatter):
    def __init__(self, options):
        self.options = options

    def to_github_api_body_fragment(self, comment):
        return comment.body

    def to_github_api_comment(self, ranges, comment):
        return dict(body=comment.to_github_api_body_fragment(),
                    path=comment.path,
                    position=ranges[comment.path][comment.line])

def get_comments(options, modified_ranges): # type: (argparse.Namespace, RangeSet) -> sequence[Comment]
    f = options.sarif_file
    print("****** Importing '{0}' *******".format(f))
    # Each imported file gets its own CodeSonar state   
    state = github_sarif_state.GithubSarifState()
    sarif_parser.process_sarif(f, state)
    return state.comments

'''
def get_comments(options, modified_ranges): # type: (argparse.Namespace, RangeSet) -> sequence[Comment]

    # The return statement below is a placeholder for code that
    # fetches, parses, and constructs comments from the SARIF file.
    return [Comment('This is a positionless comment.  Here are some backticks that need to be escaped: `foo`.'),
            Comment('This is the second positionless comment.'),
            PositionalComment('This comment has position on line LONGFILE 127', 'LONGFILE', 127),
            PositionalComment('This comment has position on line 1', 'README', 1),
            PositionalComment('This comment has position on line 2', 'README', 2),
            PositionalComment('This comment has position on line 3', 'README', 3),
            PositionalComment('This comment has position on line 5', 'README', 5),
            PositionalComment('This comment has position on line 7', 'README', 7),
            PositionalComment('This comment has position on line 8', 'README', 8),
            PositionalComment('This comment has position on line 9', 'README', 9),
            PositionalComment('This comment has position on line 6', 'README', 6),
            PositionalComment('This comment has position on line 4', 'README', 4),
            PositionalComment('This comment has position on line 15', 'README', 15),
            PositionalComment('This comment has position on line 18', 'README', 18),
            PositionalComment('This comment has position on line 100', 'README', 100),
            PositionalComment('This comment has position on line VICTIM 10', 'VICTIM', 10),
            PositionalComment('This comment has position on line NEWFILE 10', 'NEWFILE', 10),
            PositionalComment('This comment has position on line LONGFILE 197', 'LONGFILE', 197),
            PositionalComment('This comment has position on line LONGFILE 284', 'LONGFILE', 284),
            PositionalComment('This comment is in another file', 'NOTINPR', 5),
            ]
'''            

# SARIF files contain absolute paths. Github diff contain
# paths relative to the root of the repo.
def adjust_comment_paths(options, comments):
    if options.prefix:
        if not options.prefix.startswith('file://'):
            options.prefix = 'file://' + options.prefix
        if not options.prefix.endswith('/'):
            options.prefix += '/'
        prefix_len = len(options.prefix)
        for c in comments:
            if getattr(c, 'path', None) != None:
                # just in case some funky path exists
                if c.path.startswith(options.prefix):
                    c.path = c.path[prefix_len:]
                    if options.windows_path:
                        c.path = c.path.lower()

def filter_comments(options, ranges, comments):
    comments_len = len(comments)
    comments[:] = [c for c in comments if c.path in ranges]
    return comments_len - len(comments)

def adjust_formatters(comments, formatter):
    for comment in comments:
        comment.formatter = formatter

def cut_down_to_byte_size(options, comments, ranges):
    sum = 0
    num_comments = len(comments)
    for i in xrange(0, len(comments)):
        comment_length = 0
        if   (isinstance(comments[i], PositionalComment)
              and comments[i].path in ranges
              and comments[i].line in ranges[comments[i].path]):
            comment_length = len(comments[i].to_github_api_comment(ranges))
        else:
            comment_length = len(comments[i].to_github_api_body_fragment())
        if sum + comment_length > options.review_size:
            num_comments = i
            break
        sum += comment_length
    return num_comments

def sort_comments(options, comments):
    comments.sort()

def handle_hub_uris(options, comments):
    if options.hosted_viewer_uri:
        for c in comments:
            c.hub = options.hosted_viewer_uri
                                    

def main(argv): # type: (list[str]) -> int
    try:
        Debug.make_python_warnings_show_stack_traces()
        options = parse_args(argv[1:])
        print(options)

        if options.windows_path:
            if options.prefix:
                options.prefix = options.prefix.lower().replace('\\', '/')
        
        repo = github_connection.Repo(options)
        pr = repo.get_pull_request(options.pull_request)

        if options.sarif_file:
            modified_ranges = pr.get_modified_ranges()
            print modified_ranges
            
            comments = get_comments(options, modified_ranges)

            adjust_comment_paths(options, comments)

            removed = filter_comments(options, modified_ranges, comments)

            adjust_formatters(comments, AnnotateFormatter(options))

            sort_comments(options, comments)

            comments.insert(0, Comment('CodeSonar has detected the following warnings in files modified by this pull request.\n%d comments were not in files in this pull request.' % removed, 0, '', '', '', LeadFormatter(options)))

            num_comments = cut_down_to_byte_size(options, comments, modified_ranges)
            comments[0].body += '\n%d comments were redacted due to space constraints.\n' % (len(comments) - num_comments)
            comments = comments[:num_comments]

            pr.make_review(
                modified_ranges,
                comments)
        if options.dump_pr_to_file:
            import json
            with open(options.dump_pr_to_file, 'w') as f:
                json.dump(pr.dump_last_review(),
                          f,
                          sort_keys=True,
                          indent=4, separators=(',', ': '))
        return 0
    except UserError, e:
        print str(e)
        return 1
    except Exception:
        Debug.print_exc('EXCEPTION')
        return 1
        
    
def check_positive(value): # type: (str) -> int
    ivalue = int(value)
    if ivalue <= 0:
         raise UserError("%s is an invalid positive int value" % value)
    return ivalue

def handle_prefix_style(v):
    if platform.system() == 'Windows':
        return v.lower() != 'posix'
    else:
        return v.lower() == 'windows'

def parse_args(argv):
    parser = argparse.ArgumentParser(description='Adds comments to a pull request from a SARIF file.')

    # requires repo
    parser.add_argument('-s', '--sarif-file', 
                        dest='sarif_file',
                        help='the SARIF file to use to make comments')
    parser.add_argument('-p', '--pull-request', 
                        dest='pull_request',
                        type=check_positive,
                        help='the pull request number')
    parser.add_argument('-r', '--repo', 
                        dest='repo',
                        help='the github repo used (e.g., https://github.com/octocat/Hello-World.git)')
    parser.add_argument('-t', '--token', 
                        dest='token',
                        help='the github access token to use')
    parser.add_argument('--prefix', 
                        dest='prefix',
                        help="the prefix prepended to each file mentioned in the pull request's diff file")
    parser.add_argument('--dump-pr-to-file', 
                        dest='dump_pr_to_file',
                        help='filename to which a dump of the reviews in the pull request should be saved')
    parser.add_argument('--review-size',
                        dest='review_size',
                        default=74000,
                        type=check_positive,
                        help='approximate size of comments in review, default 74000')
    parser.add_argument('--hosted-viewer-uri',
                        dest='hosted_viewer_uri',
                        help='uses argument instead of hostedViewerUri from SARIF file')
    parser.add_argument('--prefix-style', 
                        dest='windows_path',
                        type=handle_prefix_style,
                        default= True if platform.system() == 'Windows' else False,
                        help="handle the --prefix argument as a posix or windows path")

    return parser.parse_args(argv)
    
if __name__ == '__main__':
    sys.exit(main(sys.argv))
    
