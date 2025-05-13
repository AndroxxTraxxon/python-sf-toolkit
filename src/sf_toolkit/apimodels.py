from typing import TypeVar


_T_ApiVer = TypeVar("_T_ApiVer", bound="ApiVersion")


class ApiVersion:
    """
    Data structure representing a Salesforce API version.
    https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/resources_versions.htm
    """

    version: float
    label: str
    url: str

    def __init__(self, version: float | str, label: str, url: str):
        """
        Initialize an ApiVersion object.

        Args:
            version: The API version number as a float
            label: The display label for the API version
            url: The URL for accessing this API version
        """
        self.version = float(version)
        self.label = label
        self.url = url

    @classmethod
    def lazy_build(cls, value) -> "ApiVersion":
        if isinstance(value, cls):
            return value
        elif isinstance(value, str):
            if value.startswith("/services/data/v"):
                version_number = float(value.removeprefix("/services/data/v"))
                return cls(version_number, f"{version_number:.01f}", value)
            else:
                # attempt to isolate version number from any other characters
                value = "".join(c for c in value if c.isdigit() or c == ".")
                version_number = float(value)
                return cls(
                    version_number,
                    f"{version_number:.01f}",
                    f"/services/data/v{version_number:.01f}",
                )

        elif isinstance(value, float):
            return cls(value, f"{value:.01f}", f"/services/data/v{value:.01f}")

        elif isinstance(value, int):
            value = float(value)
            return cls(value, f"{value:.01f}", f"/services/data/v{value:.01f}")

        elif isinstance(value, dict):
            return cls(**value)

        raise TypeError("Unable to build an ApiVersion from value %s", repr(value))

        raise TypeError("Unable to build an ApiVersion from value %s", repr(value))

    def __repr__(self) -> str:
        return f"ApiVersion(version={self.version}, label='{self.label}')"

    def __str__(self) -> str:
        return f"Salesforce API Version {self.label} ({self.version:.01f})"

    def __float__(self) -> float:
        return self.version

    def __eq__(self, other) -> bool:
        if isinstance(other, ApiVersion):
            return self.version == other.version and self.url == other.url
        elif isinstance(other, (int, float)):
            return self.version == float(other)
        return False

    def __hash__(self) -> int:
        return hash(self.version)


class UserInfo:
    """
    Data structure representing user information returned from the Salesforce OAuth2 userinfo endpoint.
    https://help.salesforce.com/s/articleView?id=sf.remoteaccess_using_userinfo_endpoint.htm
    """

    def __init__(
        self,
        user_id: str,
        name: str,
        email: str,
        organization_id: str,
        sub: str,
        email_verified: bool,
        given_name: str,
        family_name: str,
        zoneinfo: str,
        photos: dict[str, str],
        profile: str,
        picture: str,
        address: dict,
        urls: dict[str, str],
        active: bool,
        user_type: str,
        language: str,
        locale: str,
        utcOffset: int,
        updated_at: str,
        preferred_username: str,
        **kwargs,
    ):
        """
        Initialize a UserInfo object.

        Args:
            user_id: The user's Salesforce ID
            name: The user's full name
            email: The user's email address
            organization_id: The organization's Salesforce ID
            sub: Subject identifier
            email_verified: Whether the email has been verified
            given_name: The user's first name
            family_name: The user's last name
            zoneinfo: The user's timezone (e.g., "America/Los_Angeles")
            photos: Dictionary of profile photos (picture, thumbnail)
            profile: URL to the user's profile
            picture: URL to the user's profile picture
            address: Dictionary containing address information
            urls: Dictionary of various API endpoints for this user
            active: Whether the user is active
            user_type: The type of user (e.g., "STANDARD")
            language: The user's language preference
            locale: The user's locale setting
            utcOffset: The user's UTC offset in milliseconds
            updated_at: When the user information was last updated
            preferred_username: The user's preferred username (typically email)
            **kwargs: Additional attributes from the response
        """
        self.user_id = user_id
        self.name = name
        self.email = email
        self.organization_id = organization_id
        self.sub = sub
        self.email_verified = email_verified
        self.given_name = given_name
        self.family_name = family_name
        self.zoneinfo = zoneinfo
        self.photos = photos or {}
        self.profile = profile
        self.picture = picture
        self.address = address or {}
        self.urls = urls or {}
        self.active = active
        self.user_type = user_type
        self.language = language
        self.locale = locale
        self.utcOffset = utcOffset
        self.updated_at = updated_at
        self.preferred_username = preferred_username
        self.additional_info = kwargs

    def __repr__(self) -> str:
        return f"UserInfo(name='{self.name}', user_id='{self.user_id}', organization_id='{self.organization_id}')"


class Limit:
    """
    Data structure representing a Salesforce Org Limit.
    https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/resources_limits.htm
    """

    def __init__(self, name: str, Max: int, Remaining: int, **sub_limits):
        """
        Initialize an OrgLimit object.

        Args:
            name: The name of the limit
            max_value: The maximum allowed value for this limit
            current_value: The current consumption value for this limit
        """
        self.name = name
        self.Max = Max
        self.Remaining = Remaining

        self._sub_limits = {
            name: Limit(name, **details) for name, details in sub_limits.items()
        }

    def __getattr__(self, name: str) -> "Limit":
        try:
            return self._sub_limits[name]
        except KeyError:
            try:
                return object.__getattribute__(self, name)
            except AttributeError as e:
                raise AttributeError(
                    f"No Sub-Limit '{name}' found for Limit '{self.name}'."
                ) from e

    def __repr__(self) -> str:
        return (
            f"OrgLimit(name='{self.name}', Max={self.Max}, Remaining={self.Remaining})"
        )

    @property
    def usage(self) -> int:
        """
        Calculate the remaining capacity for this limit.

        Returns:
            The difference between max_value and current_value
        """
        return self.Max - self.Remaining

    @property
    def usage_percentage(self) -> float:
        """
        Calculate the percentage of the limit that has been used.

        Returns:
            The percentage of the limit used as a float between 0 and 100
        """
        if self.Max == 0:
            return 0.0
        return (self.usage / self.Max) * 100

    @property
    def remaining_percentage(self) -> float:
        """
        Calculate the percentage of the limit that has been used.

        Returns:
            The percentage of the limit used as a float between 0 and 100
        """
        if self.Max == 0:
            return 0.0
        return (self.Remaining / self.Max) * 100

    def is_critical(self, threshold: float = 90.0) -> bool:
        """
        Determine if the limit usage exceeds a critical threshold.

        Args:
            threshold: The percentage threshold to consider critical (default: 90%)

        Returns:
            True if usage percentage exceeds the threshold, False otherwise
        """
        return self.usage_percentage >= threshold


class OrgLimits:
    _values: dict[str, Limit]

    def __init__(self, **limits):
        self._values = {
            label: Limit(label, **values) for label, values in limits.items()
        }

    def __getattr__(self, name: str) -> Limit:
        try:
            return self._values[name]
        except KeyError:
            try:
                return object.__getattribute__(self, name)
            except AttributeError as e:
                raise AttributeError(f"No Limit '{name}' found.") from e

    def __getitem__(self, name: str) -> Limit:
        return self._values[name]

    def get(self, name: str, default: Limit | None = None) -> Limit | None:
        return self._values.get(name, default)
