from datetime import datetime
from decimal import Decimal

from src.adapters.providers.travelpayouts_mapper import TravelPayoutsResponseMapper


def test_mapper_empty_response():
    mapper = TravelPayoutsResponseMapper()
    assert mapper.map({}) == []
    assert mapper.map({"data": {}}) == []
    assert mapper.map({"data": {"prices_one_way": None}}) == []
    assert mapper.map({"data": {"prices_one_way": "not_a_list"}}) == []


def test_mapper_complete_payload():
    raw_payload = {
        "data": {
            "prices_one_way": [
                {
                    "origin_airport_iata": "DEL",
                    "destination_airport_iata": "DXB",
                    "departure_at": "2026-08-15T10:30:00Z",
                    "value": 150.50,
                    "trip_duration": 240,
                    "main_airline": "AI",
                    "number_of_changes": 1,
                    "ticket_link": "/DEL1508DXB1?marker=123"
                }
            ]
        }
    }
    
    mapper = TravelPayoutsResponseMapper()
    flights = mapper.map(raw_payload)
    
    assert len(flights) == 1
    flight = flights[0]
    assert flight.origin == "DEL"
    assert flight.destination == "DXB"
    assert flight.price == Decimal("150.5")
    assert flight.stops == 1
    assert flight.duration_minutes == 240
    assert flight.airline == "AI"
    assert flight.deep_link == "https://www.aviasales.com/search/DEL1508DXB1?marker=123"
    assert isinstance(flight.departure_date, datetime)


def test_mapper_missing_required_fields():
    raw_payload = {
        "data": {
            "prices_one_way": [
                {
                    # Missing origin
                    "destination_airport_iata": "DXB",
                    "departure_at": "2026-08-15T10:30:00Z",
                    "value": 150.50,
                },
                {
                    # Missing destination
                    "origin_airport_iata": "DEL",
                    "departure_at": "2026-08-15T10:30:00Z",
                    "value": 150.50,
                },
                {
                    # Missing departure
                    "origin_airport_iata": "DEL",
                    "destination_airport_iata": "DXB",
                    "value": 150.50,
                },
                {
                    # Missing price (value)
                    "origin_airport_iata": "DEL",
                    "destination_airport_iata": "DXB",
                    "departure_at": "2026-08-15T10:30:00Z",
                },
                {
                    # Complete one to make sure loop continues
                    "origin_airport_iata": "DEL",
                    "destination_airport_iata": "DXB",
                    "departure_at": "2026-08-15T10:30:00Z",
                    "value": 200.00,
                }
            ]
        }
    }
    
    mapper = TravelPayoutsResponseMapper()
    flights = mapper.map(raw_payload)
    assert len(flights) == 1
    assert flights[0].price == Decimal("200.0")


def test_mapper_optional_fallbacks():
    raw_payload = {
        "data": {
            "prices_one_way": [
                {
                    "origin_airport_iata": "DEL",
                    "destination_airport_iata": "DXB",
                    "departure_at": "2026-08-15T10:30:00Z",
                    "value": 150.50,
                    # Optional/nullable fields omitted
                }
            ]
        }
    }
    
    mapper = TravelPayoutsResponseMapper()
    flights = mapper.map(raw_payload)
    
    assert len(flights) == 1
    flight = flights[0]
    assert flight.airline == "Unknown"
    assert flight.stops == 0
    assert flight.duration_minutes == 0
    assert flight.deep_link is None


def test_mapper_malformed_values():
    raw_payload = {
        "data": {
            "prices_one_way": [
                {
                    # Invalid price string
                    "origin_airport_iata": "DEL",
                    "destination_airport_iata": "DXB",
                    "departure_at": "2026-08-15T10:30:00Z",
                    "value": "invalid_price_val",
                },
                {
                    # Invalid date format
                    "origin_airport_iata": "DEL",
                    "destination_airport_iata": "DXB",
                    "departure_at": "invalid_date_format",
                    "value": 150.50,
                },
                {
                    # Valid one
                    "origin_airport_iata": "DEL",
                    "destination_airport_iata": "DXB",
                    "departure_at": "2026-08-15T10:30:00Z",
                    "value": 150.50,
                }
            ]
        }
    }
    
    mapper = TravelPayoutsResponseMapper()
    flights = mapper.map(raw_payload)
    assert len(flights) == 1
    assert flights[0].price == Decimal("150.5")


def test_mapper_duplicate_flights():
    raw_payload = {
        "data": {
            "prices_one_way": [
                {
                    # First duplicate
                    "origin_airport_iata": "DEL",
                    "destination_airport_iata": "DXB",
                    "departure_at": "2026-08-15T10:30:00Z",
                    "value": 150.50,
                    "main_airline": "AI",
                    "number_of_changes": 0
                },
                {
                    # Identical flight duplicate (should be skipped)
                    "origin_airport_iata": "DEL",
                    "destination_airport_iata": "DXB",
                    "departure_at": "2026-08-15T10:30:00Z",
                    "value": 150.50,
                    "main_airline": "AI",
                    "number_of_changes": 0
                },
                {
                    # Different price but same route/date/airline/stops (duplicate key)
                    "origin_airport_iata": "DEL",
                    "destination_airport_iata": "DXB",
                    "departure_at": "2026-08-15T10:30:00Z",
                    "value": 170.00,
                    "main_airline": "AI",
                    "number_of_changes": 0
                },
                {
                    # Different stops (not duplicate)
                    "origin_airport_iata": "DEL",
                    "destination_airport_iata": "DXB",
                    "departure_at": "2026-08-15T10:30:00Z",
                    "value": 140.00,
                    "main_airline": "AI",
                    "number_of_changes": 1
                }
            ]
        }
    }
    
    mapper = TravelPayoutsResponseMapper()
    flights = mapper.map(raw_payload)
    assert len(flights) == 2
    assert flights[0].price == Decimal("150.5")
    assert flights[0].stops == 0
    assert flights[1].price == Decimal("140.0")
    assert flights[1].stops == 1


def test_mapper_ignores_unexpected_fields():
    raw_payload = {
        "data": {
            "prices_one_way": [
                {
                    "origin_airport_iata": "DEL",
                    "destination_airport_iata": "DXB",
                    "departure_at": "2026-08-15T10:30:00Z",
                    "value": 150.50,
                    "unknown_field_1": "some_value",
                    "unknown_field_2": 9999,
                }
            ]
        }
    }
    
    mapper = TravelPayoutsResponseMapper()
    flights = mapper.map(raw_payload)
    assert len(flights) == 1
    assert flights[0].price == Decimal("150.5")
