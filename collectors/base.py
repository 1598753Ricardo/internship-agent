from abc import ABC, abstractmethod

from models.job import Job


class BaseCollector(ABC):
    @abstractmethod
    def collect(self) -> list[Job]:
        """Return jobs in the shared Job format."""
