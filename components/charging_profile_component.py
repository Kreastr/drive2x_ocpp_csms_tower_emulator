"""Author: Aleksei Romanenko <aleksei.romanenko@lut.fi>


This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

Funded by the European Union and UKRI. Views and opinions expressed are however those of the author(s)
only and do not necessarily reflect those of the European Union, CINEA or UKRI. Neither the European
Union nor the granting authority can be held responsible for them.
"""
import dataclasses
import datetime
from collections import defaultdict
from typing import Callable, Optional, Any

from beartype import beartype
from ocpp.v201.datatypes import StatusInfoType
from snoop import snoop

from ocpp_models.v201.clear_charging_profile import ClearChargingProfileRequest
from ocpp_models.v201.composite_types import ChargingProfileType, ChargingScheduleType, ChargingSchedulePeriodType
from ocpp.v201.enums import ChargingProfileStatusEnumType, GetChargingProfileStatusEnumType, \
    ClearChargingProfileStatusEnumType, ChargingProfileKindEnumType, ChargingLimitSourceEnumType, \
    ChargingProfilePurposeEnumType

from ocpp_models.v201.get_charging_profiles import GetChargingProfilesRequest
from ocpp_models.v201.set_charging_profile import SetChargingProfileRequest

from ocpp.v201.call import ReportChargingProfiles
from ocpp.v201.call_result import GetChargingProfiles, SetChargingProfile, ClearChargingProfile

from util import setup_logging
import logging
import json

logger = setup_logging(__name__)
logger.setLevel(logging.DEBUG)

@dataclasses.dataclass
class LimitDescriptor:
    minimal : float
    default : float
    maximal : float
    minimal_absolute : float
    maximal_absolute : float

def sign(x):
    return x/abs(x)

class ChargingProfileComponent:

    def __init__(self, evse_ids : list[int],
                       evse_hard_limits : dict[int, LimitDescriptor],
                       profile_table : Optional[dict[str, Any]] = None,
                       active_transaction_table : Optional[dict[str, Any]] = None):
        self.evse_ids = evse_ids
        self.evse_hard_limits : dict[int, LimitDescriptor] = evse_hard_limits
        self.installed_profiles : defaultdict[int, list[ChargingProfileType]] = defaultdict(list)
        if profile_table is None:
            self.profile_table = dict()
        else:
            self.profile_table: str = profile_table
        if active_transaction_table is None:
            self.active_transaction_table = dict()
        else:
            self.active_transaction_table = active_transaction_table

    def restore_from_database(self):
        self.installed_profiles = defaultdict(list)
        for key, profile_data in self.profile_table.items():
            try:
                evse_id, profile_str = json.loads(profile_data)
                profile = ChargingProfileType.model_validate(json.loads(profile_str))
                result = self._check_if_profile_can_be_accepted(profile, evse_id)
                if result is not None:
                    logger.warning(f"Failed to accept profile from database: {profile=} {result=}")
                    del self.profile_table[self._make_profile_hash(evse_id, profile)]
                    continue
                self.installed_profiles[evse_id].append(profile)
            except Exception as e:
                logger.warning(f"Failed to load profile from database: {e}")


    @staticmethod
    def _make_profile_hash(evse_id : int, profile : ChargingProfileType):
        return f"{evse_id}:{profile.chargingProfilePurpose}:{profile.stackLevel}"

    @beartype
    def cleanup_tx_profiles(self, evse_id : int):
        if evse_id not in self.evse_ids:
            logger.warning(f"Tried to remove tx profiles on unknown {evse_id=}")
            return
        installed = self.installed_profiles[evse_id]
        new_list = []
        profile : ChargingProfileType
        for profile in installed:
            if profile.chargingProfilePurpose != profile.chargingProfilePurpose.tx_profile:
                new_list.append(profile)
                continue

        self.installed_profiles[evse_id] = new_list


    @beartype
    def on_tx_start(self, evse_id : int, tx_id : str):
        if evse_id not in self.evse_ids:
            logger.warning(f"Tried to start new_tx: {tx_id} on unknown {evse_id=}")
            return
        if evse_id in self.active_transaction_table:
            logger.warning(f"Starting new transaction over an existing one. old_tx: {self.active_transaction_table[evse_id]} new_tx: {tx_id}")
            self.cleanup_tx_profiles(evse_id)

        self.active_transaction_table[evse_id] = tx_id

    @beartype
    def on_tx_end(self, evse_id : int, tx_id: str):
        if evse_id not in self.evse_ids:
            logger.warning(f"Tried to stop tx: {tx_id} on unknown {evse_id=}")
            return False
        if evse_id not in self.active_transaction_table:
            logger.warning(f"Trying to stop transaction we are not tracking stopped_tx: {tx_id} on {evse_id=}")
            return False
        if self.active_transaction_table[evse_id] != tx_id:
            logger.warning(f"Trying to stop transaction we are not tracking current_tx: {self.active_transaction_table[evse_id]} stopped_tx: {tx_id} Do nothing")
            return False
        self.cleanup_tx_profiles(evse_id)
        del self.active_transaction_table[evse_id]
        return True


    @beartype
    def _get_power_profile_value(self, evse_id : int, moment : datetime.datetime):
        if evse_id not in self.evse_ids:
            return None
        default_profiles = self._query_profile(evse_id, chargingProfilePurpose=ChargingProfilePurposeEnumType.tx_default_profile)
        tx_profiles = []
        if evse_id in self.active_transaction_table:
            for _, profile in self._query_profile(evse_id, chargingProfilePurpose=ChargingProfilePurposeEnumType.tx_profile):
                if profile.transactionId == self.active_transaction_table[evse_id]:
                    tx_profiles.append(profile)
        if len(tx_profiles) == 0:
            for _, profile in default_profiles:
                tx_profiles.append(profile)

        stacked_commands = dict()
        for profile in tx_profiles:
            has_schedule, schedule_period = self._profile_has_schedule_for(moment, profile)
            if has_schedule:
                assert profile.stackLevel not in stacked_commands, "Attempted adding duplicated stack level"
                stacked_commands[profile.stackLevel] = schedule_period.limit
        if len(stacked_commands) == 0:
            return None
        return stacked_commands[max(stacked_commands)]

    @beartype
    def get_power_setpoint(self, evse_id : int, moment : datetime.datetime) -> float:
        limit = self._get_power_profile_value(evse_id, moment)

        if limit is None:
            if evse_id in self.evse_hard_limits:
                limit = self.evse_hard_limits[evse_id].default
                if limit is None:
                    limit = self.evse_hard_limits[evse_id].maximal
                if limit is None:
                    limit = self.evse_hard_limits[evse_id].minimal
            if limit is None:
                limit = 0.0

        if limit > self.evse_hard_limits[evse_id].maximal:
            limit = self.evse_hard_limits[evse_id].maximal
        if limit < self.evse_hard_limits[evse_id].minimal:
            limit = self.evse_hard_limits[evse_id].minimal
        if abs(limit) < self.evse_hard_limits[evse_id].minimal_absolute:
            cycle_second = moment.second
            if cycle_second < 15*(int(limit*4/self.evse_hard_limits[evse_id].minimal_absolute) + 1):
                limit = sign(limit) * self.evse_hard_limits[evse_id].minimal_absolute
            else:
                limit = 0.0
        if abs(limit) > self.evse_hard_limits[evse_id].maximal_absolute:
            limit = sign(limit) * self.evse_hard_limits[evse_id].maximal_absolute
        return limit


    @beartype
    def set_profile_request(self, request : SetChargingProfileRequest) -> SetChargingProfile:
        profile = request.chargingProfile
        request_evse_id = request.evseId
        result = self.install_profile_if_possible(profile, request_evse_id)

        if result is not None:
            return result
        else:
            return SetChargingProfile(status=ChargingProfileStatusEnumType.accepted)

    @snoop
    def install_profile_if_possible(self, profile, request_evse_id):
        result = self._check_if_profile_can_be_accepted(profile, request_evse_id)
        if result is None:
            self.installed_profiles[request_evse_id].append(profile)
            self.profile_table[self._make_profile_hash(request_evse_id, profile)] = json.dumps(
                [request_evse_id, profile.model_dump_json()])
        return result

    @beartype
    def _check_if_profile_can_be_accepted(self, profile : ChargingProfileType, request_evse_id : int) -> Optional[SetChargingProfile]:

        if profile.chargingProfilePurpose == profile.chargingProfilePurpose.charging_station_max_profile:
            return SetChargingProfile(status=ChargingProfileStatusEnumType.rejected,
                                        status_info=StatusInfoType(reason_code="UNSUPPORTED_PROFILE_PURPOSE",
                                                                   additional_info="Charging station max profiles are not supported yet."))

        if profile.chargingProfilePurpose == profile.chargingProfilePurpose.charging_station_external_constraints:
            return SetChargingProfile(status=ChargingProfileStatusEnumType.rejected,
                                        status_info=StatusInfoType(reason_code="UNSUPPORTED_PROFILE_PURPOSE",
                                                                   additional_info="Charging station external constraints are not supported yet."))

        if profile.chargingProfileKind == ChargingProfileKindEnumType.recurring:
            return SetChargingProfile(status=ChargingProfileStatusEnumType.rejected,
                                        status_info=StatusInfoType(reason_code="UNSUPPORTED_PROFILE_KIND",
                                                                   additional_info="Recurring profiles are not supported yet."))

        if profile.chargingProfileKind == ChargingProfileKindEnumType.relative:
            return SetChargingProfile(status=ChargingProfileStatusEnumType.rejected,
                                        status_info=StatusInfoType(reason_code="UNSUPPORTED_PROFILE_KIND",
                                                                   additional_info="Relative profiles are not supported yet."))

        if profile.chargingProfileKind == ChargingProfileKindEnumType.absolute:
            schedule: ChargingScheduleType
            for schedule in profile.chargingSchedule:
                if schedule.startSchedule is None:
                    return SetChargingProfile(status=ChargingProfileStatusEnumType.rejected,
                                                status_info=StatusInfoType(reason_code="UNSUPPORTED_PROFILE_KIND",
                                                                           additional_info="Start Schedule is missing from one of the schedules. "
                                                                                           "Profiles with Absolute kind must have startSchedule set for "
                                                                                           "all schedules."))
                if schedule.chargingRateUnit != schedule.chargingRateUnit.watts:
                    return SetChargingProfile(status=ChargingProfileStatusEnumType.rejected,
                                                status_info=StatusInfoType(reason_code="UNSUPPORTED_CHARGING_UNIT",
                                                                           additional_info="Start Schedule uses unit other than Watts. "
                                                                                           "Current CS only support watts."))

        if request_evse_id != 0 and request_evse_id not in self.evse_ids:
            return SetChargingProfile(status=ChargingProfileStatusEnumType.rejected,
                                        status_info=StatusInfoType(reason_code="INVALID_EVSE_ID",
                                                                   additional_info=f"This CS only has EVSE Ids of {self.evse_ids} and 0."))

        if profile.chargingProfilePurpose == ChargingProfilePurposeEnumType.tx_profile:
            if request_evse_id not in self.evse_ids:
                return SetChargingProfile(status=ChargingProfileStatusEnumType.rejected,
                                            status_info=StatusInfoType(reason_code="INVALID_EVSE_ID",
                                                                       additional_info=f"Profile with TxProfile must specify a valid known EVSE Id. "
                                                                                       f"Possible values for this CS: {self.evse_ids}"))

            if request_evse_id not in self.active_transaction_table or profile.transactionId != self.active_transaction_table[
                request_evse_id]:
                return SetChargingProfile(status=ChargingProfileStatusEnumType.rejected,
                                            status_info=StatusInfoType(reason_code="INVALID_TRANSACTION_ID",
                                                                       additional_info=f"Profile with TxProfile must specify an ongoing charging transaction."))

        for evse_id, existing in self._query_profile(request_evse_id, profile.stackLevel,
                                                     profile.chargingProfilePurpose):

            if self._interval_overlaps(existing, profile):
                return SetChargingProfile(status=ChargingProfileStatusEnumType.rejected,
                                            status_info=StatusInfoType(reason_code="DUPLICATE_PROFILE",
                                                                       additional_info=f"The combination of evseID stackLevel "
                                                                                       "and chargingProfilePurpose is not unique "
                                                                                       "and the existing profile validity interval "
                                                                                       "overlaps with the new one. "
                                                                                       f"Existing profile: {existing.validFrom=} {existing.validTo=}"))

        return None

    @beartype
    def get_profile_request(self, request : GetChargingProfilesRequest) -> tuple[GetChargingProfiles, list[ReportChargingProfiles]]:
        profiles = self._query_profile(request.evseId,request.chargingProfile.stackLevel,request.chargingProfile.chargingProfilePurpose)
        reports = []
        for evseId, profile in profiles:
            reports.append(ReportChargingProfiles(request_id=request.requestId,
                                                    charging_limit_source=ChargingLimitSourceEnumType.cso,
                                                    evse_id=evseId,
                                                    charging_profile=[profile]
                                                    ))
        if len(reports) == 0:
            return GetChargingProfiles(status=GetChargingProfileStatusEnumType.no_profiles), reports
        else:
            return GetChargingProfiles(status=GetChargingProfileStatusEnumType.accepted), reports

    @beartype
    def clear_profiles_request(self, request : ClearChargingProfileRequest) -> ClearChargingProfile:
        remaining_profiles = self._query_profile(evseId=0,
                                                 stackLevel=request.chargingProfileCriteria.stackLevel,
                                                 chargingProfilePurpose=request.chargingProfileCriteria.chargingProfilePurpose)
        remaining_profiles_final : defaultdict[int, list[ChargingProfileType]] = defaultdict(list)
        p : ChargingProfileType
        if request.chargingProfileCriteria.chargingProfileId is not None:
            for evseId, p in remaining_profiles:
                if p.id not in request.chargingProfileCriteria.chargingProfileId:
                    remaining_profiles_final[evseId].append(p)
        if len(list(remaining_profiles_final.items())) == len(list(self.installed_profiles.items())):
            return ClearChargingProfile(status=ClearChargingProfileStatusEnumType.unknown)

        self.installed_profiles = remaining_profiles_final
        return ClearChargingProfile(status=ClearChargingProfileStatusEnumType.accepted)

    @beartype
    def _query_profile(self, evseId=None, stackLevel=None, chargingProfilePurpose=None, inverse_selection=False) -> list[tuple[int, ChargingProfileType]]:
        result : list[tuple[int, ChargingProfileType]] = []
        profile : ChargingProfileType
        if evseId is None:
            evseIdList = self.evse_ids
            skippedIds = []
        else:
            evseIdList = [0, evseId]
            skippedIds = [i for i in self.evse_ids if i not in evseIdList]

        for _evseId in evseIdList:
            for profile in self.installed_profiles[_evseId]:
                if stackLevel is not None:
                    if profile.stackLevel != stackLevel:
                        if inverse_selection:
                            result.append((_evseId, profile))
                        continue
                if chargingProfilePurpose is not None:
                    if profile.chargingProfilePurpose != chargingProfilePurpose:
                        if inverse_selection:
                            result.append((_evseId, profile))
                        continue
                if not inverse_selection:
                    result.append((_evseId, profile))

        if inverse_selection:
            for _evseId in skippedIds:
                for profile in self.installed_profiles[_evseId]:
                    result.append((_evseId, profile))

        return result

    @staticmethod
    @beartype
    def _profile_has_schedule_for(moment: datetime.datetime, profile : ChargingProfileType) -> tuple[bool, Optional[ChargingSchedulePeriodType]]:
        """
            Checks if the profile has a valid schedule for a given moment.
            IF yes returns also the related ChargingProfileType copy
        :param moment: for this moment of time we query the provided profile
        :param profile: the provided profile we look into
        :return: bool and IF true returns also the related ChargingProfileType copy
        """
        from_a = profile.validFrom
        to_a = profile.validTo
        
        if from_a is None:
            from_a = datetime.datetime(datetime.MINYEAR,1,1,0,0,0,0, tzinfo=datetime.UTC)
        if to_a is None:
            to_a = datetime.datetime(datetime.MAXYEAR,12,31,23,59,59,999, tzinfo=datetime.UTC)

        if from_a > moment or moment >= to_a:
            return False, None

        schedule_information : ChargingScheduleType
        for schedule_information in profile.chargingSchedule:
            start_schedule = schedule_information.startSchedule

            # We only support absolute profiles now
            if start_schedule is None:
                logger.warning(f"Cannot determine startSchedule for {moment=} in profile {profile=}")
                continue

            end_schedule = datetime.datetime(datetime.MAXYEAR,12,31,23,59,59,999999, tzinfo=datetime.UTC)
            if schedule_information.duration is not None:
                end_schedule = start_schedule + datetime.timedelta(seconds=schedule_information.duration)

            if start_schedule > moment or moment >= end_schedule:
                continue

            interval : ChargingSchedulePeriodType
            previous = None
            previous_start = start_schedule

            for interval in schedule_information.chargingSchedulePeriod:
                interval_start = start_schedule + datetime.timedelta(seconds=interval.startPeriod)
                if previous is not None:
                    if previous_start <= moment < interval_start:
                        return True, previous
                else:
                    if moment < interval_start:
                        return False, None
                previous = interval
                previous_start = interval_start
            return True, previous

        # No valid schedule found
        return False, None

    @staticmethod
    @beartype
    def _interval_overlaps(existing : ChargingProfileType, chargingProfile : ChargingProfileType) -> bool:
        from_a = existing.validFrom
        to_a = existing.validTo
        from_b = chargingProfile.validFrom
        to_b = chargingProfile.validTo
        if from_a is None:
            from_a = datetime.datetime(datetime.MINYEAR,1,1,0,0,0,0, tzinfo=datetime.UTC)
        if from_b is None:
            from_b = datetime.datetime(datetime.MINYEAR,1,1,0,0,0,0, tzinfo=datetime.UTC)
        if to_a is None:
            to_a = datetime.datetime(datetime.MAXYEAR,12,31,23,59,59,999, tzinfo=datetime.UTC)
        if to_b is None:
            to_b = datetime.datetime(datetime.MAXYEAR,12,31,23,59,59,999, tzinfo=datetime.UTC)

        if from_a <= from_b < to_a:
            return True
        if from_a <= to_b < to_a:
            return True
        if from_b <= from_a < to_b:
            return True
        if from_b <= to_a < to_b:
            return True
        return False