from datetime import datetime
from decimal import Decimal, InvalidOperation

from loguru import logger

from src.domain.entities import Flight


class TravelPayoutsResponseMapper:
    """
    Response mapper responsible for parsing raw TravelPayouts GraphQL JSON response
    and mapping it to normalized internal domain Flight entities.
    """
    def __init__(self, currency_converter=None):
        self.currency_converter = currency_converter

    def map(self, raw_json: dict) -> list[Flight]:
        """
        Parses raw GraphQL JSON from TravelPayouts and returns a list of normalized Flight entities.
        """
        if not raw_json:
            return []

        data = raw_json.get("data")
        if not data:
            logger.warning("GraphQL payload does not contain a 'data' block.")
            return []

        prices_list = data.get("prices_one_way")
        if not isinstance(prices_list, list):
            logger.warning("GraphQL payload 'prices_one_way' is missing or not a list.")
            return []

        flights: list[Flight] = []
        seen_flight_keys: set[tuple[str, str, str, str, int]] = set()

        for idx, item in enumerate(prices_list):
            if not isinstance(item, dict):
                logger.warning(f"Item at index {idx} is not a dictionary. Skipping.")
                continue

            # 1. Validate required fields
            origin = item.get("origin_airport_iata")
            destination = item.get("destination_airport_iata")
            departure_str = item.get("departure_at")
            price_val = item.get("value")

            if not origin:
                logger.warning(f"Item at index {idx} is missing 'origin_airport_iata'. Skipping.")
                continue
            if not destination:
                logger.warning(
                    f"Item at index {idx} is missing 'destination_airport_iata'. Skipping."
                )
                continue
            if not departure_str:
                logger.warning(f"Item at index {idx} is missing 'departure_at'. Skipping.")
                continue
            if price_val is None:
                logger.warning(f"Item at index {idx} is missing 'value' (price). Skipping.")
                continue

            # 2. Parse price to Decimal
            try:
                price = Decimal(str(price_val))
            except (ValueError, InvalidOperation):
                logger.warning(
                    f"Item at index {idx} has invalid price value '{price_val}'. Skipping."
                )
                continue

            # Convert currency to INR if converter is available
            if self.currency_converter:
                currency_code = item.get("currency") or "RUB"
                price = self.currency_converter.convert_to_inr(price, currency_code)

            # 3. Parse date
            try:
                formatted_date = departure_str.replace("Z", "+00:00")
                departure_date = datetime.fromisoformat(formatted_date)
            except ValueError:
                logger.warning(
                    f"Item at index {idx} has invalid departure date format '{departure_str}'."
                    " Skipping."
                )
                continue

            # 4. Handle optional / nullable values
            # Duration: check both 'trip_duration' and 'duration', fallback to 0
            duration_val = item.get("trip_duration")
            if duration_val is None:
                duration_val = item.get("duration")
            
            try:
                duration_minutes = int(duration_val) if duration_val is not None else 0
            except ValueError:
                duration_minutes = 0

            # Stops (number of changes)
            stops_val = item.get("number_of_changes")
            try:
                stops = int(stops_val) if stops_val is not None else 0
            except ValueError:
                stops = 0

            # Airline (main_airline)
            airline = item.get("main_airline") or "Unknown"

            # 5. Build booking link correctly without double slashes
            ticket_suffix = item.get("ticket_link")
            deep_link = None
            if ticket_suffix:
                clean_suffix = ticket_suffix.lstrip("/")
                deep_link = f"https://www.aviasales.com/search/{clean_suffix}"

            # 6. Deduplicate flights
            flight_key = (
                departure_date.isoformat(),
                origin.upper(),
                destination.upper(),
                airline.upper(),
                stops
            )
            if flight_key in seen_flight_keys:
                logger.warning(f"Duplicate flight detected for key {flight_key}. Skipping.")
                continue
            seen_flight_keys.add(flight_key)

            # 7. Generate flight ID
            flight_id = (
                f"tp_{origin.lower()}_{destination.lower()}_"
                f"{departure_date.strftime('%Y%m%d')}_{idx}"
            )

            # Instantiate normalized Flight model
            flight = Flight(
                id=flight_id,
                origin=origin.upper(),
                destination=destination.upper(),
                departure_date=departure_date,
                return_date=None,
                price=price,
                airline=airline,
                stops=stops,
                duration_minutes=duration_minutes,
                cabin_class="economy",
                deep_link=deep_link
            )
            flights.append(flight)

        return flights
