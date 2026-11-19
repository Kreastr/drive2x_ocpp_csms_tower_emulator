import pytest
from .. import NotifyEVChargingNeeds

def test_ev_charging_needs_model_v2g():
    inner = {
        "evseId": 1,
        "timestamp": "2026-11-19T08:17:55+00:00",
        "maxScheduleTuples": None,
        "chargingNeeds": {
            "controlMode": "Dynamic",
            "mobilityNeedsMode": "EVCC",
            "requestedEnergyTransfer": "DC",
            "v2xChargingParameters": {
                "evMaxEnergyRequest": 6300,
                "evMaxV2XEnergyRequest": 1000,
                "evMinEnergyRequest": -37600,
                "evMinV2XEnergyRequest": -37600,
                "evTargetEnergyRequest": 5300,
                "maxChargePower": 10200,
                "maxDischargePower": -10000,
                "minChargePower": 600,
                "minDischargePower": -700,
            },
        },
    }
    
    validated = NotifyEVChargingNeeds. model_validate(inner)

def test_ev_charging_needs_model_limiting():
    inner = {
        "evseId": 1,
        "timestamp": "2026-11-19T08:17:55+00:00",
        "maxScheduleTuples": None,
        "chargingNeeds": {
            "controlMode": "Scheduled",
            "mobilityNeedsMode": "EVCC",
            "requestedEnergyTransfer": "DC",
            "v2xChargingParameters": {
            },
        },
    }

    validated = NotifyEVChargingNeeds.model_validate(inner)