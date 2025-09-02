
transaction_uml = """@startuml
[*] -> Idle
Idle --> Authorized : on authorized
Idle --> CableConnected : if cable connected
CableConnected --> Idle : if cable disconnected
Authorized --> Transaction : if cable connected
CableConnected --> Transaction : on authorized
Transaction --> Transaction : on report interval
Transaction --> Idle : if cable disconnected
Transaction --> Idle : on deauthorized
Authorized --> Idle : on deauthorized
@enduml
"""