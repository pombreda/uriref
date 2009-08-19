"""uriref - extensible URI parser.

This code provides regular expressions to validate and parse Universal Resource 
Identifiers as defined by (the BNF in) RFC 2396. 

Each BNF term is translated to Python Regular Expression. The resulting set of 
partial expressions are merged using string formatting and compiled into regex 
object to match absolute and relative references, and some other parts of URIs 
(URLs and URNs). This method does not provide the most optimized expressions, 
but is very precise and easy to work with.


Uniform Resource Indicator parts
--------------------------------
This diagram breaks a reference up into its parts, using the names from the BNF
terms in RFC 2396. Only the major terms are shown.

::

    ( domainlabel "." ) toplabel [ "." ]
    ------------------------------------
              |
           hostname | IPv4address
           ----------------------         *pchar *( ";" param ) 
                     |                    ---------------------
                   host [ ":" port ]               |
                   -----------------        *--------------*
                         |                  |              |
   [ [ userinfo "@" ] hostport ]         segment *( "/" segment )
   -----------------------------         ------------------------
               |                              |
             server | reg_name        "/"  path_segments
             -----------------        ------------------
                       |                        |
                       |               *--------*----------------------*
                       |               |        |                      |
                "//" authority [ abs_path ]     |    rel_segment [  abs_path ]
                ---------------------------     |    -------------------------
                              |                 |               |
            *-----------------*                 |               |
            |          *------|------------*----*               |
            |          |      |            |                    *---*
            |          |      |            |                        |
            |          |   ( net_path | abs_path | opaque_part | rel_path ) [ "?" query ]
            |          |   --------------------------------------------------------------
            |          |                        |
       ( net_path | abs_path ) [ "?" query]     |
       ------------------------------------     |
                        |                       |
        scheme ":" ( hier_part | opaque_part )  |
        --------------------------------------  |
                                 |              |
                           [ absoluteURI | relativeURI ] [ "#" fragment ]
                           ----------------------------------------------
                                               |
                                               |
                                         URI-reference

See: http://www.faqs.org/rfcs/rfc2396.html

The only deviation between the RFC's BNF terms and the regular expressions groups
is that the `net_path` *match group* is the `abs_path` of the `net_path` *BNF term*.
Otherwise these terms give difficulties with regex nesting (as group id's
should be unique).

There are three types of path found in URIs:

- net_path, abs_path in uri with authority given
- abs_path, absolute, rooted paths but no authority (any other abs_path)
- rel_path, relative paths (no authority possible)

`rel_path` only appears in relative URIs, `net_path` and `abs_path` in both
relative and absolute URIs.


Usage of this module
--------------------
Most importantly, this module provides the compiled expressions `relativeURI`
and `absoluteURI` to match the respective reference notations. Function `match`
takes any reference and uses the compiled expression `scheme` to determine
if the string represents a relative or absolute reference.

The function `parseuri` uses the RegEx match objects return by `match` and
returns a six-part tuple such as Python's stdlib urlparse.

In addition, each part is available as attribute on instances of `URIRef`,
where paths gives any of the types of path found::

  >>> from cllct.uri import URIRef
  >>> URIRef('file://home/test').path


Extending to match specific URIs
--------------------------------
Patterns are named after their BNF terms and kept in dictionaries.

- `partial_expressions` contains the translated BNF terms from RFC 2396,
  which is merged into `expressions`.
- `grouped_partial_expressions` adds some match group id's to the partial
  expressions, `grouped_expressions` contains the merged form of these.

The parts in these dictionaries can used to build your own custom regex's
for URI matching. For example, to match `mysql://` style links one could
create an regex object as follows::

  grouped_partial_expressions['mysq_db_ref'] = \
      r"^mysql: // %(authority)s / (?P<db> %(pchar)s*)$"
  mysql_link_expr = merge_strings(grouped_partial_expressions)['mysq_db_ref']
  mysql_link_re = re.compile(mysql_link_expr, re.VERBOSE)

See above diagram or the RFC for the part names. Because the dictionary with 
match-group IDs is used (and one is added, 'db'), this results in a match 
object with the following nicely named groups::

  __________<mysql://user:withpass@dbhost:3306/database>
  userinfo :         user:withpass
  host     :                       dbhost
  port     :                              3306
  db       :                                   database

Examples of references
----------------------
::

  _____________<http://user@sub.domain.org:80/path/to/leaf.php?query=arg&q=foo#fragment>
  scheme      : http
  authority   :        user@sub.domain.org:80
  userinfo    :        user
  host        :             sub.domain.org
  port        :                            80
  net_path    :                              /path/to/leaf.php
  query       :                                                query=arg&q=foo
  fragment    :                                                                fragment

::

  _____________<ftp://usr:pwd@example.org:4321/pub/>
  scheme      : ftp
  authority   :       usr:pwd@example.org:4321
  userinfo    :       usr:pwd
  host        :               example.org
  port        :                           4321
  net_path    :                               /pub/

::

  _____________<mid:some-message@example.org>
  scheme      : mid
  opaque_part :     some-message@example.org

::

  _____________<service?query=foo>
  rel_path    : service
  query       :         query=foo


See bin/parseuri for interactive parsing and tabular parts rendering.

Misc.
-----
- TODO: better parsing of paths, parameters, testing.
- XXX: stdlib 'urlparse' only allows parameters on the last path segment.
- TODO: update to RFC 3986

References
----------
.. [RFC 2396] `Uniform Resource Identifiers (URI): Generic Syntax`, 
              T. Berners-Lee et al., 1998 <http://tools.ietf.org/html/rfc2396>
.. [RFC 3986] `Uniform Resource Identifiers (URI): Generic Syntax`, 
              T. Berners-Lee et al., 2005 <http://tools.ietf.org/html/rfc3986>

"""
import re
import pprint


# Expressions
"""
A dictionary of Regular Expressions as transcribed from RFC 2396 BNF, 
parts are referenced using Python's string formatting notation.
"""
partial_expressions = {
    'digit': r"0-9",
    'lowalpha': r"a-z",
    'upalpha': r"A-Z",
    'alpha': r"%(lowalpha)s%(upalpha)s",
    'alphanum': r"%(alpha)s%(digit)s",
    'escaped': r"%%a-zA-Z0-9",
    'mark': r"- _ \. ! ~ * ' ( )",
    'unreserved': r"%(mark)s%(alphanum)s",
    'reserved': r"; / ? : @ & = + $ ,",
    'uric': r"[%(unreserved)s%(reserved)s%(escaped)s]",
    'query': r"%(uric)s*",
    'fragment': r"%(uric)s*",
    'pchar': r"[%(unreserved)s%(escaped)s:@&=+$,]",
    'param': r"%(pchar)s*",
    'segment': r"(%(pchar)s* (; %(param)s)*)",
    'path_segments': r"(%(segment)s) (/ %(segment)s)*",
    'abs_path': r"/ %(path_segments)s",
    'port': r"[0-9]+",
    'IPv4address': r"([0-9]+ \. [0-9]+ \. [0-9]+ \. [0-9]+)",
    'toplabel': r"([%(alpha)s] | ([%(alpha)s] [-%(alphanum)s]* [%(alphanum)s]))",
    'domainlabel': r"([%(alphanum)s] | ([%(alphanum)s][-%(alphanum)s]*[%(alphanum)s]))",
    'hostname': r"(%(domainlabel)s \.)* %(toplabel)s (\.)? ", # RFC 2396 says there can be a trailing "." for local domains
    'host': r"(%(hostname)s |    %(IPv4address)s)",
    'hostport': r"%(host)s ( : %(port)s )?",
    'userinfo': r"[%(unreserved)s %(escaped)s $ , ; : & = +]*",
    'reg_name': r"[%(unreserved)s %(escaped)s $ , ; : & = +]*",
    'server': r"(%(userinfo)s @)? %(hostport)s",
    'authority': r"%(server)s | %(reg_name)s",
    'scheme': r"[%(alpha)s] [- + \. %(alpha)s %(digit)s]*",
    'rel_segment': r"[ %(unreserved)s %(escaped)s ; @ & = + $ ,]{1}",
    'rel_path': r"%(rel_segment)s (%(abs_path)s)?",
    'net_path': r"// %(authority)s %(abs_path)s",
    'uric_no_slash': r"[%(unreserved)s %(escaped)s ; ? : @ & = + $ ,]",
    'opaque_part': r"%(uric_no_slash)s %(uric)s*",
    'hier_part': r"((%(net_path)s) | (%(abs_path)s)) (\? %(query)s)?",
    'relativeURI': r"((%(net_path)s) | (%(abs_path)s) | (%(rel_path)s) | (%(opaque_part)s)) (\? %(query)s)?",
    'absoluteURI': r"%(scheme)s : (%(hier_part)s) | (%(opaque_part)s)",
    'URI_reference': r"((%(absoluteURI)s | %(relativeURI)s) (\# %(fragment)s)?)",
}

def merge_strings(strings):
    """
    Format every string in dictionary `strings` using the same dictionary until 
    every string has been formatted (merged). Returns a dictionary with all
    string formatting references replaced.
    
    Important! More than one non-existing formatting reference will cause an infinite loop.
    """

    results = {}

    names = strings.keys()
    while names:
        # cycle through the list until all strings are resolved
        name = names.pop(0)
        try:
            results[name] = (strings[name] % results)
        except Exception, e:
            names.append(name)
            # one unformatted string left while every other string is merged:
            assert name != names[0], 'Cannot resolve %s' % name

    return results

# Merge unformatted strings
expressions = merge_strings(partial_expressions)


# Give some regex groups an ID
grouped_partial_expressions = {
    'userinfo': r"(?P<userinfo> [%(unreserved)s %(escaped)s ; : & = + $ ,]*)",
    'port': r"(?P<port> [0-9]*)",
    'host': r"(?P<host> %(hostname)s | %(IPv4address)s)",
    'query': r"(?P<query> %(uric)s*)",
    'abs_path': r"/ %(path_segments)s",
    'authority': r"(?P<authority> (%(server)s) | %(reg_name)s)",
    'net_path': r"// %(authority)s (?P<net_path> %(abs_path)s)",
    'hier_part': r"((%(net_path)s) | (?P<abs_path> %(abs_path)s)) (\? %(query)s)?",
    'opaque_part': r"(?P<opaque_part> %(uric_no_slash)s %(uric)s*)",
    'scheme': r"(?P<scheme> %s)" % partial_expressions['scheme'],
    'relativeURI': r"((%(net_path)s) | (?P<abs_path> %(abs_path)s) | (?P<rel_path> %(rel_path)s) | (%(opaque_part)s)) (\? %(query)s)?",
    'absoluteURI': r"%(scheme)s : (%(hier_part)s | %(opaque_part)s)",
}
for k, e in partial_expressions.items():
    grouped_partial_expressions.setdefault(k, e)

# Merge unformatted strings
grouped_expressions = merge_strings(grouped_partial_expressions)


### Regex objects for matching relative and absolute URIRef notations

relativeURI = re.compile(r"^%(relativeURI)s(\# (?P<fragment> %(fragment)s))?$" % grouped_expressions, re.VERBOSE)
"a URI with no scheme-part and optional fragment part"

absoluteURI = re.compile(r"^%(absoluteURI)s(\# (?P<fragment> %(fragment)s))?$" % grouped_expressions, re.VERBOSE)
"a URI with scheme-part and optional fragment part"


### Regex objects of URIRef strings

abs_path = re.compile(r"^%(abs_path)s$" % grouped_expressions, re.VERBOSE)
"matches an absolute path"

net_path = re.compile(r"^%(net_path)s$" % grouped_expressions, re.VERBOSE)
"matches a full net_path, ie. //host/path "

scheme = re.compile(r"^%(scheme)s:" % grouped_expressions, re.VERBOSE)
"matches the scheme part"

net_scheme = re.compile(r"^%(scheme)s:(\/\/)?" % grouped_expressions, re.VERBOSE)
"matches the scheme part and tests for a net_path"


### Functions to validate and parse URIRef strings

def match(uriref):
    """
    Match given `uriref` string using a Regular Expression.

    If the passed in string starts with a valid scheme sequence it is treated as
    an absolute-URI, otherwise a relative one.

    Returns the match object or None.
    """

    if scheme.match(uriref):
        return absoluteURI.match(uriref)
    else:
        return relativeURI.match(uriref)


def urlparse(uriref):
    """
    Comparible with Python's stdlib urlparse, parse a URL into 6 components:

        <scheme>://<netloc>/<path>;<params>?<query>#<fragment>

    and no further split of the components. Returns tuple.
    """

    md = match(uriref).groupdict()

    netloc = None
    if 'hostname' in md:
        netloc = md['hostname']
        if 'userinfo' in md:
            netloc = "%s@%s" % (md['userinfo'], netloc)
        if 'port' in md:
            netloc += ':%i' % md['port']

    path = None
    if 'abs_path' in md:
        path = md['abs_path']
    elif 'net_path' in md:
        path = md['net_path']

    last_params = None

    return md['scheme'], netloc, path, last_params, md['query'], md['fragment']


def is_uri(uristr):
    """
    TODO: uri.path can contains spaces... if this is restricted, is it possible
    to deterimine if a random string is a valid reference (absolute or
    relative/local)?
    """

    uri = URIRef(uristr)
    if uri.scheme:
        return True

    elif uri.path:
        print 'uri.path',uri.path
        return True


# TODO: compare regex results against urlparse.urlsplit

### URI parsing based on urlparse
import urlparse

def isfragment(url, location=None):

    """Return true if URL links to a fragment.
    """

    urlparts = urlparse.urlsplit(url)
    if not location and not urlparts[4] is None:
        return False

    elif location and urlparts[4]:
        locparts = urlparse.urlsplit(location)
        # scheme
        if urlparts[0] and not urlparts[0] is locparts[0]:
            return False
        # domain
        elif not onsamedomain(url, location):
            return False
        # path
        elif urlparts[2] and not urlparts[2] is locparts[2]:
            return False
        # query
        elif urlparts[3] and not urlparts[3] is locparts[3]:
            return False
        return True

    elif urlparts[4]:
        return True

    return False

def get_hostname(url):

    """Return the hostname of the given `url`.
    """

    hostname = urlparse.urlsplit(url)[1]
    if ':' in hostname:
        hostname = hostname.split(':').pop(0)
    return hostname

def onsamedomain(url1, url2):

    """Examine the URLs and return true if they are on the same
    domain (but perhaps in a different subdomain).
    """

    url1parts = urlparse.urlsplit(url1)
    url2parts = urlparse.urlsplit(url2)
    host1, host2 = url1parts[1], url2parts[1]
    host1, host2 = host1.split('.'), host2.split('.')

    # TLD
    if len(host1) > 0 and len(host2) > 0:
        part1, part2 = host1.pop(), host2.pop()
        if not part1 == part2:
            return False
    # domain
    if len(host1) > 0 and len(host2) > 0:
        part1, part2 = host1.pop(), host2.pop()
        if not part1 == part2:
            return False
        else:
            return True
    return False



class URIRef(str):

    """
    Convenience class with regular expression parsing of URI's and
    formatting back to string representation again.
    """

    def __new__(type, *args, **kwds):
        return str.__new__(type, *args)

    def __init__(self, uri, opaque_targets=[]):
        "Construct instance with match object and parts dictionary."
        "`opaque_targets` indicates partnames which may 'default' to opaque_part."

        str.__init__(uri)
        self.__match__ = match(uri)
        self.__groups__ = self.__match__.groupdict()

        self.opaque_targets = opaque_targets
        "The partnames that if not set get the value of opaque_part/"

    @property
    def query(self, *value):
        return self.__groups__['query']

    @property
    def path(self, *value):
        for path in 'abs_path', 'rel_path', 'net_path':
            if path in self.__groups__ and self.__groups__[path]:
                return self.__groups__[path]

    def __getattr__(self, name):
        part = None
        if name in self.__groups__:
            part = self.__groups__[name]
        if not part and name in self.opaque_targets:
            part = self.__groups__['opaque_part']
        if not part and name == 'path':
            part = self.path
        return part

    def generate_signature(self):
        sig = []
        if self.scheme:
            sig.extend((self.scheme, ':'))

        if self.host:
            sig.append('//')
            if self.userinfo:
                sig.extend((self.userinfo, '@'))
            sig.append(self.host)
            if self.port:
                sig.extend((':', self.port))

        if self.path:
            sig.append(self.path)
        elif self.opaque_part:
            sig.append(self.opaque_part)
        else:
            sig.append('/')

        if self.query:
            sig.extend(('?', self.query))
        if self.fragment:
            sig.extend(('#', self.fragment))

        return tuple(sig)

    def __repr__(self):
        return "URIRef(%s)" % self

    def __str__(self):
        return "".join(self.generate_signature())



def print_complete_expressions():
    print "**relativeURI**::\n\t", r"^%(relativeURI)s(\# (?P<fragment> %(fragment)s))?$" % expressions
    print
    print "**absoluteURI**::\n\t", r"^%(absoluteURI)s(\# (?P<fragment> %(fragment)s))?$" % expressions
    print
    print "**abs_path**::\n\t", r"%(abs_path)s" % expressions
    print
    print "**net_path**::\n\t", r"%(net_path)s" % expressions
    print
    print "**scheme**::\n\t", r"%(scheme)s:" % expressions
    print
    print "**net_scheme**::\n\t", r"%(scheme)s:(\/\/)?" % expressions
    print


if __name__ == '__main__':
    print_complete_expressions()