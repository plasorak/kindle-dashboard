#!/usr/bin/env python3
"""Fetch electricity and gas consumption from the Octopus Energy API.

Usage:
    OCTOPUS_API_KEY=sk_live_xxx OCTOPUS_DEVICE_ID=yyy python octopus_power.py

To discover your device/meter IDs for the first time, run with only OCTOPUS_API_KEY set.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

TZ = ZoneInfo("Europe/London")

GRAPHQL_URL = "https://api.octopus.energy/v1/graphql/"


def graphql(query: str, token: str | None = None) -> dict:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    resp = requests.post(GRAPHQL_URL, json={"query": query}, headers=headers, timeout=15)
    if not resp.ok:
        print(f"HTTP {resp.status_code}: {resp.text}", file=sys.stderr)
        resp.raise_for_status()
    body = resp.json()
    if "errors" in body:
        raise RuntimeError(f"GraphQL errors: {body['errors']}")
    return body["data"]


def get_token(api_key: str) -> str:
    data = graphql(f"""
        mutation {{
            obtainKrakenToken(input: {{APIKey: "{api_key}"}}) {{
                token
            }}
        }}
    """)
    return data["obtainKrakenToken"]["token"]


def get_account_number(token: str) -> str:
    data = graphql("""
        query {
            viewer {
                accounts {
                    number
                }
            }
        }
    """, token)
    accounts = data["viewer"]["accounts"]
    if not accounts:
        raise RuntimeError("No accounts found")
    return accounts[0]["number"]


def get_device_id(token: str, account_number: str) -> str:
    data = graphql(f"""
        query {{
            account(accountNumber: "{account_number}") {{
                electricityAgreements(active: true) {{
                    meterPoint {{
                        meters(includeInactive: false) {{
                            smartDevices {{ deviceId }}
                        }}
                    }}
                }}
            }}
        }}
    """, token)
    for agreement in data["account"].get("electricityAgreements", []):
        for meter in agreement["meterPoint"].get("meters", []):
            for device in meter.get("smartDevices", []):
                return device["deviceId"]
    raise RuntimeError("No smart device (Home Mini) found on account")


def get_gas_meter(token: str, account_number: str) -> tuple[str, str]:
    """Return (mprn, serial_number) for the first active gas meter."""
    data = graphql(f"""
        query {{
            account(accountNumber: "{account_number}") {{
                gasAgreements(active: true) {{
                    meterPoint {{
                        mprn
                        meters(includeInactive: false) {{
                            serialNumber
                        }}
                    }}
                }}
            }}
        }}
    """, token)
    for agreement in data["account"].get("gasAgreements", []):
        mp = agreement["meterPoint"]
        mprn = mp.get("mprn")
        for meter in mp.get("meters", []):
            serial = meter.get("serialNumber")
            if mprn and serial:
                return mprn, serial
    raise RuntimeError("No gas meter found on account")


def get_electricity_meter(token: str, account_number: str) -> tuple[str, str]:
    """Return (mpan, serial_number) for the first active electricity meter."""
    data = graphql(f"""
        query {{
            account(accountNumber: "{account_number}") {{
                electricityAgreements(active: true) {{
                    meterPoint {{
                        mpan
                        meters(includeInactive: false) {{
                            serialNumber
                        }}
                    }}
                }}
            }}
        }}
    """, token)
    for agreement in data["account"].get("electricityAgreements", []):
        mp = agreement["meterPoint"]
        mpan = mp.get("mpan")
        for meter in mp.get("meters", []):
            serial = meter.get("serialNumber")
            if mpan and serial:
                return mpan, serial
    raise RuntimeError("No electricity meter found on account")


def get_day_electricity_cost_pence(api_key: str, mpan: str, serial: str, product: str, tariff: str, days_ago: int = 1) -> tuple[float, int, float]:
    """Return (total_pence, n_slots, total_kwh) for a given day using the REST consumption API.

    days_ago=1 → the most recent complete day (yesterday).
    days_ago=2 → the day before that.

    Note: smart meter data typically lags by a few hours so the figure reflects
    confirmed consumption up to the latest available slot, not necessarily now.
    """
    now = datetime.now(TZ)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)
    period_from = midnight.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    period_to   = (midnight + timedelta(days=1)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"  Querying {period_from} → {period_to}")
    def parse_slot(ts: str) -> datetime:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc).replace(second=0, microsecond=0)

    # Consumption (kWh per half-hour slot) from smart meter
    cons_url = (
        f"https://api.octopus.energy/v1/electricity-meter-points/{mpan}"
        f"/meters/{serial}/consumption/"
        f"?period_from={period_from}&period_to={period_to}&page_size=100&order_by=period"
    )
    resp = requests.get(cons_url, auth=(api_key, ""), timeout=15)
    if not resp.ok:
        print(f"HTTP {resp.status_code}: {resp.text}", file=sys.stderr)
        resp.raise_for_status()
    raw = resp.json().get("results", [])
    for s in raw:
        local_t = datetime.fromisoformat(s["interval_start"].replace("Z", "+00:00")).astimezone(TZ).strftime("%H:%M")
        print(f"    {local_t}  {float(s['consumption']):.4f} kWh")
    consumption = {parse_slot(s["interval_start"]): float(s["consumption"]) for s in raw}
    if not consumption:
        raise RuntimeError("No electricity consumption data for today yet")

    # Agile prices (p/kWh per half-hour slot)
    price_url = (
        f"https://api.octopus.energy/v1/products/{product}/electricity-tariffs/{tariff}"
        f"/standard-unit-rates/?period_from={period_from}&period_to={period_to}&page_size=100"
    )
    resp = requests.get(price_url, timeout=15)
    resp.raise_for_status()
    prices = {parse_slot(s["valid_from"]): float(s["value_inc_vat"]) for s in resp.json().get("results", [])}
    
    matched = {slot: kwh for slot, kwh in consumption.items() if slot in prices}
    if len(matched) != 48:
        return None, None, None

    total_pence = sum(kwh * prices[slot] for slot, kwh in matched.items())
    return total_pence, len(matched), sum(matched.values())


# m³ → kWh conversion constants (standard UK values)
_GAS_CALORIFIC_VALUE = 40.0   # MJ/m³ (typical; varies slightly by region)
_GAS_CORRECTION_FACTOR = 1.02264
_GAS_KWH_PER_M3 = _GAS_CALORIFIC_VALUE * _GAS_CORRECTION_FACTOR / 3.6


def get_latest_gas_kwh(api_key: str, mprn: str, serial: str) -> tuple[float, str]:
    """Return (kWh, interval_start) for the most recent half-hourly gas reading."""
    now = datetime.now(timezone.utc)
    period_from = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (
        f"https://api.octopus.energy/v1/gas-meter-points/{mprn}"
        f"/meters/{serial}/consumption/"
        f"?period_from={period_from}&page_size=1&order_by=-period"
    )
    resp = requests.get(url, auth=(api_key, ""), timeout=15)
    if not resp.ok:
        print(f"HTTP {resp.status_code}: {resp.text}", file=sys.stderr)
        resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        raise RuntimeError("No gas consumption data returned in the last 24 hours")
    latest = results[0]
    kwh = float(latest["consumption"]) * _GAS_KWH_PER_M3
    return kwh, latest["interval_start"]


def get_average_watts(token: str, device_id: str, minutes: int = 5) -> float:
    now = datetime.now(timezone.utc)
    start = (now - timedelta(minutes=minutes)).isoformat()
    end = now.isoformat()

    data = graphql(f"""
        query {{
            smartMeterTelemetry(
                deviceId: "{device_id}"
                grouping: TEN_SECONDS
                start: "{start}"
                end: "{end}"
            ) {{
                readAt
                demand
            }}
        }}
    """, token)

    readings = data.get("smartMeterTelemetry", [])
    demands = [float(r["demand"]) for r in readings if r.get("demand") is not None]
    if not demands:
        raise RuntimeError("No telemetry readings returned — is the Home Mini online?")

    return sum(demands) / len(demands)


def main():
    api_key = os.environ.get("OCTOPUS_API_KEY")
    if not api_key:
        print("Error: set OCTOPUS_API_KEY environment variable", file=sys.stderr)
        sys.exit(1)

    print("Authenticating...")
    token = get_token(api_key)

    account_number = None

    device_id = os.environ.get("OCTOPUS_DEVICE_ID")
    if not device_id:
        print("OCTOPUS_DEVICE_ID not set — discovering from account...")
        account_number = get_account_number(token)
        device_id = get_device_id(token, account_number)
        print(f"  Found device: {device_id}")
        print(f"  Set OCTOPUS_DEVICE_ID={device_id} to skip this step next time")

    print("Fetching last 3-minute electricity telemetry...")
    avg_w = get_average_watts(token, device_id, minutes=3)
    print(f"\n  Average electricity (last 3 min): {avg_w:.0f} W")

    mprn = os.environ.get("OCTOPUS_GAS_MPRN")
    serial = os.environ.get("OCTOPUS_GAS_SERIAL")
    if not (mprn and serial):
        print("\nOCTOPUS_GAS_MPRN / OCTOPUS_GAS_SERIAL not set — discovering from account...")
        if not account_number:
            account_number = get_account_number(token)
        mprn, serial = get_gas_meter(token, account_number)
        print(f"  Found gas meter: mprn={mprn}  serial={serial}")
        print(f"  Set OCTOPUS_GAS_MPRN={mprn} OCTOPUS_GAS_SERIAL={serial} to skip next time")

    print("Fetching latest gas reading...")
    try:
        kwh, interval_start = get_latest_gas_kwh(api_key, mprn, serial)
        local_time = datetime.fromisoformat(interval_start.replace("Z", "+00:00")).astimezone().strftime("%H:%M")
        print(f"\n  Latest gas reading (slot starting {local_time}): {kwh:.3f} kWh")
    except RuntimeError as e:
        print(f"\n  Warning: {e}")

    elec_mpan = os.environ.get("OCTOPUS_ELEC_MPAN")
    elec_serial = os.environ.get("OCTOPUS_ELEC_SERIAL")
    if not (elec_mpan and elec_serial):
        print("\nOCTOPUS_ELEC_MPAN / OCTOPUS_ELEC_SERIAL not set — discovering from account...")
        if not account_number:
            account_number = get_account_number(token)
        elec_mpan, elec_serial = get_electricity_meter(token, account_number)
        print(f"  Found electricity meter: mpan={elec_mpan}  serial={elec_serial}")
        print(f"  Set OCTOPUS_ELEC_MPAN={elec_mpan} OCTOPUS_ELEC_SERIAL={elec_serial} to skip next time")

    product = os.environ.get("OCTOPUS_PRODUCT", "AGILE-24-10-01")
    region  = os.environ.get("OCTOPUS_REGION", "H")
    tariff  = f"E-1R-{product}-{region}"

    print("\nFetching today's electricity cost...")
    try:
        pence, n_slots, total_kwh = get_day_electricity_cost_pence(api_key, elec_mpan, elec_serial, product, tariff)
        print(f"  Matched slots: {n_slots}  |  Total kWh: {total_kwh:.3f}  |  Cost: {pence:.1f}p  (£{pence/100:.2f})")
    except RuntimeError as e:
        print(f"  Warning: {e}")


if __name__ == "__main__":
    main()
