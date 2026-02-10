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
from ocpp.v201.call_result import GetChargingProfiles
from ocpp.v201.enums import *
import datetime

from components.charging_profile_component import ChargingProfileComponent, LimitDescriptor
from ocpp_models.v201.clear_charging_profile import ClearChargingProfileRequest
from ocpp_models.v201.composite_types import ChargingProfileType, ChargingScheduleType, ChargingSchedulePeriodType, \
    ChargingProfileCriterionType
from ocpp_models.v201.get_charging_profiles import GetChargingProfilesRequest
from ocpp_models.v201.set_charging_profile import SetChargingProfileRequest

def clear_all_profiles(cpc : ChargingProfileComponent):
    cpc.clear_profiles_request(ClearChargingProfileRequest(chargingProfileCriteria=ChargingProfileCriterionType()))

    reports, status = report_profiles(cpc)
    assert status == status.no_profiles
    assert len(reports) == 0

def add_one_profile(cpc, evseId=1, stackLevel=0, profile_id=1, schedule_id=1, limits=((0,4000.0), ),
                    kind=ChargingProfileKindEnumType.absolute, valid_from=None, valid_to=None, schedule_duration=None,
                    tx_id=None):
    if valid_from is None:
        valid_from = datetime.datetime(
                                      2025, 12, 1, 3,
                                      45, 00,
                                      tzinfo=datetime.UTC)
    if valid_to is None:
        if schedule_duration is not None:
            valid_to = valid_from + datetime.timedelta(seconds=schedule_duration)
    response = cpc.set_profile_request(SetChargingProfileRequest(evseId=evseId,
                                                      chargingProfile=ChargingProfileType(stackLevel=stackLevel,
                                                                                          chargingProfilePurpose=ChargingProfilePurposeEnumType.tx_default_profile if tx_id is None else ChargingProfilePurposeEnumType.tx_profile,
                                                                                          transactionId=tx_id,
                                                                                          chargingProfileKind=ChargingProfileKindEnumType.absolute,
                                                                                          chargingSchedule=[
                                                                                              ChargingScheduleType(
                                                                                                  startSchedule=valid_from,
                                                                                                  chargingRateUnit=ChargingRateUnitEnumType.watts,
                                                                                                  id=schedule_id,
                                                                                                  duration=schedule_duration,
                                                                                                  chargingSchedulePeriod=[
                                                                                                      ChargingSchedulePeriodType(
                                                                                                          startPeriod=p[0],
                                                                                                          limit=p[1]
                                                                                                      ) for p in limits])],
                                                                                          id=profile_id,
                                                                                          validFrom=valid_from,
                                                                                          validTo=valid_to)))
    return response

def report_profiles(cpc):
    result, reports = cpc.get_profile_request(GetChargingProfilesRequest(requestId=1,
                                                                         chargingProfile=ChargingProfileCriterionType(),
                                                                         ))
    assert type(result) is GetChargingProfiles
    return reports, result.status

def test_set_charging():
    cpc = ChargingProfileComponent(evse_ids=[1],
                                   evse_hard_limits=get_limit_descriptor(),
                                   report_profiles_call=lambda x: None)
    add_one_profile(cpc)
    reports, status = report_profiles(cpc)
    assert status == status.accepted, f"{status}"
    assert len(reports) == 1
    assert str(reports[0]) == ("ReportChargingProfiles(request_id=1, charging_limit_source=<ChargingLimitSourceEnumType.cso: 'CSO'>, "
                               "charging_profile=[ChargingProfileType(id=1, stackLevel=0, "
                               "chargingProfilePurpose=<ChargingProfilePurposeEnumType.tx_default_profile: 'TxDefaultProfile'>, "
                               "chargingProfileKind=<ChargingProfileKindEnumType.absolute: 'Absolute'>, recurrencyKind=None, "
                               "validFrom=datetime.datetime(2025, 12, 1, 3, 45, tzinfo=datetime.timezone.utc), "
                               "validTo=None, transactionId=None, "
                               "chargingSchedule=[ChargingScheduleType(id=1, "
                               "startSchedule=datetime.datetime(2025, 12, 1, 3, 45, tzinfo=datetime.timezone.utc), duration=None, "
                               "chargingRateUnit=<ChargingRateUnitEnumType.watts: 'W'>, minChargingRate=None, "
                               "chargingSchedulePeriod=[ChargingSchedulePeriodType(startPeriod=0, limit=4000.0, "
                               "numberPhases=None, phaseToUse=None)], salesTariff=None)])], evse_id=1, tbc=None, custom_data=None)"), \
        f"Got unexpected report {reports[0]}"

    clear_all_profiles(cpc)

def test_duplicate_profiles_not_added():
    cpc = ChargingProfileComponent(evse_ids=[1],
                                   evse_hard_limits=get_limit_descriptor(),
                                   report_profiles_call=lambda x: None)
    result1 = add_one_profile(cpc)
    result2 = add_one_profile(cpc)
    assert result1.status == result1.status.accepted, f"Got wrong status: {result1.status } {result1.status_info=}"
    assert result2.status == result2.status.rejected, f"Got wrong status: {result2.status } {result2.status_info=}"
    reports, status = report_profiles(cpc)
    assert status == status.accepted
    assert len(reports) == 1

def test_nonduplicates_work():
    cpc = ChargingProfileComponent(evse_ids=[1, 2],
                                   evse_hard_limits=get_limit_descriptor(),
                                   report_profiles_call=lambda x: None)
    result1 = add_one_profile(cpc)
    result2 = add_one_profile(cpc, evseId=2)
    result3 = add_one_profile(cpc, stackLevel=1)
    assert result1.status == result1.status.accepted, f"Got wrong status: {result1.status }"
    assert result2.status == result2.status.accepted, f"Got wrong status: {result2.status }"
    assert result3.status == result3.status.accepted, f"Got wrong status: {result3.status }"
    reports, status = report_profiles(cpc)
    assert status == status.accepted
    assert len(reports) == 3

def test_tx_ops():
    cpc = ChargingProfileComponent(evse_ids=[1, 2],
                                   evse_hard_limits=get_limit_descriptor(),
                                   report_profiles_call=lambda x: None)
    assert len(cpc.active_transaction) == 0
    cpc.on_tx_start(1, "aaa")
    assert cpc.active_transaction[1] == "aaa"
    cpc.on_tx_start(1, "bbb")
    assert cpc.active_transaction[1] == "bbb"
    assert not cpc.on_tx_end(1, "aaa")
    assert cpc.active_transaction[1] == "bbb"
    assert cpc.on_tx_end(1, "bbb")
    assert len(cpc.active_transaction) == 0


def get_limit_descriptor():
    result = dict()
    result[1] = LimitDescriptor(minimal=-8000.0,
                                maximal=8000.0,
                                default=1000.0,
                                minimal_absolute=2000.0,
                                maximal_absolute=8000.0)
    return result


def test_limits():
    cpc = ChargingProfileComponent(evse_ids=[1, 2],
                                   evse_hard_limits=get_limit_descriptor(),
                                   report_profiles_call=lambda x: None)
    start = datetime.datetime(2026,3,1,0,0,0, tzinfo=datetime.UTC)
    assert add_one_profile(cpc, limits=((0, 8000.0),), valid_from=start)
    assert cpc.get_power_setpoint(1, moment=start) == 8000.0, f"Expected 8000.0 got {cpc.get_power_setpoint(1, moment=start)}"

def test_pulse_charge():
    cpc = ChargingProfileComponent(evse_ids=[1, 2],
                                   evse_hard_limits=get_limit_descriptor(),
                                   report_profiles_call=lambda x: None)
    start = datetime.datetime(2026,3,1,0,0,0, tzinfo=datetime.UTC)
    response = add_one_profile(cpc, limits=((0, 499.0),), valid_from=start)
    assert response.status == response.status.accepted, f"Got wrong status: {response.status }"
    assert cpc.get_power_setpoint(1, moment=start) == 2000.0, f"Expected 2000.0 got {cpc.get_power_setpoint(1, moment=start)}"
    assert_profile(cpc, ((0, 2000.0), (14, 2000.0), (15, 0.0), (119, 0.0)), start)

    response = add_one_profile(cpc, limits=((0, 2400.0),), valid_from=start, tx_id="bbb")
    assert response.status == response.status.rejected, f"Got wrong status: {response.status }"
    cpc.on_tx_start(1, "aaa")
    response = add_one_profile(cpc, limits=((60, 2499.0),), valid_from=start, tx_id="aaa")
    assert response.status == response.status.accepted, f"Got wrong status: {response.status }"
    assert_profile(cpc, ((0, 2499.0), (14, 2499.0), (15, 2499.0), (30, 2499.0), (119, 2499.0)), start)

def test_pulse_charge():
    cpc = ChargingProfileComponent(evse_ids=[1, 2],
                                   evse_hard_limits=get_limit_descriptor(),
                                   report_profiles_call=lambda x: None)
    start = datetime.datetime(2026,3,1,0,0,0, tzinfo=datetime.UTC)
    response = add_one_profile(cpc, limits=((0, 2000.0),), valid_from=start)
    assert response.status == response.status.accepted, f"Got wrong status: {response.status }"
    assert cpc.get_power_setpoint(1, moment=start) == 2000.0, f"Expected 2000.0 got {cpc.get_power_setpoint(1, moment=start)}"
    assert_profile(cpc, ((0, 2000.0), (14, 2000.0), (15, 2000.0), (119, 2000.0)), start)

    response = add_one_profile(cpc, limits=((0, 3000.0),), valid_from=start, tx_id="bbb")
    assert response.status == response.status.rejected, f"Got wrong status: {response.status }"
    cpc.on_tx_start(1, "aaa")
    response = add_one_profile(cpc, limits=((0, 2000.0), (60, 3000.0),), valid_from=start, tx_id="aaa")
    assert response.status == response.status.accepted, f"Got wrong status: {response.status }"
    assert_profile(cpc, ((0, 2000.0), (14, 2000.0), (15, 2000.0), (30, 2000.0), (60, 3000.0), (119, 3000.0)), start)
    cpc.on_tx_end(1, "aaa")
    assert_profile(cpc, ((0, 2000.0), (14, 2000.0), (15, 2000.0), (30, 2000.0), (60, 2000.0), (119, 2000.0)), start)

def assert_profile(cpc, points, start):
    for i, check_value in points:
        period = start + datetime.timedelta(seconds=i)
        assert cpc.get_power_setpoint(1, moment=period) == check_value, \
            f"At t={i} Expected {check_value=} got {cpc.get_power_setpoint(1, moment=period)}"
