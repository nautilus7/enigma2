from time import ctime, time

from enigma import eDVBLocalTimeHandler, eEPGCache, eTimer

from Components.config import ConfigSelection, ConfigSubsection, ConfigText, config
from Components.Console import Console
from Tools.StbHardware import setRTCtime

config.time = ConfigSubsection()
config.time.syncMethod = ConfigSelection(default="auto", choices=[
	#("auto", _("Auto")),
	("dvb", _("Transponder time")),
	("ntp", _("Internet time (NTP)"))
])
config.time.syncInterval = ConfigSelection(default="30", choices=[
	("30", "30 " + _("minutes")),
	("60", "1 " + _("Hour")),
	("720", _("Twice per day")),
	("1440", _("Once per day"))
])
config.time.ntpServer = ConfigText("pool.ntp.org", fixed_size=False)


class NTPSyncPoller:
	"""Automatically Poll NTP"""

	def __init__(self):
		self.timer = eTimer()
		self.Console = Console()

	def startTimer(self):
		if self.timeCheck not in self.timer.callback:
			self.timer.callback.append(self.timeCheck)
		self.timer.startLongTimer(0)

	def stopTimer(self):
		if self.timeCheck in self.timer.callback:
			self.timer.callback.remove(self.timeCheck)
		self.timer.stop()

	def timeCheck(self):
		if config.time.syncMethod.value == "ntp":
			self.Console.ePopen(["/usr/sbin/ntpd", "/usr/sbin/ntpd", "-nq", "-p", config.time.ntpServer.value], self.updateSchedule)
		else:
			self.updateSchedule()

	def updateSchedule(self, data=None, retVal=None, extraArgs=None):
		if retVal and data:
			print("[NetworkTime] Error %d: Unable to synchronize the time!\n%s" % (retVal, data.strip()))
		nowTime = time()
		if nowTime > 10000:
			timeSource = config.time.syncMethod.value
			print("[NetworkTime] Setting time to '%s' (%s) from '%s'." % (ctime(nowTime), str(nowTime), config.time.syncMethod.toDisplayString(timeSource)))
			setRTCtime(nowTime)
			eDVBLocalTimeHandler.getInstance().setUseDVBTime(timeSource == "dvb")
			eEPGCache.getInstance().timeUpdated()
			self.timer.startLongTimer(int(config.time.syncInterval.value) * 60)
		else:
			print("[NetworkTime] System time not yet available.")
			self.timer.startLongTimer(10)


ntpSyncPoller = NTPSyncPoller()
