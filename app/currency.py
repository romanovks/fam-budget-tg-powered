from dataclasses import dataclass

import httpx

from app.models import Currency


@dataclass(frozen=True)
class Rate:
    currency: Currency
    pln: float
    effective_date: str
    table: str


class NbpClient:
    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._http = http_client or httpx.AsyncClient(timeout=10)

    async def get_rate(self, currency: Currency, date: str) -> Rate:
        if currency == Currency.PLN:
            return Rate(currency=currency, pln=1.0, effective_date=date, table="PLN")

        url = f"https://api.nbp.pl/api/exchangerates/rates/a/{currency.value.lower()}/{date}/"
        response = await self._http.get(url, params={"format": "json"})
        if response.status_code == 404:
            response = await self._http.get(
                f"https://api.nbp.pl/api/exchangerates/rates/a/{currency.value.lower()}/last/1/",
                params={"format": "json"},
            )
        response.raise_for_status()
        payload = response.json()
        rate = payload["rates"][0]
        return Rate(
            currency=currency,
            pln=float(rate["mid"]),
            effective_date=rate["effectiveDate"],
            table=rate["no"],
        )
