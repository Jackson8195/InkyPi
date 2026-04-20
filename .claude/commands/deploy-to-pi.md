Deploy the current branch to the Pi by running git restore + git pull, then restarting the inkypi service.

Steps:
1. Run restore and pull: `ssh -o ConnectTimeout=30 pi@inky-pizero2w.local "cd /home/pi/InkyPi && git restore . && git pull 2>&1"`
2. Restart the service: `ssh -o ConnectTimeout=15 pi@inky-pizero2w.local "sudo systemctl restart inkypi.service && echo restarted"`
3. Report what files changed and confirm the service restarted.
