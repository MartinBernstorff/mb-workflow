from typing import TYPE_CHECKING

from safe_result import Err, Result

from mb_workflow.b_core.d_domain_model.issue import IssueIdentifier, LabelName
from mb_workflow.c_infrastructure.credentials import CredentialsError, MissingCredentialsError
from mb_workflow.c_infrastructure.lazy_linear import LazyLinear, LazyLinearClaims

if TYPE_CHECKING:
    from mb_workflow.c_infrastructure.linear import LinearApiKey


MISSING = "No Linear credentials for this repository."


def missing_key() -> Result[LinearApiKey, CredentialsError]:
    return Err(MissingCredentialsError(MISSING))


def test_a_lazy_registry_reads_no_key_until_it_is_used() -> None:
    read = LazyLinearClaims(missing_key).claims(IssueIdentifier.fake())
    assert isinstance(read, Err)
    assert MISSING in str(read.error)


def test_a_lazy_tracker_returns_the_missing_key_from_a_lookup() -> None:
    read = LazyLinear(missing_key).read_issue(IssueIdentifier.fake())
    assert isinstance(read, Err)
    assert MISSING in str(read.error)


def test_a_lazy_tracker_reads_no_key_until_it_is_used() -> None:
    removed = LazyLinear(missing_key).remove_label(IssueIdentifier.fake(), LabelName("claimed"))
    assert isinstance(removed, Err)
    assert MISSING in str(removed.error)
