# -*- coding: utf-8 -*-
""" Pydantic models for the NotifyEVChargingNeeds payload."""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, ValidationError, model_validator, ConfigDict


class ControlMode(str, Enum):
    Scheduled = "Scheduled"
    Dynamic = "Dynamic"

class MobilityNeedsMode(str, Enum):
    EVCC = "EVCC"

class EnergyTransferMode(str, Enum):
    DC = "DC"

class V2XChargingParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    ev_max_energy_request: Optional[float] = Field(None, alias="evMaxEnergyRequest")
    ev_max_v2x_energy_request: Optional[float] = Field(None, alias="evMaxV2XEnergyRequest")
    ev_min_energy_request: Optional[float] = Field(None, alias="evMinEnergyRequest")
    ev_min_v2x_energy_request: Optional[float] = Field(None, alias="evMinV2XEnergyRequest")
    ev_target_energy_request: Optional[float] = Field(None, alias="evTargetEnergyRequest")
    max_charge_power: Optional[float] = Field(None, alias="maxChargePower")
    max_discharge_power: Optional[float] = Field(None, alias="maxDischargePower")
    min_charge_power: Optional[float] = Field(None, alias="minChargePower")
    min_discharge_power: Optional[float] = Field(None, alias="minDischargePower")

class ChargingNeeds(BaseModel):
    control_mode: ControlMode = Field(..., alias="controlMode")
    mobility_needs_mode: MobilityNeedsMode = Field(..., alias="mobilityNeedsMode")
    requested_energy_transfer: EnergyTransferMode = Field(..., alias="requestedEnergyTransfer")
    v2x_charging_parameters: V2XChargingParameters = Field(
        default_factory=V2XChargingParameters,
        alias="v2xChargingParameters",
    )

    model_config = {"extra": "forbid", "populate_by_name": True}

class NotifyEVChargingNeeds(BaseModel):
    evse_id: int = Field(..., alias="evseId")
    timestamp: datetime
    max_schedule_tuples: Optional[int] = Field(None, alias="maxScheduleTuples")
    charging_needs: ChargingNeeds = Field(..., alias="chargingNeeds")

    model_config = {"extra": "forbid", "populate_by_name": True}
