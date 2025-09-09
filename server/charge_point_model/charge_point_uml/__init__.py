
charge_point_uml = """@startuml
[*] --> Created
Created --> Unknown : on start
Unknown --> Identified : on serial number obtained
Unknown --> Rejected : on serial number not obtained
Unknown --> Booted : on boot notification 
Rejected --> [*]
Identified --> Booted : on boot notification
Identified --> Booted : on cached boot notification
Identified --> Failed : on boot timeout
Failed --> [*]
Booted --> RunningTransaction : on transaction_manager request
Booted --> Identified : on boot notification
RunningTransaction --> RunningTransaction
RunningTransaction --> Booted : if no active transactions
Booted --> Closing : on reboot confirmed
Closing --> [*]
@enduml
"""

"""
Booted --> Failed : if heartbeat timeout
Unknown --> Failed : if heartbeat timeout
Identified --> Failed : if heartbeat timeout
RunningTransaction --> Failed : if heartbeat timeout
"""