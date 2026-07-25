class DestinationResolver:
    # Country to airport codes mapping
    COUNTRY_MAPPING = {
        "thailand": ["BKK", "DMK", "HKT", "CNX", "KBV"],
        "singapore": ["SIN"],
        "malaysia": ["KUL", "PEN", "LGK", "JHB", "BKI", "KCH"],
        "united arab emirates": ["DXB", "AUH", "SHJ"],
        "hong kong": ["HKG"],
        "japan": ["HND", "NRT", "KIX", "CTS", "FUK", "OKA", "ITM", "TYO", "NGO"],
        "south korea": ["ICN", "GMP", "PUS"],
        "germany": ["FRA", "MUC", "BER", "HAM", "DUS", "TXL"],
        "france": ["CDG", "ORY", "NCE"],
        "netherlands": ["AMS"],
        "united kingdom": ["LHR", "LGW", "MAN", "STN"],
        "oman": ["MCT", "SLL"],
        "vietnam": ["HAN", "SGN", "DAD"],
        "indonesia": ["DPS", "CGK", "SUB"],
        "italy": ["FCO", "MXP", "VCE"],
        "united states": ["JFK", "LAX", "SFO", "ORD", "MIA"],
    }

    # City to airport codes mapping
    CITY_MAPPING = {
        "tokyo": ["HND", "NRT"],
        "osaka": ["KIX"],
        "kuala lumpur": ["KUL"],
        "bangkok": ["BKK", "DMK"],
        "berlin": ["BER", "TXL"],
        "munich": ["MUC"],
        "london": ["LHR", "LGW", "MAN", "STN"],
        "paris": ["CDG", "ORY"],
        "frankfurt": ["FRA"],
        "amsterdam": ["AMS"],
        "seoul": ["ICN", "GMP"],
        "singapore": ["SIN"],
        "dubai": ["DXB"],
        "muscat": ["MCT"],
        "hanoi": ["HAN"],
        "ho chi minh city": ["SGN"],
        "saigon": ["SGN"],
        "bali": ["DPS"],
        "denpasar": ["DPS"],
        "jakarta": ["CGK"],
        "surabaya": ["SUB"],
        "rome": ["FCO"],
        "milan": ["MXP"],
        "venice": ["VCE"],
        "phuket": ["HKT"],
        "chiang mai": ["CNX"],
        "krabi": ["KBV"],
        "penang": ["PEN"],
        "langkawi": ["LGK"],
        "johor bahru": ["JHB"],
        "kota kinabalu": ["BKI"],
        "kuching": ["KCH"],
        "abu dhabi": ["AUH"],
        "sharjah": ["SHJ"],
        "nagoya": ["NGO"],
        "sapporo": ["CTS"],
        "fukuoka": ["FUK"],
        "okinawa": ["OKA"],
        "itami": ["ITM"],
        "busan": ["PUS"],
        "hamburg": ["HAM"],
        "dusseldorf": ["DUS"],
        "nice": ["NCE"],
        "manchester": ["MAN"],
        "salalah": ["SLL"],
        "da nang": ["DAD"],
    }

    # Synonyms mapping
    SYNONYMS = {
        "uk": "united kingdom",
        "united kingdom": "united kingdom",
        "britain": "united kingdom",
        "usa": "united states",
        "united states": "united states",
        "america": "united states",
        "uae": "united arab emirates",
        "emirates": "united arab emirates",
        "south korea": "south korea",
        "korea": "south korea",
    }

    def resolve_destination(self, query: str) -> list[str] | None:
        if not query:
            return None
        
        q = query.strip().lower()
        
        # 1. Check Synonyms
        if q in self.SYNONYMS:
            q = self.SYNONYMS[q]
            
        # 2. Check Country Mapping
        if q in self.COUNTRY_MAPPING:
            return self.COUNTRY_MAPPING[q]
            
        # 3. Check City Mapping
        if q in self.CITY_MAPPING:
            return self.CITY_MAPPING[q]
            
        # 4. If query matches a 3-letter IATA code in our known list, return it
        known_airports = set()
        for codes in self.COUNTRY_MAPPING.values():
            for code in codes:
                known_airports.add(code.upper())
        for codes in self.CITY_MAPPING.values():
            for code in codes:
                known_airports.add(code.upper())

        if len(q) == 3 and q.upper() in known_airports:
            return [q.upper()]
            
        return None
