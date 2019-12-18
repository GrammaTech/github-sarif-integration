import sys, bisect

class RangeMap(object):
    '''A map from integer ranges to values.  Uses a sparse
    representation with space costs linear in the number of ranges and
    lookup time logarithmic in the number of ranges.'''
    # Ranges should be a list of disjoint (lower, upper, value) triples in
    # sorted order.  Upper bounds are exclusive.
    def __init__(self, ranges, posinf=sys.maxint):
        self.ranges = [(lower, upper, value) for lower, upper, value in ranges if lower != upper]
        self.posinf = posinf
        last_upper = None
        for lower, upper, value in self.ranges:
            assert lower < upper
            assert upper < posinf
            if last_upper is not None:
                assert lower >= last_upper
            last_upper = upper

    def __getitem__(self, x):
        j = bisect.bisect(self.ranges, (x, self.posinf, None))
        if j == 0:
            raise KeyError(x)
        lower, upper, value = self.ranges[j - 1]
        if x >= lower and x < upper:
            return value
        raise KeyError(x)

    def __contains__(self, x):
        try:
            self[x]
            return True
        except KeyError:
            return False

    def get(self, x, default=None):
        try:
            return self[x]
        except KeyError:
            return default

    def __repr__(self):
        return '%s(%r, %r)' % (type(self).__name__, self.ranges, self.posinf)


