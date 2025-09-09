from abc import abstractmethod, ABC


class CallableInterface(ABC):
    
    @abstractmethod
    async def call_payload(
        self, payload, suppress=True, unique_id=None, skip_schema_validation=False
    ):
        pass