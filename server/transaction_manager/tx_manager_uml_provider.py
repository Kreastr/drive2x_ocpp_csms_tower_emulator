
transaction_manager_uml = """@startuml
[*] -> Unknown
Unknown --> Occupied : if occupied
Available --> Occupied : if occupied
Unknown --> Available : if available
Occupied --> Available : if available
Available --> Authorized : on authorized
Occupied --> Occupied : on authorized
Occupied --> Ready : on start tx event
Authorized --> Ready : on start tx event
Authorized --> Unknown : on deauthorized
Ready --> Charging : if charge setpoint
Discharging --> Charging : if charge setpoint
Ready --> Discharging : if discharge setpoint
Charging --> Discharging : if discharge setpoint
Charging --> Ready : if idle setpoint
Discharging --> Ready : if idle setpoint
Charging --> Terminating : on terminate
Discharging --> Terminating : on terminate
Ready --> Terminating : on terminate
Terminating --> Unknown : on end tx event
@enduml
"""