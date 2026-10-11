from app.core.verification.conflicts import mark_field_conflicts
from app.schemas.evidence import VerifiedFact


def fact(fid, value):
    return VerifiedFact(fact_id=fid, candidate_id="c1", field="weight", value=value,
                        evidence_id="e1", excerpt=f"重量 | {value}", status="supported")


def test_disagreeing_values_stay_separate_and_conflicting():
    facts, unresolved = mark_field_conflicts([fact("f1", "1.24kg"), fact("f2", "1.29kg")])
    assert [item.status for item in facts] == ["conflicting", "conflicting"]
    assert [item.value for item in facts] == ["1.24kg", "1.29kg"]
    assert len(unresolved) == 1
    assert unresolved[0].field == "weight"
    assert "1.24kg" in unresolved[0].description
    assert "1.29kg" in unresolved[0].description


def test_identical_values_are_not_a_conflict():
    facts, unresolved = mark_field_conflicts([fact("f1", "1.24kg"), fact("f2", "1.24kg")])
    assert unresolved == []
    assert all(item.status == "supported" for item in facts)
