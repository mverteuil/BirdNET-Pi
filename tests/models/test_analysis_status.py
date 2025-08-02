from birdnetpi.models.analysis_status import AnalysisStatus


class TestAnalysisStatus:
    """Test the AnalysisStatus enum."""

    def test_enum_values(self):
        """Should have correct enum values."""
        assert AnalysisStatus.PENDING.value == "PENDING"
        assert AnalysisStatus.IN_PROGRESS.value == "IN_PROGRESS"
        assert AnalysisStatus.COMPLETED.value == "COMPLETED"
        assert AnalysisStatus.FAILED.value == "FAILED"

    def test_enum_members(self):
        """Should have all expected enum members."""
        expected_members = {"PENDING", "IN_PROGRESS", "COMPLETED", "FAILED"}
        actual_members = {member.name for member in AnalysisStatus}
        assert actual_members == expected_members

    def test_string_representation(self):
        """Should have correct string representation."""
        assert str(AnalysisStatus.PENDING) == "AnalysisStatus.PENDING"
        assert str(AnalysisStatus.IN_PROGRESS) == "AnalysisStatus.IN_PROGRESS"
        assert str(AnalysisStatus.COMPLETED) == "AnalysisStatus.COMPLETED"
        assert str(AnalysisStatus.FAILED) == "AnalysisStatus.FAILED"

    def test_equality(self):
        """Should support equality comparison."""
        assert AnalysisStatus.PENDING == AnalysisStatus.PENDING
        assert AnalysisStatus.PENDING != AnalysisStatus.COMPLETED

    def test_iteration(self):
        """Should support iteration over enum members."""
        statuses = list(AnalysisStatus)
        assert len(statuses) == 4
        assert AnalysisStatus.PENDING in statuses
        assert AnalysisStatus.IN_PROGRESS in statuses
        assert AnalysisStatus.COMPLETED in statuses
        assert AnalysisStatus.FAILED in statuses
