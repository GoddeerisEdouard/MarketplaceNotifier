from abc import ABC, abstractmethod

from marketplace_notifier.notifier.models import IListingInfo


class INotifier(ABC):
    """
    interface of marketplace notifier
    """
    @abstractmethod
    async def get_listing(self) -> IListingInfo:
        pass
