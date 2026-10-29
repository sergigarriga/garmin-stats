"""Cliente con pausa entre peticiones, reintentos y renovación del token."""

from __future__ import annotations

import logging
import time

import requests
from garmin_personal_api import (
    GarminPersonalApiClient,
    PersonalApiAuthenticator,
    resolve_api_key,
)
from garmin_personal_api.errors import HttpError

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}


class Api:
    """Envuelve el cliente oficial. Cada llamada espera `pause` segundos antes."""

    def __init__(self, pause: float = 0.35, max_retries: int = 6) -> None:
        self._pause = pause
        self._max_retries = max_retries
        self._auth = PersonalApiAuthenticator()
        self._client = GarminPersonalApiClient(self._token())
        self.calls = 0

    def _token(self, force: bool = False) -> str:
        return self._auth.obtain_token(resolve_api_key(), force_refresh=force).access_token

    def call(self, method: str, *args, **kwargs):
        delay = 5.0
        refreshed = False
        for attempt in range(1, self._max_retries + 1):
            time.sleep(self._pause)
            self.calls += 1
            try:
                return getattr(self._client, method)(*args, **kwargs)
            except HttpError as e:
                if e.status_code == 401 and not refreshed:
                    log.info("Token rechazado, pido uno nuevo")
                    self._client.update_bearer_token(self._token(force=True))
                    refreshed = True
                    continue
                if e.status_code in RETRY_STATUS and attempt < self._max_retries:
                    log.warning("HTTP %s en %s, reintento en %.0fs", e.status_code, method, delay)
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
            except (requests.ConnectionError, requests.Timeout):
                if attempt >= self._max_retries:
                    raise
                log.warning("Error de red en %s, reintento en %.0fs", method, delay)
                time.sleep(delay)
                delay *= 2
        raise RuntimeError(f"{method}: sin respuesta tras {self._max_retries} intentos")

    def close(self) -> None:
        self._client.close()
        self._auth.close()
