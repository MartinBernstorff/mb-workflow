from fixit.testing import add_lint_rule_tests_to_module

from lint_rules import no_raise

add_lint_rule_tests_to_module(globals(), [no_raise.NoRaise(), no_raise.NoRaiseAtTyperBoundary()])
