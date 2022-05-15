from os.path import isfile
from time import time

from Tools.Directories import SCOPE_CONFIG, fileReadLines, fileWriteLine, resolveFilename

MODULE_NAME = __name__.split(".")[-1]

PERCENTAGE_START = 0
PERCENTAGE_END = 100

profileData = {}
profileStart = time()
totalTime = 1
timeStamp = None
profileFile = resolveFilename(SCOPE_CONFIG, "profile")
profileFd = None

profileOld = fileReadLines(profileFile, source=MODULE_NAME)
if profileOld:
	for line in profileOld:
		if "\t" in line:
			(timeStamp, checkPoint) = line.strip().split("\t")
			timeStamp = float(timeStamp)
			totalTime = timeStamp
			profileData[checkPoint] = timeStamp
else:
	print("[Profile] Error: No profile data available!")

try:
	profileFd = open(profileFile, "w")
except (IOError, OSError) as err:
	print("[Profile] Error %d: Couldn't open profile file '%s'!  (%s)" % (err.errno, profileFile, err.strerror))


def profile(checkPoint):
	global profileData, profileStart, totalTime, timeStamp, profileFd
	now = time() - profileStart
	if profileFd:
		profileFd.write("%7.3f\t%s\n" % (now, checkPoint))
		if checkPoint in profileData:
			timeStamp = profileData[checkPoint]
			if totalTime:
				percentage = timeStamp * (PERCENTAGE_END - PERCENTAGE_START) // totalTime + PERCENTAGE_START
			else:
				percentage = PERCENTAGE_START
			if isfile("/proc/progress"):
				fileWriteLine("/proc/progress", "%d \n" % percentage, source=MODULE_NAME)


def profileFinal():
	global profileFd
	if profileFd is not None:
		profileFd.close()
		profileFd = None
