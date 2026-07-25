import json
import os
import sys

import httpx
from loguru import logger

# Add src to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def load_env_token() -> str:
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("TRAVELPAYOUTS_API_TOKEN"):
                    parts = line.strip().split("=", 1)
                    if len(parts) == 2:
                        return parts[1].strip().strip('"').strip("'")
    return ""


def main():
    token = load_env_token()
    if not token:
        logger.error("Please add TRAVELPAYOUTS_API_TOKEN to .env first.")
        sys.exit(1)

    url = "https://api.travelpayouts.com/graphql/v1/query"
    
    # GraphQL query requesting both value and currency
    query = """
    query {
      prices_one_way(
        params: {
          origin: "DEL"
        }
        grouping: DIRECTIONS
        paging: {
          limit: 3
          offset: 0
        }
      ) {
        origin_airport_iata
        destination_airport_iata
        value
        currency
      }
    }
    """

    headers = {
        "X-Access-Token": token,
        "Content-Type": "application/json",
    }

    logger.info("Sending Everywhere query with currency field...")
    
    try:
        response = httpx.post(url, json={"query": query}, headers=headers, timeout=15.0)
        logger.info(f"Status: {response.status_code}")
        
        data = response.json()
        if "errors" in data:
            logger.error("Failed with errors:")
            print(json.dumps(data["errors"], indent=2))
            sys.exit(1)

        results = data.get("data", {}).get("prices_one_way", [])
        print("\n=== TravelPayouts Currency Output ===")
        for i, item in enumerate(results):
            origin = item.get("origin_airport_iata")
            dest = item.get("destination_airport_iata")
            val = item.get("value")
            curr = item.get("currency")
            print(f"Result #{i+1}: {origin} -> {dest} | Value: {val} | Currency: {curr}")

    except Exception as e:
        logger.exception(f"Failed: {e}")


if __name__ == "__main__":
    main()
