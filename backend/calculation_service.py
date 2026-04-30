import requests
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class BCBCalculator:
    """
    Client for Banco Central do Brasil (BCB) SGS API.
    Handles fetching of financial indices like CDI and Poupança.
    """
    
    # Series IDs from SGS
    SERIES_CDI = 12       # Taxa DI (Daily)
    SERIES_SELIC = 11     # Taxa Selic (Daily)
    SERIES_POUPANCA = 115 # Poupança (Monthly interest)
    
    BASE_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{}/dados?formato=json"

    def __init__(self):
        self._cache = {}

    def get_data(self, series_id: int, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """
        Fetches data for a specific series and date range.
        Dates in DD/MM/YYYY format.
        """
        cache_key = f"{series_id}_{start_date}_{end_date}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        url = f"{self.BASE_URL.format(series_id)}&dataInicial={start_date}&dataFinal={end_date}"
        
        try:
            logger.info(f"Fetching BCB data for series {series_id} from {start_date} to {end_date}")
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            self._cache[cache_key] = data
            return data
        except Exception as e:
            logger.error(f"Error fetching BCB data: {str(e)}")
            return []

    def calculate_correction(self, value: float, start_date: str, end_date: str, method: str = 'cdi') -> Dict[str, Any]:
        """
        Calculates the corrected value based on the chosen index accumulated over the period.
        Simplified version: accumulates (1 + rate/100) for each day/month in period.
        """
        series_id = self.SERIES_CDI if method == 'cdi' else self.SERIES_POUPANCA
        data = self.get_data(series_id, start_date, end_date)
        
        if not data:
            # Fallback to a safe factor if API fails (e.g. 1.05 for Poupanca, 1.12 for CDI)
            # This is better than returning 0
            fallback = 1.05 if method == 'poupanca' else 1.12
            return {
                "original_value": value,
                "corrected_value": value * fallback,
                "factor": fallback,
                "method": method,
                "fallback": True,
                "points": 0
            }

        # Accumulate factor
        # BCB returns "valor" as a string formatted like "0.04523"
        total_factor = 1.0
        for entry in data:
            try:
                rate = float(entry['valor']) / 100.0
                total_factor *= (1.0 + rate)
            except:
                continue

        return {
            "original_value": value,
            "corrected_value": value * total_factor,
            "factor": total_factor,
            "method": method,
            "fallback": False,
            "points": len(data)
        }

# Singleton instance
calculator = BCBCalculator()
