import sys
from uptime_tracker import append_runtime

# First argument is seconds of uptime
append_runtime(int(sys.argv[1]))
