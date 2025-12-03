"""Tests for render_compose.py module."""

import pytest
from bug_finding.src.render_compose import parse_cpu_range, format_cpu_list


class TestParseCpuRange:
    """Test parse_cpu_range function."""

    def test_simple_range(self):
        """Test simple range format like '0-7'."""
        result = parse_cpu_range('0-7')
        assert result == [0, 1, 2, 3, 4, 5, 6, 7]

    def test_single_core(self):
        """Test single core specification."""
        result = parse_cpu_range('5')
        assert result == [5]

    def test_comma_separated_list(self):
        """Test comma-separated list format like '0,2,4,6'."""
        result = parse_cpu_range('0,2,4,6')
        assert result == [0, 2, 4, 6]

    def test_mixed_format(self):
        """Test mixed format with ranges and individual cores."""
        result = parse_cpu_range('0-3,8,12-15')
        assert result == [0, 1, 2, 3, 8, 12, 13, 14, 15]

    def test_with_spaces(self):
        """Test that spaces are handled correctly."""
        result = parse_cpu_range('0-3, 8, 12-15')
        assert result == [0, 1, 2, 3, 8, 12, 13, 14, 15]

    def test_duplicates_removed(self):
        """Test that duplicate cores are removed."""
        result = parse_cpu_range('0-3,2-5')
        assert result == [0, 1, 2, 3, 4, 5]

    def test_unsorted_input(self):
        """Test that output is sorted even with unsorted input."""
        result = parse_cpu_range('8,0-3,5')
        assert result == [0, 1, 2, 3, 5, 8]

    def test_large_range(self):
        """Test larger CPU range."""
        result = parse_cpu_range('0-15')
        assert result == list(range(16))

    def test_non_zero_start_range(self):
        """Test range not starting at 0."""
        result = parse_cpu_range('4-11')
        assert result == [4, 5, 6, 7, 8, 9, 10, 11]


class TestFormatCpuList:
    """Test format_cpu_list function."""

    def test_simple_list(self):
        """Test formatting a simple list."""
        result = format_cpu_list([0, 1, 2, 3])
        assert result == '0,1,2,3'

    def test_non_contiguous_list(self):
        """Test formatting non-contiguous cores."""
        result = format_cpu_list([0, 2, 4, 6])
        assert result == '0,2,4,6'

    def test_single_core(self):
        """Test formatting single core."""
        result = format_cpu_list([5])
        assert result == '5'

    def test_large_list(self):
        """Test formatting larger list."""
        result = format_cpu_list([0, 1, 2, 3, 4, 5, 6, 7])
        assert result == '0,1,2,3,4,5,6,7'


class TestRoundTrip:
    """Test round-trip conversion (parse -> format)."""

    def test_range_format(self):
        """Test that range format survives round-trip as comma-separated."""
        parsed = parse_cpu_range('0-7')
        formatted = format_cpu_list(parsed)
        assert formatted == '0,1,2,3,4,5,6,7'
        # Re-parse to verify consistency
        reparsed = parse_cpu_range(formatted)
        assert reparsed == parsed

    def test_list_format(self):
        """Test that list format survives round-trip."""
        original = '0,2,4,6'
        parsed = parse_cpu_range(original)
        formatted = format_cpu_list(parsed)
        assert formatted == original
        reparsed = parse_cpu_range(formatted)
        assert reparsed == parsed

    def test_mixed_format(self):
        """Test mixed format round-trip."""
        parsed = parse_cpu_range('0-3,8,12-15')
        formatted = format_cpu_list(parsed)
        reparsed = parse_cpu_range(formatted)
        assert reparsed == parsed
