"""
skills/weather.py — Weather Skill
Uses Open-Meteo API (free, no API key needed) + IP geolocation.
"""

import requests
import logging
from typing import Optional

logger = logging.getLogger(__name__)

WMO_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "icy fog",
    51: "light drizzle", 53: "moderate drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "moderate rain", 65: "heavy rain",
    71: "light snow", 73: "moderate snow", 75: "heavy snow",
    80: "rain showers", 81: "moderate showers", 82: "violent showers",
    95: "thunderstorm", 96: "thunderstorm with hail",
}


class WeatherSkill:
    def __init__(self, config: dict):
        self.cfg = config
        self._cached_location = None

    def _get_location(self) -> Optional[dict]:
        """Get user's location via IP geolocation (no API key needed)."""
        if self._cached_location:
            return self._cached_location
        try:
            resp = requests.get("http://ip-api.com/json/", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    self._cached_location = {
                        "lat": data["lat"],
                        "lon": data["lon"],
                        "city": data["city"],
                        "country": data["country"],
                    }
                    return self._cached_location
        except Exception as e:
            logger.error(f"Location lookup failed: {e}")
        return None

    def get_current_weather(self) -> str:
        """Get current weather conditions."""
        location = self._get_location()
        if not location:
            return "I couldn't determine your location to get weather data."

        try:
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": location["lat"],
                "longitude": location["lon"],
                "current": [
                    "temperature_2m",
                    "apparent_temperature",
                    "weathercode",
                    "windspeed_10m",
                    "relativehumidity_2m",
                ],
                "temperature_unit": "celsius",
                "windspeed_unit": "kmh",
                "timezone": "auto",
            }

            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                return "I couldn't fetch the weather right now."

            data = resp.json()["current"]
            temp = round(data["temperature_2m"])
            feels_like = round(data["apparent_temperature"])
            code = data["weathercode"]
            wind = round(data["windspeed_10m"])
            humidity = data["relativehumidity_2m"]
            condition = WMO_CODES.get(code, "unknown conditions")
            city = location["city"]

            response = (
                f"In {city}, it's currently {temp}°C with {condition}. "
                f"It feels like {feels_like}°C. "
                f"Wind is {wind} kilometers per hour with {humidity}% humidity."
            )
            return response

        except Exception as e:
            logger.error(f"Weather fetch error: {e}")
            return "I had trouble getting the weather. Check your internet connection."

    def get_forecast(self) -> str:
        """Get a 3-day weather forecast."""
        location = self._get_location()
        if not location:
            return "I couldn't determine your location."

        try:
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": location["lat"],
                "longitude": location["lon"],
                "daily": [
                    "weathercode",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_probability_max",
                ],
                "temperature_unit": "celsius",
                "timezone": "auto",
                "forecast_days": 4,
            }

            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()["daily"]

            days = ["Today", "Tomorrow", "Day after tomorrow"]
            parts = []
            for i in range(1, 4):  # Skip today (index 0), show next 3
                if i >= len(data["weathercode"]):
                    break
                code = data["weathercode"][i]
                high = round(data["temperature_2m_max"][i])
                low = round(data["temperature_2m_min"][i])
                rain_chance = data["precipitation_probability_max"][i]
                condition = WMO_CODES.get(code, "mixed")
                parts.append(
                    f"{days[i-1]}: {condition}, {low} to {high}°C"
                    + (f", {rain_chance}% chance of rain" if rain_chance > 20 else "")
                )

            return "Here's the forecast. " + ". ".join(parts) + "."

        except Exception as e:
            logger.error(f"Forecast error: {e}")
            return "I couldn't get the forecast right now."
