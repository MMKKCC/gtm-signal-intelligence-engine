from abc import ABC, abstractmethod


class DataProviderInterface(ABC):
    """
    Adapter contract for all data sources.

    Level 2: implemented by MockCSVProvider (reads from uploaded CSV files).
    Level 3: will be implemented by ApolloAPIProvider, ClearbitProvider, etc.

    Downstream services (account_service, signal_service) only import this ABC,
    which means swapping the underlying data source in Level 3 requires zero changes
    to any service or engine code.
    """

    @abstractmethod
    def fetch_accounts(self) -> list[dict]:
        """Return a list of account dicts matching the AccountInput schema field names."""

    @abstractmethod
    def fetch_contacts(self) -> list[dict]:
        """Return a list of contact dicts matching the ContactInput schema field names."""

    @abstractmethod
    def fetch_signals(self) -> list[dict]:
        """Return a list of signal dicts matching the SignalInput schema field names."""
