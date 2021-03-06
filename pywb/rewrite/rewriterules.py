from pywb.utils.dsrules import BaseRule

from regex_rewriters import RegexRewriter, CSSRewriter, XMLRewriter
from regex_rewriters import JSLinkAndLocationRewriter, JSLinkOnlyRewriter
from regex_rewriters import JSLocationOnlyRewriter, JSNoneRewriter

from header_rewriter import HeaderRewriter
from html_rewriter import HTMLRewriter

import itertools
import re


#=================================================================
class RewriteRules(BaseRule):
    def __init__(self, url_prefix, config={}):
        super(RewriteRules, self).__init__(url_prefix, config)

        self.rewriters = {}

        #self._script_head_inserts = config.get('script_head_inserts', {})

        self.rewriters['header'] = config.get('header_class', HeaderRewriter)
        self.rewriters['css'] = config.get('css_class', CSSRewriter)
        self.rewriters['xml'] = config.get('xml_class', XMLRewriter)
        self.rewriters['html'] = config.get('html_class', HTMLRewriter)
        self.rewriters['json'] = config.get('json_class', JSLinkOnlyRewriter)

        self.parse_comments = config.get('parse_comments', False)

        # Custom handling for js rewriting, often the most complex
        self.js_rewrite_location = config.get('js_rewrite_location', 'location')

        # ability to toggle rewriting
        if self.js_rewrite_location == 'all':
            js_default_class = JSLinkAndLocationRewriter
        elif self.js_rewrite_location == 'location':
            js_default_class = JSLocationOnlyRewriter
            self.rewriters['json'] = JSNoneRewriter
        elif self.js_rewrite_location == 'none':
            js_default_class = JSNoneRewriter
            self.rewriters['json'] = JSNoneRewriter
        else:
            js_default_class = JSLinkOnlyRewriter

        # set js class, using either default or override from config
        self.rewriters['js'] = config.get('js_class', js_default_class)

        # add any regexs for js rewriter
        self._add_custom_regexs('js', config)

        # cookie rewrite scope
        self.cookie_scope = config.get('cookie_scope', 'default')

        req_cookie_rewrite = config.get('req_cookie_rewrite', [])
        for rc in req_cookie_rewrite:
            rc['rx'] = re.compile(rc.get('match', ''))

        self.req_cookie_rewrite = req_cookie_rewrite

    def _add_custom_regexs(self, field, config):
        regexs = config.get(field + '_regexs')
        if not regexs:
            return

        rewriter_cls = self.rewriters[field]

        #rule_def_tuples = RegexRewriter.parse_rules_from_config(regexs)
        parse_rules_func = RegexRewriter.parse_rules_from_config(regexs)

        def extend_rewriter_with_regex(urlrewriter):
            rule_def_tuples = parse_rules_func(urlrewriter)
            return rewriter_cls(urlrewriter, rule_def_tuples)

        self.rewriters[field] = extend_rewriter_with_regex
