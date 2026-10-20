from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.api.schemas import BaseResponseSchema


@dataclass
class ApiDomain(ABC):
    @abstractmethod
    async def execute(self) -> BaseResponseSchema: ...
