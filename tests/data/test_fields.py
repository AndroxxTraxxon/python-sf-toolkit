from datetime import date, datetime, time
from decimal import Decimal

import pytest

from sf_toolkit.data.fields import (
    Address,
    AddressField,
    BlobData,
    BlobField,
    CheckboxField,
    DateField,
    DateTimeField,
    Field,
    FieldConfigurableObject,
    FieldFlag,
    Geolocation,
    GeolocationField,
    IdField,
    IntField,
    ListField,
    MultiPicklistField,
    MultiPicklistValue,
    NumberField,
    PicklistField,
    RawField,
    ReadOnlyAssignmentException,
    ReferenceField,
    TextField,
    TimeField,
    dirty_fields,
    object_fields,
    serialize_object,
)


class TestFieldConfigurableObject:
    """Test the FieldConfigurableObject base class"""

    def test_field_configurable_object_creation(self):
        """Test basic object creation and field assignment"""

        class TestObject(FieldConfigurableObject):
            name = TextField()
            age = IntField()

        obj = TestObject()
        obj.name = "John"
        obj.age = 30

        assert obj.name == "John"
        assert obj.age == 30

    def test_field_configurable_object_getitem_setitem(self):
        """Test dictionary-style access"""

        class TestObject(FieldConfigurableObject):
            name = TextField()
            age = IntField()

        obj = TestObject()
        obj["name"] = "Jane"
        obj["age"] = 25

        assert obj["name"] == "Jane"
        assert obj["age"] == 25


class TestRawField:
    """Test RawField implementation"""

    def test_raw_field_accepts_any_value(self):
        """Test that RawField accepts any type of value"""

        class TestObject(FieldConfigurableObject):
            raw_field = RawField()

        obj = TestObject()

        # Test various types
        obj.raw_field = "string"
        assert obj.raw_field == "string"

        obj.raw_field = 123
        assert obj.raw_field == 123

        obj.raw_field = [1, 2, 3]
        assert obj.raw_field == [1, 2, 3]

        obj.raw_field = {"key": "value"}
        assert obj.raw_field == {"key": "value"}


class TestTextField:
    """Test TextField implementation"""

    def test_text_field_basic(self):
        """Test basic text field functionality"""

        class TestObject(FieldConfigurableObject):
            description = TextField()

        obj = TestObject()
        obj.description = "Hello World"

        assert obj.description == "Hello World"

    def test_text_field_none_value(self):
        """Test text field with None value"""

        class TestObject(FieldConfigurableObject):
            description = TextField()

        obj = TestObject()
        obj.description = None

        assert obj.description is None


class TestIdField:
    """Test IdField implementation"""

    def test_id_field_valid_format(self):
        """Test IdField with valid Salesforce ID formats"""

        class TestObject(FieldConfigurableObject):
            sf_id = IdField()

        obj = TestObject()

        # 15-character ID
        obj.sf_id = "003000000000001"
        assert obj.sf_id == "003000000000001"

        # 18-character ID
        obj.sf_id = "003000000000001AAA"
        assert obj.sf_id == "003000000000001AAA"

    def test_id_field_invalid_format(self):
        """Test IdField with invalid formats"""

        class TestObject(FieldConfigurableObject):
            sf_id = IdField()

        obj = TestObject()

        # Test invalid ID (too short)
        with pytest.raises(ValueError):
            obj.sf_id = "123"


class TestPicklistField:
    """Test PicklistField implementation"""

    def test_picklist_field_valid_values(self):
        """Test picklist with valid values"""

        class TestObject(FieldConfigurableObject):
            status = PicklistField(options=["New", "Open", "Closed"])

        obj = TestObject()
        obj.status = "New"

        assert obj.status == "New"

    def test_picklist_field_invalid_value(self):
        """Test picklist with invalid value"""

        class TestObject(FieldConfigurableObject):
            status = PicklistField(options=["New", "Open", "Closed"])

        obj = TestObject()

        with pytest.raises(ValueError):
            obj.status = "Invalid"


class TestMultiPicklistField:
    """Test MultiPicklistField implementation"""

    def test_multi_picklist_valid_values(self):
        """Test multi-picklist with valid values"""

        class TestObject(FieldConfigurableObject):
            tags = MultiPicklistField(options=["Tag1", "Tag2", "Tag3"])

        obj = TestObject(tags=MultiPicklistValue("Tag1;Tag2"))

        assert "Tag1" in obj.tags.values
        assert "Tag2" in obj.tags.values

    def test_multi_picklist_string_input(self):
        """Test multi-picklist with string input"""

        class TestObject(FieldConfigurableObject):
            tags = MultiPicklistField(options=["Tag1", "Tag2", "Tag3"])

        obj = TestObject()
        obj.tags = "Tag1;Tag2"

        # Should be converted to MultiPicklistValue
        assert isinstance(obj.tags, MultiPicklistValue)

    def test_multi_picklist_invalid_value(self):
        """Test multi-picklist with invalid value"""

        class TestObject(FieldConfigurableObject):
            tags = MultiPicklistField(options=["Tag1", "Tag2", "Tag3"])

        obj = TestObject()

        with pytest.raises(ValueError):
            obj.tags = MultiPicklistValue("InvalidTag")


class TestNumberField:
    """Test NumberField implementation"""

    def test_number_field_valid_values(self):
        """Test NumberField with valid numeric values"""

        class TestObject(FieldConfigurableObject):
            amount = NumberField()

        obj = TestObject()

        obj.amount = 123.45
        assert obj.amount == 123.45

    def test_number_field_none_value(self):
        """Test NumberField with None"""

        class TestObject(FieldConfigurableObject):
            amount = NumberField()

        obj = TestObject()
        obj.amount = None

        assert obj.amount is None


class TestIntField:
    """Test IntField implementation"""

    def test_int_field_valid_values(self):
        """Test IntField with valid integer values"""

        class TestObject(FieldConfigurableObject):
            count = IntField()

        obj = TestObject()

        obj.count = 42
        assert obj.count == 42

        obj.count = "123"
        assert obj.count == 123

    def test_int_field_none_value(self):
        """Test IntField with None"""

        class TestObject(FieldConfigurableObject):
            count = IntField()

        obj = TestObject()
        obj.count = None

        assert obj.count is None


class TestCheckboxField:
    """Test CheckboxField implementation"""

    def test_checkbox_field_boolean_values(self):
        """Test CheckboxField with boolean values"""

        class TestObject(FieldConfigurableObject):
            is_active = CheckboxField()

        obj = TestObject()

        obj.is_active = True
        assert obj.is_active is True

        obj.is_active = False
        assert obj.is_active is False

    def test_checkbox_field_string_values(self):
        """Test CheckboxField with string representations"""

        class TestObject(FieldConfigurableObject):
            is_active = CheckboxField()

        obj = TestObject()

        obj.is_active = "true"
        assert obj.is_active is True

        obj.is_active = "false"
        assert obj.is_active is False


class TestDateField:
    """Test DateField implementation"""

    def test_date_field_date_object(self):
        """Test DateField with date object"""

        class TestObject(FieldConfigurableObject):
            birth_date = DateField()

        obj = TestObject()
        test_date = date(2023, 1, 15)
        obj.birth_date = test_date

        assert obj.birth_date == test_date

    def test_date_field_string_input(self):
        """Test DateField with string input"""

        class TestObject(FieldConfigurableObject):
            birth_date = DateField()

        obj = TestObject()
        obj.birth_date = "2023-01-15"

        assert obj.birth_date == date(2023, 1, 15)


class TestTimeField:
    """Test TimeField implementation"""

    def test_time_field_time_object(self):
        """Test TimeField with time object"""

        class TestObject(FieldConfigurableObject):
            meeting_time = TimeField()

        obj = TestObject()
        test_time = time(14, 30, 0)
        obj.meeting_time = test_time

        assert obj.meeting_time == test_time

    def test_time_field_string_input(self):
        """Test TimeField with string input"""

        class TestObject(FieldConfigurableObject):
            meeting_time = TimeField()

        obj = TestObject()
        obj.meeting_time = "14:30:00.000Z"

        assert isinstance(obj.meeting_time, time)


class TestDateTimeField:
    """Test DateTimeField implementation"""

    def test_datetime_field_datetime_object(self):
        """Test DateTimeField with datetime object"""

        class TestObject(FieldConfigurableObject):
            created_date = DateTimeField()

        obj = TestObject()
        test_datetime = datetime(2023, 1, 15, 14, 30, 0)
        obj.created_date = test_datetime

        assert obj.created_date == test_datetime

    def test_datetime_field_string_input(self):
        """Test DateTimeField with string input"""

        class TestObject(FieldConfigurableObject):
            created_date = DateTimeField()

        obj = TestObject()
        obj.created_date = "2023-01-15T14:30:00.000+0000"

        assert isinstance(obj.created_date, datetime)


class TestReferenceField:
    """Test ReferenceField implementation"""

    def test_reference_field_dict(self):
        """Test basic ReferenceField functionality"""

        class ReferencedObject(FieldConfigurableObject):
            name = TextField()

        class TestObject(FieldConfigurableObject):
            account = ReferenceField(py_type=ReferencedObject)

        test_acct_name = "Test Account"
        obj = TestObject()
        obj.account = {"name": test_acct_name}

        assert obj.account.name == test_acct_name

    def test_reference_field_none(self):
        """Test basic ReferenceField functionality"""

        class ReferencedObject(FieldConfigurableObject):
            name = TextField()

        class TestObject(FieldConfigurableObject):
            account = ReferenceField(py_type=ReferencedObject)

        obj = TestObject()
        obj.account = None

        assert obj.account is None

    def test_reference_field_obj(self):
        """Test basic ReferenceField functionality"""

        class ReferencedObject(FieldConfigurableObject):
            name = TextField()

        class TestObject(FieldConfigurableObject):
            account = ReferenceField(py_type=ReferencedObject)

        test_acct_name = "Test Account"
        obj = TestObject()
        obj.account = ReferencedObject(name=test_acct_name)

        assert obj.account.name == test_acct_name


class TestListField:
    """Test ListField implementation"""

    def test_list_field_basic(self):
        """Test basic ListField functionality"""

        class TestObject(FieldConfigurableObject):
            items = ListField(str)

        obj = TestObject()
        obj.items = ["item1", "item2", "item3"]

        assert obj.items == ["item1", "item2", "item3"]

    def test_list_field_with_field_type(self):
        """Test ListField with specific field type"""

        class TestObject(FieldConfigurableObject):
            numbers = ListField(int)

        obj = TestObject()
        obj.numbers = [1, 2, 3]

        assert obj.numbers == [1, 2, 3]


class TestGeolocationField:
    """Test GeolocationField implementation"""

    def test_geolocation_field_basic(self):
        """Test basic GeolocationField functionality"""

        class TestObject(FieldConfigurableObject):
            location = GeolocationField()

        obj = TestObject()
        obj.location = Geolocation(latitude=37.7749, longitude=-122.4194)

        assert obj.location.latitude == 37.7749
        assert obj.location.longitude == -122.4194


class TestAddressField:
    """Test AddressField implementation"""

    def test_address_field_basic(self):
        """Test basic AddressField functionality"""

        class TestObject(FieldConfigurableObject):
            address = AddressField()

        obj = TestObject()
        obj.address = Address(
            Street="123 Main St", City="San Francisco", State="CA", PostalCode="94105"
        )

        assert obj.address.Street == "123 Main St"
        assert obj.address.City == "San Francisco"
        assert obj.address.State == "CA"
        assert obj.address.PostalCode == "94105"


class TestBlobField:
    """Test BlobField implementation"""

    def test_blob_field_basic(self):
        """Test basic BlobField functionality"""

        class TestObject(FieldConfigurableObject):
            attachment = BlobField()

        obj = TestObject()
        blob_data = BlobData(b"test data", "test.txt")
        obj.attachment = blob_data

        assert obj.attachment.data == b"test data"
        assert obj.attachment.filename == "test.txt"


class TestFieldFlags:
    """Test field flags and readonly functionality"""

    def test_readonly_field(self):
        """Test readonly field flag"""

        class TestObject(FieldConfigurableObject):
            readonly_field = TextField(FieldFlag.readonly)

        obj = TestObject(readonly_field="initial value")

        # Should raise exception when trying to set readonly field
        with pytest.raises(ReadOnlyAssignmentException):
            obj.readonly_field = "test"


class TestFieldValidation:
    """Test field validation functionality"""

    def test_field_validation_called(self):
        """Test that field validation is called during assignment"""

        class TestObject(FieldConfigurableObject):
            validated_field = PicklistField(options=["A", "B", "C"])

        obj = TestObject()

        # Valid value should work
        obj.validated_field = "A"
        assert obj.validated_field == "A"

        # Invalid value should raise exception
        with pytest.raises(ValueError):
            obj.validated_field = "Invalid"


class TestFieldRevive:
    """Test field revive functionality (deserialization)"""

    def test_date_field_revive(self):
        """Test DateField revive from string"""

        class TestObject(FieldConfigurableObject):
            date_field = DateField()

        obj = TestObject()

        # Simulate reviving from serialized data
        field = object_fields(type(obj))["date_field"]
        revived_date = field.revive("2023-01-15")

        assert revived_date == date(2023, 1, 15)

    def test_int_field_revive(self):
        """Test IntField revive from string"""

        class TestObject(FieldConfigurableObject):
            int_field = IntField()

        obj = TestObject()

        field = object_fields(type(obj))["int_field"]
        revived_int = field.revive("42")

        assert revived_int == 42
        assert isinstance(revived_int, int)


class TestFieldFormat:
    """Test field format functionality (serialization)"""

    def test_date_field_format(self):
        """Test DateField format to string"""

        class TestObject(FieldConfigurableObject):
            date_field = DateField()

        obj = TestObject()
        obj.date_field = date(2023, 1, 15)

        field = object_fields(type(obj))["date_field"]
        formatted = field.format(obj.date_field)

        assert formatted == "2023-01-15"

    def test_datetime_field_format(self):
        """Test DateTimeField format to string"""

        class TestObject(FieldConfigurableObject):
            datetime_field = DateTimeField()

        obj = TestObject()
        test_dt = datetime(2023, 1, 15, 14, 30, 0)
        obj.datetime_field = test_dt

        field = object_fields(type(obj))["datetime_field"]
        formatted = field.format(obj.datetime_field)

        # Should be in ISO format with timezone
        assert "2023-01-15T14:30:00" in formatted


class TestFieldDefaults:
    """Test field default values"""

    def test_field_with_default_value(self):
        """Test field with default value"""

        class TestObject(FieldConfigurableObject):
            status = TextField(default="New")

        obj = TestObject()

        # Should have default value
        assert obj.status == "New"

    def test_field_with_callable_default(self):
        """Test field with callable default"""

        def get_default():
            return "Generated"

        class TestObject(FieldConfigurableObject):
            generated_field = TextField(default=get_default)

        obj = TestObject()

        # Should call the default function
        assert obj.generated_field == "Generated"


class TestSerializeObject:
    """Test serialize_object include_fields behavior.

    These tests guard against a regression where only_changes=True would
    strip reference fields (Id, external ID) that are required by Salesforce
    for update and upsert operations.
    """

    def test_only_changes_excludes_non_dirty_fields(self):
        """Baseline: only_changes=True should exclude fields that are not dirty."""

        class TestObject(FieldConfigurableObject):
            Id = IdField()
            Name = TextField()
            Industry = TextField()

        obj = TestObject(Id="001XX000000AAAAAA1", Name="Acme", Industry="Tech")
        dirty_fields(obj).clear()

        obj.Name = "Updated"

        result = serialize_object(obj, only_changes=True)
        assert "Name" in result
        assert "Id" not in result, (
            "Id should be excluded when not dirty and no include_fields"
        )
        assert "Industry" not in result

    def test_only_changes_with_include_fields_preserves_id(self):
        """include_fields should force the Id into the output even when it is
        not dirty, which is the fix for the save_update_list regression."""

        class TestObject(FieldConfigurableObject):
            Id = IdField()
            Name = TextField()
            Industry = TextField()

        obj = TestObject(Id="001XX000000AAAAAA1", Name="Acme", Industry="Tech")
        dirty_fields(obj).clear()

        obj.Name = "Updated"

        result = serialize_object(obj, only_changes=True, include_fields=["Id"])
        assert result["Id"] == "001XX000000AAAAAA1", (
            "Id must be preserved by include_fields"
        )
        assert "Name" in result
        assert "Industry" not in result

    def test_only_changes_with_include_fields_preserves_external_id(self):
        """include_fields should force an external ID field into the output,
        which is the fix for the save_upsert_list regression."""

        class TestObject(FieldConfigurableObject):
            Id = IdField()
            Name = TextField()
            ExternalId__c = TextField()

        obj = TestObject(Id="001XX000000AAAAAA1", Name="Acme", ExternalId__c="EXT-001")
        dirty_fields(obj).clear()

        obj.Name = "Updated"

        result = serialize_object(
            obj, only_changes=True, include_fields=["ExternalId__c"]
        )
        assert result["ExternalId__c"] == "EXT-001", (
            "External ID must be preserved by include_fields"
        )
        assert "Name" in result
        assert "Id" not in result

    def test_only_changes_with_include_fields_preserves_readonly_field(self):
        """include_fields should override the readonly exclusion rule."""

        class TestObject(FieldConfigurableObject):
            Id = IdField(FieldFlag.readonly)
            Name = TextField()

        obj = TestObject(Id="001XX000000AAAAAA1", Name="Acme")
        dirty_fields(obj).clear()

        obj.Name = "Updated"

        # Without include_fields, readonly Id is excluded
        result_without = serialize_object(obj, only_changes=True)
        assert "Id" not in result_without

        # With include_fields, readonly Id is preserved
        result_with = serialize_object(obj, only_changes=True, include_fields=["Id"])
        assert result_with["Id"] == "001XX000000AAAAAA1"

    def test_default_mode_with_include_fields_preserves_readonly_field(self):
        """include_fields should also override readonly exclusion in the
        default serialization mode (only_changes=False)."""

        class TestObject(FieldConfigurableObject):
            Id = IdField(FieldFlag.readonly)
            Name = TextField()

        obj = TestObject(Id="001XX000000AAAAAA1", Name="Acme")

        # Without include_fields, readonly Id is excluded
        result_without = serialize_object(obj)
        assert "Id" not in result_without

        # With include_fields, readonly Id is preserved
        result_with = serialize_object(obj, include_fields=["Id"])
        assert result_with["Id"] == "001XX000000AAAAAA1"
        assert "Name" in result_with

    def test_include_fields_no_effect_on_all_fields_mode(self):
        """When all_fields=True every field is already included, so
        include_fields should not cause any difference."""

        class TestObject(FieldConfigurableObject):
            Id = IdField(FieldFlag.readonly)
            Name = TextField()

        obj = TestObject(Id="001XX000000AAAAAA1", Name="Acme")

        result = serialize_object(obj, all_fields=True, include_fields=["Id"])
        assert result["Id"] == "001XX000000AAAAAA1"
        assert result["Name"] == "Acme"
