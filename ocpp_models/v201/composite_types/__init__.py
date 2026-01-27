from _pydatetime import datetime
from typing import Optional

from ocpp.v201.enums import CostKindEnumType, ChargingRateUnitEnumType, ChargingProfilePurposeEnumType, \
    ChargingProfileKindEnumType, RecurrencyKindEnumType
from pydantic import BaseModel, Field

from ocpp_models.v201.base_types import CiString32Type, CiString36Type


class ChargingSchedulePeriodType(BaseModel):
    startPeriod : int
    limit : float
    numberPhases : Optional[int] = None
    phaseToUse : Optional[int] = None


class RelativeTimeIntervalType(BaseModel):
    start : int
    duration : Optional[int] = None


class CostType(BaseModel):
    costKind : CostKindEnumType
    amount : int
    amountMultiplier : int = 0


class ConsumptionCostType(BaseModel):
    startValue : float
    cost : list[CostType]


class SalesTariffEntryType(BaseModel):
    ePriceLevel : Optional[int] = None
    relativeTimeInterval : RelativeTimeIntervalType
    consumptionCost : list[ConsumptionCostType] = Field(default_factory=list)


class SalesTariffType(BaseModel):
    id : int
    salesTariffDescription : Optional[CiString32Type] = None
    numEPriceLevels : Optional[int] = None
    salesTariffEntry : list[SalesTariffEntryType ]


class ChargingScheduleType(BaseModel):
    id : int
    startSchedule : Optional[datetime] = None
    duration : Optional[int] = None
    chargingRateUnit : ChargingRateUnitEnumType
    minChargingRate : Optional[float] = None
    chargingSchedulePeriod : list[ChargingSchedulePeriodType]
    salesTariff : Optional[SalesTariffType ]


class ChargingProfileType(BaseModel):
    id : int
    stackLevel : int
    chargingProfilePurpose : ChargingProfilePurposeEnumType
    chargingProfileKind : ChargingProfileKindEnumType
    recurrencyKind : Optional[RecurrencyKindEnumType] = None
    validFrom : Optional[datetime] = None
    validTo : Optional[datetime] = None
    transactionId : Optional[CiString36Type] = None
    chargingSchedule : list[ChargingScheduleType]
