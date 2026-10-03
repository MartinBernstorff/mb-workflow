# Code conventions

Clean as you go. Whenever you touch a file that has violations, fix those violations.

## Testing

* TE-3a: Tests should only specify literals that their outcomes depend on. Any literals that are asserted on should be assigned to a variable, and assert against that variable.
* TE-c8: Fakes should be stateful, and assertions should be against fake state.
* TE-m8: Mocking and patching is not allowed. Tests should never assert on implementation.
* TE-9c: Do _not_ maintain a `tests` folder. Instead, place tests next to the code they test, as `test_<module>.py`, or in the same file when possible.

## Observability

* OB-A7: Whenever something retries, log the retry and/or update a metric.

## Naming

* Do not allow free functions. At the call-site, it's hard to understand the scope. Instead, make them static methods on a class.
* Use descriptive method names. No `to(param)`, instead `to_<type>`.

## Types

* TY-c1: _Never_ allow primitives as function parameters, fields, etc. Instead, use a Pydantic `RootModel`. Enforced by `moon run noprim`.
* TY-a8: On each domain model/`RootModel`, add a `.fake` static method for testing. It should hold default values for every value. When the item is an aggregate, call the `.fake` of its member objects to construct the default values.
* TY-7e: Return errors as values using [safe-result](https://github.com/overflowy/safe-result).
  * Migration in progress. The cookbook is in MB-106. `test_raise_check.py` fails on any `raise` it does not allow, and `raise-baseline/` holds the remaining count per module. The check lowers a count when it drops; never raise one.
* TY-fg: Use nominal typing and explicit subtyping. E.g. if a class is implementing a protocol, also make it inherit that protocol.

## Modules

* MO-9r: When a module grows large enough that it needs multiple files, place it in a folder with its own `__init__` for exports.
* MO-t8: _Never_ maintain a `__all__` list. Instead, use direct imports.
* MO-kf: Avoid constants. Whenever you need a constant, consider whether it should be an argument for the caller instead.
