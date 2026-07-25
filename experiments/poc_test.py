import json
import os
import sys

from loguru import logger

# Inject vendor directory into python import path
VENDOR_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "mcp-skyscanner", "vendor", "skyscanner")
)
sys.path.append(VENDOR_PATH)

try:
    from skyscanner import config
    from skyscanner.skyscanner import SkyScanner
    from skyscanner.types import Airport, SpecialTypes
except ImportError as e:
    logger.error(f"Failed to import from skyscanner client library: {e}")
    sys.exit(1)


def main():
    logger.info("Initializing Skyscanner client...")
    try:
        scanner = SkyScanner(locale="en-US", currency="USD", market="US")
        logger.info(f"Session headers: {json.dumps(dict(scanner.session.headers), indent=2)}")
    except Exception as e:
        logger.error(f"Failed to initialize SkyScanner client: {e}")
        sys.exit(1)

    logger.info("Sending direct query to SEARCH_ORIGIN_ENDPOINT...")
    try:
        url = config.SEARCH_ORIGIN_ENDPOINT
        params = {
            "query": "DEL",
            "inboundDate": "",
            "outboundDate": "",
        }
        
        req = scanner.session.get(url, params=params)
        logger.info(f"Response status code: {req.status_code}")
        logger.info(f"Response headers: {json.dumps(dict(req.headers), indent=2)}")
        
        try:
            logger.info(f"Response JSON: {json.dumps(req.json(), indent=2)}")
        except Exception:
            logger.warning("Response is not JSON.")
            logger.info(f"Response Text (first 500 chars): {req.text[:500]}")
            
    except Exception as e:
        logger.exception(f"Direct request failed: {e}")


if __name__ == "__main__":
    main()
