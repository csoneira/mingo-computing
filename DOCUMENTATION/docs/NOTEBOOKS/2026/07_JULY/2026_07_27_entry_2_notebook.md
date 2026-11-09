# Two channels of the mingo01 were counting arbitrary values, some really high, as seen in the TDC DAQ control webpage

## Description
Two channels of the mingo01 were counting arbitrary values, some really high, as seen in the TDC DAQ control webpage. Even desconecting the FEE maintained those high conunts on the TDC.

## Cause
Basically what I did on saturday was putting the FEE so close with the screws to the aluminum profile that the pins of entry of the LV power source touched the ground and shortcircuited, which means that indeed it broke, because it breaks on shortcircuit. This could be seen because there were two green lights on, instead of  three lights, which is what it should be.

## Solution
Alberto replaced the source and everything worked properly again. Conclusion: its not a problem of the TDC/TRB, but a problem of the FEE not being properly fed the voltage. This means that some daughterboards (red ones) were not connected, hence the connection for those chanels was indeed floating, and that's why the TRB saw "floating-like" counts.

Then startDAQ. Also TRB_powercycle can be useful.

## Key identification, for the next time.
FEE requires three lights turned on green in the MB 

---

# One channel of the mingo01 was in red and not counting, as seen in the TDC DAQ control webpage

# Description
Also it is relevant to indicate that after this fix there was one channel in red, giving poblems.

## Cause
Probably the FEE mess previously described, or the trip by car.

## Solution
What we wanted to do was unscrew the red board (the BACD red channel board, the DB), to change it for another identical one. On the process of unscreweing, because there were some pins joining the DB and the MB that moved when unscrewing, it fixed itself, so we screw back and everything worked properly!

## Key identification, for the next time.
One channel of the mingo01 was in red and not counting, as seen in the TDC DAQ control webpage.
