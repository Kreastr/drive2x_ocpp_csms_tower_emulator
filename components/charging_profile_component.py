from ocpp_models.v201.composite_types import ChargingProfileType
from ocpp.v201.enums import ChargingProfileStatusEnumType, GetChargingProfileStatusEnumType

from ocpp_models.v201.get_charging_profiles import GetChargingProfilesRequest


class ChargingProfileComponent:

    def __init__(self):
        self.installed_profiles : list[ChargingProfileType] = list()

    def set_profile_request(self, new_profile : ChargingProfileType) -> ChargingProfileStatusEnumType:
        return ChargingProfileStatusEnumType.rejected

    def get_profile_request(self, request : GetChargingProfilesRequest) -> GetChargingProfileStatusEnumType:
        return GetChargingProfileStatusEnumType.no_profiles