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

	def syncMethodChanged(self, configElement):
		print("[NetworkTime] Time reference changed to '%s'." % configElement.toDisplayString(configElement.value))
		eDVBLocalTimeHandler.getInstance().setUseDVBTime(configElement.value == "dvb")
		eEPGCache.getInstance().timeUpdated()
		self.timer.startLongTimer(0)

	def ntpServerChanged(self, configElement):
		print("[NetworkTime] Time server changed to '%s'." % configElement.value)
		self.timeCheck()

	def syncIntervalChanged(self, configElement):
		print("[NetworkTime] Time sync period changed to '%s'." % configElement.toDisplayString(configElement.value))
		self.timeCheck()

	def startTimer(self):
		if self.timeCheck not in self.timer.callback:
			self.timer.callback.append(self.timeCheck)
			config.time.syncMethod.addNotifier(self.syncMethodChanged, initial_call=False, immediate_feedback=False)
			config.time.ntpServer.addNotifier(self.ntpServerChanged, initial_call=False, immediate_feedback=False)
			config.time.syncInterval.addNotifier(self.syncIntervalChanged, initial_call=False, immediate_feedback=False)
		self.timer.startLongTimer(0)

	def stopTimer(self):
		if self.timeCheck in self.timer.callback:
			self.timer.callback.remove(self.timeCheck)
		self.timer.stop()

	def timeCheck(self):
		if config.time.syncMethod.value == "ntp":
			print("[NetworkTime] Updating time via NTP.")
			self.Console.ePopen(["/usr/sbin/ntpd", "/usr/sbin/ntpd", "-nq", "-p", config.time.ntpServer.value], self.updateSchedule)
		else:
			self.updateSchedule()

	def updateSchedule(self, data=None, retVal=None, extraArgs=None):
		if retVal and data:
			print("[NetworkTime] Error %d: /usr/sbin/ntpd was unable to synchronize the time!\n%s" % (retVal, data.strip()))
		nowTime = time()
		if nowTime > 10000:
			print("[NetworkTime] Setting time to '%s' (%s)." % (ctime(nowTime), str(nowTime)))
			setRTCtime(nowTime)
			eDVBLocalTimeHandler.getInstance().setUseDVBTime(config.time.syncMethod.value == "dvb")
			eEPGCache.getInstance().timeUpdated()
			self.timer.startLongTimer(int(config.time.syncInterval.value) * 60)
		else:
			print("[NetworkTime] System time not yet available.")
			self.timer.startLongTimer(10)


ntpSyncPoller = NTPSyncPoller()
