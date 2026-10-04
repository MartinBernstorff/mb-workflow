from fixit.testing import add_lint_rule_tests_to_module

from lint_rules import no_dunder_all

add_lint_rule_tests_to_module(globals(), [no_dunder_all.NoDunderAll()])
