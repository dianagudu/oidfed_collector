from aiohttp import ClientSession, TCPConnector
from datetime import datetime, timedelta

class SessionManager:
    def __init__(self, *, ttl_seconds=600, max_connections=100):
        self.ttl = timedelta(seconds=ttl_seconds)
        self._session = None
        self._created_at = None
        self._connector = TCPConnector(limit=max_connections, ttl_dns_cache=300)

    async def get_session(self) -> ClientSession:
        now = datetime.now()
        # If session is missing, closed, or expired, recreate it
        if (
            self._session is None or
            self._session.closed or
            (self._created_at and now - self._created_at > self.ttl)
        ):
            await self.close()  # Close old session if needed
            self._session = ClientSession(connector=self._connector)
            self._created_at = now
            print("[INFO] Created new session at", self._created_at)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            print("[INFO] Closed session")

    async def __aenter__(self):
        return await self.get_session()

    async def __aexit__(self, *args):
        # await self.close()
        pass
