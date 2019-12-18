try:
    from gtr.util import UserError
except ImportError:
    from tinygtr.util import UserError
try:
    from gtr.rangemap import RangeMap
except ImportError:
    from tinygtr.rangemap import RangeMap
from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport
try:
    import gtr
except ImportError:
    import tinygtr
import urllib2
import unidiff
# now we mess with the internals of unidiff...
# Unidiff is very unicode-centric. However, github diffs
# may not be unicode compatible (especially when the diff
# contains multiple translation files).
# as we don't use the content of the diff, only the names and
# changes, we un-unicode unidiff here.
# If we don't modify unidiff, non-UTF-8 compatible strings
# can't be read. If we modify the reading to not use any encoding,
# the strings can't be encoded on their way out.
# The new_* functions here are essentially the undecorated versions
# of the functions found in unidiff/patch.py anf should track those functions
# in new versions of unidiff.
unidiff.DEFAULT_ENCODING = 'string-escape'
unidiff.make_str = lambda x: x.encode(unidiff.DEFAULT_ENCODING)
def new_linestr(self):
    return "%s%s" % (self.line_type, self.value)
unidiff.patch.Line.__str__ = new_linestr
def new_patchinfostr(self):
    return ''.join(line for line in self)
unidiff.patch.PatchInfo.__str__ = new_patchinfostr
def new_hunkstr(self):
    # section header is optional and thus we output it only if it's present
    head = "@@ -%d,%d +%d,%d @@%s\n" % (
        self.source_start, self.source_length,
        self.target_start, self.target_length,
        ' ' + self.section_header if self.section_header else '')
    content = ''.join(line for line in self)
    return head + content
unidiff.patch.Hunk.__str__ = new_hunkstr
def new_patchsetstr(self):
    return ''.join(patched_file for patched_file in self)
unidiff.PatchSet.__str__ = new_patchsetstr
unidiff.unicode = str
import ssl
import comment

class TargetToGitHubLineMap(RangeMap):
    def __getitem__(self, x):
        # x is a target line, but git wants a "diff line" so we
        # need to translate between coordinate systems.
        base_target_line, base_github_line = super(TargetToGitHubLineMap, self).__getitem__(x)
        return base_github_line + x - base_target_line


class PullRequest(object):
    def __init__(self, repo, number, prid):
        self.repo = repo
        self.number = number
        self.prid = prid
        self.options = repo.options
        self.client = repo.client
        
    def make_global_comment(self, prid, message): # type: (int, str) -> None
        query = gql("""
        mutation AddPullRequestComment($vars:AddCommentInput!) {
          addComment(input: $vars) {
            subject {
              id
            }
          }
        }
        """)
        variables = dict(
            vars=dict(
                subjectId=prid,
                body=message,
                ))
    
        print(self.client.execute(query, variables))
    
    def make_review(self, ranges, comments): # type: (RangeSet, list[Comment]) -> None
        body = []
        comdicts = []
        for c in comments:
            if   (isinstance(c, comment.PositionalComment)
                  and c.path in ranges
                  and c.line in ranges[c.path]):
                comdicts.append(c.to_github_api_comment(ranges))
            else:
                body.append(c.to_github_api_body_fragment())
        
        query = gql("""
        mutation AddPullRequestReview($vars:AddPullRequestReviewInput!) {
          addPullRequestReview(input: $vars) {
            pullRequestReview {
              id
            }
          }
        }
        """)
        variables = dict(
            vars=dict(
                pullRequestId=self.prid,
                body='\n'.join(body),
                event='COMMENT',
                comments=comdicts,
                ))

        print variables
    
        print(self.client.execute(
            query,
            variables,
            ))

    def get_modified_ranges(self): # type: () -> dict[str, RangeSet]
        files = {}

        http_stream = self.get_diff_via_urllib2()
        for patch in unidiff.PatchSet.parse(
              http_stream,
              None):

            ranges = []
            hunk_base_position = 1
            for hunk in patch:
                last_github_pos = None
                last_github_start = None
                last_target = None
                last_target_start = None
                target_count = 0
                for line in hunk.target_lines():
                    # This is the position in the coordinate system that github uses.
                    github_pos = hunk_base_position + line.diff_line_no - hunk[0].diff_line_no
                    target_count += 1
                    if last_github_pos is not None and last_github_pos + 1 != github_pos:
                        ranges.append((last_target_start,
                                       last_target + 1,
                                       (last_target_start, last_github_start)))
                    if last_github_pos is None or last_github_pos + 1 != github_pos:
                        last_github_start = github_pos
                        last_target_start = line.target_line_no
                    last_github_pos = github_pos
                    last_target = line.target_line_no
                    assert last_github_start + line.target_line_no - last_target_start == github_pos
                    # positions.append(pos)
                if last_github_pos is not None:
                    ranges.append((last_target_start,
                                   last_target + 1,
                                   (last_target_start, last_github_start)))
                # I don't understand why the +1 is necessary, but
                # positions are wrong without it.
                hunk_base_position += len(hunk) + 1
            files[patch.path] = TargetToGitHubLineMap(ranges)
        return files
    
    def get_pull_request_url(self): # type: () -> str
        # We need repo (already checked), and pull request.
        if not self.options.pull_request:
            raise UserError('Missing mandatory "--pull-request 123" arguments')
        return 'https://api.github.com/repos/%s/%s/pulls/%d' % (gtr.urlencode(self.options.repo_owner),
                                                                gtr.urlencode(self.options.repo_name),
                                                                self.options.pull_request)
    
    def get_diff_via_urllib2(self): # type: () -> stream
        url = self.get_pull_request_url()
        headers = {'Authorization':'token %s' % self.token,'Accept':'application/vnd.github.v3.diff'}
        request = urllib2.Request(url, headers = headers)
        context = ssl._create_unverified_context()
        return urllib2.urlopen(request, context=context)

    @property
    def token(self):
        return self.repo.token

    # Useful for testing the github pull request integration
    def dump_last_review(self):
        query = gql("""
        query PullRequestDump($number:Int!, $owner:String!, $name:String!) {
          repository(owner:$owner, name:$name) {
            pullRequest(number:$number) {
              reviews(last:1){
                nodes{
                  author{login},
                  body,
                  comments(first:100){
                    nodes{
                      body,
                      path,
                      position
                    }
                  }
                }
              }
            }
          }
        }
        """)

        variables = dict(
            number=self.number,
            owner=self.options.repo_owner,
            name=self.options.repo_name,
            )
        response = self.client.execute(query, variables)
        return response['repository']['pullRequest']['reviews']

    

class Repo(object):
    
    def get_pr_id(self, user_facing_pr_id): # type: (int) -> int
        query = gql("""
        query FindPullRequestID($prid:Int!, $owner:String!, $name:String!) {
          repository(owner:$owner, name:$name) {
            pullRequest(number:$prid) {
              id
            }
          }
        }
        """)

        variables = dict(
            prid=user_facing_pr_id,
            owner=self.options.repo_owner,
            name=self.options.repo_name,
            )
        response = self.client.execute(query, variables)
        return response['repository']['pullRequest']['id']

    def get_pull_request(self, user_facing_pr_id): # type: (int) -> PullRequest
        return PullRequest(self, user_facing_pr_id, self.get_pr_id(user_facing_pr_id))
    
    @property
    def token(self):
        if not self.options.token:
            raise UserError('Missing mandatory --token argument.  Visit https://github.com/settings/tokens/new to generate a token.')
        return self.options.token
    
    def make_client(self): # type: () -> Client
        _transport = RequestsHTTPTransport(
            url='https://api.github.com/graphql',
            use_json=True,
            headers={'Authorization': 'token %s' % self.token},
        )
        return Client(
            transport=_transport,
            fetch_schema_from_transport=True,
        )
    
    def split_repo(self): # type: () -> None
        repo = self.options.repo
        if repo.startswith('git@'):
            raise UserError('Expected --repo argument %r to begin with https://github.com/' % repo)
        if repo.startswith('https://'):
            if not repo.startswith('https://github.com/'):
                raise UserError('Expected --repo argument %r to begin with https://github.com/' % repo)
            repo = repo[len('https://github.com/'):]
        if repo.endswith('.git'):
            repo = repo[:-len('.git')]
        r = repo.split('/')
        if len(r) != 2:
            raise UserError("Expected --repo argument %r to have the form https://github.com/octocat/Hello-World.git" % self.options.repo)
        self.options.repo_owner = r[0]
        self.options.repo_name = r[1]
    
    def __init__(self, options): # type: (argparse.Namespace) -> None
        self.options = options
        if options.repo:
            self.split_repo()
        else:
            raise UserError('Missing mandatory --repo flag')
        self.client = self.make_client()
