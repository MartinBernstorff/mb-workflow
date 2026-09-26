from mb_workflow.b_core.d_domain_model.clock import Today
from mb_workflow.b_core.d_domain_model.issue import CreatedAfter, CreatedWithin


def test_the_window_starts_the_lookback_before_today() -> None:
    assert CreatedAfter.of(CreatedWithin.fake(), Today.fake()) == CreatedAfter.fake()
