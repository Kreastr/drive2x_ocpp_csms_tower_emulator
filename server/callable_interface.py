from abc import abstractmethod, ABCMeta


class CallableInterface(ABCMeta):
    
    @abstractmethod
    async def call_payload(
        self, payload, suppress=True, unique_id=None, skip_schema_validation=False
    ):
        pass