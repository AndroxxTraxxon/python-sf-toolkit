import pytest
from sf_toolkit.apimodels import ApiVersion, Limit, UserInfo


class TestApiVersion:
    """Tests for the ApiVersion class."""

    def test_init(self):
        """Test basic initialization with different parameter types."""
        # Test with float version
        version = ApiVersion(50.0, "Winter '21", "/services/data/v50.0")
        assert version.version == 50.0
        assert version.label == "Winter '21"
        assert version.url == "/services/data/v50.0"

        # Test with string version
        version = ApiVersion("51.0", "Spring '21", "/services/data/v51.0")
        assert version.version == 51.0
        assert version.label == "Spring '21"
        assert version.url == "/services/data/v51.0"

    def test_lazy_build_from_version(self):
        """Test lazy_build with version number inputs."""
        # Test with float
        version = ApiVersion.lazy_build(52.0)
        assert version.version == 52.0
        assert version.url == "/services/data/v52.0"

        # Test with string representing a float
        version = ApiVersion.lazy_build("53.0")
        assert version.version == 53.0
        assert version.url == "/services/data/v53.0"

    def test_lazy_build_from_url(self):
        """Test lazy_build with URL inputs."""
        # Test with URL string
        version = ApiVersion.lazy_build("/services/data/v54.0")
        assert version.version == 54.0
        assert version.url == "/services/data/v54.0"

    def test_lazy_build_from_instance(self):
        """Test lazy_build with existing ApiVersion instance."""
        original = ApiVersion(55.0, "Summer '22", "/services/data/v55.0")
        version = ApiVersion.lazy_build(original)
        assert version is original  # Should return the same instance

    def test_lazy_build_invalid_input(self):
        """Test lazy_build with invalid inputs."""
        with pytest.raises(TypeError, match="Unable to build an ApiVersion from value"):
            ApiVersion.lazy_build(None)

        with pytest.raises(TypeError, match="Unable to build an ApiVersion from value"):
            ApiVersion.lazy_build(["not", "valid"])

    def test_str_representation(self):
        """Test string representation."""
        version = ApiVersion(56.0, "Winter '23", "/services/data/v56.0")
        assert str(version) == "Salesforce API Version Winter '23 (56.0)"
        assert repr(version) == "ApiVersion(version=56.0, label='Winter '23')"

    def test_float_conversion(self):
        """Test conversion to float."""
        version = ApiVersion(57.0, "Spring '23", "/services/data/v57.0")
        assert float(version) == 57.0

    def test_equality(self):
        """Test equality comparisons."""
        version1 = ApiVersion(58.0, "Summer '23", "/services/data/v58.0")
        version2 = ApiVersion(58.0, "Different Label", "/services/data/v58.0")
        version3 = ApiVersion(59.0, "Fall '23", "/services/data/v59.0")

        # Same version number should be equal regardless of label
        assert version1 == version2
        assert version1 != version3

        # Test equality with float
        assert version1 == 58.0
        assert version1 != 59.0

        # Test equality with int
        assert version1 == 58
        assert version1 != 59

        # Test equality with other types
        assert version1 != "58.0"
        assert version1 is not None
        assert version1 != object()

    def test_hash(self):
        """Test hash function."""
        version = ApiVersion(60.0, "Winter '24", "/services/data/v60.0")
        assert hash(version) == hash(60.0)

        # Test in dictionary
        versions_dict = {version: "test"}
        assert versions_dict[version] == "test"

        # Same version number should have same hash
        version2 = ApiVersion(60.0, "Different Label", "/different/url")
        assert hash(version) == hash(version2)


class TestOrgLimit:
    """Tests for the OrgLimit class."""

    def test_init(self):
        """Test basic initialization."""
        limit = Limit("DailyApiRequests", 1000000, 500000)
        assert limit.name == "DailyApiRequests"
        assert limit.max_value == 1000000
        assert limit.current_value == 500000

    def test_repr(self):
        """Test string representation."""
        limit = Limit("DailyApiRequests", 1000000, 500000)
        assert (
            repr(limit)
            == "OrgLimit(name='DailyApiRequests', current_value=500000, max_value=1000000)"
        )

    def test_remaining(self):
        """Test remaining method."""
        limit = Limit("DailyApiRequests", 1000000, 250000)
        assert limit.remaining() == 750000

    def test_usage_percentage(self):
        """Test usage_percentage method."""
        # 50% usage
        limit = Limit("DailyApiRequests", 1000000, 500000)
        assert limit.usage_percentage() == 50.0

        # 0% usage
        limit = Limit("DailyApiRequests", 1000000, 0)
        assert limit.usage_percentage() == 0.0

        # 100% usage
        limit = Limit("DailyApiRequests", 1000000, 1000000)
        assert limit.usage_percentage() == 100.0

        # Handle division by zero
        limit = Limit("Unlimited", 0, 0)
        assert limit.usage_percentage() == 0.0

    def test_is_critical(self):
        """Test is_critical method."""
        # Below threshold
        limit = Limit("DailyApiRequests", 1000000, 800000)  # 80%
        assert not limit.is_critical()
        assert not limit.is_critical(85.0)

        # At threshold
        limit = Limit("DailyApiRequests", 1000000, 900000)  # 90%
        assert limit.is_critical()  # Default threshold is 90%
        assert not limit.is_critical(95.0)  # But not critical at 95% threshold

        # Above threshold
        limit = Limit("DailyApiRequests", 1000000, 950000)  # 95%
        assert limit.is_critical()
        assert limit.is_critical(90.0)


class TestUserInfo:
    """Tests for the UserInfo class."""

    @pytest.fixture
    def user_info_data(self):
        """Fixture providing sample UserInfo data."""
        return {
            "user_id": "005x0000000abcdAAA",
            "name": "Test User",
            "email": "test@example.com",
            "organization_id": "00Dx0000000abcdAAA",
            "sub": "https://login.salesforce.com/id/00Dx0000000abcdAAA/005x0000000abcdAAA",
            "email_verified": True,
            "given_name": "Test",
            "family_name": "User",
            "zoneinfo": "America/Los_Angeles",
            "photos": {
                "picture": "https://example.com/picture.jpg",
                "thumbnail": "https://example.com/thumbnail.jpg",
            },
            "profile": "https://example.com/profile",
            "picture": "https://example.com/picture.jpg",
            "address": {"country": "US", "street": "123 Main St"},
            "urls": {
                "enterprise": "https://example.my.salesforce.com",
                "metadata": "https://example.my.salesforce.com/services/Soap/m/",
            },
            "active": True,
            "user_type": "STANDARD",
            "language": "en_US",
            "locale": "en_US",
            "utcOffset": -28800000,  # in milliseconds (-8 hours)
            "updated_at": "2023-01-01T00:00:00Z",
            "preferred_username": "test@example.com",
            "custom_field": "custom value",  # Additional field
        }

    def test_init(self, user_info_data):
        """Test basic initialization."""
        user_info = UserInfo(**user_info_data)

        # Verify core attributes
        assert user_info.user_id == "005x0000000abcdAAA"
        assert user_info.name == "Test User"
        assert user_info.email == "test@example.com"
        assert user_info.organization_id == "00Dx0000000abcdAAA"
        assert user_info.email_verified is True
        assert user_info.given_name == "Test"
        assert user_info.family_name == "User"

        # Verify dictionary attributes
        assert user_info.photos["picture"] == "https://example.com/picture.jpg"
        assert user_info.address["country"] == "US"
        assert user_info.urls["enterprise"] == "https://example.my.salesforce.com"

        # Verify additional info is stored
        assert user_info.additional_info["custom_field"] == "custom value"

    def test_init_with_empty_dicts(self):
        """Test initialization with empty or missing dictionary fields."""
        # Create with minimal required fields, omitting dict fields
        minimal_data = {
            "user_id": "005x0000000abcdAAA",
            "name": "Test User",
            "email": "test@example.com",
            "organization_id": "00Dx0000000abcdAAA",
            "sub": "https://login.salesforce.com/id/00Dx0000000abcdAAA/005x0000000abcdAAA",
            "email_verified": True,
            "given_name": "Test",
            "family_name": "User",
            "zoneinfo": "America/Los_Angeles",
            "profile": "https://example.com/profile",
            "picture": "https://example.com/picture.jpg",
            "active": True,
            "user_type": "STANDARD",
            "language": "en_US",
            "locale": "en_US",
            "utcOffset": -28800000,
            "updated_at": "2023-01-01T00:00:00Z",
            "preferred_username": "test@example.com",
            "photos": {},
            "address": {},
            "urls": {},
        }

        user_info = UserInfo(**minimal_data)

        # Verify dictionary fields are empty but not None
        assert user_info.photos == {}
        assert user_info.address == {}
        assert user_info.urls == {}

    def test_repr(self, user_info_data):
        """Test string representation."""
        user_info = UserInfo(**user_info_data)
        expected_repr = "UserInfo(name='Test User', user_id='005x0000000abcdAAA', organization_id='00Dx0000000abcdAAA')"
        assert repr(user_info) == expected_repr
